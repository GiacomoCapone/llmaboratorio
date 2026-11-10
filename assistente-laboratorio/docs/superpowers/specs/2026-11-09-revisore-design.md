# Revisore delle risposte: specifica

Data: 2026-11-09. Stato: approvata; rivista durante l'implementazione (forma dei messaggi del revisore) e il
2026-11-10 dopo le prove reali (schema del giudizio, tetto di token, indicazione: vedi «Revisione del
2026-11-10»).

## Contesto
Step 2 del percorso «grafo con due nodi LLM», dopo il router (`2026-11-09-router-design.md`). Oggi una
risposta finale dell'agente (nodo `modello`, senza tool call) chiude il turno. Questo step aggiunge un nodo
revisore che giudica la risposta proposta: se è incompleta o fuori tema torna all'agente con il motivo,
finché non è coerente o si raggiunge un limite di revisioni. Nessuna dipendenza nuova.

## Obiettivo
Una risposta incompleta o fuori tema torna all'agente con il motivo come indicazione; l'agente risponde di
nuovo. Al limite di revisioni si restituisce l'ultima risposta e lo si segnala nei log.

## Fuori ambito
- Verifica dell'esattezza dei dati: il revisore non vede i risultati degli strumenti.
- Revisione del rifiuto del router e del messaggio di limite dei passaggi con gli strumenti.
- Messaggio all'utente quando la risposta non è approvata (solo log).
- Riassunto della cronologia, resource e prompt MCP (step successivi).

## Decisioni concordate
- A fine turno la cronologia della sessione conserva domanda, eventuali passaggi con gli strumenti e risposta
  finale: bozze scartate e indicazioni del revisore sono rimosse (restano nei log).
- Il revisore vede la domanda corrente, la risposta proposta e i messaggi precedenti fra utente e assistente
  fino a 4 in tutto (`ultimi_messaggi` del router), esclusi bozze scartate e indicazioni; non vede i
  `ToolMessage`. *Rivista durante l'implementazione:* i messaggi arrivano al modello come testo in un solo
  messaggio utente (`trascrivi`), perché con l'ultimo messaggio dell'assistente e la tool call obbligatoria
  LM Studio risponde HTTP 400 («Failed to initialize samplers: Unexpected empty grammar stack»).
- Output strutturato con la stessa tecnica del router: strumento obbligatorio
  (`bind_tools([Giudizio], tool_choice="required", max_tokens=1024)`), argomenti validati con Pydantic.
  *Rivista il 2026-11-10:* il modello elenca le richieste della domanda e quelle senza risposta; la
  coerenza la decide il codice (nessuna richiesta mancante).
- Guasto del revisore (eccezione, risposta senza tool call, argomenti non validi) → risposta approvata,
  avviso nei log.
- Limite `MAX_REVISIONI` (intero ≥ 1, predefinito 2) dal `.env` o dall'ambiente: è il numero massimo di
  volte in cui la risposta torna all'agente (con 2 l'agente risponde al massimo 3 volte).
- Il conteggio dei passaggi con gli strumenti (`MAX_PASSAGGI`) vale per l'intero turno e non si azzera fra
  le revisioni; se si esaurisce durante una revisione il turno è interrotto come oggi.

## Architettura

