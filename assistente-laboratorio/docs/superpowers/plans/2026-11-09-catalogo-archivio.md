# Catalogo dell'inventario (server MCP «archivio»): piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** due strumenti MCP (`cerca_inventario`, `dettaglio_articolo`) su un CSV dell'inventario, serviti
da un server «archivio» via stdio e usati dall'assistente tramite il registro degli strumenti.

**Architecture:** pacchetto `src/archivio/` (logica pura in `inventario.py`, server `MCPServer` in
`server.py`, avvio in `__main__.py`); in `src/assistente/mcp_client.py` un `ClientArchivio` sincrono
che tiene la sessione MCP in un thread con il proprio event loop e trasforma gli strumenti del server in
`Strumento`; `crea_strumenti(..., esterni=...)` e la CLI li collegano. Il grafo non cambia.

**Tech Stack:** Python 3.14, `mcp==2.3.0` (server `MCPServer`, client `stdio_client` + `ClientSession`),
`csv`/`unicodedata` della libreria standard, pytest.

**Spec:** `docs/superpowers/specs/2026-11-09-catalogo-archivio-design.md` (leggerla per intero: messaggi,
formati e descrizioni sono fissati lì alla lettera e non vanno ricopiati con variazioni).

## Global Constraints
- Lavorare solo in `assistente-laboratorio/`, nel branch `feature`; nessun branch o worktree nuovo.
- Usare il Python del `.venv`: `.venv/Scripts/python.exe` (comandi sotto scritti per Git Bash dalla
  cartella `assistente-laboratorio/`).
- Non leggere né toccare `lezione_3/`; non mettere in commit `CLAUDE.md` con la modifica dell'utente
  (vedi Task 5) né `docs/superpowers/2026-11-02-handoff.md`.
- Commit in Conventional Commits in italiano; prima di ogni commit `git status`, controllo del diff,
  staging selettivo; messaggio che termina con
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Tutti i risultati e gli errori degli strumenti sono testi; gli errori iniziano con `Errore:`.
- Descrizioni degli strumenti e dei parametri: alla lettera dalla specifica.
- `archivio` non importa nulla da `assistente` e viceversa.
- Nessuna dipendenza oltre a `mcp==2.3.0` e alle sue transitive fissate (Task 2).
- Nomi in italiano come nel resto del codice.

## Review Focus
1. **Ctrl-C durante un turno** (Windows: il segnale arriva a tutto il gruppo della console): il server
   deve sopravvivere e il turno successivo deve poter usare l'archivio → `__main__` ignora `SIGINT`;
   test in Task 2 (`test_main_ignora_sigint`) più verifica manuale in Task 5.
2. **`null` per i parametri facoltativi** (gemma passa spesso `"categoria": null`): deve comportarsi come
   parametro assente, non dare un errore di validazione → parametri `str | None = None`; test in Task 2
   (`test_cerca_con_null`).
3. **Avvio da un'altra cartella** (`python avvia.py` lanciato da `C:\`): il sottoprocesso deve trovare
   `archivio` → `PYTHONPATH` assoluto; test in Task 2 (`test_avvio_da_altra_cartella`).
4. **CSV salvato da Excel** (BOM, fine riga CRLF, campi fra virgolette con `;` dentro): deve caricarsi
   → test in Task 1 (`test_csv_da_excel`).
5. **Caratteri non ASCII nel percorso stdio** (`Quantità`, `«»`, `—`, accenti nei dati): devono arrivare
   intatti al modello → test in Task 2 (`test_caratteri_non_ascii`).

---

### Task 1: logica dell'inventario e dati di esempio

**Files:**
- Create: `src/archivio/__init__.py` (solo docstring), `src/archivio/inventario.py`,
  `src/archivio/inventario.csv`
- Test: `tests/test_archivio_inventario.py`

