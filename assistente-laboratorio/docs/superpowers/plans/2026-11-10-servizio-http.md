# Agente come servizio HTTP: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** lo stesso agente della CLI è raggiungibile via HTTP (`GET /salute`, `GET /prompt`, `POST /turno`), senza stato, con la cronologia completa e opaca portata dal chiamante; si avvia con `python avvia.py --http` e con il servizio Compose `agente`.

**Architecture:** la costruzione di archivio e grafo esce da `cli.main` e va in `avvio.apri_assistente(config)`, usato da CLI e servizio; `servizio.crea_app(grafo, prompt)` è un'app Starlette con gestori sincroni e un lock per i turni, che riusa `cli.esegui_turno`; `servizio.servi(config)` apre l'assistente e avvia uvicorn.

**Tech Stack:** Python 3.14, `starlette==1.10.0`, `uvicorn==0.54.0`, `httpx==0.28.1` (TestClient), `langchain_core.messages.messages_to_dict` / `messages_from_dict`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-servizio-http-design.md`

## Global Constraints
- Comandi dalla cartella `assistente-laboratorio/` con `.venv\Scripts\python` (da Bash: `.venv/Scripts/python.exe`).
- Nessuna dipendenza nuova; `requirements*.txt` invariati. Grafo, router, revisore, riassunto, strumenti, `mcp_client` e server «archivio» invariati.
- Variabili: `HTTP_HOST` (default `127.0.0.1`, spazi tolti, vuoto → default), `HTTP_PORTA` (default `8000`, intero 1–65535). Errore: `HTTP_PORTA deve essere un intero fra 1 e 65535, trovato '<grezzo>'.` (con `!r` come le altre variabili).
- Errori HTTP con corpo `{"errore": "<messaggio>"}`; testi esatti:
  - `corpo della richiesta non valido: atteso un oggetto JSON.` (400)
  - `indicare esattamente uno fra 'domanda' e 'prompt'.` (400)
  - `'domanda' deve essere un testo non vuoto.` (400)
  - `'cronologia' non valida: <dettaglio>` (400)
  - `'prompt' non valido: atteso un oggetto con 'nome' e 'argomenti'.` (400)
  - `prompt sconosciuto '<nome>'.` (400)
  - `<nome> richiede: <arg1>, <arg2>.` (400, argomenti mancanti o vuoti)
  - `argomenti non previsti per <nome>: <a>, <b>.` (400)
  - `gli argomenti di <nome> devono essere testi.` (400)
  - messaggio di `ErroreArchivio` così com'è (422)
  - `turno fallito: <causa>` (500)
- Risposta vuota → `MESSAGGIO_RISPOSTA_VUOTA` di `cli.py`; turno interrotto → cronologia ricevuta invariata (`esegui_turno`).
- Log: INFO `assistente.servizio` `turno: %d messaggi in ingresso, %.1f s`; INFO `prompt: %s %s` (nome, dict argomenti); WARNING `turno fallito: %s`; INFO `servizio in ascolto su http://%s:%d`.
- Uso della riga di comando: `Uso: python avvia.py [--http]` su stderr, uscita 2.
- Un solo commit a fine step (Task 4), nessun commit intermedio; ogni task termina con `python -m pytest` verde.
- Staging selettivo: mai `lezione_3/`, file fuori da `assistente-laboratorio/`, `.env`, `dati/`.
- Nei test, funzioni d'appoggio che cominciano con `test` vengono raccolte da pytest: usare altri nomi.
- Heredoc dal tool Bash: le sequenze `\n` vengono alterate; per sorgenti con escape usare Write/Edit.