### Grafo (`src/assistente/grafo.py`)
```
START → router ─┬─ conversazione → modello ⇄ strumenti / limite → END
                │                     ↓ risposta finale (nessuna tool call)
                │                  revisore ─┬─ coerente → END
                │                            ├─ non coerente, revisioni < MAX_REVISIONI → modello
                │                            └─ non coerente, limite raggiunto → END
                └─ fuori_ambito → rifiuto → END
```
- `Stato` acquista `revisioni: int` (volte in cui la risposta è tornata all'agente nel turno) e
  `scartati: list[str]` (id di bozze rifiutate e indicazioni), sovrascritti dai nodi (nessun riduttore).
- `instrada_dopo_modello`: la destinazione `"fine"` diventa il nodo `revisore` (mappa
  `{"strumenti": "strumenti", "limite": "limite", "fine": "revisore"}`); la funzione resta invariata.
- `build_graph(llm, strumenti, max_passaggi, router, revisore, max_revisioni)`: `revisore` è un callable
  `list[AnyMessage] -> Valutazione`.
- Nodo `revisore`:
  1. chiama `revisore(messaggi senza gli id in scartati)`;
  2. coerente → log `revisore coerente=sì motivo=<...> → fine`; restituisce
     `RemoveMessage(id)` per ogni id in `scartati`, `scartati=[]` ed `esito="fine"`;
  3. non coerente e `revisioni < max_revisioni` → log
     `revisore coerente=no motivo=<...> → agente (revisione <n>/<max>)`; aggiunge
     `HumanMessage(INDICAZIONE_REVISORE.format(motivo=...))` con un id generato (`uuid4`), aggiunge a
     `scartati` l'id della bozza (ultimo messaggio) e quello dell'indicazione, `revisioni + 1`,
     `esito="agente"`;
  4. non coerente e `revisioni == max_revisioni` → log come al punto 3 con `→ fine`, poi WARNING
     `limite di revisioni raggiunto (<max>): restituita l'ultima risposta`; rimozione come al punto 2.
- `Stato` acquista anche `esito_revisione: str` (`"agente"` | `"fine"`), scritto dal nodo revisore.
- `instrada_dopo_revisore(stato) -> Literal["agente", "fine"]`: restituisce `stato["esito_revisione"]`
  (la decisione col limite è presa nel nodo, che la registra nei log).
- `INDICAZIONE_REVISORE` = «Indicazione del revisore (l'utente non la vede): la risposta precedente non è
  adeguata. Motivo: {motivo}. Scrivi una nuova risposta completa alla domanda dell'utente, senza citare la
  risposta precedente né questa indicazione.» (*rivista il 2026-11-10*: prima l'agente apriva con «Mi scuso
  per la risposta precedente», riferito a una bozza che l'utente non vede).
- Limite di ricorsione: `max_passaggi * 2 + 12 + 2 * (max_revisioni + 1)`.

### Revisore (`src/assistente/revisore.py`, nuovo)
- `Valutazione` (Pydantic): `coerente: bool`, `motivo: str`: è ciò che il revisore restituisce al grafo.
- `Giudizio` (Pydantic, *2026-11-10*): lo strumento chiesto al modello, con `richieste: list[str]` (le cose
  chieste nell'ultima domanda, una per elemento) e `mancanti: list[str]` (le richieste senza risposta;
  vuota se le tratta tutte).
- `PROMPT_REVISORE` (*2026-11-10*): il revisore non risponde all'utente e chiama lo strumento Giudizio;
  elenca in `richieste` le cose chieste nell'ULTIMA domanda (di solito una sola) e in `mancanti` quelle a
  cui l'ULTIMA risposta non risponde affatto o risponde parlando d'altro; una richiesta ha risposta anche se
  la risposta è breve, contiene un dato grezzo, dice che non ci sono risultati o riferisce un errore; non
  verifica l'esattezza dei dati e non chiede spiegazioni, fonti o dettagli in più. Nessuna regola sulle
  domande di seguito: fa approvare le risposte parziali (vedi «Revisione del 2026-11-10»).
- Conversione in `Valutazione`: le voci di `mancanti` vuote o di soli spazi sono ignorate; nessuna mancante
  → `coerente=True`, `motivo="richieste trattate: <richieste separate da «; »>"`; altrimenti
  `coerente=False`, `motivo="manca la risposta a: <mancanti separate da «; »>"`.
- `crea_revisore(llm) -> Callable`: `llm.bind_tools([Giudizio], tool_choice="required",
  max_tokens=MAX_TOKEN_REVISORE)` (1024) costruito una volta; la funzione restituita invoca
  `[SystemMessage(PROMPT_REVISORE), HumanMessage(trascrivi(ultimi_messaggi(messaggi)))]` e valida gli
  argomenti della prima tool call. Eccezione, nessuna tool call o argomenti non validi →
  `Valutazione(coerente=True, motivo="revisore non disponibile")` e WARNING `revisore non disponibile:
  <causa>` nel logger `assistente.revisore`.
- *Revisione finale (2026-11-10):* se l'ultimo messaggio ricevuto non è una risposta dell'assistente con
  testo (risposta vuota o di soli spazi, lista vuota), il revisore restituisce subito
  `Valutazione(coerente=False, motivo="risposta vuota")` senza chiamare il modello: `ultimi_messaggi` scarta
  le risposte vuote e la domanda sarebbe trascritta come risposta proposta. Test: `test_revisore.py`
  `test_risposta_vuota_rimandata_senza_modello`, `test_grafo.py` `test_risposta_vuota_rimandata_dal_revisore_vero`.
- `trascrivi(messaggi) -> str`: «Conversazione precedente:» con righe `Utente: ...` / `Assistente: ...` (solo
  se ci sono messaggi precedenti), poi `Domanda dell'utente: ...` e `Risposta proposta dall'assistente: ...`.
- `ultimi_messaggi` è importato da `assistente.router`.

### Configurazione (`src/assistente/config.py`)
- `Config` acquista `max_revisioni: int` (predefinito 2); valore non intero o < 1 →
  `ErroreConfigurazione` («MAX_REVISIONI deve essere un intero positivo, trovato ...»).
- `.env.example`: `MAX_REVISIONI=2` con una riga di commento.

### CLI (`src/assistente/cli.py`)
- `main` passa `crea_revisore(llm)` e `config.max_revisioni` a `build_graph`.
- `esegui_turno` aggiunge allo stato iniziale `revisioni: 0`, `scartati: []`, `esito_revisione: ""`.
  Una risposta restituita al limite di revisioni non è un turno interrotto ed entra nella cronologia.

## Log (evidenze)
Logger `assistente.grafo`, livello INFO salvo dove indicato:
- risposta approvata: `revisore coerente=sì motivo=<...> → fine`;
- risposta rifiutata: `revisore coerente=no motivo=<...> → agente (revisione 1/2)`, poi di nuovo
  `agente: chiamata al modello`;
- limite: `revisore coerente=no motivo=<...> → fine` e WARNING
  `limite di revisioni raggiunto (2): restituita l'ultima risposta`.
Logger `assistente.revisore`, WARNING: `revisore non disponibile: <causa>`.

## Test
(a) Automatici, senza LM Studio (`python -m pytest`):
- `tests/finti.py`: `RevisoreFinto(esiti: list[bool], motivo="...")` (l'ultimo esito si ripete) che registra
  i messaggi ricevuti.
- `tests/test_grafo.py`:
  - `test_revisore_rimanda_risposta_parziale`: domanda in due parti, agente simulato che risponde prima a
    una parte e poi a entrambe, `RevisoreFinto([False, True])` → due chiamate all'agente, la seconda
    contiene l'indicazione con il motivo; risposta finale completa; log di rifiuto e approvazione; la
    cronologia finale non contiene né la bozza né l'indicazione;
  - `test_revisore_approva_al_primo_passaggio`: una sola chiamata all'agente, log `coerente=sì`;
  - `test_limite_di_revisioni`: `RevisoreFinto([False])`, `max_revisioni=2` → tre chiamate all'agente,
    ultima risposta restituita, WARNING di limite, `interrotto` falso;
  - `test_revisore_non_vede_bozze_scartate`: alla seconda valutazione il revisore non riceve la prima bozza
    né l'indicazione;
  - `test_revisore_non_esegue_dopo_rifiuto_del_router` e dopo il limite dei passaggi;
  - `test_instradamento_dopo_revisore` (parametrizzato).
  - Le chiamate esistenti a `build_graph` passano `RevisoreFinto([True])` e `max_revisioni=2`.
- `tests/test_revisore.py`: strumento obbligatorio `Giudizio` con `max_tokens`; prompt di sistema;
  messaggi senza `ToolMessage`; conversione del giudizio (nessuna mancante, mancanti, mancanti vuote);
  eccezione / testo senza tool call / argomenti non validi → coerente con avviso nei log.
- `tests/test_config.py`: `MAX_REVISIONI` predefinito, esplicito, non valido (`0`, `-1`, `abc`).
- `tests/test_cli.py`: `main` passa revisore e limite; un turno con revisione lascia nella cronologia solo
  domanda e risposta finale.

(b) Prove reali con LM Studio (`python -m pytest -m reale -v`), in `tests/reale/test_lmstudio.py`:
- revisore vero con domanda «Che ore sono a Tokyo e quanto fa 12 * 4?» e risposta costruita a mano che tratta
  solo l'ora → `coerente` falso con un motivo; con la risposta completa → `coerente` vero (la risposta
  parziale è costruita a mano perché non si può costringere il modello a rispondere a metà);
- *2026-11-10:* revisore vero su risposte corrette a una sola richiesta, che il primo prompt rifiutava
  (ora come timestamp grezzo, «20» giorni lavorativi, elenco degli strumenti di misura, «non ci sono note»)
  → `coerente` vero, più una risposta che dice di non poterlo fare (previsione di domani) e una che chiede
  un dato mancante: **osservazioni** segnate `xfail` non stretto (verdetto instabile fra sessioni);
  risposta fuori tema → `coerente` falso (vincolante, come risposta parziale e completa);
  nessun «revisore non disponibile»;
- *2026-11-10:* domanda di seguito («Che ore sono a Roma?» / «e a Londra?» → «A Londra sono le 12:00.»)
  → `coerente` vero, segnata `xfail` (limite noto);
- le prove reali esistenti costruiscono il grafo con il revisore vero e restano valide.

## Revisione del 2026-11-10 (dopo le prove reali)
La suite reale passava, ma 4 turni su 22 arrivavano al limite di revisioni. Sonde sul solo revisore
(8 coppie domanda/risposta fisse, 5 risultati giusti e 3 sbagliati, 5 ripetizioni; verdetti deterministici):
- primo prompt (`coerente`/`motivo`, tetto 256): 15/40 verdetti errati, tutti rifiuti di risposte corrette a
  una sola richiesta («solo un timestamp», «non specifica quali festività», «fra» preso alla lettera), più 5
  valutazioni saltate: `gemma-4-e2b` ragiona (190–300 token) nonostante `reasoning_effort=none` e il tetto
  interrompe il modello prima della tool call (`finish_reason: length`);
- prompt riscritto con lo stesso schema: 10/40 errati; con «in caso di dubbio coerente»: 5/40 errati ma 10
  saltate;
- schema `richieste`/`mancanti` con tetto 1024: 8/8 corretti, nessuna saltata, circa 13 s per valutazione.
Decisione dell'utente: schema `Giudizio`, tetto 1024, indicazione che vieta di citare la risposta precedente.

Durante l'implementazione la regola «i messaggi precedenti servono solo a capire le domande di seguito»,
aggiunta al prompt della sonda, faceva approvare la risposta parziale e rifiutare quella completa
(isolata con una sonda: senza la frase entrambe corrette; la docstring di `Giudizio` è ininfluente).
Le domande di seguito («e a Londra?», «e moltiplicato per 2?») sono rifiutate a torto con e senza la frase;
chiedere al modello di completare la richiesta coi messaggi precedenti le sistema in parte ma fa approvare le
risposte parziali (3/12 errati). Decisione dell'utente: prompt senza la frase e **limite noto** — una risposta
corretta a una domanda di seguito può tornare all'agente fino a `MAX_REVISIONI` volte (prova reale `xfail`).

Suite reale completa con questo prompt: dei 22 turni col grafo vero 21 senza revisioni e 1 al limite (prima 4),
nessun «Mi scuso» nelle risposte finali. Ma due prove del solo revisore passate un'ora prima («strumenti di
misura», «non ci sono note») fallivano, poi 5/5 in un processo nuovo: il verdetto sulle risposte corrette a
una richiesta cambia **fra sessioni** di LM Studio (`gemma-4-e2b` ragiona 200–300 token in modo nascosto
nonostante `reasoning_effort=none`); stabili in tutte le esecuzioni solo i rifiuti di risposte parziali e
fuori tema e l'approvazione della risposta completa. Il turno al limite («Che tempo farà domani a Trieste?»)
aveva una risposta corretta («non ho accesso alle previsioni»). Rimessa la regola della prima versione («dice
di non poterlo fare o chiede un dato mancante» → coerente) e misurata in due processi: 4/11 errati in
entrambi (previsione e «mi serve la data» sempre rifiutate; la risposta completa rifiutata con prosa in
`mancanti`), quindi **tolta**. Decisione dell'utente: prove di approvazione come osservazioni (`xfail` non
stretto), prove di rifiuto vincolanti; limite documentato nel README.
Il router ha lo stesso tetto di 256 token: fuori da questo step.

## Documentazione
README: sezione sul revisore (grafo, `MAX_REVISIONI`, righe di log, pulizia della cronologia), variabile
nell'elenco, diagnosi (`revisore non disponibile`, limite di revisioni raggiunto spesso). `CLAUDE.md`:
modulo `revisore` nella struttura e revisore nell'obiettivo. Un solo commit a fine step con specifica,
piano, codice, test e documenti.
