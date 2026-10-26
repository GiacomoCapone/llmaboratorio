# Assistente del laboratorio: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Applicazione da terminale che conversa con LM Studio tramite un grafo LangGraph esplicito, con strumento orologio, cronologia di sessione, limite di passaggi e avvio via Docker Compose.

**Architecture:** Ciclo `modello -> (strumenti -> modello)* -> fine`, con ramo `limite` quando il modello chiede ancora lo strumento oltre `MAX_PASSAGGI`. Moduli piccoli e sincroni: `config`, `modello`, `strumenti`, `grafo`, `cli`. L'LLM e l'orologio sono iniettati, così i test non richiedono il modello.

**Tech Stack:** Python (3.10 in locale, 3.12 in Docker), `langgraph`, `langchain-openai`, `httpx`, `tzdata`, `pytest`.

**Spec:** `assistente-laboratorio/docs/superpowers/specs/2026-10-26-assistente-laboratorio-design.md`

## Global Constraints

- Tutto il lavoro è dentro `assistente-laboratorio/`; i comandi del piano partono da quella cartella, i `git` dalla radice della repository. Non leggere né modificare `lezione_3/`.
- Codice sincrono, nessun framework o strumento oltre a quelli in spec (niente MCP, RAG, web, altri strumenti).
- Indirizzo del server e identificativo del modello solo da variabili d'ambiente: `LMSTUDIO_BASE_URL` (obbligatoria), `LMSTUDIO_MODEL` (obbligatoria, mai un valore inventato), `MAX_PASSAGGI` (predefinito 5, intero positivo), `LOG_LEVEL` (predefinito `INFO`).
- Chiave API: segnaposto fisso `lm-studio`. `.env.example` senza credenziali; `.env`, `.venv`, cache fuori da Git.
- Log con `logging` su stderr (`%(asctime)s %(levelname)s %(name)s %(message)s`); conversazione su stdout.
- Dipendenze con versioni fissate: `langgraph==1.2.17`, `langchain-openai==1.7.2` (risolvibili su Python 3.10), le altre fissate da `pip freeze` nel Task 1.
- Test automatici senza modello attivo; prove reali marcate `reale`, escluse di default.
- Commit: Conventional Commits in italiano, `git status` e controllo del diff prima di ogni commit, staging selettivo, trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Nessun push.
- Il README riporta solo comandi realmente eseguiti, con variante PowerShell.

## Review Focus

Ingressi che la spec non nomina e che un utente incontrerà; ognuno ha il test nel task indicato.

1. Fuso orario con percorso o forma strana (`""`, `"   "`, `"../etc/passwd"`, `"Mars/Base"`): errore leggibile restituito al modello, nessuna eccezione. (Task 2)
2. Il modello chiede uno strumento inesistente, o `ora_corrente` senza `fuso`: `ToolMessage` di errore e il grafo prosegue. (Task 4)
3. Più `tool_calls` nella stessa risposta: un `ToolMessage` per ciascuno, un solo passaggio contato. (Task 4)
4. Server spento o errore a metà sessione: messaggio all'utente, turno scartato, la sessione continua. (Task 5)
5. Input vuoto, `exit`/`esci`, Ctrl-C, fine dell'input (EOF): nessuna chiamata al modello e uscita pulita. (Task 5)

Anche `MAX_PASSAGGI` alto rispetto al limite di ricorsione di LangGraph è coperto, nel Task 4.

---

## Struttura dei file

| File | Responsabilità |
|---|---|
| `src/assistente/__init__.py`, `__main__.py` | pacchetto; `python -m assistente` chiama `cli.main()` |
| `src/assistente/config.py` | lettura e validazione delle variabili d'ambiente |
| `src/assistente/strumenti.py` | strumento orologio e sua definizione per il modello |
| `src/assistente/modello.py` | verifica via `GET /v1/models` e creazione del `ChatOpenAI` |
| `src/assistente/grafo.py` | stato, nodi, instradamento, `build_graph` |
| `src/assistente/cli.py` | turno di conversazione, ciclo di input, `main` |
| `tests/finti.py` | `LlmFinto`, usato dai test di grafo e CLI |
| `tests/test_*.py`, `tests/reale/` | test automatici e prove reali |
| `pytest.ini`, `requirements*.txt`, `.env.example`, `.gitignore`, `Dockerfile`, `compose.yaml`, `.dockerignore`, `README.md` | contorno |