## Review Focus
- `domanda` di soli spazi o solo BOM (`"﻿  "`): 400 `'domanda' deve essere un testo non vuoto.`, grafo non chiamato — Task 2, `test_domanda_vuota` (parametrizzato `""`, `"   "`, `"﻿ "`, `5`).
- `cronologia` con elementi non dizionario (`["ciao"]`), con `type` sconosciuto, o `null`: 400 `'cronologia' non valida: …`, mai 500 — Task 2, `test_cronologia_non_valida` (parametrizzato `None`, `"x"`, `["ciao"]`, `[{"type": "boh", "data": {}}]`, `[{"type": "human"}]`).
- Argomenti del prompt non testuali (`{"codice": 1}`) o di soli spazi: 400, `testo_prompt` non chiamato — Task 2, `test_prompt_argomenti_non_validi`.
- Domanda con lettere accentate (`"Che giorno sarà?"`): arriva al grafo intatta e torna intatta in `domanda` — Task 2, `test_turno_con_domanda` (usa quel testo).
- Turno fallito con 500 non lascia il lock occupato: la richiesta successiva riesce — Task 2, `test_turno_fallito_libera_il_lock`.

---

### Task 1: costruzione condivisa in `avvio.py`

Refactoring senza cambi di comportamento.

**Files:**
- Create: `src/assistente/avvio.py`
- Modify: `src/assistente/cli.py` (togliere da `main` la costruzione e `leggi_contesto`)
- Test: `tests/test_cli.py` (bersagli dei `monkeypatch`)

**Interfaces:**
- Produces: `apri_assistente(config: Config) -> ContextManager[tuple[grafo, ClientArchivio]]` (con `contextlib.contextmanager`) e `leggi_contesto(archivio) -> list[str]` in `assistente.avvio`. Dentro il `with`: `ClientArchivio(ambiente={"NOTE_DB": str(config.note_db), "FUSO_PREDEFINITO": config.fuso_predefinito})`, `leggi_contesto`, `verifica_modello`, `crea_strumenti`, `crea_llm`, `build_graph(...)` con gli stessi argomenti di oggi; yield `(grafo, archivio)`. Logger di `leggi_contesto`: `assistente.avvio` (stessi messaggi).

