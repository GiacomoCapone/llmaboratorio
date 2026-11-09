# Router di ambito: specifica

Data: 2026-11-09. Stato: approvata; rivista durante l'implementazione (output strutturato del router).

## Contesto
Step 1 del percorso «grafo con due nodi LLM». Oggi il grafo è `START → modello ⇄ strumenti / limite → END`
e ogni domanda raggiunge l'agente (nodo `modello`). Questo step aggiunge, all'inizio del turno, un nodo
router che usa lo stesso modello con un prompt di sistema diverso e classifica la domanda: le domande fuori
ambito ricevono un rifiuto senza raggiungere l'agente. Nessuna dipendenza nuova (`langchain-openai` e
`pydantic` sono già presenti).

## Obiettivo
Le domande fuori ambito ricevono un rifiuto motivato e il nodo `modello` non viene eseguito; le domande in
ambito proseguono verso l'agente come prima. L'ambito è descritto in un file di configurazione, non nel codice.

## Fuori ambito
- Il router non valuta gli strumenti: se servono lo decide l'agente, come prima.
- Revisore delle risposte, riassunto della cronologia, resource e prompt MCP (step successivi).
- Rifiuto generato dal modello: il testo del rifiuto è fisso, con il motivo del router.
- Categorie diverse da `conversazione` e `fuori_ambito`.

## Decisioni concordate
- L'ambito sta nel file di testo `ambito.txt` nella cartella del progetto (versionato, senza credenziali);
  il percorso si può cambiare con `AMBITO_FILE` (relativo alla cartella del progetto, come `NOTE_DB`).
- Il router vede la domanda corrente e i messaggi precedenti fra utente e assistente fino a un totale di 4
  messaggi (costante nel codice), esclusi i `ToolMessage` e le risposte dell'assistente con sole tool call.
- Output strutturato tramite uno strumento obbligatorio: `llm.bind_tools([Classificazione],
  tool_choice="required", max_tokens=256)`, argomenti validati con Pydantic. *Rivista durante
  l'implementazione* (prima: `with_structured_output(method="json_schema")`): con lo schema in
  `response_format` LM Studio ignora `reasoning_effort=none` e gemma-4-e2b ragiona per migliaia di token
  (fino a 688 s per una classificazione, contro ~3 s con lo strumento obbligatorio);
  `with_structured_output(method="function_calling")` invia `tool_choice` in forma di oggetto, che
  LM Studio rifiuta (accetta solo `none`, `auto`, `required`).
- Varianti di scrittura della categoria (maiuscole, spazi, trattino: «Fuori ambito») sono normalizzate.
- Categoria diversa dai due valori ammessi (gemma-4-e2b scrive a volte l'argomento, es. «meteo», ma solo
  per domande in ambito) → `conversazione` con il motivo del modello e avviso
  `categoria non valida '<valore>': considerata conversazione`.
- Guasto del router (eccezione, output non valido) → la domanda passa all'agente come `conversazione` e il
  guasto è segnalato nei log con un avviso.
- Il turno rifiutato (domanda e rifiuto) entra nella cronologia come un turno normale.

## Architettura

### Grafo (`src/assistente/grafo.py`)
```
START → router ─┬─ conversazione → modello ⇄ strumenti / limite → END   (invariato)
                └─ fuori_ambito  → rifiuto → END
```
- `Stato` acquista i campi `categoria: str` e `motivo: str`, scritti dal nodo `router`.
- `build_graph(llm, strumenti, max_passaggi, router)`: `router` è un callable
  `list[AnyMessage] -> Classificazione`; il grafo non sa come classifica. Il nodo router è sempre presente.
- Nodo `router`: chiama `router(stato["messaggi"])`, registra il risultato, restituisce `categoria` e `motivo`.
- `instrada_dopo_router(stato) -> Literal["agente", "rifiuto"]`: funzione pura; `fuori_ambito` → `rifiuto`,
  altrimenti `agente`.
- Nodo `rifiuto`: non chiama il modello; aggiunge `AIMessage(MESSAGGIO_RIFIUTO.format(motivo=...))`.
  `MESSAGGIO_RIFIUTO` = «Posso rispondere solo a domande sul laboratorio e sui suoi strumenti. Motivo: {motivo}».
- Nodo `modello`: invariato, salvo una riga di log iniziale `agente: chiamata al modello`.
- Il limite di ricorsione cresce di 2 (i due nuovi passaggi).