---

### Task 1: Scaffolding, dipendenze e configurazione

**Files:**
- Create: `pytest.ini`, `.gitignore`, `.env.example`, `requirements.txt`, `requirements-dev.txt`, `src/assistente/__init__.py`, `src/assistente/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `class ErroreConfigurazione(Exception)`
  - `@dataclass(frozen=True) class Config: base_url: str; model: str; max_passaggi: int; log_level: str`
  - `carica_config(env: Mapping[str, str] | None = None) -> Config` (con `None` usa `os.environ`)

- [ ] **Step 1: Creare l'ambiente e fissare le versioni.** Da `assistente-laboratorio/`: `python -m venv .venv`, attivarlo, `pip install langgraph==1.2.17 langchain-openai==1.7.2 httpx tzdata`, salvare `pip freeze` in `requirements.txt`; poi `pip install pytest` e scrivere `requirements-dev.txt` con `-r requirements.txt` e `pytest==<versione installata>`.
  Verifica: `python -c "import langgraph, langchain_openai, httpx, tzdata"` termina senza errori.
- [ ] **Step 2: Scrivere `pytest.ini`** con `pythonpath = src`, `testpaths = tests`, marker `reale: prove con LM Studio attivo (escluse di default)` e `addopts = -m "not reale"`. Scrivere `.gitignore` (`.venv/`, `.env`, `__pycache__/`, `.pytest_cache/`) e `.env.example` con le quattro variabili e valori d'esempio (`LMSTUDIO_BASE_URL=http://localhost:1234/v1`, `LMSTUDIO_MODEL=` da riempire con un id restituito da `GET /v1/models`, `MAX_PASSAGGI=5`, `LOG_LEVEL=INFO`).
- [ ] **Step 3: Scrivere i test in `tests/test_config.py`** (nomi e asserzioni):
  - `test_valori_predefiniti`: env con solo `LMSTUDIO_BASE_URL` e `LMSTUDIO_MODEL` → `max_passaggi == 5`, `log_level == "INFO"`.
  - `test_valori_espliciti`: `MAX_PASSAGGI="3"`, `LOG_LEVEL="DEBUG"` → `3`, `"DEBUG"`.
  - `test_modello_mancante`: senza `LMSTUDIO_MODEL` → `ErroreConfigurazione` con messaggio che cita `LMSTUDIO_MODEL`; idem per `LMSTUDIO_BASE_URL`; idem per valore vuoto o di soli spazi.
  - `test_max_passaggi_non_valido`: parametrizzato su `"0"`, `"-1"`, `"abc"`, `""` → `ErroreConfigurazione` che cita `MAX_PASSAGGI`.
- [ ] **Step 4: Eseguire `python -m pytest tests/test_config.py -v`**; atteso: FAIL (`ModuleNotFoundError: assistente.config`).
- [ ] **Step 5: Implementare `config.py`** secondo le interfacce; `base_url` senza barra finale; messaggi in italiano che nominano la variabile.
- [ ] **Step 6: Eseguire `python -m pytest -v`**; atteso: PASS.
- [ ] **Step 7: Commit** (da radice repo): `git add assistente-laboratorio/{pytest.ini,.gitignore,.env.example,requirements.txt,requirements-dev.txt,src,tests}` e `git commit -m "feat(config): aggiunge scaffolding e lettura della configurazione"` con trailer. Controllare prima con `git status` che `.venv` non compaia.

---

### Task 2: Strumento orologio

**Files:**
- Create: `src/assistente/strumenti.py`, `tests/test_strumenti.py`

**Interfaces:**
- Produces:
  - `NOME_ORA_CORRENTE: str = "ora_corrente"`
  - `DEFINIZIONE_ORA_CORRENTE: dict` (formato funzione OpenAI: `{"type": "function", "function": {"name", "description", "parameters"}}`, un solo parametro stringa obbligatorio `fuso`, nome IANA come `Europe/Rome`)
  - `ora_corrente(fuso: str, adesso: Callable[[], datetime]) -> str`: data e ora ISO 8601 nel fuso richiesto; per fuso non valido restituisce un testo che inizia con `Errore:` e non solleva.

