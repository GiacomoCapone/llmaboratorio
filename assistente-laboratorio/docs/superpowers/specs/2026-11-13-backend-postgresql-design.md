# Step 7 — Back-end delle conversazioni con PostgreSQL

Data: 2026-11-13. Stato: approvata.

## Intento
L'agente dello step 6 è un servizio HTTP **senza stato**: ogni `POST /turno` porta la cronologia completa e
chi chiama la custodisce. Lo step 7 aggiunge quel chiamante: un **back-end** che conserva le conversazioni in
PostgreSQL, chiama l'agente a ogni messaggio e offre al front-end dello step 8 un'API per gestire più
conversazioni. Lo step 9 metterà insieme i quattro servizi (postgres, agente, back-end, front-end) in Compose.

## Decisioni dell'utente (brainstorming del 2026-11-13)
- **Più conversazioni, senza utenti:** si creano, si elencano, si riaprono, si eliminano. Nessun login.
- **La chat com'è stata scambiata:** riaprendo una conversazione si vedono tutte le domande e le risposte
  originali, anche dopo che l'agente ha riassunto i turni vecchi. Per questo il back-end salva **due cose**:
  i messaggi visibili (tabella `messaggi`) e, a parte, la cronologia opaca dell'agente da rimandargli.
- Proposte accettate: titolo dai primi caratteri della prima domanda; salvataggio di un turno in una sola
  transazione dopo la risposta dell'agente; agente in errore → nulla salvato, errore al chiamante; prompt MCP
  inoltrati, nella chat compare ciò che la persona ha scritto (`/scheda_articolo MIS-001`); secondo messaggio
  sulla stessa conversazione mentre un turno è in corso → errore «turno in corso», non attesa.
- **Approccio A: SQL esplicito con `psycopg` 3** (vedi «Approcci»).

## Obiettivi
- Pacchetto `src/backend/` con un servizio HTTP Starlette + uvicorn (già dipendenze del progetto).
- Persistenza in PostgreSQL di conversazioni, messaggi visibili e cronologia dell'agente.
- Chiamata all'agente **solo via HTTP** (`httpx`, già installato): il back-end non importa `assistente`.
- Test automatici ripetibili senza database né agente; prove con PostgreSQL vero e con LM Studio separate.
- Servizi Compose `postgres` e `backend` accanto ad `assistente` e `agente`.