### Router (`src/assistente/router.py`, nuovo)
- `Classificazione` (Pydantic): `categoria: Literal["conversazione", "fuori_ambito"]`, `motivo: str`.
- `PROMPT_ROUTER`: istruzioni di classificazione nel codice (classificare l'argomento dell'ultimo messaggio
  dell'utente, domanda o richiesta anche all'imperativo, rispetto all'ambito; non chiedersi se l'assistente
  conosce la data o ha gli strumenti; i messaggi precedenti servono solo a capire le domande di seguito; saluti e domande
  su cosa sa fare l'assistente sono `conversazione`; non rispondere alla domanda; motivo breve in italiano);
  il testo dell'ambito è inserito nel prompt.
- `ultimi_messaggi(messaggi, n=4)`: tiene `HumanMessage` e `AIMessage` con testo, esclude `ToolMessage` e
  `AIMessage` con sole tool call, restituisce gli ultimi `n`.
- `crea_router(llm, ambito) -> Callable`: costruisce `llm.bind_tools([Classificazione],
  tool_choice="required", max_tokens=MAX_TOKEN_ROUTER)` una volta; la funzione restituita invoca
  `[SystemMessage(prompt), *ultimi_messaggi(messaggi)]` e valida gli argomenti della prima tool call.
  Categoria sconosciuta → `conversazione` (vedi sopra). Qualunque eccezione, risposta senza tool call o
  argomenti non validi → `Classificazione(categoria="conversazione", motivo="router non disponibile")` e avviso
  `router non disponibile: <causa>` nel logger `assistente.router`.

### Configurazione (`src/assistente/config.py`)
- `Config` acquista `ambito: str` (il testo letto dal file).
- `AMBITO_FILE` facoltativa; predefinito `<progetto>/ambito.txt`; percorsi relativi rispetto alla cartella
  del progetto.
- File mancante o vuoto (solo spazi) → `ErroreConfigurazione` con il percorso cercato.
- `.env.example`: riga commentata `# AMBITO_FILE=ambito.txt` con spiegazione.

### CLI (`src/assistente/cli.py`)
- `main` crea `llm = crea_llm(config)` e passa `crea_router(llm, config.ambito)` a `build_graph`.
- `esegui_turno` e `ciclo` invariati: il turno rifiutato ha `interrotto=False` ed entra nella cronologia.

### Docker
- `Dockerfile`: `COPY ambito.txt .` (in `/app`, che è la cartella del progetto nel container).

## Log (evidenze)
Logger `assistente.grafo`, livello INFO:
- in ambito: `router categoria=conversazione motivo=<...> → agente`, poi `agente: chiamata al modello`;
- fuori ambito: `router categoria=fuori_ambito motivo=<...> → rifiuto` e nessuna riga `agente:`.
Logger `assistente.router`, livello WARNING: `router non disponibile: <causa>`.

## Test
(a) Automatici, senza LM Studio (`python -m pytest`):
- `tests/finti.py`: `RouterFinto(categoria, motivo="...")` (anche una lista di categorie, una per chiamata)
  che registra i messaggi ricevuti; `LlmFinto.bind_tools` registra gli argomenti in più
  (`opzioni_strumenti`); le risposte del router simulato sono tool call verso `Classificazione`.
- `tests/test_grafo.py`:
  - `test_router_in_ambito_passa_all_agente`: `LlmFinto` chiamato, risposta dell'agente, log con categoria,
    motivo e `→ agente`;
  - `test_router_fuori_ambito_rifiuta_senza_agente`: `LlmFinto` con 0 chiamate, ultimo messaggio = rifiuto con
    il motivo, nessuna riga `agente:` nei log;
  - `test_instradamento_dopo_router` (parametrizzato sulle due categorie).
- `tests/test_router.py`: prompt di sistema con il testo dell'ambito; `ultimi_messaggi` esclude i messaggi
  degli strumenti e tiene gli ultimi 4; eccezione del modello → `conversazione` con avviso nei log;
  `bind_tools` chiamato con `tool_choice="required"` e `max_tokens`; categoria sconosciuta → `conversazione`
  con il motivo del modello.
- `tests/test_config.py`: ambito predefinito, `AMBITO_FILE` relativo e assoluto, file mancante, file vuoto.
- Le chiamate esistenti a `build_graph` nei test passano `RouterFinto("conversazione")`.
- `tests/test_cli.py`: un turno rifiutato entra nella cronologia.

(b) Prove reali con LM Studio (`python -m pytest -m reale -v`), in `tests/reale/test_lmstudio.py`:
- «Che ore sono?» → `conversazione`, il nodo `modello` viene eseguito;
- «Scrivimi una poesia sul calcio» → `fuori_ambito`, nessuna riga `agente:` nei log.
- Le prove reali esistenti costruiscono il grafo con il router vero.

## Documentazione
README: file `ambito.txt` e `AMBITO_FILE`, grafo aggiornato, righe di log da cercare, diagnosi (router
non disponibile, domanda in ambito rifiutata → modificare `ambito.txt`). `CLAUDE.md`: modulo `router` nella
struttura e router nell'obiettivo. Un solo commit a fine step con specifica, piano, codice, test e documenti.