- [ ] **Step 1: Scrivere i test** con `adesso = lambda: datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)`:
  - `test_europe_rome`: risultato `"2026-01-15T13:00:00+01:00"`.
  - `test_utc`: `"2026-01-15T12:00:00+00:00"`.
  - `test_estate_ora_legale`: istante di luglio a `Europe/Rome` → offset `+02:00`.
  - `test_fuso_non_valido`: parametrizzato su `""`, `"   "`, `"../etc/passwd"`, `"Mars/Base"`, `"Europe/Roma"` → inizia con `"Errore:"` e contiene il fuso ricevuto.
  - `test_definizione_dichiara_fuso_obbligatorio`: `required == ["fuso"]` e nome `ora_corrente`.
- [ ] **Step 2: Eseguire** `python -m pytest tests/test_strumenti.py -v`; atteso: FAIL.
- [ ] **Step 3: Implementare** con `zoneinfo.ZoneInfo`; catturare `ZoneInfoNotFoundError`, `ValueError` e `OSError`; se l'istante è naive, trattarlo come UTC.
- [ ] **Step 4: Eseguire** gli stessi test; atteso: PASS. Poi `python -m pytest -v` (tutti verdi).
- [ ] **Step 5: Commit**: Un solo commit `feat(strumenti): aggiunge lo strumento orologio con fuso orario esplicito` con `src/assistente/strumenti.py` e `tests/test_strumenti.py`.

---

### Task 3: Collegamento al modello

**Files:**
- Create: `src/assistente/modello.py`, `tests/test_modello.py`

**Interfaces:**
- Consumes: `Config` da `config.py`.
- Produces:
  - `class ErroreModello(Exception)`
  - `elenca_modelli(base_url: str, client: httpx.Client | None = None) -> list[str]`: `GET {base_url}/models`, timeout 5 s, restituisce gli `id`; `ErroreModello` con l'indirizzo provato se non raggiungibile, se lo stato non è 200 o se il corpo non è JSON con `data`.
  - `verifica_modello(config: Config, elenca: Callable[[str], list[str]] = elenca_modelli) -> None`: `ErroreModello` se `config.model` non è nell'elenco; il messaggio elenca gli identificativi disponibili.
  - `crea_llm(config: Config) -> ChatOpenAI`: `base_url`, `model` da config, `api_key="lm-studio"`, `temperature=0`.

- [ ] **Step 1: Scrivere i test** usando `httpx.Client(transport=httpx.MockTransport(...))`:
  - `test_elenca_modelli`: risposta `{"data": [{"id": "a"}, {"id": "b"}]}` → `["a", "b"]`.
  - `test_server_non_raggiungibile`: il transport solleva `httpx.ConnectError` → `ErroreModello`, messaggio contiene l'URL.
  - `test_risposta_non_valida`: stato 500, e corpo non JSON → `ErroreModello`.
  - `test_verifica_modello_presente` / `test_verifica_modello_assente`: con `elenca` finto; nel secondo il messaggio contiene gli id disponibili.
  - `test_crea_llm_usa_configurazione`: `llm.model_name == config.model`, e base URL come in config.
- [ ] **Step 2: Eseguire** `python -m pytest tests/test_modello.py -v`; atteso: FAIL.
- [ ] **Step 3: Implementare** secondo le interfacce.
- [ ] **Step 4: Eseguire** `python -m pytest -v`; atteso: PASS.
- [ ] **Step 5: Commit** `feat(modello): verifica l'identificativo su /v1/models e crea il client` con i due file.

---

### Task 4: Grafo

**Files:**
- Create: `src/assistente/grafo.py`, `tests/finti.py`, `tests/test_grafo.py`

**Interfaces:**
- Consumes: `NOME_ORA_CORRENTE`, `DEFINIZIONE_ORA_CORRENTE`, `ora_corrente` da `strumenti.py`.
- Produces:
  - `MESSAGGIO_LIMITE: str` (testo italiano che cita il limite di passaggi)
  - `class Stato(TypedDict)`: `messaggi: Annotated[list[AnyMessage], add_messages]`, `passaggi: int`, `interrotto: bool`
  - `instrada_dopo_modello(stato: Stato, max_passaggi: int) -> Literal["strumenti", "limite", "fine"]`
  - `build_graph(llm, adesso: Callable[[], datetime], max_passaggi: int)` → grafo compilato; l'ingresso è `{"messaggi": [...], "passaggi": 0, "interrotto": False}`; internamente usa `llm.bind_tools([DEFINIZIONE_ORA_CORRENTE])` e imposta `recursion_limit = max_passaggi * 2 + 10`.
  - Logger `assistente.grafo`: per ogni tool call `INFO tool_call nome=<nome> args=<dict>` e `INFO tool_result nome=<nome> risultato=<testo>`; `WARNING` quando si entra in `limite`.