## Non obiettivi
- Utenti, autenticazione, rinomina delle conversazioni, paginazione, ricerca nei messaggi.
- Risposte in streaming (l'agente dà una sola risposta JSON a turno concluso).
- Migrazioni di schema (le tabelle si creano all'avvio con `CREATE TABLE IF NOT EXISTS`).
- Front-end e CORS (step 8); Compose finale a quattro servizi con front-end (step 9).
- Pool di connessioni (`psycopg_pool` sarebbe una dipendenza in più; il carico è di una persona).

## Anti-obiettivi (sarebbe un fallimento anche se funziona)
- Il back-end che importa moduli di `assistente` o ne duplica la logica (router, grafo, strumenti).
- La chat visibile che cambia dopo un riassunto dell'agente.
- Un turno fallito che lascia la conversazione a metà (domanda salvata senza risposta, cronologia vecchia
  con messaggi nuovi o viceversa).
- Credenziali del database nel repository.

## Approcci
- **A — SQL esplicito con `psycopg` 3 (scelto dall'utente).** Una sola dipendenza nuova, SQL leggibile in
  un modulo, tabelle create all'avvio, test simulati con un deposito in memoria e prove separate su
  PostgreSQL vero. Contro: schema scritto a mano, niente migrazioni.
- **B — SQLAlchemy + Alembic.** Modelli e migrazioni versionate; due o tre dipendenze e molta superficie per
  due tabelle; il `jsonb` lega comunque a PostgreSQL. Scartato.
- Scartati in partenza: `asyncpg`/codice asincrono (`CLAUDE.md` chiede codice sincrono), framework web nuovi
  (FastAPI, Django: Starlette e uvicorn ci sono già).

## Dipendenza nuova
- `psycopg[binary]==3.3.9` in `requirements.txt` (verificato il 2026-11-13: esiste la wheel
  `psycopg_binary-3.3.9-cp314-cp314-win_amd64.whl`). Motivo: driver PostgreSQL sincrono, ufficiale, con
  `jsonb` e transazioni. Le dipendenze transitive vanno fissate come le altre.

## Configurazione (variabili d'ambiente o `.env`, come il resto del progetto)
| Variabile | Default | Note |
| --- | --- | --- |
| `DATABASE_URL` | nessuno, obbligatoria per il back-end | conninfo PostgreSQL, es. `postgresql://laboratorio:<password>@127.0.0.1:5432/laboratorio` |
| `AGENTE_URL` | `http://127.0.0.1:8000` | indirizzo del servizio dello step 6 |
| `AGENTE_TIMEOUT` | `900` | secondi di attesa di un turno (un turno può durare minuti) |
| `BACKEND_HOST` | `127.0.0.1` | come `HTTP_HOST` |
| `BACKEND_PORTA` | `8001` | intero 1–65535, come `HTTP_PORTA` |

Valori non validi → `Errore: …` su stderr e uscita 1, con messaggi nello stile di `assistente.config`.
`.env.example` riceve le righe commentate con un segnaposto al posto della password.

## Avvio
- Locale: `python avvia.py --backend` (stesso lanciatore, stesso `.venv`, stesso `.env`). L'uso diventa
  `Uso: python avvia.py [--http | --backend]` (uscita 2 per argomenti sconosciuti).
- All'avvio: connessione a PostgreSQL e creazione delle tabelle se mancano; un errore di connessione →
  `Errore: database non raggiungibile: …`, uscita 1. L'agente **non** è richiesto all'avvio (può partire
  dopo): la sua assenza emerge al primo messaggio come 502.
- Log INFO `backend in ascolto su http://%s:%d`; Ctrl-C → uscita 0 come il servizio dello step 6.

## Schema
```sql
CREATE TABLE IF NOT EXISTS conversazioni (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titolo      text        NOT NULL,
    creata      timestamptz NOT NULL DEFAULT now(),
    aggiornata  timestamptz NOT NULL DEFAULT now(),
    cronologia  jsonb       NOT NULL DEFAULT '[]'::jsonb
);
CREATE TABLE IF NOT EXISTS messaggi (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversazione_id bigint      NOT NULL REFERENCES conversazioni(id) ON DELETE CASCADE,
    ruolo            text        NOT NULL CHECK (ruolo IN ('utente', 'assistente')),
    testo            text        NOT NULL,
    ora              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messaggi_per_conversazione ON messaggi (conversazione_id, id);
```
- `cronologia` è esattamente la lista `cronologia` restituita dall'ultimo `POST /turno`, mai interpretata.
- Titolo di una conversazione nuova: `Nuova conversazione`; al primo messaggio diventa il testo visibile del
  messaggio (domanda, o `/nome argomenti` per un prompt) senza spazi ai lati e tagliato a 60 caratteri con
  `…` se più lungo.

## Struttura del codice (`src/backend/`)
- `config.py`: lettura e validazione delle variabili sopra.
- `deposito.py`: l'interfaccia del deposito delle conversazioni e l'implementazione PostgreSQL con SQL
  esplicito: `prepara()` (schema), `crea()`, `elenca()`, `leggi(id)`, `cronologia(id)`,
  `registra_turno(id, testo_utente, testo_risposta, cronologia_nuova)` (una transazione: due righe in
  `messaggi`, `cronologia`, `aggiornata`, titolo se era il primo messaggio), `elimina(id)`. Una connessione
  per operazione.
- `agente.py`: client `httpx` del servizio dello step 6 (`prompt()`, `turno(...)`), che traduce gli esiti in
  risultati o eccezioni del back-end.
- `app.py`: `crea_app(deposito, agente)` con le rotte; nessuna conoscenza di SQL o di `httpx`.
- `__main__.py`: `main()` / `servi(config)` con uvicorn.
- I nomi dei moduli sono una proposta: il costruttore può cambiarli mantenendo la separazione.

## API
Tutte le risposte sono JSON con `Content-Type: application/json; charset=utf-8` (come lo step 6, per
Windows PowerShell 5.1). Errori con corpo `{"errore": "<messaggio>"}`. Date in ISO 8601 con fuso.

| Metodo e percorso | Esito |
| --- | --- |
| `GET /salute` | 200 `{"stato": "ok"}` (non tocca database né agente) |
| `GET /prompt` | inoltra `GET /prompt` dell'agente: 200 con lo stesso corpo; agente non raggiungibile → 502 |
| `GET /conversazioni` | 200 `{"conversazioni": [{"id", "titolo", "creata", "aggiornata"}]}`, la più recente (`aggiornata`) per prima |
| `POST /conversazioni` | 201 `{"id", "titolo", "creata", "aggiornata"}` (corpo ignorato) |
| `GET /conversazioni/{id}` | 200 `{"id", "titolo", "creata", "aggiornata", "messaggi": [{"ruolo", "testo", "ora"}]}` in ordine; 404 |
| `DELETE /conversazioni/{id}` | 204 senza corpo; 404 |
| `POST /conversazioni/{id}/messaggi` | vedi sotto |

`{id}` non intero → 404. Messaggio 404: `conversazione <id> inesistente.`

### `POST /conversazioni/{id}/messaggi`
- Corpo: `{"domanda": "<testo>"}` oppure `{"prompt": {"nome": "<nome>", "argomenti": {...}}}`.
- Il back-end controlla solo la forma minima (oggetto JSON, esattamente uno dei due campi, `domanda` testo,
  `prompt` oggetto) → 400 con i testi dello step 6 dove coincidono; i controlli di merito (domanda vuota,
  prompt sconosciuto, argomenti) restano all'agente, il cui 400 è inoltrato **con lo stesso messaggio**.
- Flusso: conversazione inesistente → 404; turno già in corso sulla stessa conversazione → 409
  `turno in corso per la conversazione <id>.`; altrimenti si legge la `cronologia`, si chiama
  `POST {AGENTE_URL}/turno` con `domanda` o `prompt` e `cronologia`, poi `registra_turno`.
- Testo visibile del messaggio utente: la domanda così com'è; per un prompt `/<nome> <valori degli argomenti
  nell'ordine ricevuto, separati da spazio>` (es. `/scheda_articolo MIS-001`).
- 200 `{"risposta": "<testo>", "messaggi": [<messaggio utente>, <messaggio assistente>]}` con i due messaggi
  salvati (ruolo, testo, ora).
- Esiti dell'agente: 400 e 422 → stesso codice e stesso messaggio; 500, risposta non JSON, errore di rete o
  timeout → 502 `agente non disponibile: <causa>`. In tutti questi casi **nulla viene salvato**.
- Conversazione eliminata mentre il turno era in corso → 404 e nulla salvato.
- Errore del database → 500 `errore del database: <causa>` e log WARNING.
- Il controllo «turno in corso» è in memoria nel processo (un insieme di id protetto da lock): vale per un
  solo processo back-end, che è il caso previsto.
- Log INFO `messaggio: conversazione %d, %.1f s`.

## Compose
- `postgres`: immagine ufficiale con tag fissato (verificarne l'esistenza), volume con nome per i dati,
  `POSTGRES_USER`/`POSTGRES_DB`/`POSTGRES_PASSWORD` presi dal `.env` (non versionato), porta
  `127.0.0.1:5432:5432` per le prove dall'host, healthcheck `pg_isready`.
- `backend`: stessa immagine del progetto, `command: ["python", "-m", "backend"]`, `AGENTE_URL:
  http://agente:8000`, `DATABASE_URL` verso l'host `postgres`, `BACKEND_HOST: 0.0.0.0`, porta
  `127.0.0.1:8001:8001`, `depends_on` `postgres` (sano) e `agente`.
- `assistente` e `agente` invariati.

## Test e verifiche
- **Automatici (senza database né agente):** rotte con un deposito in memoria e un agente finto
  (`httpx.MockTransport`, parte di `httpx`): creazione, elenco ordinato, lettura, eliminazione, 404, un turno
  che salva due messaggi e la cronologia, titolo al primo messaggio (taglio a 60), prompt con testo
  `/nome argomenti`, 400 propri e inoltrati, 422 inoltrato, 502 per 500/rete/timeout senza salvataggio, 409
  con un turno in corso, configurazione (valori validi e non validi), charset.
- **PostgreSQL vero (marcatore `postgres`, escluso di default):** `deposito.py` contro un database
  raggiungibile da `DATABASE_URL`, in uno schema temporaneo creato e rimosso dalla prova: schema idempotente,
  transazione di `registra_turno`, `ON DELETE CASCADE`, ordine dei messaggi, `jsonb` restituito intatto.
- **Reale (marcatore `reale`):** back-end + agente + LM Studio + PostgreSQL: due messaggi concatenati in una
  conversazione, il secondo usa la cronologia salvata dal primo.
- **Manuali:** PowerShell (avvio locale di agente e back-end, `Invoke-RestMethod` sulle rotte) e Docker
  (`docker compose up -d postgres agente backend`), con esiti nel README.

## Scelte del redattore dopo la lettura del costruttore (2026-11-13, da controllare)
1. **Gestori come lo step 6:** rotte `async` che leggono il corpo ed eseguono database e agente con
   `run_in_threadpool`; client `httpx` e `psycopg` sincroni. Un turno lungo non blocca `/salute` né le altre
   conversazioni (limite: il thread pool di Starlette, 40 thread, ampiamente sufficiente).
2. **Rilascio del «turno in corso»:** l'id esce dall'insieme in un `finally` su ogni percorso (successo,
   errore dell'agente, errore del database, eccezione inattesa).
3. **Eliminazione durante un turno:** `DELETE` resta permesso. `registra_turno` aggiorna la conversazione con
   `UPDATE … RETURNING` dentro la transazione e, se la riga non c'è più, solleva un'eccezione distinta
   (`ConversazioneInesistente`) → 404; gli altri errori del database → 500.
4. **Primo messaggio:** è tale se la conversazione non ha ancora messaggi, controllato dentro la transazione
   (non dal titolo). Il testo visibile di un prompt senza argomenti è `/<nome>` senza spazio finale.
5. **Testo visibile:** per l'assistente si salva e si mostra solo `risposta`; il testo espanso del prompt
   non è salvato fra i messaggi visibili (resta, opaco, dentro la `cronologia` dell'agente).
6. **Cronologia in `jsonb`:** salvata così com'è, senza limiti di dimensione. Se PostgreSQL la rifiuta (per
   esempio `\u0000` in un testo) il turno finisce con 500 `errore del database: …` e nulla è salvato; una
   prova `postgres` usa una cronologia realistica (tool call, `ToolMessage`, riassunto).
7. **Deposito in memoria:** sta nei test, è protetto da lock e riproduce la semantica di quello PostgreSQL
   (eliminazione a cascata, `registra_turno` su id inesistente, titolo al primo messaggio); in caso di
   dubbio fanno fede le prove `postgres`.
8. **Prove `postgres` isolate:** il deposito PostgreSQL accetta un parametro facoltativo con lo schema da
   usare (impostato su ogni connessione); il marcatore `postgres` è registrato in `pytest.ini` ed escluso di
   default come `reale` e `rete`.
9. **Password del database in un solo posto per Compose:** il servizio `backend` compone `DATABASE_URL` da
   `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` del `.env` (interpolazione di Compose); il
   `DATABASE_URL` del `.env` serve solo all'avvio locale, e `.env.example` dice di tenerli allineati.
   `agente` senza healthcheck: il back-end non ne ha bisogno all'avvio.

## Lasciato al costruttore
- Nomi interni di funzioni e moduli, nel rispetto della separazione descritta.
- Forma esatta dei messaggi di errore di configurazione, nello stile di `assistente.config`.
- Tag dell'immagine PostgreSQL (fissato e verificato).
- Come lo schema temporaneo delle prove `postgres` viene isolato (`search_path` o simili).

## Revisione del 2026-11-13 (esecuzione)
Scarti dalla specifica emersi durante l'esecuzione (registro SDD, ruling del controllore); lo stato resta
approvata.
- **Porta dell'host di `postgres`: 5433, non 5432** (ruling 3): sul computer di sviluppo un servizio PostgreSQL
  di Windows occupa già la 5432. `compose.yaml` pubblica `127.0.0.1:5433:5432`; `DATABASE_URL` locale e
  `.env.example` usano la 5433. Dentro Compose `backend` raggiunge `postgres:5432`. Gli esempi con la 5432 nelle
  sezioni «Configurazione» e «Compose» valgono per un computer senza altro PostgreSQL.
- **Immagine `postgres:18.7`** (tag fissato e verificato) con volume `pgdati:/var/lib/postgresql`: l'immagine 18
  tiene i dati in `/var/lib/postgresql/18/docker`, quindi si monta la cartella superiore.
- **Fixture condivise in `tests/conftest.py`**: l'URL del database e lo schema temporaneo servono sia a
  `tests/postgres/` sia alla prova reale, quindi stanno nel `conftest.py` generale e non in `tests/postgres/`.
- **Il marcatore `postgres` seleziona anche la prova reale** (`pytestmark = [reale, postgres]`): per le sole prove
  del database il comando è `pytest -m "postgres and not reale"`; per la prova reale `pytest -m "reale and
  postgres" -v -s -k backend`.
- **`TransportInProcess` nella prova reale:** l'agente dello step 6 gira in-process in un `TestClient`, ma
  `TestClient._transport` non è utilizzabile direttamente come `transport` di `httpx`; la prova reale definisce
  perciò un piccolo `TransportInProcess` che inoltra le richieste del `ClientAgente` al `TestClient`.
- **Revisione finale: `errore interno: <causa>` (500)**: un'eccezione inattesa (non `ErroreDatabase` né
  `ErroreAgente`) restituisce JSON con charset, non il testo semplice di Starlette; il turno in corso è comunque
  liberato. Un `AGENTE_URL` malformato (`httpx.InvalidURL`) dà 502 `agente non disponibile: <causa>`.
- **Compose richiede `POSTGRES_*` nel `.env` per ogni comando** (`${VAR:?}` in `compose.yaml`), anche per
  `docker compose run --rm assistente`: da documentare nel README.