- [ ] **Step 1:** in `tests/test_cli.py` sostituire i bersagli `"assistente.cli.<nome>"` con `"assistente.avvio.<nome>"` per `ClientArchivio`, `verifica_modello`, `crea_llm`, `crea_router`, `crea_revisore`, `crea_riassuntore`, `build_graph`; spostare eventuali test di `leggi_contesto` sull'import da `assistente.avvio`. Le asserzioni non cambiano (se un test controlla il nome del logger `assistente.cli` per i messaggi del contesto, passarlo ad `assistente.avvio`).
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_cli.py -q` → FAIL (`assistente.avvio` non esiste).
- [ ] **Step 3:** creare `avvio.py`; `cli.main` diventa `with apri_assistente(config) as (grafo, archivio):` + benvenuto + `ciclo(..., prompt=archivio)`; gestione errori e codici d'uscita invariati.
- [ ] **Step 4:** `.venv\Scripts\python -m pytest` → tutto verde (692 passati come a fine step 5).

### Task 2: applicazione HTTP `crea_app`

**Files:**
- Create: `src/assistente/servizio.py`, `tests/test_servizio.py`

**Interfaces:**
- Consumes: `cli.esegui_turno(grafo, cronologia, domanda) -> EsitoTurno(testo, cronologia, interrotto)`, `cli.MESSAGGIO_RISPOSTA_VUOTA`, `mcp_client.ErroreArchivio`, `mcp_client.PromptArchivio(nome, descrizione, argomenti)`.
- Produces: `crea_app(grafo, prompt) -> starlette.applications.Starlette`; `prompt` ha `prompt_disponibili() -> list[PromptArchivio]` e `testo_prompt(nome: str, argomenti: dict[str, str]) -> str`.

Finti in `tests/test_servizio.py`:
- `GrafoFinto(risposta="ok", interrotto=False, errore=None, attesa=0.0)`: `invoke(stato)` registra `stato["messaggi"]` in `self.ricevuti`, dorme `attesa`, misura le esecuzioni contemporanee in `self.massimo_contemporanei` (contatore protetto da un `threading.Lock` proprio), solleva `errore` se dato (solo alla prima chiamata), altrimenti restituisce `{**stato, "messaggi": stato["messaggi"] + [AIMessage(risposta)], "interrotto": interrotto}`.
- `PromptFinto(prompt=[PromptArchivio("scheda_articolo", "Scheda", ["codice"])], errore=None)`: `testo_prompt` registra le chiamate e restituisce `f"Dettagli di {argomenti['codice']}"` o solleva `errore`.

- [ ] **Step 1: test** (client: `TestClient(crea_app(grafo, prompt))`, senza `with`):
  - `test_salute`: `GET /salute` → 200, `{"stato": "ok"}`.
  - `test_elenco_prompt`: → `{"prompt": [{"nome": "scheda_articolo", "argomenti": ["codice"], "descrizione": "Scheda"}]}`; `test_elenco_prompt_vuoto` → `{"prompt": []}`.
  - `test_turno_con_domanda`: `{"domanda": "Che giorno sarà?"}` → 200; `domanda == "Che giorno sarà?"`, `risposta == "ok"`, `interrotto is False`; `messages_from_dict(corpo["cronologia"])` è `[HumanMessage("Che giorno sarà?"), AIMessage("ok")]` (confronto su tipo e contenuto); `grafo.ricevuti[0] == [HumanMessage("Che giorno sarà?")]`.
  - `test_cronologia_andata_e_ritorno`: cronologia con `SystemMessage("Riassunto…")`, `HumanMessage`, `AIMessage("", tool_calls=[{"name": "elenca_note", "args": {}, "id": "c1"}])`, `ToolMessage("Nessuna nota.", tool_call_id="c1")`, `AIMessage("Nessuna nota.")` serializzata con `messages_to_dict` → i primi 5 messaggi ricevuti dal grafo sono uguali (`==`) agli originali.
  - `test_turno_interrotto`: grafo `interrotto=True`, cronologia di 2 messaggi → `interrotto is True` e `cronologia` uguale a quella inviata.
  - `test_risposta_vuota` (parametrizzato `""`, `"  "`) → `risposta == MESSAGGIO_RISPOSTA_VUOTA`.
  - `test_turno_con_prompt`: `{"prompt": {"nome": "scheda_articolo", "argomenti": {"codice": "MIS-001"}}}` → `domanda == "Dettagli di MIS-001"`, il grafo riceve quel testo, `testo_prompt` chiamato con `("scheda_articolo", {"codice": "MIS-001"})`.
  - `test_prompt_senza_argomenti`: prompt `PromptArchivio("aiuto", "Aiuto", [])`, corpo `{"prompt": {"nome": "aiuto"}}` → 200, `testo_prompt` chiamato con `{}`.
  - `test_corpo_non_valido` (parametrizzato: testo `"non json"`, JSON `[1]`, JSON `"x"`) → 400 e messaggio esatto; grafo non chiamato.
  - `test_domanda_e_prompt` (entrambi; nessuno dei due; `{}`) → 400 `indicare esattamente uno fra 'domanda' e 'prompt'.`
  - `test_domanda_vuota` (Review Focus) → 400.
  - `test_cronologia_non_valida` (Review Focus) → 400, `errore` comincia con `'cronologia' non valida:`.
  - `test_prompt_malformato` (`"prompt": "x"`, `{"argomenti": {}}`, `{"nome": "scheda_articolo", "argomenti": [1]}`) → 400 `'prompt' non valido: …`.
  - `test_prompt_sconosciuto` → 400 `prompt sconosciuto 'boh'.`; `test_prompt_argomenti_mancanti` (`{}` e `{"codice": " "}`) → `scheda_articolo richiede: codice.`; `test_prompt_argomenti_in_piu` (`{"codice": "A", "x": "1"}`) → `argomenti non previsti per scheda_articolo: x.`; `test_prompt_argomenti_non_validi` (Review Focus, `{"codice": 1}`) → `gli argomenti di scheda_articolo devono essere testi.`; in tutti `testo_prompt` e grafo non chiamati.
  - `test_errore_archivio_sul_prompt`: `PromptFinto(errore=ErroreArchivio("nessun articolo con codice 'XYZ'."))` → 422, `errore` uguale al messaggio, grafo non chiamato.
  - `test_turno_fallito_libera_il_lock` (Review Focus): grafo con `errore=RuntimeError("LM Studio spento")` → 500 `turno fallito: LM Studio spento`, WARNING in `caplog`; la richiesta successiva → 200.
  - `test_un_turno_alla_volta`: `GrafoFinto(attesa=0.3)`, due `POST /turno` da due `threading.Thread` → entrambi 200, `grafo.massimo_contemporanei == 1`.
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_servizio.py -q` → FAIL (modulo mancante).
- [ ] **Step 3:** implementare `crea_app` in `servizio.py`: tre `Route` con gestori `def` sincroni che restituiscono `JSONResponse`; lettura del corpo con `json.loads(await…)` non è possibile in un gestore sincrono, quindi `/turno` è `async def` che legge e valida il corpo, poi esegue prompt e turno con `await starlette.concurrency.run_in_threadpool(...)`; il lock è un `threading.Lock` creato in `crea_app` e preso dentro la funzione eseguita nel thread pool. Validazione del prompt prima di `testo_prompt` (contro `prompt_disponibili()`); `messages_from_dict` dentro `try` su `(KeyError, TypeError, ValueError, AttributeError)`, più controllo che `cronologia` sia una lista. Argomenti mancanti/in più elencati nell'ordine dichiarato / ordinati alfabeticamente.
- [ ] **Step 4:** `.venv\Scripts\python -m pytest` → tutto verde.