- In `tests/finti.py`: `class LlmFinto(risposte: list[AIMessage], ripeti_ultima: bool = False)` con `bind_tools(self, tools) -> LlmFinto` (restituisce `self`), `invoke(self, messaggi) -> AIMessage` (restituisce le risposte in ordine; con `ripeti_ultima` ripete l'ultima all'infinito, altrimenti `AssertionError` se esaurite) e `chiamate: list[list]` con i messaggi ricevuti a ogni invocazione. Funzione di supporto `richiesta_ora(fuso, id="c1") -> AIMessage` con un `tool_call` `ora_corrente`.

- [ ] **Step 1: Scrivere `tests/finti.py` e `tests/test_grafo.py`**, con orologio fisso come nel Task 2:
  - `test_risposta_diretta`: nessun tool call → ultimo messaggio è la risposta, `passaggi == 0`, `interrotto is False`.
  - `test_un_giro_con_strumento`: `richiesta_ora("Europe/Rome")` poi risposta finale → i messaggi sono Human, AI(tool_call), Tool, AI; il `ToolMessage` contiene `"2026-01-15T13:00:00+01:00"`, ha `tool_call_id == "c1"`; il secondo `invoke` del finto ha visto il `ToolMessage`; `passaggi == 1`.
  - `test_piu_giri_in_sequenza`: due richieste poi risposta → `passaggi == 2`.
  - `test_piu_tool_calls_in_una_risposta` (Review Focus 3): un `AIMessage` con due tool call (`c1`, `c2`) → due `ToolMessage` con gli id corretti e `passaggi == 1`.
  - `test_strumento_sconosciuto` e `test_argomento_fuso_mancante` (Review Focus 2): il `ToolMessage` inizia con `"Errore:"`, il grafo arriva alla risposta finale senza eccezioni.
  - `test_limite_raggiunto`: `max_passaggi=2`, `LlmFinto([richiesta_ora("UTC")], ripeti_ultima=True)` → `interrotto is True`, `passaggi == 2`, ultimo messaggio contiene `MESSAGGIO_LIMITE`, il `caplog` ha un `WARNING`.
  - `test_limite_alto_non_supera_la_ricorsione`: `max_passaggi=15` con finto che richiede sempre lo strumento → termina in `limite` senza `GraphRecursionError`.
  - `test_instradamento`: parametrizzato sui tre esiti di `instrada_dopo_modello` (nessun tool call; tool call con `passaggi < max`; tool call con `passaggi == max`).
  - `test_log_delle_chiamate_allo_strumento`: `caplog` contiene `tool_call nome=ora_corrente` con l'argomento `Europe/Rome` e `tool_result`.
