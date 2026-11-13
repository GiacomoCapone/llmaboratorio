# Agente come servizio HTTP: specifica

Data: 2026-11-10. Stato: approvata (corretta il 2026-11-13: vedi «Revisione del 2026-11-13»).

## Contesto
Step 6 del percorso a 9 step, dopo le primitive MCP (step 4 resource, step 5 prompt). Oggi la CLI
(`src/assistente/cli.py`) è l'unica interfaccia: costruisce archivio, strumenti e grafo in `main()`, conserva
la cronologia nel ciclo, interpreta i comandi `/nome argomenti` dei prompt (`espandi_prompt`) e legge le
categorie dell'inventario all'avvio (`leggi_contesto`). Lo step espone lo stesso agente come servizio HTTP,
che negli step successivi sarà chiamato dal back-end (step 7, PostgreSQL), usato dal front-end (step 8) e
messo in Docker Compose con gli altri servizi (step 9).

## Obiettivo
Un programma esterno esegue turni di conversazione con l'agente tramite HTTP, con lo stesso grafo e lo
stesso comportamento della CLI (router, agente, strumenti, revisore, riassunto), e usa i prompt MCP
dell'archivio. La CLI resta disponibile e invariata per l'utente.

## Fuori ambito
- Persistenza delle conversazioni (step 7, nel back-end); sessioni o stato di conversazione nell'agente.
- Streaming degli eventi del turno (SSE): eventualmente in uno step successivo, se il front-end ne avrà
  bisogno.
- Autenticazione, HTTPS, CORS, limiti di dimensione del corpo, timeout del turno lato server.
- Documentazione OpenAPI generata.
- Modifiche a grafo, router, revisore, riassunto, strumenti e server «archivio».

## Decisioni concordate
- **Agente senza stato:** ogni richiesta porta la cronologia e la nuova domanda; la risposta restituisce la
  cronologia aggiornata. Chi chiama la custodisce.
- **Cronologia completa e opaca:** tutti i messaggi del grafo (domande, risposte, chiamate e risultati degli
  strumenti, `SystemMessage` del riassunto) serializzati con `messages_to_dict` di `langchain_core`; il
  chiamante li rimanda tali e quali. La risposta da mostrare è in un campo separato.
- **Prompt con endpoint dedicati:** `GET /prompt` per l'elenco; la richiesta di turno accetta un prompt
  strutturato (`nome`, `argomenti`) al posto della domanda. La sintassi `/nome argomenti` resta solo nella CLI.
- **Una sola risposta JSON** a turno concluso.
- **Un turno alla volta:** le richieste concorrenti attendono in fila (lock).
- **CLI e servizio convivono**, con la costruzione dell'assistente in comune; il servizio si avvia con
  `python avvia.py --http`; in Compose un nuovo servizio `agente`.
- **Starlette + uvicorn**, già in `requirements.txt` con versione fissata (dipendenze di `mcp==2.3.0`):
  nessuna dipendenza nuova. I test usano il `TestClient` di Starlette (`httpx`, già presente).

## Architettura

