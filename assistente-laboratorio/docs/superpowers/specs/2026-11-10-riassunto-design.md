# Riassunto della cronologia: specifica

Data: 2026-11-10. Stato: approvata; rivista durante l'implementazione (riassunto per concatenazione, vedi «Revisione
del 2026-11-10»).

## Contesto
Step 3 del percorso «grafo con due nodi LLM», dopo il router (`2026-11-09-router-design.md`) e il revisore
(`2026-11-09-revisore-design.md`). Oggi la cronologia della sessione cresce senza limiti (domande, passaggi con
gli strumenti, risposte) e a ogni turno è inviata intera al modello; `google/gemma-4-e2b` in LM Studio è
caricato con un contesto di 8192 token, che una sessione lunga supera. Nessuna dipendenza nuova.

## Obiettivo
Restare nel contesto del modello: quando la cronologia stimata supera una soglia, i messaggi più vecchi sono
sostituiti da un riassunto prodotto dal modello; restano integri gli ultimi turni.

## Fuori ambito
- Mostrare il riassunto all'utente o un comando per chiederlo.
- Persistenza della cronologia o del riassunto fra sessioni.
- Conteggio esatto dei token (tokenizzatore o `prompt_tokens` del server).
- Resource e prompt MCP, servizio HTTP (step successivi).

## Decisioni concordate
- Scopo: tenuta tecnica (sessioni lunghe nel contesto, turni più leggeri), non memoria consultabile.
- Soglia sui **token stimati** (caratteri / 4) dell'intera cronologia del turno, configurabile.
- Restano intatti gli **ultimi 2 turni completi** (domanda, passaggi con gli strumenti, risposta) più la
  domanda corrente; il numero 2 è una costante del codice (`TURNI_RECENTI`).
- Nodo `riassunto` **all'inizio del turno**, prima del router.
- Riassunto **cumulativo per concatenazione** (*rivisto in esecuzione*): il modello riassume solo i turni
  nuovi; il codice accoda il loro riassunto a quello precedente, conservato alla lettera; oltre metà della
  soglia il codice toglie le righe più vecchie. In cronologia c'è al massimo un riassunto, sempre in testa.
- Guasto → cronologia invariata, avviso nei log; il turno prosegue.

## Architettura

### Grafo (`src/assistente/grafo.py`)
```
START → riassunto → router ─┬─ conversazione → modello ⇄ strumenti / limite → … → revisore → END
                             └─ fuori_ambito → rifiuto → END
```
- `build_graph(llm, strumenti, max_passaggi, router, revisore, max_revisioni, riassuntore, soglia_riassunto)`:
  `riassuntore` è un callable `list[AnyMessage] -> str` (testo del riassunto; solleva in caso di guasto).
- Arco `START → riassunto` e `riassunto → router` (al posto di `START → router`).
- Nodo `riassunto`:
  1. `stima = stima_token(messaggi)`; se `stima <= soglia_riassunto` → log DEBUG
     `riassunto: stima <stima> token, sotto la soglia <soglia>`, nessuna modifica (`{}`), nessuna chiamata;
  2. `vecchi, recenti = dividi(messaggi)`; se `vecchi` è vuoto → log INFO
     `riassunto: stima <stima> token sopra la soglia <soglia>, niente da riassumere`, nessuna modifica;
  3. se `vecchi` comincia con il riassunto precedente, `precedente` è il suo testo senza prefisso e `nuovi`
     il resto; altrimenti `precedente = ""` e `nuovi = vecchi`; se `nuovi` è vuoto → log INFO
     `niente da riassumere` come al punto 2, nessuna modifica;
  4. `testo = riassuntore(nuovi)`; eccezione o testo vuoto / di soli spazi → WARNING
     `riassunto non disponibile: <causa>`, nessuna modifica;
  5. `unito, tolte = unisci(precedente, testo.strip(), soglia_riassunto // 2)`; se `tolte > 0` → WARNING
     `riassunto oltre <soglia // 2> token: tolte <tolte> righe più vecchie`;
  6. restituisce `[RemoveMessage(id=REMOVE_ALL_MESSAGES), SystemMessage(PREFISSO_RIASSUNTO + unito,
     id=<uuid4>), *recenti]` e log INFO
     `riassunto: <len(nuovi)> messaggi riassunti, stima <stima> → <stima nuova> token`.
- Limite di ricorsione: `+ 1` per il nodo nuovo.

### Riassunto (`src/assistente/riassunto.py`, nuovo)
- `CARATTERI_PER_TOKEN = 4`, `TURNI_RECENTI = 2`, `MAX_TOKEN_RIASSUNTO = 1024` (margine per il ragionamento
  nascosto di `gemma-4-e2b` osservato nel revisore).