- [ ] **Step 2: Eseguire** `python -m pytest tests/test_grafo.py -v`; atteso: FAIL.
- [ ] **Step 3: Implementare `grafo.py`.** Nodi: `modello` (`llm.invoke(stato["messaggi"])`), `strumenti` (esegue ogni tool call dell'ultimo `AIMessage`, restituisce i `ToolMessage` e `passaggi + 1`), `limite` (aggiunge un `AIMessage(MESSAGGIO_LIMITE)`, `interrotto=True`, log `WARNING`). Archi come in spec: `START -> modello`, condizionale su `instrada_dopo_modello`, `strumenti -> modello`, `limite -> END`. Nel nodo strumenti il dispatch avviene per nome; errori di nome o argomenti diventano testo `Errore: ...` nel `ToolMessage`.
- [ ] **Step 4: Eseguire** `python -m pytest -v`; atteso: PASS.
- [ ] **Step 5: Commit** `feat(grafo): aggiunge il grafo con strumenti, limite di passaggi e log` con `grafo.py`, `tests/finti.py`, `tests/test_grafo.py`.

---

### Task 5: Interfaccia da terminale e cronologia

**Files:**
- Create: `src/assistente/cli.py`, `src/assistente/__main__.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `build_graph` e `MESSAGGIO_LIMITE` da `grafo.py`; `carica_config`, `ErroreConfigurazione`; `verifica_modello`, `crea_llm`, `ErroreModello`.
- Produces:
  - `@dataclass class EsitoTurno: testo: str; cronologia: list[BaseMessage]; interrotto: bool`
  - `esegui_turno(grafo, cronologia: list[BaseMessage], domanda: str) -> EsitoTurno`: invoca il grafo con `cronologia + [HumanMessage(domanda)]`; `testo` è il contenuto dell'ultimo messaggio; se `interrotto` la nuova `cronologia` è quella ricevuta, invariata; altrimenti è l'elenco completo restituito dal grafo.
  - `ciclo(grafo, leggi: Callable[[], str], scrivi: Callable[[str], None]) -> None`: legge fino a `esci`, `exit`, `quit` (senza distinzione di maiuscole), `EOFError` o `KeyboardInterrupt`; ignora righe vuote; scrive su stdout la risposta; se il turno è interrotto lo dice all'utente; se `esegui_turno` solleva un'eccezione scrive `Errore: ...` e scarta il turno.
  - `main() -> int`: configura `logging` (stderr), carica la configurazione, verifica il modello, crea il grafo con `datetime.now(timezone.utc)` come orologio e avvia `ciclo` con `input("> ")` e `print`; restituisce 1 con messaggio su stderr per `ErroreConfigurazione` o `ErroreModello`, altrimenti 0.

- [ ] **Step 1: Scrivere `tests/test_cli.py`** con `LlmFinto` e grafo reale:
  - `test_la_seconda_domanda_vede_la_prima`: due domande, il secondo `invoke` del finto contiene il testo della prima domanda e della prima risposta.
  - `test_turno_interrotto_non_entra_in_cronologia`: finto che chiede sempre lo strumento con `max_passaggi=1`; dopo il turno la `cronologia` è invariata e `interrotto is True`; la domanda successiva non produce errori (nessun `tool_calls` orfano nella lista passata al finto).
  - `test_errore_del_modello_non_chiude_la_sessione` (Review Focus 4): finto la cui prima `invoke` solleva `RuntimeError("connessione")`; `ciclo` scrive una riga con `Errore:`, la domanda seguente riceve risposta, la cronologia non contiene il turno fallito.
  - `test_input_vuoto_e_uscita` (Review Focus 5): righe `""`, `"   "`, `"ESCI"` → il finto non viene mai invocato; idem con `EOFError` e con `KeyboardInterrupt` sollevati da `leggi`.
  - `test_main_configurazione_mancante`: env senza `LMSTUDIO_MODEL` (via `monkeypatch`) → `main()` restituisce 1 e scrive su stderr (`capsys`).
- [ ] **Step 2: Eseguire** `python -m pytest tests/test_cli.py -v`; atteso: FAIL.
- [ ] **Step 3: Implementare `cli.py` e `__main__.py`** (`if __name__ == "__main__": raise SystemExit(main())`). Formato log: `%(asctime)s %(levelname)s %(name)s %(message)s`, livello da `Config.log_level`.
- [ ] **Step 4: Eseguire** `python -m pytest -v`; atteso: tutti PASS.
- [ ] **Step 5: Commit** `feat(cli): aggiunge il ciclo da terminale con cronologia di sessione`.

---

### Task 6: Docker Compose e README

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `compose.yaml`, `README.md`

**Interfaces:**
- Consumes: `python -m assistente`, `requirements.txt`, `.env`.

- [ ] **Step 1: Scrivere `Dockerfile`**: base `python:3.12-slim`, `ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1`, copia di `requirements.txt` e `pip install --no-cache-dir -r requirements.txt` (include `tzdata`), copia di `src/`, `CMD ["python", "-m", "assistente"]`. `.dockerignore`: `.venv`, `.env`, `tests`, `docs`, `__pycache__`, `.git`.
- [ ] **Step 2: Scrivere `compose.yaml`**: servizio `assistente`, `build: .`, `stdin_open: true`, `tty: true`, `env_file: .env`, `environment: LMSTUDIO_BASE_URL: http://host.docker.internal:1234/v1` (sovrascrive il valore dell'`.env` locale), `extra_hosts: ["host.docker.internal:host-gateway"]`.
- [ ] **Step 3: Verificare la build**: `docker compose build`; atteso: immagine costruita senza errori. Se le versioni congelate su Python 3.10 non si installano su 3.12, correggere `requirements.txt` e ripetere.
- [ ] **Step 4: Verificare l'errore di configurazione nel container**: senza `LMSTUDIO_MODEL` nell'`.env`, `docker compose run --rm assistente`; atteso: messaggio che cita `LMSTUDIO_MODEL`, codice di uscita 1.
- [ ] **Step 5: Scrivere `README.md`** con: scopo, prerequisiti, configurazione (`Copy-Item .env.example .env` per PowerShell, `cp` per Bash; come ottenere l'id con `curl http://localhost:1234/v1/models` e `Invoke-RestMethod`), installazione locale (venv, `pip install -r requirements-dev.txt`), avvio locale, avvio con Compose, test (`python -m pytest`), diagnosi (server non raggiungibile, modello non trovato, container che non vede l'host, LM Studio in ascolto solo su loopback, tool calling non supportato dal modello). Includere solo comandi eseguiti nei Task 1-6 o nel Task 7.
- [ ] **Step 6: Commit** `feat(docker): aggiunge Dockerfile, Compose e README`. Controllare con `git status` che `.env` non sia in staging.

---

### Task 7: Prove reali e resoconto

**Files:**
- Create: `tests/reale/test_lmstudio.py`
- Modify: `README.md` (sezione «Verifiche reali»), `pytest.ini` se serve

**Interfaces:**
- Consumes: `carica_config`, `verifica_modello`, `crea_llm`, `build_graph`, logger `assistente.grafo`.

- [ ] **Step 1: Scrivere `tests/reale/test_lmstudio.py`** con `@pytest.mark.reale`: carica la configurazione dall'ambiente, esegue `verifica_modello`, costruisce il grafo con orologio reale e invia «Che ore sono a Tokyo? Usa lo strumento orologio.»; asserisce che `caplog` contenga `tool_call nome=ora_corrente`, che esista un `ToolMessage` non iniziante con `Errore:` e che l'ultima risposta non sia vuota. Il test non entra nell'esecuzione di default.
- [ ] **Step 2: Provare con LM Studio attivo**: da PowerShell impostare `LMSTUDIO_BASE_URL` e `LMSTUDIO_MODEL=google/gemma-4-e2b` (id restituito da `/v1/models`) e lanciare `python -m pytest -m reale -v`. Riportare l'esito reale: se il modello non emette tool call, registrarlo nel README come limite osservato, senza ritoccare il test per farlo passare.
- [ ] **Step 3: Prova manuale locale**: `python -m assistente`, domanda sull'ora a Tokyo, poi una seconda domanda che richiami la prima (cronologia); controllare su stderr le righe `tool_call` e `tool_result`.
- [ ] **Step 4: Prova in Docker**: `docker compose run --rm assistente` con la stessa domanda; verificare che il container raggiunga LM Studio sull'host e che i log compaiano. Se non raggiunge l'host, diagnosticare (LM Studio in ascolto solo su loopback, firewall) e documentare la soluzione verificata.
- [ ] **Step 5: Completare il README** con le sezioni «Verifiche reali» e gli esiti ottenuti.
- [ ] **Step 6: Eseguire la suite completa** `python -m pytest -v` e `git status`; atteso: tutto verde, working tree con solo file pertinenti.
- [ ] **Step 7: Commit** `test(reale): aggiunge le prove con LM Studio` e, a parte, `docs: documenta le verifiche reali`.
- [ ] **Step 8: Resoconto finale**: elencare che cosa è stato eseguito, con quale esito, e che cosa resta da provare. Proporre all'utente l'aggiornamento di `CLAUDE.md` (comando di test, struttura) senza modificarlo di iniziativa, perché si trova fuori da `assistente-laboratorio/`.

---

## Autoverifica

- **Copertura della spec**: configurazione e verifica del modello (Task 1, 3); strumento (2); grafo, limite, log, stato (4); cronologia, turno scartato, uscita (5); Docker, README (6); prove reali e criteri di successo (7).
- **Coerenza**: `instrada_dopo_modello` restituisce `"strumenti" | "limite" | "fine"`; `esegui_turno` usa `interrotto` definito nello `Stato`; `LlmFinto` è definito nel Task 4 e riusato nel 5.
