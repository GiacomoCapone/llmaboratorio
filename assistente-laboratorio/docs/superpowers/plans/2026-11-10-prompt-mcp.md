# Prompt MCP «scheda_articolo»: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** il server «archivio» offre il prompt `scheda_articolo(codice)`; la CLI lo elenca con `/prompt` e lo richiama con `/scheda_articolo MIS-001`, mandando il testo generato nel turno normale.

**Architecture:** prompt registrato in `crea_server` (codice normalizzato, errore come `MCPError`); il client legge `list_prompts` all'avvio insieme agli strumenti e offre `prompt_disponibili()` e `testo_prompt()`; `ciclo` riconosce le righe `/...` quando riceve un oggetto `prompt` e trasforma il prompt in una domanda del turno.

**Tech Stack:** Python 3.14, `mcp==2.3.0` (`MCPServer.prompt`, `ClientSession.list_prompts` / `get_prompt`, `mcp.shared.exceptions.MCPError`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-prompt-mcp-design.md`

## Global Constraints
- Comandi dalla cartella `assistente-laboratorio/` con `.venv\Scripts\python` (da Bash: `.venv/Scripts/python.exe`).
- Nessuna dipendenza nuova; grafo, router, revisore, riassunto, strumenti e resource invariati.
- Testi esatti: `DESCRIZIONE_SCHEDA = "Scheda di un articolo dell'inventario con le sue note."`; `TESTO_SCHEDA = "Dammi i dettagli dell'articolo {codice} e le note che lo riguardano."`; errore del server `nessun articolo con codice '<codice ricevuto senza spazi esterni>'.` con `MCPError(-32602, ...)`.
- Errori del client (`ErroreArchivio`): `archivio non disponibile.`; `l'archivio non ha risposto entro <t:g> secondi.`; messaggio del server; `il prompt <nome> non ha prodotto una domanda.`
- Testi della CLI: `Errore: prompt sconosciuto '/<nome>'. Scrivere /prompt per l'elenco.`; `Errore: /<nome> richiede: <arg1> <arg2>.`; `Errore: /<nome> non ha argomenti.`; `Nessun prompt disponibile.`; riga d'elenco `/<nome> <arg1> — <descrizione>`; eco `(prompt) <testo>`; benvenuto `Assistente del laboratorio. Scrivere 'esci' per terminare, '/prompt' per i prompt dell'archivio.`; log INFO (`assistente.cli`) `prompt: /%s %s` con il dict degli argomenti.
- Un solo commit a fine step (Task 4), nessun commit intermedio; ogni task termina con `python -m pytest` verde.
- Staging selettivo: mai `lezione_3/`, file fuori da `assistente-laboratorio/`, `.env`.
- Nei test, funzioni d'appoggio che cominciano con `test` vengono raccolte da pytest: usare altri nomi.
- Heredoc dal tool Bash: le sequenze `\n` vengono alterate; per sorgenti con escape usare Write/Edit.

## Review Focus
- `/scheda_articolo` seguito solo da spazi: argomento mancante, nessuna chiamata al server — Task 3, `test_prompt_argomento_mancante` (parametrizzato con `"/scheda_articolo"` e `"/scheda_articolo   "`).
- Nome del prompt in maiuscolo (`/SCHEDA_ARTICOLO MIS-001`): sconosciuto (i nomi MCP distinguono le maiuscole), messaggio con l'elenco — Task 3, `test_prompt_sconosciuto`.
- Una riga `/` da sola: trattata come prompt sconosciuto `'/'`, nessun turno — Task 3, `test_prompt_sconosciuto` (parametro).
- Ctrl-C durante il turno avviato da un prompt: turno annullato, cronologia invariata, come per una domanda scritta — Task 3, `test_prompt_ctrl_c_annulla_il_turno`.
- Archivio che muore a metà sessione e poi `/scheda_articolo`: `Errore: archivio non disponibile.` o simile, nessun turno, sessione viva — Task 2, `test_testo_prompt_server_morto`.

---

### Task 1: prompt `scheda_articolo` nel server

**Files:** Modify `src/archivio/server.py`; Test `tests/test_archivio_server.py`

**Interfaces:**
- Produces: in `archivio.server` le costanti `DESCRIZIONE_SCHEDA`, `TESTO_SCHEDA`; prompt `scheda_articolo` registrato in `crea_server`.

- [ ] **Step 1: test che falliscono** in `tests/test_archivio_server.py` (in-process, con `server_con` e un inventario di prova che contiene `MIS-001`; `asyncio.run(server.list_prompts())`, `asyncio.run(server.get_prompt(nome, argomenti))` che restituisce un risultato con `.messages[0].role` e `.messages[0].content.text`):
  - `test_prompt_elencato`: un solo prompt, `name == "scheda_articolo"`, `description == DESCRIZIONE_SCHEDA`, argomenti `[("codice", True)]` (nome, `required`).
  - `test_prompt_testo` parametrizzato `"mis-001"`, `" MIS-001 "` → un messaggio, `role == "user"`, testo `"Dammi i dettagli dell'articolo MIS-001 e le note che lo riguardano."`.
  - `test_prompt_codice_sconosciuto` parametrizzato `("XYZ", "'XYZ'")`, `(" xyz ", "'xyz'")`, `("", "''")` → `pytest.raises(MCPError)` con `"nessun articolo con codice " + atteso + "."` nel messaggio.
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_archivio_server.py -k prompt -v` → FAIL (`ImportError: DESCRIZIONE_SCHEDA`).
- [ ] **Step 3:** costanti e prompt in `crea_server` come da specifica (`@server.prompt(name="scheda_articolo", description=DESCRIZIONE_SCHEDA)`, funzione `scheda_articolo(codice: str) -> str`); docstring del modulo aggiornata (strumenti, resource e prompt).
- [ ] **Step 4:** `.venv\Scripts\python -m pytest` → verde.

### Task 2: prompt nel client

**Files:** Modify `src/assistente/mcp_client.py`; Test `tests/test_mcp_client.py`

**Interfaces:**
- Consumes: prompt del Task 1 (server vero via stdio).
- Produces: `PromptArchivio(nome: str, descrizione: str, argomenti: list[str])` (dataclass congelata); `ClientArchivio.prompt_disponibili() -> list[PromptArchivio]`; `ClientArchivio.testo_prompt(nome: str, argomenti: dict[str, str]) -> str` (solleva `ErroreArchivio`).

- [ ] **Step 1: test che falliscono** (fixture `client` di modulo esistente; per i casi distruttivi un `ClientArchivio` proprio):
  - `test_prompt_disponibili(client)`: `client.prompt_disponibili() == [PromptArchivio("scheda_articolo", "Scheda di un articolo dell'inventario con le sue note.", ["codice"])]`.
  - `test_testo_prompt(client)`: `client.testo_prompt("scheda_articolo", {"codice": "mis-001"}) == "Dammi i dettagli dell'articolo MIS-001 e le note che lo riguardano."`.
  - `test_testo_prompt_codice_sconosciuto(client)`: `pytest.raises(ErroreArchivio, match="nessun articolo con codice 'XYZ'")`; subito dopo `testo_prompt` con `MIS-001` riesce.
  - `test_testo_prompt_sconosciuto(client)`: nome `"altro"` → `ErroreArchivio`.
  - `test_testo_prompt_client_chiuso(tmp_path)`: dopo il `with` → `ErroreArchivio, match="archivio non disponibile"`.
  - `test_testo_prompt_server_morto(tmp_path)`: con `SERVER_CHE_MUORE`, due `cerca.esegui` poi `testo_prompt` → `ErroreArchivio` entro 5 s.
  - `test_testo_prompt_senza_domanda(monkeypatch, client)` parametrizzato su risultati finti di `client._sessione.get_prompt`: `GetPromptResult(messages=[])` e un solo `PromptMessage(role="assistant", content=TextContent(type="text", text="x"))` → `ErroreArchivio, match="non ha prodotto una domanda"`.
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_mcp_client.py -k prompt -v` → FAIL (`ImportError: PromptArchivio`).
- [ ] **Step 3:** in `_vivi`, dentro lo stesso `fail_after`, `prompts = (await sessione.list_prompts()).prompts` e `_pronto.set_result((strumenti, prompts))`; `__enter__` separa i due. `prompt_disponibili` costruisce i `PromptArchivio` (argomenti `[a.name for a in p.arguments or []]`). `testo_prompt`: estrarre da `leggi_risorsa` un aiuto privato `_attendi(coroutine, descrizione_errore) -> risultato` (chiuso → `archivio non disponibile.`; timeout con `cancel()`; coroutine mai inviata → `close()`; altre eccezioni → `ErroreArchivio`), usato da entrambi; per `testo_prompt` il messaggio d'errore del server è `str(errore)` senza prefisso, per `leggi_risorsa` resta `lettura di <uri> fallita: <errore>`. Testo = primo messaggio con `role == "user"` e contenuto con `text`.
- [ ] **Step 4:** `.venv\Scripts\python -m pytest tests/test_mcp_client.py -v` e poi `.venv\Scripts\python -m pytest` → verde (anche i test di `leggi_risorsa` invariati).

### Task 3: comandi `/prompt` e `/<nome>` nella CLI

**Files:** Modify `src/assistente/cli.py`; Test `tests/test_cli.py`

**Interfaces:**
- Consumes: `PromptArchivio`, `prompt_disponibili()`, `testo_prompt()` (Task 2).
- Produces: `ciclo(grafo, leggi, scrivi, prompt=None)`.

- [ ] **Step 1:** in `tests/test_cli.py`: `PromptFinti(prompt: list[PromptArchivio], testi: dict | None = None, errore: ErroreArchivio | None = None)` con `prompt_disponibili()` e `testo_prompt(nome, argomenti)` che registra le chiamate in `self.chiamate` e restituisce `f"testo di {nome} {argomenti}"` o solleva `errore`; `SCHEDA = PromptArchivio("scheda_articolo", "Scheda.", ["codice"])`, `NOTA = PromptArchivio("nota", "Nota.", ["codice", "testo"])`, `SALUTO = PromptArchivio("saluto", "Saluto.", [])`. Usare `GrafoCheRegistra` e `leggi_da` esistenti. **Test che falliscono:**
  - `test_prompt_elenco`: righe `["/prompt", "esci"]` → uscite contengono `"/scheda_articolo <codice> — Scheda."`, `"/nota <codice> <testo> — Nota."`, `"/saluto — Saluto."`; `grafo.stati == []`.
  - `test_prompt_elenco_vuoto`: nessun prompt → `"Nessun prompt disponibile."`.
  - `test_prompt_avvia_il_turno`: `["/scheda_articolo mis-001", "esci"]` → `chiamate == [("scheda_articolo", {"codice": "mis-001"})]`; uscite contengono `"(prompt) testo di scheda_articolo {'codice': 'mis-001'}"` e `"ok"`; il `HumanMessage` dell'unico stato ha quel testo; log INFO `prompt: /scheda_articolo {'codice': 'mis-001'}`.
  - `test_prompt_resta_in_cronologia`: dopo il prompt una seconda domanda `"ciao"` → il secondo stato contiene il `HumanMessage` del prompt.
  - `test_prompt_ultimo_argomento_prende_il_resto`: `"/nota MIS-001 display  rotto da ieri"` → `{"codice": "MIS-001", "testo": "display  rotto da ieri"}`.
  - `test_prompt_argomento_mancante` parametrizzato `"/scheda_articolo"`, `"/scheda_articolo   "`, `"/nota MIS-001"` → `"Errore: /scheda_articolo richiede: <codice>."` (o `"Errore: /nota richiede: <codice> <testo>."`); nessuna chiamata, nessun turno.
  - `test_prompt_senza_argomenti_con_testo`: `"/saluto x"` → `"Errore: /saluto non ha argomenti."`; `"/saluto"` → turno.
  - `test_prompt_sconosciuto` parametrizzato `"/xyz 1"`, `"/SCHEDA_ARTICOLO MIS-001"`, `"/"` → `"Errore: prompt sconosciuto '/xyz'. Scrivere /prompt per l'elenco."` (con il nome della riga: `'/SCHEDA_ARTICOLO'`, `'/'`); nessun turno.
  - `test_prompt_errore_del_server`: `errore=ErroreArchivio("nessun articolo con codice 'XYZ'.")` → `"Errore: nessun articolo con codice 'XYZ'."`; nessun turno; la sessione continua (domanda successiva → turno).
  - `test_prompt_ctrl_c_annulla_il_turno`: grafo che solleva `KeyboardInterrupt` → `"(turno annullato)"`, la domanda successiva parte con cronologia vuota.
  - `test_senza_prompt_la_barra_va_al_modello`: `ciclo(grafo, leggi_da(["/prompt", "esci"]), ...)` senza `prompt` → un turno con `"/prompt"`.
  - `test_main_passa_l_archivio_a_ciclo(monkeypatch, capsys)`: `ArchivioFinto` con `prompt_disponibili()` → `[]` e input `["/prompt", "esci"]` (sostituire `input`), grafo vero con finti come in `test_main_senza_contesto` → `main() == 0`; output contiene il benvenuto nuovo e `"Nessun prompt disponibile."`.
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_cli.py -v` → i nuovi FAIL.
- [ ] **Step 3:** in `cli.py` una funzione `espandi_prompt(riga: str, prompt) -> tuple[str | None, str | None]` (domanda da eseguire, messaggio da scrivere) con le regole della specifica (divisione `resto.split(maxsplit=len(argomenti) - 1)` dopo `strip()`; nome = testo fra `/` e il primo spazio); `ciclo` la usa per le righe che cominciano con `/` quando `prompt` non è `None`, scrive il messaggio e, se c'è una domanda, esegue il turno con la gestione esistente. `main` passa `prompt=archivio` e stampa il benvenuto nuovo. Aggiungere `prompt_disponibili()` all'`ArchivioFinto` di `test_cli.py` (predefinito `[]`).
- [ ] **Step 4:** `.venv\Scripts\python -m pytest` → verde.

### Task 4: prove reali, prove manuali, documentazione e commit

**Files:** Modify `tests/reale/test_lmstudio.py`, `README.md`, `CLAUDE.md`, `docs/superpowers/2026-11-02-handoff.md`, intestazione della specifica

- [ ] **Step 1:** in `tests/reale/test_lmstudio.py`, `test_il_modello_usa_la_scheda_articolo(caplog, tmp_path)` (**vincolante**): `note_db = tmp_path / "note.db"`, `prepara_nota(note_db, "Batteria scarica", "MIS-001")`; testo da un `ClientArchivio` (`testo_prompt("scheda_articolo", {"codice": "MIS-001"})`); `esegui_domanda(testo, caplog, note_db)` → una chiamata `dettaglio_articolo` con `codice` `MIS-001` (confronto senza maiuscole); se nessuna `elenca_note` con `codice` `MIS-001` → `pytest.xfail` (**osservazione**) con le chiamate stampate.
- [ ] **Step 2:** con LM Studio attivo: la prova nuova (`-k scheda_articolo`), poi l'intera suite `-m reale -v -s` con `CITTA_PATRONO=Pordenone`. ReadTimeout su `/v1/models` = LM Studio non raggiungibile: rilanciare le prove interessate e annotarlo. Un fallimento di comportamento del modello: fermarsi e riportare.
- [ ] **Step 3:** prove manuali con output mostrato: PowerShell `$env:LOG_LEVEL="INFO"; "/prompt","/scheda_articolo MIS-001","esci" | .venv\Scripts\python avvia.py`; Docker `docker compose build` e la stessa pipe su `docker compose run --rm -T -e LOG_LEVEL=INFO assistente` → elenco, riga `(prompt) ...`, risposta con i dati di MIS-001, uscita 0.
- [ ] **Step 4:** documentazione: README (sezione sui prompt: comandi, prompt `scheda_articolo`, errori, riga di log, esiti reali; benvenuto nuovo se citato); `CLAUDE.md` (prompt nell'obiettivo e in `src/archivio/`); specifica `Stato: approvata`; handoff con lo step 5 fatto ed evidenze.
- [ ] **Step 5:** `.venv\Scripts\python -m pytest` → verde; revisione indipendente dell'intero step; correzioni dei Critici e Importanti in TDD.
- [ ] **Step 6:** `git status`, `git diff`, staging selettivo (spec, piano, `src/`, `tests/`, README, CLAUDE.md, handoff), commit unico `feat(archivio): prompt MCP scheda_articolo richiamato dalla CLI` con il trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