### Task 3: configurazione, `servi`, `--http` e Compose

**Files:**
- Modify: `src/assistente/config.py`, `src/assistente/servizio.py`, `src/assistente/cli.py`, `src/assistente/__main__.py`, `avvia.py`, `compose.yaml`, `.env.example`
- Test: `tests/test_config.py`, `tests/test_servizio.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `avvio.apri_assistente`, `servizio.crea_app`.
- Produces: `Config.http_host: str = "127.0.0.1"`, `Config.http_porta: int = 8000` (in coda ai campi esistenti); `servi(config: Config) -> None`; `cli.main(argv: list[str] | None = None) -> int` (`None` → `[]`).

- [ ] **Step 1: test**
  - `test_config.py`: `test_http_predefiniti` → `("127.0.0.1", 8000)`; `test_http_impostati` (`" 0.0.0.0 "`, `"9000"`) → `("0.0.0.0", 9000)`; `test_http_host_vuoto` → default; `test_http_porta_non_valida` (parametrizzato `"0"`, `"65536"`, `"abc"`, `"-1"`) → `ErroreConfigurazione` con `HTTP_PORTA deve essere un intero fra 1 e 65535`.
  - `test_servizio.py`: `test_servi_avvia_uvicorn`: `monkeypatch` di `assistente.servizio.apri_assistente` (context manager finto che restituisce `(GrafoFinto(), PromptFinto())` e registra l'uscita) e di `assistente.servizio.uvicorn.run` (registra `app`, `host`, `port`) → `host == config.http_host`, `port == config.http_porta`, `app` risponde a `/salute`, contesto chiuso dopo il ritorno.
  - `test_cli.py`: `test_main_http_chiama_servi` (`monkeypatch` di `assistente.cli.servi`) → `main(["--http"]) == 0`, `servi` chiamato con la `Config`; `test_main_argomento_sconosciuto` → `main(["--boh"]) == 2`, stderr contiene `Uso: python avvia.py [--http]`, `servi` non chiamato; `test_main_http_errore_di_avvio`: `servi` che solleva `ErroreModello("x")` → uscita 1, stderr `Errore: x`.
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_config.py tests/test_servizio.py tests/test_cli.py -q` → FAIL.
- [ ] **Step 3:** implementare: `config.py` legge e valida le due variabili; `servi` con `with apri_assistente(config) as (grafo, archivio)`, log INFO di ascolto, `uvicorn.run(crea_app(grafo, archivio), host=..., port=..., log_level=config.log_level.lower())`; `main(argv)` controlla gli argomenti **prima** di caricare la configurazione, poi `basicConfig` come oggi, poi CLI o `servi`, con la stessa gestione di `ErroreConfigurazione`/`ErroreModello`/`ErroreArchivio` (1) e `KeyboardInterrupt` (130); `__main__.py` e `avvia.py` → `main(sys.argv[1:])`.
- [ ] **Step 4:** `compose.yaml`: servizio `agente` come da specifica (build `.`, `command: ["python", "-m", "assistente", "--http"]`, `env_file: .env`, `environment` con `LMSTUDIO_BASE_URL: http://host.docker.internal:1234/v1`, `NOTE_DB: /app/dati/note.db`, `HTTP_HOST: 0.0.0.0`, `extra_hosts`, volume `./dati:/app/dati`, `ports: ["127.0.0.1:8000:8000"]`); `assistente` invariato. `.env.example`: righe commentate `# Indirizzo e porta del servizio HTTP (python avvia.py --http)`, `# HTTP_HOST=127.0.0.1`, `# HTTP_PORTA=8000`. Verifica: `docker compose config` senza errori.
- [ ] **Step 5:** `.venv\Scripts\python -m pytest` → tutto verde.