### `src/assistente/avvio.py` (nuovo)
Costruzione condivisa, spostata da `cli.main` senza cambiarne il comportamento:
- `apri_assistente(config)`: context manager che apre `ClientArchivio` (con `NOTE_DB` e `FUSO_PREDEFINITO`
  nell'ambiente), legge il contesto delle categorie (`leggi_contesto`, spostata qui da `cli.py`), esegue
  `verifica_modello`, crea strumenti, LLM, router, revisore, riassuntore e grafo, e restituisce
  `(grafo, archivio)`; all'uscita chiude l'archivio.
- Gli errori `ErroreConfigurazione`, `ErroreModello`, `ErroreArchivio` si propagano al chiamante.

### `src/assistente/servizio.py` (nuovo)
- `crea_app(grafo, prompt) -> Starlette`: applicazione con le tre rotte; `prompt` è l'oggetto con
  `prompt_disponibili()` e `testo_prompt(nome, argomenti)` (l'archivio; un finto nei test). Gestori
  `/salute` e `/prompt` **sincroni** (Starlette li esegue nel suo thread pool); `/turno` è `async` (in Starlette
  un gestore sincrono non può leggere il corpo) ed esegue prompt e turno con `run_in_threadpool`. Contiene
  un `threading.Lock` per i turni. Tutte le risposte JSON dichiarano `application/json; charset=utf-8`
  (senza charset Windows PowerShell 5.1 decodifica il corpo come ISO-8859-1).
- `servi(config) -> None`: `with apri_assistente(config)`, poi `uvicorn.run(crea_app(...), host=config.http_host,
  port=config.http_porta, log_level=...)`; uvicorn restituisce dopo Ctrl-C/SIGTERM e l'archivio si chiude.
  Un messaggio INFO indica l'indirizzo di ascolto.

### `src/assistente/cli.py`
- `esegui_turno`, `EsitoTurno`, `MESSAGGIO_RISPOSTA_VUOTA`, `ciclo`, `espandi_prompt` restano qui; il
  servizio importa `esegui_turno` e `MESSAGGIO_RISPOSTA_VUOTA` (una sola regola per il turno interrotto e la
  risposta vuota).
- `main(argv: list[str] | None = None) -> int`: `argv` vuoto → CLI come oggi (con `apri_assistente`);
  `["--http"]` → `servi(config)`; qualunque altro argomento → messaggio d'uso su stderr, uscita 2. Errori
  di configurazione, modello e archivio → `Errore: …` su stderr, uscita 1, per entrambe le modalità
  (rilevati prima di avviare uvicorn). Ctrl-C durante l'avvio → 130 come oggi.

### `src/assistente/config.py`
- `HTTP_HOST` (default `127.0.0.1`; spazi tolti; vuoto → default) e `HTTP_PORTA` (default `8000`; intero
  fra 1 e 65535, altrimenti `ErroreConfigurazione` «HTTP_PORTA deve essere un intero fra 1 e 65535,
  trovato '<valore>'.»). Nuovi campi `http_host`, `http_porta` di `Config`, con default.

### `avvia.py`, `src/assistente/__main__.py`
Passano `sys.argv[1:]` a `main`.

### Docker
- `compose.yaml`: nuovo servizio `agente` con la stessa build, `command: ["python", "-m", "assistente",
  "--http"]`, `env_file: .env`, `environment` con `LMSTUDIO_BASE_URL` per `host.docker.internal`,
  `NOTE_DB: /app/dati/note.db` e `HTTP_HOST: 0.0.0.0`, stesso `extra_hosts`, volume `./dati:/app/dati`,
  `ports: ["127.0.0.1:8000:8000"]` (pubblicata solo sull'host locale). Il servizio `assistente` resta
  interattivo e invariato.
- `Dockerfile` invariato.

## Interfaccia HTTP
Corpi JSON in UTF-8. Errori: `{"errore": "<messaggio in italiano>"}`.

### `GET /salute`
`200 {"stato": "ok"}`. Non chiama il modello (verificato all'avvio).

### `GET /prompt`
`200 {"prompt": [{"nome": "scheda_articolo", "argomenti": ["codice"], "descrizione": "..."}]}`, dall'elenco
`prompt_disponibili()` letto all'avvio; elenco vuoto → `{"prompt": []}`.

### `POST /turno`
Richiesta, con **esattamente uno** fra `domanda` e `prompt`:
```json
{"cronologia": [], "domanda": "Che ore sono a Tokyo?"}
{"cronologia": [], "prompt": {"nome": "scheda_articolo", "argomenti": {"codice": "MIS-001"}}}
```
- `cronologia`: facoltativa, default `[]`; lista dei messaggi restituiti dal turno precedente.
- `domanda`: stringa non vuota dopo `strip()` (come la CLI, il BOM `﻿` è tolto).
- `prompt.argomenti`: oggetto con valori stringa; i nomi devono coincidere con gli argomenti dichiarati dal
  prompt (né mancanti né in più); valori non vuoti dopo `strip()`. Facoltativo se il prompt non ha argomenti.

Risposta `200`:
```json
{"domanda": "...", "risposta": "...", "cronologia": [], "interrotto": false}
```
- `domanda`: il testo eseguito (con un prompt, il testo generato dall'archivio).
- `risposta`: contenuto dell'ultimo messaggio; vuoto o di soli spazi → `MESSAGGIO_RISPOSTA_VUOTA`
  («(il modello non ha prodotto una risposta)»).
- `cronologia`: `messages_to_dict` dei messaggi dopo il turno; se il riassunto è scattato è più corta di
  quella inviata.
- `interrotto: true` (tetto `MAX_PASSAGGI`): `cronologia` è quella ricevuta, invariata.

Flusso: validazione del corpo → `messages_from_dict` della cronologia → se c'è un prompt, `testo_prompt`
(fuori dal lock) → acquisizione del lock → `esegui_turno(grafo, cronologia, domanda)` → serializzazione.
Log INFO `turno: <n> messaggi in ingresso, <durata> s` a fine turno; con un prompt, `prompt: <nome> <argomenti>`
come la CLI.

## Errori
| Caso | Codice | Messaggio (sostanza) |
| --- | --- | --- |
| Corpo non JSON o non oggetto | 400 | «corpo della richiesta non valido: atteso un oggetto JSON.» |
| `domanda` e `prompt` insieme o nessuno dei due | 400 | «indicare esattamente uno fra 'domanda' e 'prompt'.» |
| `domanda` non stringa o vuota | 400 | «'domanda' deve essere un testo non vuoto.» |
| `cronologia` non lista, o messaggi non ricostruibili | 400 | «'cronologia' non valida: …» |
| `prompt` malformato, sconosciuto, argomenti errati | 400 | «prompt sconosciuto '<nome>'.», «<nome> richiede: <argomenti>.», «argomenti non previsti per <nome>: …» |
| `testo_prompt` solleva `ErroreArchivio` (codice inesistente, archivio non disponibile) | 422 | messaggio dell'archivio; il turno non parte |
| Eccezione durante il turno | 500 | «turno fallito: <causa>»; WARNING `turno fallito` come la CLI; il servizio resta attivo |
| Rotta o metodo sconosciuti | 404/405 | comportamento predefinito di Starlette |

Altri comportamenti:
- **Avvio:** configurazione, modello o archivio non validi → `Errore: …`, uscita 1, uvicorn non parte.
- **Arresto:** Ctrl-C o SIGTERM → uvicorn attende il turno in corso, poi l'archivio si chiude; uscita 0.
- **Client disconnesso a metà turno:** il turno arriva alla fine e il risultato è scartato; nessuno stato da
  ripulire.
- **Note:** come oggi, il file `note.db` va usato da un solo processo alla volta (CLI o servizio).

## Test
Automatici, senza modello (`python -m pytest`):
- `tests/test_servizio.py` con `TestClient` e `crea_app` su grafo e archivio finti:
  - `/salute`; `/prompt` con elenco e vuoto;
  - `/turno` con domanda: risposta, cronologia serializzata che contiene domanda e risposta, ricostruibile
    con `messages_from_dict`;
  - andata e ritorno: la cronologia rimandata arriva al grafo con messaggi uguali, compresi `AIMessage` con
    `tool_calls`, `ToolMessage` e `SystemMessage`;
  - turno interrotto → cronologia ricevuta e `interrotto: true`; risposta vuota → messaggio sostitutivo;
  - `/turno` con prompt: il testo generato arriva al grafo e torna in `domanda`; prompt senza argomenti;
  - ogni caso 400 e 422 della tabella, con il grafo non chiamato;
  - 500: il grafo solleva, il turno successivo riesce;
  - lock: due richieste da due thread su un grafo finto che misura le esecuzioni sovrapposte → massimo 1.
- `tests/test_config.py`: default e validazione di `HTTP_HOST` e `HTTP_PORTA` (0, 65536, testo).
- `tests/test_cli.py`: `main(["--http"])` chiama `servi`; argomento sconosciuto → uscita 2; i test esistenti
  continuano a passare dopo lo spostamento in `avvio.py`.

Prova reale (`-m reale`, LM Studio), `tests/reale/`: servizio in-process con `TestClient` e grafo vero:
- due turni concatenati con la cronologia restituita: «Annota che il multimetro MIS-001 ha la batteria
  scarica», poi «Quali note ci sono?» → `elenca_note` chiamato e nota trovata; nota di prova eliminata alla
  fine (database temporaneo);
- turno con `prompt` `scheda_articolo` `MIS-001` → `dettaglio_articolo` chiamato.

Prove manuali, riportate nel resoconto:
- PowerShell: `python avvia.py --http`; `Invoke-RestMethod` su `/salute`, `/prompt` e due `/turno`
  concatenati; Ctrl-C → uscita 0.
- Docker: `docker compose up agente`, stesse chiamate su `127.0.0.1:8000`, `docker compose stop agente`.
- CLI: `python avvia.py` con una domanda, uscita 0.

## Documentazione
Nello stesso commit di fine step: README (variabili `HTTP_*`, avvio del servizio, esempi PowerShell, diagnosi),
`CLAUDE.md` (struttura con `avvio` e `servizio`, comando di avvio), `.env.example` (`HTTP_HOST`/`HTTP_PORTA`
commentate), handoff.

## Revisione del 2026-11-13 (durante l'implementazione)
- Gestori: `/turno` è `async` e usa `run_in_threadpool` per prompt e turno; solo `/salute` e `/prompt` sono
  sincroni. In Starlette un gestore sincrono non può leggere il corpo della richiesta.
- Intestazione: le risposte JSON dichiarano `application/json; charset=utf-8`. Starlette manda
  `application/json` senza charset e Windows PowerShell 5.1 (`Invoke-RestMethod`) leggeva «Quantità» come
  «QuantitÃ ».
- Import: `cli` e `servizio` si importano come moduli per evitare l'import circolare.
- Stato: approvata.
