# Back-end delle conversazioni con PostgreSQL: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un back-end HTTP (`python avvia.py --backend`, servizio Compose `backend`) che conserva più conversazioni in PostgreSQL (chat visibile + cronologia opaca dell'agente) e a ogni messaggio chiama il servizio HTTP senza stato dello step 6.

**Architecture:** nuovo pacchetto `src/backend/` che non importa `assistente`: `config` (variabili), `deposito` (SQL esplicito con `psycopg` 3, una connessione per operazione), `agente` (client `httpx` di `/prompt` e `/turno`), `app` (Starlette, rotte `async` con `run_in_threadpool`), `__main__` (uvicorn). Nei test le rotte usano un deposito in memoria e un agente finto via `httpx.MockTransport`.

**Tech Stack:** Python 3.14, `psycopg[binary]==3.3.9` (nuova), `starlette==1.10.0`, `uvicorn==0.54.0`, `httpx==0.28.1`, `python-dotenv==1.2.4`, PostgreSQL in Docker, pytest.

**Spec:** `docs/superpowers/specs/2026-11-13-backend-postgresql-design.md` (approvata il 2026-11-13; vincolante, comprese le «Scelte del redattore» 1–9).

## Global Constraints
- Comandi dalla cartella `assistente-laboratorio/` con `.venv\Scripts\python` (da Bash: `.venv/Scripts/python.exe`).
- Unica dipendenza nuova: `psycopg[binary]==3.3.9` (in `requirements.txt` anche `psycopg-binary==3.3.9` e ogni altra transitiva nuova, fissate). Nessun'altra.
- `src/backend/` non importa `assistente` né `archivio`; grafo, strumenti, `mcp_client`, server «archivio», servizio dello step 6 invariati (unica modifica in `assistente`: il testo d'uso in `cli.py`).
- Codice sincrono; rotte `async` solo per leggere il corpo, lavoro bloccante in `run_in_threadpool` (come `assistente/servizio.py`).
- Risposte JSON con `Content-Type: application/json; charset=utf-8`; errori con corpo `{"errore": "<messaggio>"}`; date con `datetime.isoformat()` (timestamptz → con fuso).
- Testi esatti:
  - `conversazione <id> inesistente.` (404; anche per `{id}` non intero, con l'id così com'è nel percorso)
  - `turno in corso per la conversazione <id>.` (409)
  - `corpo della richiesta non valido: atteso un oggetto JSON.` (400)
  - `indicare esattamente uno fra 'domanda' e 'prompt'.` (400)
  - `'domanda' deve essere un testo non vuoto.` (400, solo se `domanda` non è una stringa; una stringa vuota va all'agente)
  - `'prompt' non valido: atteso un oggetto con 'nome' e 'argomenti'.` (400)
  - 400 e 422 dell'agente → stesso codice, stesso `errore`
  - `agente non disponibile: <causa>` (502)
  - `errore del database: <causa>` (500)
  - `Uso: python avvia.py [--http | --backend]` (stderr, uscita 2)
  - `Errore: database non raggiungibile: <causa>` (avvio, uscita 1)
- Titolo iniziale `Nuova conversazione`; al primo messaggio: testo visibile `strip()`, se più di 60 caratteri → primi 59 + `…` (60 in tutto).
- Testo visibile di un prompt: `"/" + nome` più, se ci sono argomenti, `" "` + valori `str()` uniti da spazio nell'ordine del JSON ricevuto.
- Variabili: `DATABASE_URL` (obbligatoria), `AGENTE_URL` (`http://127.0.0.1:8000`, `/` finale tolto), `AGENTE_TIMEOUT` (`900`, numero > 0), `BACKEND_HOST` (`127.0.0.1`, vuoto → default), `BACKEND_PORTA` (`8001`, intero 1–65535), `LOG_LEVEL` (`INFO`). Precedenza: ambiente > `.env` del progetto.
- Log (`backend`): INFO `backend in ascolto su http://%s:%d`; INFO `messaggio: conversazione %d, %.1f s`; WARNING `errore del database: %s`; WARNING `agente non disponibile: %s`.
- Marcatore `postgres` registrato in `pytest.ini` ed escluso di default (`-m "not reale and not rete and not postgres"`).
- Un solo commit a fine step (Task 5); ogni task termina con `python -m pytest` verde. Staging selettivo: mai `lezione_3/`, `.env`, `dati/`, file fuori da `assistente-laboratorio/`.
- `.env` è dell'utente: le righe `POSTGRES_*` e `DATABASE_URL` le aggiunge il controllore **dopo conferma dell'utente** (Task 1, Step 1), mai versionate.
- Nei test, funzioni d'appoggio che cominciano con `test` vengono raccolte da pytest: usare altri nomi. Heredoc dal tool Bash alterano `\n`: per i sorgenti usare Write/Edit.

## Review Focus
- Agente più lento di `AGENTE_TIMEOUT`: 502 `agente non disponibile: …`, nulla salvato, conversazione di nuovo libera — Task 3, `test_timeout_agente_non_salva_e_libera`.
- Conversazione eliminata mentre l'agente risponde: 404, nessun messaggio orfano — Task 1, `test_registra_turno_su_conversazione_eliminata` (PostgreSQL); Task 3, `test_eliminata_durante_il_turno`.
- Testi con accenti, emoji e virgolette in domanda, risposta e cronologia: tornano identici da `jsonb` e `text` — Task 1, `test_testi_e_cronologia_intatti`.
- Due messaggi ravvicinati sulla stessa conversazione: il secondo 409, una conversazione diversa non è bloccata, dopo il primo un terzo riesce — Task 3, `test_turno_in_corso_409`.
- `/conversazioni/abc` e `/conversazioni/999`: 404 con JSON, mai 500 — Task 3, `test_id_non_valido_o_inesistente`.

---

### Task 1: dipendenza, configurazione, deposito PostgreSQL e servizio `postgres`

**Files:**
- Create: `src/backend/__init__.py` (vuoto), `src/backend/config.py`, `src/backend/deposito.py`, `tests/test_backend_config.py`, `tests/postgres/test_deposito_postgres.py`
- Modify: `requirements.txt`, `pytest.ini`, `compose.yaml` (solo servizio `postgres` e volume), `.env.example`

**Interfaces:**
- Produces (`backend.config`): `class ErroreConfigurazione(Exception)`; `@dataclass(frozen=True) class ConfigBackend: database_url: str; agente_url: str = "http://127.0.0.1:8000"; agente_timeout: float = 900.0; host: str = "127.0.0.1"; porta: int = 8001; log_level: str = "INFO"`; `carica_config(env: Mapping[str, str] | None = None) -> ConfigBackend` (`None` → `.env` di `Path(__file__).resolve().parents[2]` letto con `dotenv_values`, poi `os.environ` con precedenza).
- Produces (`backend.deposito`): `TITOLO_INIZIALE = "Nuova conversazione"`; `titolo_da(testo: str) -> str`; `@dataclass(frozen=True) Conversazione(id: int, titolo: str, creata: datetime, aggiornata: datetime)`; `@dataclass(frozen=True) Messaggio(ruolo: str, testo: str, ora: datetime)`; `class ConversazioneInesistente(Exception)` (attributo `id: int`); `class ErroreDatabase(Exception)`; `class Deposito(Protocol)` con `prepara() -> None`, `crea() -> Conversazione`, `elenca() -> list[Conversazione]` (per `aggiornata` decrescente, poi `id` decrescente), `leggi(id: int) -> tuple[Conversazione, list[Messaggio]]`, `cronologia(id: int) -> list[dict]`, `registra_turno(id: int, testo_utente: str, testo_risposta: str, cronologia: list[dict]) -> list[Messaggio]` (i due salvati), `elimina(id: int) -> None`; `class DepositoPostgres(conninfo: str, schema: str | None = None)` che lo implementa. Errori: id assente → `ConversazioneInesistente`; ogni `psycopg.Error` → `ErroreDatabase(str(errore))`.

- [ ] **Step 1: ambiente.** Il controllore chiede all'utente il permesso di aggiungere al suo `.env` `POSTGRES_USER=laboratorio`, `POSTGRES_DB=laboratorio`, `POSTGRES_PASSWORD=<generata localmente>`, `DATABASE_URL=postgresql://laboratorio:<stessa>@127.0.0.1:5432/laboratorio`. `.env.example`: le stesse righe con `POSTGRES_PASSWORD=` vuoto e il commento «tenere DATABASE_URL allineato a POSTGRES_* (Compose costruisce il suo dal resto)», più `# AGENTE_URL=http://127.0.0.1:8000`, `# AGENTE_TIMEOUT=900`, `# BACKEND_HOST=127.0.0.1`, `# BACKEND_PORTA=8001`.
- [ ] **Step 2: dipendenza.** `.venv/Scripts/python.exe -m pip install "psycopg[binary]==3.3.9"`; aggiungere a `requirements.txt` (ordine alfabetico come il file) `psycopg==3.3.9`, `psycopg-binary==3.3.9` e ogni transitiva che `pip` installa e il file non ha. `pytest.ini`: marcatore `postgres: prove con PostgreSQL attivo e DATABASE_URL (escluse di default)` e `addopts = -m "not reale and not rete and not postgres"`.
- [ ] **Step 3: `compose.yaml`, servizio `postgres`.** Immagine `postgres:<tag esatto>` (ultima patch 17.x o 18.x che `docker pull` scarica; annotare il tag nel report), `environment` `POSTGRES_USER: ${POSTGRES_USER:?…}`, `POSTGRES_DB: ${POSTGRES_DB:?…}`, `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?…}` con messaggio «definire POSTGRES_… nel .env», volume con nome `pgdati:/var/lib/postgresql/data` (o il percorso che l'immagine 18 richiede), `ports: ["127.0.0.1:5432:5432"]`, `healthcheck` con `pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}`. Verifica: `docker compose config --quiet`; `docker compose up -d postgres` → stato `healthy`.
- [ ] **Step 4: test della configurazione** (`tests/test_backend_config.py`, `carica_config(env)` con dizionari):
  - `test_predefiniti`: `{"DATABASE_URL": "postgresql://x"}` → `ConfigBackend("postgresql://x")` coi default.
  - `test_impostati`: `AGENTE_URL="http://agente:8000/"`, `AGENTE_TIMEOUT="30"`, `BACKEND_HOST=" 0.0.0.0 "`, `BACKEND_PORTA="9001"`, `LOG_LEVEL="debug"` → `agente_url == "http://agente:8000"`, `agente_timeout == 30.0`, `host == "0.0.0.0"`, `porta == 9001`, `log_level == "DEBUG"`.
  - `test_database_url_mancante` (parametrizzato assente, `""`, `"  "`) → `ErroreConfigurazione` con `DATABASE_URL`.
  - `test_porta_non_valida` (`"0"`, `"65536"`, `"abc"`) → messaggio `BACKEND_PORTA deve essere un intero fra 1 e 65535, trovato '<grezzo>'.`
  - `test_timeout_non_valido` (`"0"`, `"-5"`, `"x"`) → messaggio `AGENTE_TIMEOUT deve essere un numero positivo di secondi, trovato '<grezzo>'.`
  - `test_titolo_da`: `"  Ciao  "` → `"Ciao"`; 60 caratteri → invariato; 61 → 59 + `"…"` (`len == 60`).
- [ ] **Step 5: test PostgreSQL** (`tests/postgres/test_deposito_postgres.py`, `pytestmark = pytest.mark.postgres`; fixture che legge `DATABASE_URL` da `carica_config()`, salta con un motivo chiaro se manca o il server non risponde, crea uno schema `prova_<uuid hex>` e lo rimuove con `DROP SCHEMA … CASCADE` alla fine; `DepositoPostgres(url, schema=...)`; `prepara()` chiamata due volte):
  - `test_crea_elenca_leggi`: due `crea()` → `elenca()` con la seconda per prima; `leggi` → titolo `Nuova conversazione`, nessun messaggio.
  - `test_registra_turno`: dopo un turno, `leggi` dà `[utente, assistente]` coi testi, titolo = `titolo_da(testo_utente)`, `cronologia(id)` uguale a quella passata, `aggiornata` aumentata; secondo turno → titolo invariato, 4 messaggi in ordine.
  - `test_testi_e_cronologia_intatti`: testi `"Perché è così? «ok» 🔧 \"x\""` e una cronologia realistica (dict con `human`, `ai` con `tool_calls`, `tool`, `system` di riassunto) tornano uguali.
  - `test_registra_turno_su_conversazione_eliminata`: `elimina(id)` poi `registra_turno(id, …)` → `ConversazioneInesistente`; nessuna riga in `messaggi` per quell'id.
  - `test_elimina_a_cascata` e `test_inesistente` (`leggi`, `cronologia`, `elimina` su id 999999 → `ConversazioneInesistente`).
  - `test_cronologia_rifiutata`: una cronologia con `"\u0000"` in un testo → `ErroreDatabase`, nessun messaggio salvato.
  - `test_errore_di_connessione`: `DepositoPostgres("postgresql://x:y@127.0.0.1:1/z").prepara()` → `ErroreDatabase`.
- [ ] **Step 6:** `.venv/Scripts/python.exe -m pytest tests/test_backend_config.py -q` e `-m postgres tests/postgres -v` → FAIL (moduli mancanti).
- [ ] **Step 7: implementare** `config.py` e `deposito.py`. Schema esattamente come nella spec. `schema` → `options=f"-c search_path={schema}"` alla connessione e `CREATE SCHEMA IF NOT EXISTS` in `prepara()`. `cronologia` passata con `psycopg.types.json.Jsonb`. `registra_turno` in `with conn.transaction()`: `SELECT … FOR UPDATE` della conversazione (assente → `ConversazioneInesistente`), conteggio dei messaggi per il titolo, due `INSERT … RETURNING ruolo, testo, ora`, `UPDATE` di `cronologia`, `aggiornata = now()` e titolo.
- [ ] **Step 8:** i due comandi dello Step 6 → PASS; `.venv/Scripts/python.exe -m pytest -q` verde.

### Task 2: client dell'agente

**Files:**
- Create: `src/backend/agente.py`, `tests/test_backend_agente.py`

**Interfaces:**
- Produces: `class ErroreAgente(Exception)` con attributi `codice: int` (400, 422 o 502) e `messaggio: str` (`str(errore) == messaggio`); `class ClientAgente(url: str, timeout: float, transport: httpx.BaseTransport | None = None)` con `prompt() -> dict` (corpo di `GET {url}/prompt`) e `turno(cronologia: list[dict], domanda: str | None = None, prompt: dict | None = None) -> tuple[str, list[dict]]` (`risposta`, `cronologia`); invia `{"domanda" | "prompt": …, "cronologia": …}`.

- [ ] **Step 1: test** (`httpx.MockTransport` che registra le richieste):
  - `test_turno_con_domanda`: richiesta `POST /turno` con corpo `{"domanda": "Che ore sono?", "cronologia": [...]}`; risposta 200 → `("ok", [...])`.
  - `test_turno_con_prompt`: corpo con `prompt` e senza `domanda`.
  - `test_prompt`: `GET /prompt` → corpo restituito tale e quale.
  - `test_errori_inoltrati` (parametrizzato 400, 422): `ErroreAgente` con stesso codice e messaggio dell'`errore` dell'agente.
  - `test_errori_502` (parametrizzato: 500 con `{"errore": "turno fallito: x"}` → `agente non disponibile: turno fallito: x`; 200 non JSON → `agente non disponibile: risposta non valida`; `httpx.ConnectError` → `agente non disponibile: ` + testo dell'eccezione; `httpx.ReadTimeout` → `agente non disponibile: tempo scaduto dopo 900 s`): `codice == 502`.
  - `test_timeout_usato`: il client creato con `timeout=30` passa 30 secondi a `httpx` (verificare sull'estensione `timeout` della richiesta registrata).
- [ ] **Step 2:** `pytest tests/test_backend_agente.py -q` → FAIL.
- [ ] **Step 3: implementare** `agente.py` con un `httpx.Client(base_url=url, timeout=timeout, transport=transport)` per chiamata o per istanza (scelta libera); una risposta 400/422 senza `errore` → 502 `agente non disponibile: risposta non valida`.
- [ ] **Step 4:** test → PASS; `python -m pytest -q` verde.

### Task 3: rotte del back-end

**Files:**
- Create: `src/backend/app.py`, `tests/finti_backend.py` (deposito in memoria), `tests/test_backend_app.py`

**Interfaces:**
- Consumes: `Deposito`, `Conversazione`, `Messaggio`, `ConversazioneInesistente`, `ErroreDatabase`, `titolo_da`, `TITOLO_INIZIALE` (Task 1); `ClientAgente`, `ErroreAgente` (Task 2).
- Produces: `crea_app(deposito: Deposito, agente: ClientAgente) -> Starlette`; `testo_visibile(domanda: str | None, prompt: dict | None) -> str`; in `tests/finti_backend.py` `class DepositoMemoria` (thread-safe, stessa semantica del PostgreSQL: ordine di `elenca`, titolo al primo messaggio, cascata, `ConversazioneInesistente`; opzione `errore: ErroreDatabase | None` per simulare il database rotto).

- [ ] **Step 1: test** (`TestClient(crea_app(DepositoMemoria(), ClientAgente("http://agente", 5, transport=MockTransport(...))))`):
  - `test_salute`, `test_charset` (content-type `application/json; charset=utf-8` su `/salute`, `/conversazioni`, un 404, un 409).
  - `test_prompt_inoltrato` e `test_prompt_agente_giu` (502).
  - `test_crea_elenca_leggi_elimina`: 201 con `titolo == "Nuova conversazione"` e date ISO; elenco ordinato; `GET` con `messaggi == []`; `DELETE` → 204 senza corpo, poi `GET` → 404.
  - `test_id_non_valido_o_inesistente` (`abc`, `999`; `GET`, `DELETE`, `POST …/messaggi`) → 404 `conversazione <id> inesistente.`
  - `test_messaggio_con_domanda`: l'agente riceve `cronologia == []` e la domanda; risposta 200 `{"risposta", "messaggi": [{ruolo "utente"}, {ruolo "assistente"}]}`; un secondo messaggio manda all'agente la cronologia restituita dal primo; `GET` mostra 4 messaggi; titolo = prima domanda.
  - `test_messaggio_con_prompt`: `{"prompt": {"nome": "scheda_articolo", "argomenti": {"codice": "MIS-001"}}}` → l'agente riceve `prompt`; messaggio utente `/scheda_articolo MIS-001`; senza argomenti → `/nome`.
  - `test_400_propri` (parametrizzato: corpo `[]`, `"x"`, non JSON; `{}`; entrambi i campi; `domanda: 5`; `prompt: "x"`, `{"nome": 1, "argomenti": {}}`, `{"nome": "a"}`) → 400 coi testi esatti; agente non chiamato.
  - `test_errori_agente_inoltrati` (400, 422) e `test_errori_agente_502` (500, rete): stesso codice/messaggio o 502; conversazione invariata (nessun messaggio, cronologia invariata).
  - `test_timeout_agente_non_salva_e_libera`: trasporto che solleva `httpx.ReadTimeout` → 502; nessun messaggio; un messaggio successivo riesce.
  - `test_turno_in_corso_409`: agente finto bloccato su un `threading.Event`; primo `POST` in un thread; un secondo sulla stessa conversazione → 409 `turno in corso per la conversazione <id>.`; uno su un'altra conversazione non riceve 409 (verificare con un secondo trasporto non bloccante o sbloccando dopo l'avvio); sbloccato il primo, un terzo riesce.
  - `test_eliminata_durante_il_turno`: agente bloccato, `DELETE` → 204, sblocco → il `POST` dà 404.
  - `test_errore_database`: `DepositoMemoria(errore=ErroreDatabase("giù"))` → 500 `errore del database: giù`.
- [ ] **Step 2:** `pytest tests/test_backend_app.py -q` → FAIL.
- [ ] **Step 3: implementare** `app.py`: `_RispostaJSON` come nello step 6 (classe propria, non importata); un `set[int]` di conversazioni occupate con `threading.Lock`, controllato dopo la verifica d'esistenza e rilasciato in `finally`; ordine: id → esistenza (404) → corpo (400) → occupata (409) → `cronologia` → agente → `registra_turno`. Log come nei Global Constraints.
- [ ] **Step 4:** test → PASS; `python -m pytest -q` verde.

### Task 4: avvio, `--backend` e servizio Compose `backend`

**Files:**
- Create: `src/backend/__main__.py`, `tests/test_backend_avvio.py`
- Modify: `avvia.py`, `src/assistente/cli.py` (testo d'uso), `tests/test_cli.py` (asserzione del testo d'uso), `compose.yaml`

**Interfaces:**
- Consumes: `carica_config`, `ConfigBackend` (Task 1), `DepositoPostgres`, `ErroreDatabase` (Task 1), `ClientAgente` (Task 2), `crea_app` (Task 3).
- Produces: `servi(config: ConfigBackend) -> None` (`DepositoPostgres(config.database_url).prepara()`, log di ascolto, `uvicorn.run(crea_app(...), host=config.host, port=config.porta, log_level=getattr(logging, config.log_level, logging.INFO))`); `main(argv: list[str] | None = None) -> int`. `deposito`, `uvicorn` e `DepositoPostgres` importati a livello di modulo per il `monkeypatch`.

- [ ] **Step 1: test** (`tests/test_backend_avvio.py`, `monkeypatch` di `backend.__main__.DepositoPostgres` e `backend.__main__.uvicorn.run`):
  - `test_servi_prepara_e_avvia`: `prepara` chiamato prima di `run`; `run` riceve `host`, `port`, `log_level` (`logging.DEBUG` per `"DEBUG"`, `logging.INFO` per un nome inesistente); l'app risponde a `/salute`; nessuna richiesta all'agente.
  - `test_main_database_non_raggiungibile`: `prepara` solleva `ErroreDatabase("rifiutata")` → `main([]) == 1`, stderr `Errore: database non raggiungibile: rifiutata`.
  - `test_main_configurazione_non_valida`: env senza `DATABASE_URL` (patch di `carica_config` o dell'ambiente) → 1, stderr comincia con `Errore: `.
  - `test_main_argomenti` → `main(["x"]) == 2`, stderr `Uso: python avvia.py [--http | --backend]`.
  - In `tests/test_cli.py` l'asserzione esistente sul testo d'uso diventa `Uso: python avvia.py [--http | --backend]`.
- [ ] **Step 2:** `pytest tests/test_backend_avvio.py tests/test_cli.py -q` → FAIL.
- [ ] **Step 3: implementare** `__main__.py` (`basicConfig` come `assistente.cli`; `if __name__ == "__main__": raise SystemExit(main(sys.argv[1:]))`); in `avvia.py`, dopo l'inserimento di `src` nel percorso, `sys.argv[1:] == ["--backend"]` → `from backend.__main__ import main as main_backend` e `raise SystemExit(main_backend([]))`, con lo stesso messaggio di dipendenza mancante; in `cli.py` il nuovo testo d'uso.
- [ ] **Step 4: `compose.yaml`, servizio `backend`:** `build: .`, `command: ["python", "-m", "backend"]`, `env_file: .env`, `environment`: `DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}`, `AGENTE_URL: http://agente:8000`, `BACKEND_HOST: 0.0.0.0`; `ports: ["127.0.0.1:8001:8001"]`; `depends_on: {postgres: {condition: service_healthy}, agente: {condition: service_started}}`. Verifica: `docker compose config --quiet`.
- [ ] **Step 5:** test → PASS; `python -m pytest -q` verde; `.venv/Scripts/python.exe avvia.py --boh` → uscita 2 col nuovo testo.

### Task 5: prova reale, prove manuali, documentazione, revisione e commit

**Files:**
- Create: `tests/reale/test_backend_reale.py`
- Modify: `README.md`, `CLAUDE.md`, `docs/superpowers/2026-11-02-handoff.md`

- [ ] **Step 1: prova reale** (`pytestmark = [pytest.mark.reale, pytest.mark.postgres]`; schema temporaneo come nel Task 1; agente dello step 6 costruito in-process con `assistente.avvio.apri_assistente` + `assistente.servizio.crea_app` dentro un `TestClient`, e un `ClientAgente` del back-end il cui `transport` è quello del `TestClient` — se non praticabile, il servizio avviato con `python avvia.py --http` e il test che si salta senza): `test_backend_due_messaggi`: conversazione nuova, «Annota che il multimetro MIS-001 ha la batteria scarica», poi «Quali note ci sono?» → entrambi 200; la seconda risposta contiene `batteria`; `GET` mostra 4 messaggi; titolo = prima domanda. Stampare i tempi (`-s`).
- [ ] **Step 2:** `docker compose up -d postgres`; `pytest -m postgres -v` (Task 1) e `pytest -m "reale and postgres" -v -s -k backend` con LM Studio → passate; annotare comandi ed esiti.
- [ ] **Step 3: prove manuali PowerShell:** `python avvia.py --http` e `python avvia.py --backend` in due finestre; `Invoke-RestMethod` su `/salute`, `POST /conversazioni`, due messaggi concatenati (uno con `prompt` `scheda_articolo` `MIS-001`), `GET /conversazioni`, `GET /conversazioni/<id>` con accenti corretti, un 404, `DELETE`; agente spento → 502.
- [ ] **Step 4: Docker:** `docker compose build`, `docker compose up -d postgres agente backend`, stesse chiamate sulla porta 8001, `docker compose logs backend`, riavvio di `backend` con i dati conservati (volume), `docker compose stop`.
- [ ] **Step 5: documentazione:** README (variabili, `.env` con `POSTGRES_*`/`DATABASE_URL`, avvio `--backend`, API con esempi PowerShell **verificati**, Compose, test `postgres`, verifiche reali, diagnosi: database non raggiungibile, 502, 409, password diversa fra `DATABASE_URL` e `POSTGRES_PASSWORD`); `CLAUDE.md` (struttura con `src/backend/`, comandi `--backend` e `pytest -m postgres`, obiettivo); handoff (step 7 fatto, evidenze, prossimo step 8).
- [ ] **Step 6:** `python -m pytest` verde; revisione indipendente dell'intero step; correzioni.
- [ ] **Step 7: commit unico:** `git status`, `git diff`, staging selettivo dei file dello step (sorgenti, test, `requirements.txt`, `pytest.ini`, `compose.yaml`, `.env.example`, `avvia.py`, README, `CLAUDE.md`, spec, piano, handoff), poi `git commit -m "feat(backend): conversazioni in PostgreSQL attorno all'agente HTTP"` con la riga `Co-Authored-By`.