### Task 4: prova reale, prove manuali, documentazione e commit

**Files:**
- Create: `tests/reale/test_servizio_reale.py`
- Modify: `README.md`, `CLAUDE.md`, `docs/superpowers/2026-11-02-handoff.md`, spec (`Stato: approvata`)

- [ ] **Step 1: prova reale** (`pytestmark = pytest.mark.reale`): `config = dataclasses.replace(carica_config(), note_db=tmp_path / "note.db")`; `with apri_assistente(config) as (grafo, archivio): client = TestClient(crea_app(grafo, archivio))`.
  - `test_servizio_turni_concatenati`: `POST /turno` «Annota che il multimetro MIS-001 ha la batteria scarica», poi con la `cronologia` restituita «Quali note ci sono?» → entrambi 200; fra i `tool_calls` degli `AIMessage` della seconda cronologia c'è `elenca_note`; la seconda `risposta` contiene `batteria` (senza maiuscole). Il database temporaneo sparisce con `tmp_path`.
  - `test_servizio_prompt_scheda_articolo`: `{"prompt": {"nome": "scheda_articolo", "argomenti": {"codice": "MIS-001"}}}` → 200, `dettaglio_articolo` con `MIS-001` fra le chiamate.
  - Stampare le chiamate (`-s`) come le altre prove reali.
- [ ] **Step 2:** `.venv\Scripts\python -m pytest -m reale -v -s -k servizio` con LM Studio → 2 passate (se fallisce: fermarsi, diagnosticare con il log, riportare). Poi l'intera `CITTA_PATRONO=Pordenone ... -m reale -v -s` per il resoconto.
- [ ] **Step 3: prove manuali PowerShell** (annotare comandi ed esiti): `python avvia.py --http`; in un'altra finestra `Invoke-RestMethod http://127.0.0.1:8000/salute`, `Invoke-RestMethod http://127.0.0.1:8000/prompt`, due `/turno` concatenati (`$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/turno -ContentType 'application/json; charset=utf-8' -Body (@{domanda='Che ore sono a Tokyo?'} | ConvertTo-Json)`; il secondo con `cronologia=$r.cronologia` e `ConvertTo-Json -Depth 20`); un errore 400; Ctrl-C → uscita 0. CLI: `python avvia.py` con una domanda, uscita 0.
- [ ] **Step 4: Docker:** `docker compose build`, `docker compose up -d agente`, stesse chiamate da PowerShell, `docker compose logs agente`, `docker compose stop agente` (uscita 0 nei log).
- [ ] **Step 5: documentazione:** README (variabili `HTTP_HOST`/`HTTP_PORTA`, avvio `--http`, endpoint ed esempi PowerShell verificati, Compose `agente`, diagnosi: porta occupata, 422/500); `CLAUDE.md` (struttura con `avvio`, `servizio`; comando `python avvia.py --http`; obiettivo: servizio HTTP senza stato); handoff (step 6 fatto, evidenze, prossimo step 7); spec `Stato: approvata`.
- [ ] **Step 6:** `.venv\Scripts\python -m pytest` → verde; revisione indipendente dell'intero step; correzioni.
- [ ] **Step 7: commit unico:** `git status`, `git diff`, staging selettivo dei file dello step (sorgenti, test, `compose.yaml`, `.env.example`, `avvia.py`, README, `CLAUDE.md`, spec, piano, handoff), poi
  `git commit -m "feat(servizio): agente come servizio HTTP senza stato"` con la riga `Co-Authored-By`.