**Interfaces:**
- Produces:
  - `class ErroreInventario(Exception)` — messaggio già nella forma
    `inventario non valido, riga N: <motivo>.` (senza `Errore: `).
  - `@dataclass(frozen=True) class Articolo: codice, nome, categoria: str; quantita: int;
    collocazione, descrizione: str`
  - `PERCORSO_INVENTARIO: Path` (il CSV del pacchetto).
  - `carica(percorso: Path) -> Inventario`
  - `class Inventario` con `articoli: tuple[Articolo, ...]`, `cerca(testo: str | None, categoria: str |
    None) -> str`, `dettaglio(codice: str | None) -> str`. `None` vale come stringa vuota.
  - `normalizza(testo: str) -> str` (NFD, rimozione dei combinanti, `casefold`).

- [ ] **Step 1: scrivere i test** in `tests/test_archivio_inventario.py`. Un helper
  `scrivi_csv(tmp_path, righe: list[str], *, bom=False, fine="\n") -> Path` scrive l'intestazione
  `codice;nome;categoria;quantita;collocazione;descrizione` più le righe. Test (nomi e asserzioni):
  - `test_carica_valido`: due righe → `len(articoli) == 2`, campi ripuliti dagli spazi, `quantita` int.
  - `test_csv_da_excel`: BOM, `fine="\r\n"`, una descrizione `"tensione; corrente"` fra virgolette →
    carica, descrizione `== "tensione; corrente"`.
  - `test_errori_di_validazione` (parametrizzato, `pytest.raises(ErroreInventario, match=...)`):
    intestazione sbagliata → `riga 1`; riga con 5 campi → `riga 2`; codice vuoto, nome vuoto,
    categoria vuota, collocazione vuota → `riga 2`; codice ripetuto con maiuscole diverse
    (`mis-001` dopo `MIS-001`) → `riga 3`; quantità `-1`, `due`, `4.0` → `riga 2`.
    Il testo inizia con `inventario non valido, riga `.
  - `test_descrizione_vuota_ammessa`.
  - `test_cerca_maiuscole_e_accenti`: articolo «Saldatore a stagno», collocazione «Bancone più
    vicino alla finestra» → `cerca("SALDATORE", None)` e `cerca("piu", None)` iniziano con
    `Trovato 1 articolo:`.
  - `test_cerca_singolare_plurale`: «Multimetro digitale» trovato da `multimetri`; «Cavo USB» da
    `cavi`; parola di 3 caratteri `usb` usata intera.
  - `test_cerca_parole_in_and`: `multimetro armadio` trova solo l'articolo che ha entrambe.
  - `test_cerca_formato`: risultato esatto per due articoli, confrontato come stringa intera:
    `"Trovati 2 articoli:\n- MIS-001 — Multimetro digitale — 4 pezzi — Armadio A, ripiano 2\n- MIS-002 — Oscilloscopio — 1 pezzo — Bancone 3"`
    (articoli scritti nel CSV in ordine inverso, per provare l'ordine per codice); `0 pezzi` per
    quantità 0.
  - `test_cerca_limite`: 12 articoli che corrispondono → 10 righe `- ` e ultima riga
    `(altri 2 risultati: restringere la ricerca)`, intestazione `Trovati 12 articoli:`.
  - `test_cerca_categoria`: `cerca(None, "Strumenti di Misura")` trova la categoria
    `strumenti di misura`; `cerca("multimetro", "attrezzi")` → nessun risultato.
  - `test_cerca_categoria_sconosciuta`: `== "Errore: categoria sconosciuta 'cucina'. Categorie: attrezzi, strumenti di misura."`
  - `test_cerca_nessun_risultato` (tre varianti della specifica, alla lettera, con i valori ripuliti).
  - `test_cerca_parametri_vuoti`: `cerca(None, None)`, `cerca("  ", "")` →
    `"Errore: indicare un testo da cercare o una categoria."`
  - `test_cerca_troppo_lungo`: 101 caratteri in `testo` o in `categoria` →
    `"Errore: testo troppo lungo (massimo 100 caratteri)."`; 100 caratteri accettati.
  - `test_dettaglio`: `dettaglio("  mis-001 ")` uguale alle sei righe della specifica;
    descrizione vuota → `Descrizione: (nessuna)`.
  - `test_dettaglio_errori`: vuoto o `None` → `"Errore: indicare il codice dell'articolo, per esempio MIS-001."`;
    sconosciuto → `"Errore: nessun articolo con codice 'XYZ-9'."`; oltre 100 caratteri → errore
    «troppo lungo».
  - `test_inventario_del_pacchetto`: `carica(PERCORSO_INVENTARIO)` ha almeno 20 articoli, 7 categorie
    (quelle della tabella della specifica), contiene `MIS-001` con `nome` che contiene «Multimetro» e
    quantità > 1, e almeno un articolo con quantità 0.

- [ ] **Step 2: eseguire i test e verificarne il fallimento**
  Run: `.venv/Scripts/python.exe -m pytest tests/test_archivio_inventario.py -q`
  Expected: errori di import (`archivio` non esiste).

- [ ] **Step 3: implementare `inventario.py` e scrivere `inventario.csv`**
  - Lettura con `open(percorso, encoding="utf-8-sig", newline="")` e `csv.reader(..., delimiter=";")`.
    Righe completamente vuote ignorate.
  - Ricerca come da specifica (radice: parole normalizzate di almeno 4 caratteri perdono l'ultimo
    carattere); la ricerca confronta con i quattro campi normalizzati, precalcolati al caricamento.
  - CSV: circa 25 articoli realistici in italiano nelle 7 categorie della specifica, codici
    `PREFISSO-NNN`; `MIS-001` «Multimetro digitale» con quantità 4 e collocazione «Armadio A,
    ripiano 2»; almeno un articolo con quantità 0. UTF-8 senza BOM, fine riga `\n`.

- [ ] **Step 4: eseguire i test**
  Run: `.venv/Scripts/python.exe -m pytest tests/test_archivio_inventario.py -q` → tutti passati;
  `.venv/Scripts/python.exe -m pytest -q` → nessuna regressione.

- [ ] **Step 5: commit**
  `git add src/archivio/__init__.py src/archivio/inventario.py src/archivio/inventario.csv tests/test_archivio_inventario.py`
  Messaggio: `feat(archivio): inventario del laboratorio con ricerca e dettaglio`

---

### Task 2: dipendenza `mcp`, server «archivio» e client sincrono

**Files:**
- Modify: `requirements.txt`
- Create: `src/archivio/server.py`, `src/archivio/__main__.py`, `src/assistente/mcp_client.py`
- Test: `tests/test_mcp_client.py`

**Interfaces:**
- Consumes: `carica`, `PERCORSO_INVENTARIO`, `Inventario.cerca`, `Inventario.dettaglio`,
  `ErroreInventario` (Task 1); `Strumento` da `assistente.strumenti`.
- Produces:
  - `archivio.server.crea_server(inventario: Inventario) -> MCPServer`
  - `archivio.__main__.main() -> int` (ignora `SIGINT`, carica, avvia `run("stdio")`; con
    `ErroreInventario` stampa `Errore: <messaggio>` su stderr e restituisce 1). Il modulo chiama
    `raise SystemExit(main())` sotto `if __name__ == "__main__":`.
  - `assistente.mcp_client.ErroreArchivio(Exception)`
  - `assistente.mcp_client.ClientArchivio(comando: list[str] | None = None, timeout: float = 10.0)`:
    context manager; `strumenti() -> list[Strumento]`.

- [ ] **Step 1: dipendenze**
  Aggiungere a `requirements.txt`, in ordine alfabetico senza distinzione di maiuscole come le righe
  esistenti: `attrs==26.1.0`, `cffi==2.1.1`, `click==8.5.1`, `cryptography==50.0.2`,
  `jsonschema==4.26.0`, `jsonschema-specifications==2025.9.1`, `mcp==2.3.0`, `mcp-types==2.3.0`,
  `opentelemetry-api==1.45.2`, `pycparser==3.12`, `PyJWT==2.15.1`, `python-multipart==0.0.33`,
  `pywin32==312; sys_platform == "win32"`, `referencing==0.37.0`, `rpds-py==2026.9.1`,
  `sse-starlette==3.7.0`, `starlette==1.10.0`, `uvicorn==0.54.0`.
  Run: `.venv/Scripts/python.exe -m pip install -r requirements-dev.txt` → nessun errore;
  `.venv/Scripts/python.exe -m pip check` → `No broken requirements found.`

- [ ] **Step 2: scrivere i test** in `tests/test_mcp_client.py` (server vero come sottoprocesso).
  Fixture di modulo `client` che apre un `ClientArchivio()` e lo chiude a fine modulo (un solo avvio,
  circa 1 s). Test:
  - `test_definizioni`: nomi `["cerca_inventario", "dettaglio_articolo"]`; ogni definizione ha
    `type == "function"` e `function` con `name`, `description`, `parameters`; descrizioni uguali alla
    lettera alla specifica (testo unito su una riga, con gli spazi della specifica); descrizioni dei
    parametri `testo`, `categoria`, `codice` alla lettera; `parameters["required"] == ["codice"]` per
    il dettaglio e nessun `required` per la ricerca.
  - `test_cerca_e_dettaglio`: `cerca_inventario({"testo": "multimetro"})` inizia con `Trovat` e
    contiene `MIS-001`; `dettaglio_articolo({"codice": "MIS-001"})` inizia con `Codice: MIS-001`.
  - `test_cerca_con_null`: `{"testo": "multimetro", "categoria": None}` inizia con `Trovat`.
  - `test_caratteri_non_ascii`: il dettaglio di `MIS-001` contiene `Quantità: ` e una ricerca senza
    risultati contiene `«` e `»`.
  - `test_argomento_di_tipo_sbagliato`: `dettaglio_articolo({"codice": 5})` e `({})` iniziano con
    `Errore:`.
  - `test_avvio_da_altra_cartella`: con `monkeypatch.chdir(tmp_path)` un nuovo `ClientArchivio()` si
    avvia ed elenca due strumenti.
  - `test_avvio_fallito_comando_inesistente`: `ClientArchivio(["comando-inesistente-xyz"])` →
    `pytest.raises(ErroreArchivio, match="archivio non avviato")`.
  - `test_avvio_fallito_con_messaggio`: comando `[sys.executable, "-c", "import sys; print('Errore: inventario non valido, riga 3: prova.', file=sys.stderr); sys.exit(1)"]`
    → `ErroreArchivio` il cui testo contiene `riga 3: prova`.
  - `test_chiusura`: con un client proprio (non la fixture), dopo l'uscita dal `with`
    `client._thread.is_alive() is False` e l'`esegui` di uno strumento ottenuto prima della chiusura
    restituisce `"Errore: archivio non disponibile."` (`stdio_client` non espone il PID: la
    terminazione del processo si verifica a mano nel Task 5).
  - `test_main_ignora_sigint`: `monkeypatch` di `archivio.__main__.crea_server` con un oggetto finto
    il cui `run` registra `signal.getsignal(signal.SIGINT)`; `main()` restituisce 0 e il valore
    registrato è `signal.SIG_IGN` (ripristinare il gestore originale a fine test).
  - `test_main_inventario_non_valido`: `monkeypatch` di `archivio.__main__.PERCORSO_INVENTARIO` verso un
    CSV non valido in `tmp_path` → `main() == 1`, stderr inizia con
    `Errore: inventario non valido, riga`.

- [ ] **Step 3: implementare server e client**
  - `server.py`: `MCPServer("archivio", log_level="WARNING")`; due funzioni decorate con
    `@server.tool(description=<descrizione della specifica>)`; parametri
    `Annotated[str | None, Field(description=...)] = None` per la ricerca e
    `Annotated[str, Field(description=...)]` per il codice; restituiscono `str` delegando
    all'`Inventario`.
  - `__main__.py`: `signal.signal(signal.SIGINT, signal.SIG_IGN)` prima di tutto; importa
    `PERCORSO_INVENTARIO` e `crea_server` a livello di modulo (per il monkeypatch dei test).
  - `mcp_client.py`, struttura verificata con un prototipo (vedi specifica, sezione Dipendenza):
    - `__enter__`: `loop = asyncio.new_event_loop()`, thread daemon con `loop.run_forever`;
      `errlog = tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace")`; in una coroutine
      `_apri()` un `AsyncExitStack` con `stdio_client(StdioServerParameters(command=comando[0],
      args=comando[1:], env={"PYTHONPATH": <src assoluta> + os.pathsep + PYTHONPATH esistente,
      "PYTHONIOENCODING": "utf-8"}), errlog=errlog)` e `ClientSession(lettura, scrittura)`;
      `initialize()`, `list_tools()`; in caso di eccezione `_apri` chiude lo stack prima di
      rilanciare. Il thread principale attende `future.result(timeout)`; con qualsiasi eccezione
      (compreso `TimeoutError`) annulla il future, ferma il loop, attende il thread, legge `errlog` e
      solleva `ErroreArchivio(f"archivio non avviato: {motivo}")`, dove `motivo` è lo stderr ripulito se
      non vuoto, altrimenti `str(eccezione)` o il nome del tipo.
      La cartella `src` è `Path(__file__).resolve().parents[1]`.
    - Il thread del loop è nell'attributo `_thread` (usato da `test_chiusura`).
    - `strumenti()`: definizione `{"type": "function", "function": {"name": t.name, "description":
      t.description, "parameters": t.input_schema}}`; `esegui` lega il nome con un parametro
      predefinito della lambda.
    - `_chiama(nome, args) -> str`: se chiuso → `Errore: archivio non disponibile.`; altrimenti
      `run_coroutine_threadsafe(sessione.call_tool(nome, args), loop).result(timeout)`; testo = blocchi
      con attributo `text` uniti da `\n`; con `is_error` prefisso `Errore: ` se assente e log `WARNING`;
      `TimeoutError` → annulla il future, `Errore: l'archivio non ha risposto.`; ogni altra eccezione →
      log `WARNING` con il dettaglio, `Errore: archivio non disponibile.`
    - `__exit__`: segna il client come chiuso, chiude lo stack nel loop (attesa al massimo `timeout`;
      un errore di chiusura va solo nel log), ferma il loop, `join` del thread, chiude `errlog`.
      Restituisce `False` (non sopprime eccezioni).

- [ ] **Step 4: eseguire i test**
  Run: `.venv/Scripts/python.exe -m pytest tests/test_mcp_client.py -v` → tutti passati;
  `.venv/Scripts/python.exe -m pytest -q` → nessuna regressione, nessun avviso
  `ResourceWarning`/«Task was destroyed» nell'uscita.

- [ ] **Step 5: commit**
  `git add requirements.txt src/archivio/server.py src/archivio/__main__.py src/assistente/mcp_client.py tests/test_mcp_client.py`
  Messaggio: `feat(archivio): server MCP via stdio e client sincrono dell'assistente`

---

### Task 3: registro e CLI

**Files:**
- Modify: `src/assistente/strumenti/__init__.py` (`crea_strumenti`), `src/assistente/cli.py` (`main`)
- Test: `tests/test_strumenti.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `ClientArchivio`, `ErroreArchivio` (Task 2).
- Produces: `crea_strumenti(adesso, fuso_predefinito, citta_patrono=None, scarica=scarica_json,
  esterni: Sequence[Strumento] = ()) -> dict[str, Strumento]`.

- [ ] **Step 1: scrivere i test**
  - `tests/test_strumenti.py`:
    - `test_esterni_in_coda`: uno `Strumento` finto `prova_esterna` → ultimo nome del registro, e la
      sua `esegui` è quella data.
    - `test_esterno_con_nome_duplicato`: un esterno chiamato `calcola` → `ValueError` con
      `nome duplicato`.
  - `tests/test_cli.py` (`monkeypatch.setattr("assistente.cli.ClientArchivio", ...)`, niente
    sottoprocessi):
    - `test_main_archivio_non_avviato`: un finto il cui `__enter__` solleva
      `ErroreArchivio("archivio non avviato: prova")` → `main() == 1`, stderr contiene
      `Errore: archivio non avviato: prova`; `verifica_modello` sostituito da una funzione che fallisce
      il test se chiamata (l'archivio parte prima del controllo del modello).
    - `test_main_passa_gli_strumenti_dell_archivio`: un finto con uno strumento `prova_esterna`,
      `verifica_modello` e `crea_llm` sostituiti, `build_graph` sostituito da una funzione che registra
      i nomi del registro e solleva `KeyboardInterrupt` → `main() == 130`, `prova_esterna` fra i nomi
      registrati e il finto ha ricevuto `__exit__`.

- [ ] **Step 2: eseguire e verificare il fallimento**
  Run: `.venv/Scripts/python.exe -m pytest tests/test_strumenti.py tests/test_cli.py -q` → i nuovi
  test falliscono.

- [ ] **Step 3: implementare**
  - `crea_strumenti`: `strumenti = [... locali ..., *esterni]`.
  - `cli.main`: dopo il `logging.basicConfig`, `with ClientArchivio() as archivio:` racchiude
    `verifica_modello`, `crea_strumenti(..., esterni=archivio.strumenti())`, `build_graph`, il saluto e
    `ciclo`. `ErroreArchivio` si aggiunge alla tupla gestita con `Errore: ...` e codice 1.
  - I test esistenti di `main` che arrivano oltre `carica_config` (`test_main_ctrl_c_all_avvio`)
    devono continuare a passare: ora avviano il server vero; se il tempo diventa un problema,
    sostituire `ClientArchivio` con un finto anche lì.

- [ ] **Step 4: eseguire i test**
  Run: `.venv/Scripts/python.exe -m pytest -q` → tutti passati.

- [ ] **Step 5: prova manuale breve senza modello**
  Run (PowerShell, LM Studio spento o no): `"esci" | .venv\Scripts\python.exe avvia.py` → con LM
  Studio spento il messaggio è quello del modello non raggiungibile (l'archivio è partito e si è chiuso
  senza messaggi); con un CSV reso temporaneamente non valido il messaggio è
  `Errore: archivio non avviato: ... riga N ...` (ripristinare il CSV con `git checkout`).
  Riportare gli esiti nel resoconto del task.

- [ ] **Step 6: commit**
  `git add src/assistente/strumenti/__init__.py src/assistente/cli.py tests/test_strumenti.py tests/test_cli.py`
  Messaggio: `feat(cli): collega gli strumenti dell'archivio MCP al registro`

---

### Task 4: prove reali con LM Studio

**Files:**
- Modify: `tests/reale/test_lmstudio.py`

**Interfaces:**
- Consumes: `ClientArchivio` (Task 2), `crea_strumenti(..., esterni=...)` (Task 3).

- [ ] **Step 1: scrivere le prove**
  - `esegui_domanda` apre `ClientArchivio()` e passa `esterni=archivio.strumenti()`, così tutte le
    prove reali vedono i 7 strumenti come nell'applicazione (il `with` racchiude anche
    `grafo.invoke`).
  - `test_il_modello_usa_il_catalogo_per_cercare`: «Abbiamo dei multimetri? Dove sono?» → asserzioni
    della specifica; la collocazione attesa si legge con `carica(PERCORSO_INVENTARIO)` (articolo
    `MIS-001`), non scritta nel test.
  - `test_il_modello_usa_il_dettaglio`: «Dammi i dettagli dell'articolo MIS-001».
  - `test_il_modello_cerca_per_categoria`: «Che cosa c'è fra gli strumenti di misura?».
  Messaggi di asserzione con l'elenco delle chiamate, come nelle prove esistenti.