- `PREFISSO_RIASSUNTO = "Riassunto della conversazione precedente: "`.
- `stima_token(messaggi) -> int`: somma delle lunghezze di `str(m.content)` di tutti i messaggi (compresi
  `ToolMessage` e riassunto; per un `AIMessage` con tool call anche `str(tool_calls)`), divisa per
  `CARATTERI_PER_TOKEN` per eccesso.
- `dividi(messaggi) -> tuple[list, list]`: un turno comincia da un `HumanMessage`. L'ultimo `HumanMessage` è la
  domanda corrente. `recenti` comincia dal (`TURNI_RECENTI` + 1)-esimo `HumanMessage` contando dalla fine
  (con 2: la domanda che apre il più vecchio dei due turni completi tenuti) e arriva alla fine; per esempio
  con le domande D1…D5 (D5 corrente) i recenti cominciano da D3;
  `vecchi` è tutto quello che lo precede (compreso un eventuale `SystemMessage` di riassunto). Con meno di
  `TURNI_RECENTI + 1` domande, `vecchi` è vuoto. Un turno rifiutato dal router conta come turno. Il taglio cade sempre su un `HumanMessage`, quindi ogni tool
  call resta col suo `ToolMessage`.
- `unisci(precedente: str, nuovo: str, limite_token: int) -> tuple[str, int]` (*rivisto in esecuzione*):
  righe di `precedente` (se non vuoto) seguite da quelle di `nuovo`, unite con un a capo; finché la stima del
  testo (caratteri / 4 per eccesso) supera `limite_token` e restano almeno due righe, toglie la prima;
  restituisce il testo e il numero di righe tolte (l'ultima riga non è mai tolta).
- `trascrivi(nuovi) -> str`: una riga per messaggio: `Utente: ...`,
  `Assistente: ...` (solo `AIMessage` con testo), `Strumento <name>: <risultato>` (`ToolMessage`); gli
  `AIMessage` di sole tool call sono omessi (il risultato basta).
- `PROMPT_RIASSUNTO`: in italiano; riassumi la conversazione fra l'utente e l'assistente del laboratorio; il
  riassunto serve all'assistente per continuare la conversazione; conserva le richieste dell'utente e i dati
  ottenuti dagli strumenti (valori, orari, risultati, codici degli articoli, numeri delle note); non
  inventare nulla; al massimo 10 frasi; rispondi solo con il riassunto.
- `crea_riassuntore(llm) -> Callable[[list[AnyMessage]], str]`: `llm.bind(max_tokens=MAX_TOKEN_RIASSUNTO)`
  costruito una volta, **senza strumenti**; invoca `[SystemMessage(PROMPT_RIASSUNTO),
  HumanMessage(trascrivi(nuovi))]` e restituisce `str(risposta.content)`. Le eccezioni passano al nodo, che
  le registra.

### Configurazione (`src/assistente/config.py`)
- `Config` acquista `soglia_riassunto: int` (predefinito 3000, da `RIASSUNTO_SOGLIA_TOKEN`); valore non intero
  o < 1 → `ErroreConfigurazione` («RIASSUNTO_SOGLIA_TOKEN deve essere un intero positivo, trovato ...»).
- `.env.example`: `RIASSUNTO_SOGLIA_TOKEN=3000` con una riga di commento.
- Il predefinito 3000 lascia spazio, negli 8192 token caricati, a definizioni dei 10 strumenti, prompt e
  risposta; le prove reali misurano i `prompt_tokens` veri e lo confermano o lo correggono (con l'utente).

### CLI (`src/assistente/cli.py`)
- `main` passa `crea_riassuntore(llm)` e `config.soglia_riassunto` a `build_graph`.
- `esegui_turno` invariato: la cronologia restituita (già compatta) è usata nei turni successivi; un turno
  interrotto lascia la cronologia precedente (il riassunto di quel turno si rifà al turno dopo).

## Log (evidenze)
Logger `assistente.grafo`:
- DEBUG `riassunto: stima <n> token, sotto la soglia <s>`;
- INFO `riassunto: stima <n> token sopra la soglia <s>, niente da riassumere`;
- INFO `riassunto: <k> messaggi riassunti, stima <n> → <m> token`;
- WARNING `riassunto non disponibile: <causa>`;
- WARNING `riassunto oltre <n> token: tolte <k> righe più vecchie`.

## Test
(a) Automatici, senza LM Studio (`python -m pytest`):
- `tests/test_riassunto.py`: `stima_token` (testo, tool call, arrotondamento per eccesso); `dividi` (meno di 3
  domande → vecchi vuoti; confine su un `HumanMessage`; coppie tool call / `ToolMessage` intere nei recenti;
  riassunto precedente fra i vecchi); `unisci` (concatenazione, righe più vecchie tolte oltre il limite,
  ultima riga mai tolta); `trascrivi` (righe attese, tool call omesse);
  `crea_riassuntore` (nessuno strumento, `max_tokens`, prompt di sistema, un solo messaggio utente).
- `tests/finti.py`: `RiassuntoreFinto(testo="riassunto di prova", errore=None)` che registra i messaggi ricevuti.
- `tests/test_grafo.py`: sotto la soglia nessuna chiamata e messaggi invariati; sopra la soglia un solo
  `SystemMessage` in testa seguito dai recenti, log INFO; sopra la soglia senza vecchi nessuna chiamata; due
  riassunti consecutivi → un solo riassunto, il precedente **non** arriva al riassuntore ed è conservato alla
  lettera in testa al nuovo; righe tolte oltre metà soglia con WARNING; guasto (eccezione, testo
  vuoto) → messaggi invariati e WARNING; il router riceve la cronologia compatta; le chiamate esistenti a
  `build_graph` passano un `RiassuntoreFinto` e una soglia alta.
- `tests/test_config.py`: `RIASSUNTO_SOGLIA_TOKEN` predefinito, esplicito (anche con spazi), non valido
  (`0`, `-1`, `abc`, `1.5`).
- `tests/test_cli.py`: `main` passa riassuntore e soglia; dopo un turno con riassunto la cronologia del turno
  successivo comincia dal riassunto.

(b) Prove reali con LM Studio (`python -m pytest -m reale -v -s`), in `tests/reale/test_lmstudio.py`:
- sessione di cinque turni più due domande finali con soglia 200 (nota, ora, calcolo, conversioni): il riassunto scatta più volte
  (log INFO), nessun «riassunto non disponibile»; il riassunto finale contiene ancora il numero della nota del
  primo turno; «Che cosa ti avevo chiesto di annotare?» → risposta con «saldatore»; «Che numero ha la nota che
  ho aggiunto?» è un'**osservazione** (`pytest.xfail` se la risposta non contiene il numero, limite noto);
- `SystemMessage` in testa accettato da LM Studio (risposta corretta, nessun HTTP 400);
- tempo del riassunto e `prompt_tokens` della prima chiamata all'agente annotati nell'output (`-s`), per
  confermare la soglia predefinita;
- le prove reali esistenti costruiscono il grafo con il riassuntore vero e la soglia della configurazione.

## Revisione del 2026-11-10 (durante le prove reali)
- Con soglia 300 tre turni brevi restano sotto la soglia: la prova usa 100. Una domanda breve con cronologia
  minima costa circa 1750 `prompt_tokens` (definizioni dei 10 strumenti): il predefinito 3000 resta negli 8192.
- Il riassunto contiene il fatto («Nota 1 salvata …») e l'agente lo usa («Che cosa ti avevo chiesto di
  annotare?» 2/2), ma non ne ricava il numero («Che numero ha la nota…» 0/6 con riassunto in `SystemMessage`, in
  una coppia utente/assistente o con istruzione; 2/2 col turno intatto). Prompt a elenco di fatti (decisione
  dell'utente, una misura): 0/2 → **limite noto**, prompt invariato.
- **Fusione dal modello scartata:** chiedendo al modello di integrare il riassunto precedente, il secondo
  riassunto conteneva solo il turno nuovo e il fatto della nota spariva (3/3, con entrambi i prompt).
  Decisione dell'utente: concatenazione nel codice, con tetto a metà soglia sulle righe più vecchie.
- Prova di sessione: con soglia 100 il tetto (50 token) toglieva proprio la riga della nota (comportamento
  specificato); la prova usa 200. `gemma-4-e2b` scrive righe lunghe un paragrafo, quindi il tetto scatta lo
  stesso su righe più recenti; la perdita della nota la rileva il controllo del numero nel riassunto. Dopo un
  taglio restava in testa una riga vuota: `unisci` ignora le righe vuote.
- Revisione finale: istruzione del ripiego (`ISTRUZIONE_RISPOSTA`) e riassunto danno due `SystemMessage` di
  seguito; con `gemma-4-e2b` in LM Studio sono accettati (verificato con una richiesta diretta). Non fusi, per
  non cambiare la forma del ripiego misurata nel ciclo 6; un modello con template più rigido potrebbe
  rispondere HTTP 400 in quel caso.

## Documentazione
README: sezione sul riassunto (grafo, `RIASSUNTO_SOGLIA_TOKEN`, stima, righe di log, limiti), variabile
nell'elenco, diagnosi (`riassunto non disponibile`). `CLAUDE.md`: modulo `riassunto` nella struttura e
riassunto nell'obiettivo. Un solo commit a fine step con specifica, piano, codice, test e documenti.