- [ ] **Step 2: eseguire tutte le prove reali** (LM Studio attivo; se non lo è, fermarsi e chiedere
  all'utente di avviarlo)
  Run: `CITTA_PATRONO=Pordenone .venv/Scripts/python.exe -m pytest -m reale -v -s`
  Expected: 15 passate, 1 xfail (catena senza «oggi»). Se un caso fallisce: fermarsi, diagnosticare con
  il log e riportare all'utente prima di cambiare descrizioni o specifica.

- [ ] **Step 3: commit**
  `git add tests/reale/test_lmstudio.py`
  Messaggio: `test(reale): prova il catalogo dell'archivio con LM Studio`

---

### Task 5: documentazione e Docker

**Files:**
- Modify: `README.md`, `CLAUDE.md` (solo la propria versione nell'indice)

- [ ] **Step 1: Docker**
  Run (PowerShell): `docker compose build` e poi
  `"Abbiamo dei multimetri? Dove sono?", "esci" | docker compose run --rm -T assistente`
  (stessa forma non interattiva con `-T` e input da pipe già verificata il 2026-11-03).
  Expected: chiamata a `cerca_inventario` nel log, risposta con la collocazione, uscita 0.
  Verificare anche che dopo l'uscita da `python avvia.py` (con `esci` e con Ctrl-C a metà turno) non
  resti un processo `python` dell'archivio: `tasklist /FI "IMAGENAME eq python.exe"` prima e dopo.
  E che dopo un Ctrl-C durante un turno la domanda successiva sull'inventario funzioni.

- [ ] **Step 2: README** (solo comandi eseguiti in questo ciclo):
  - In «Strumenti»: catalogo dell'inventario (server MCP «archivio» avviato dall'assistente via stdio,
    nessuna configurazione), esempi di domande.
  - Come modificare `src/archivio/inventario.csv` (UTF-8, separatore `;`, colonne, regole di
    validazione, errore con il numero di riga).
  - Avvio del server da solo per diagnosi: `.venv\Scripts\python.exe -m archivio` con
    `$env:PYTHONPATH = "src"`: con un CSV valido resta in attesa su stdin (Ctrl-C è ignorato: si chiude
    con Ctrl-Z e Invio), con un CSV non valido stampa l'errore con la riga ed esce con 1. Documentare
    solo ciò che si è verificato.
  - Dipendenza `mcp` e perché porta pacchetti HTTP inutilizzati.
  - In «Diagnosi»: `Errore: archivio non avviato: ...` (CSV non valido, dipendenze non installate).
  - In «Verifiche reali»: i tre casi del catalogo e l'esito del Task 4; in «Docker» l'esito dello
    Step 1 con la shell usata.

- [ ] **Step 3: CLAUDE.md**
  Costruire la propria versione su `git show HEAD:assistente-laboratorio/CLAUDE.md`: struttura (pacchetto
  `src/archivio/` server MCP, `mcp_client` in `src/assistente/`) e obiettivo (catalogo dell'inventario
  tramite il server MCP «archivio»). Registrarla nell'indice con
  `git hash-object -w <file temporaneo>` + `git update-index --cacheinfo 100644,<hash>,assistente-laboratorio/CLAUDE.md`;
  applicare le stesse righe anche alla copia di lavoro, senza togliere la modifica dell'utente.
  Verifica: `git diff --cached CLAUDE.md` mostra solo le righe nuove; `git diff CLAUDE.md` mostra solo
  la modifica dell'utente.

- [ ] **Step 4: verifica finale**
  Run: `.venv/Scripts/python.exe -m pytest -q` (tutti passati) e `git status` (nessun file estraneo).

- [ ] **Step 5: commit**
  `git add README.md` (CLAUDE.md è già nell'indice)
  Messaggio: `docs: documenta il catalogo e il server MCP archivio`
