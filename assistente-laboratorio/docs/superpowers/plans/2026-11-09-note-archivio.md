# Note del laboratorio (SQLite nel server MCP «archivio») — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tre strumenti MCP (`aggiungi_nota`, `elenca_note`, `elimina_nota`) nel server «archivio», con le note in un file SQLite che sopravvive alla sessione e al container.

**Architecture:** logica pura in `src/archivio/note.py` (una connessione `sqlite3` per operazione, orologio iniettato); `server.py` registra i tre strumenti; `__main__.py` legge `NOTE_DB` e `FUSO_PREDEFINITO` dall'ambiente; la CLI li passa al sottoprocesso tramite il nuovo parametro `ambiente` di `ClientArchivio`. Grafo e registro invariati.

**Tech Stack:** Python 3.14, `sqlite3` e `zoneinfo` della libreria standard, `mcp==2.3.0` (già presente), pytest.

**Spec:** `docs/superpowers/specs/2026-11-09-note-archivio-design.md` (leggerla prima di ogni task: testi, descrizioni e formati sono fissati lì alla lettera e qui non sono ripetuti se non nei test).

## Global Constraints
- Nessuna dipendenza nuova; `requirements.txt` invariato.
- Tutti i testi restituiti agli strumenti sono quelli della spec, alla lettera; gli errori iniziano con `Errore:`.
- Descrizioni degli strumenti e dei parametri: alla lettera dalla spec (sezione «Strumenti MCP»).
- Limiti: testo 500 caratteri, codice 100, elenco 20 note, `sqlite3.connect(..., timeout=5)`.
- Il pacchetto `archivio` non importa nulla da `assistente`.
- **I test automatici non devono mai toccare `dati/note.db` del progetto**: ogni `ClientArchivio(...)` nei test riceve `ambiente={"NOTE_DB": <file in tmp_path>}`; ogni chiamata a `archivio.__main__.main()` nei test ha `NOTE_DB` impostata con `monkeypatch.setenv`.
- Comandi con il Python del `.venv`: `.venv/Scripts/python.exe -m pytest ...` (da Git Bash) o `.venv\Scripts\python.exe -m pytest ...` (PowerShell).
- Git: Conventional Commits in italiano, `git status` e diff prima di ogni commit, staging selettivo. Non mettere in commit la modifica dell'utente a `CLAUDE.md`, né `lezione_3/`, né `dati/`. Nessun push.

## Review Focus
1. Test che creano `dati/note.db` nel progetto per errore (un `ClientArchivio()` senza `ambiente`, o `main()` senza `NOTE_DB`): dopo `pytest` la cartella `dati/` non deve esistere → verifica esplicita nel Task 3 e nel Task 4.
2. `NOTE_DB` che punta a una cartella esistente invece che a un file → `ErroreNote` all'avvio, non un'eccezione grezza → test nel Task 1.
3. Testo fatto solo di caratteri di controllo (`"\n\t"`) → dopo la pulizia è vuoto → `Errore: indicare il testo della nota.` → test nel Task 1.
4. Il modello passa `numero` come stringa (`"3"`) → l'SDK lo converte e l'eliminazione riesce; `"tre"` → testo `Errore:` → test nel Task 3.
5. Codice con accenti/minuscole/spazi (`" mis-001 "`) nel filtro dell'elenco → stesso risultato del codice canonico → test nel Task 2.

---

### Task 1: `codice_canonico`, apertura del database e aggiunta delle note

**Files:**
- Modify: `src/archivio/inventario.py` (metodo `codice_canonico`, `dettaglio` lo usa)
- Create: `src/archivio/note.py`
- Test: `tests/test_archivio_inventario.py`, `tests/test_archivio_note.py` (nuovo)

**Interfaces:**
- Produces:
  - `Inventario.codice_canonico(codice: str) -> str | None` — codice come nel CSV, cercato dopo `strip()` e `normalizza`; `None` se assente.
  - `note.PERCORSO_NOTE_PREDEFINITO: Path` = `Path(__file__).resolve().parents[2] / "dati" / "note.db"`
  - `note.CARTELLA_PROGETTO: Path` = `Path(__file__).resolve().parents[2]`
  - `class ErroreNote(Exception)`
  - `note.apri(percorso: Path, inventario: Inventario, adesso: Callable[[], datetime]) -> Note`
  - `Note.aggiungi(testo: str | None, codice: str | None) -> str`
  - costanti `LUNGHEZZA_TESTO = 500`, `NOTE_MASSIME = 20`, `ATTESA_LOCK = 5`

- [ ] **Step 1: Test di `codice_canonico`** in `tests/test_archivio_inventario.py`: con l'inventario di prova esistente nel file, `codice_canonico(" mis-001 ") == "MIS-001"`, `codice_canonico("XYZ-9") is None`, `codice_canonico("") is None`. I test esistenti di `dettaglio` restano invariati.

- [ ] **Step 2: Test di apertura e aggiunta** in `tests/test_archivio_note.py`. Fixture: inventario costruito direttamente con `Inventario([Articolo("MIS-001", "Multimetro", "strumenti di misura", 3, "armadio A", ""), Articolo("SAL-002", "Saldatore", "attrezzi", 2, "banco 1", "")])`; orologio fisso `lambda: datetime(2026, 11, 9, 14, 32, 5, tzinfo=ZoneInfo("Europe/Rome"))`; `note = apri(tmp_path / "note.db", inventario, adesso)`.
  - `test_aggiungi_senza_codice`: `aggiungi("ordinare fusibili da 2 A", None) == "Nota 1 salvata (2026-11-09 14:32): ordinare fusibili da 2 A."`
  - `test_aggiungi_con_codice_canonico`: `aggiungi("display difettoso", "mis-001") == "Nota 1 salvata (MIS-001, 2026-11-09 14:32): display difettoso."`
  - `test_punto_finale_non_raddoppiato`: `"batteria scarica!"` → termina con `"batteria scarica!"` e non con `"!."`; idem con `.` e `?`.
  - `test_pulizia_del_testo`: `"  riga uno\nriga\t due   "` → testo salvato `"riga uno riga due"`.
  - `test_testo_vuoto` (parametrizzato: `None`, `""`, `"   "`, `"\n\t"`) → `"Errore: indicare il testo della nota."`
  - `test_testo_troppo_lungo`: 501 `"a"` → `"Errore: testo troppo lungo (massimo 500 caratteri)."`; 500 `"a"` → salvata.
  - `test_codice_troppo_lungo`: 101 caratteri → `"Errore: testo troppo lungo (massimo 100 caratteri)."`
  - `test_codice_sconosciuto_non_salva`: `"Errore: nessun articolo con codice 'XYZ-9'."`; la successiva aggiunta valida riceve il numero 1.
  - `test_codice_vuoto_equivale_a_nessuno`: `codice="  "` → risultato senza codice.
  - `test_data_salvata_con_scostamento`: dopo un'aggiunta, `sqlite3` diretto sul file legge `creata == "2026-11-09T14:32:05+01:00"`.
  - `test_persistenza`: aggiunta, poi una seconda `apri` sullo stesso file e un'altra aggiunta → `Nota 2 salvata ...`.
  - `test_crea_la_cartella`: `apri(tmp_path / "a" / "b" / "note.db", ...)` → la cartella esiste.
  - `test_file_non_sqlite`: file con testo `"non sono un database"` → `pytest.raises(ErroreNote, match="archivio delle note non valido")`, con il percorso nel messaggio.
  - `test_schema_diverso`: file creato con `CREATE TABLE note (numero INTEGER, testo TEXT)` → `ErroreNote`.
  - `test_percorso_e_una_cartella`: `apri(tmp_path, ...)` → `ErroreNote`.
  - `test_cartella_non_creabile`: genitore che è un file (`(tmp_path / "f").write_text("x")`, percorso `tmp_path / "f" / "note.db"`) → `ErroreNote`.

- [ ] **Step 3: Eseguire** `.venv/Scripts/python.exe -m pytest tests/test_archivio_note.py tests/test_archivio_inventario.py -q` → FAIL (modulo `archivio.note` assente, `codice_canonico` assente).

- [ ] **Step 4: Implementare** `codice_canonico` (usa `self._per_codice`; `dettaglio` la chiama) e in `note.py` `ErroreNote`, `apri`, `Note.__init__`, `Note.aggiungi`.
  - `apri`: `percorso.parent.mkdir(parents=True, exist_ok=True)`, poi in una connessione `CREATE TABLE IF NOT EXISTS` (schema della spec) e `PRAGMA table_info(note)` con nomi `["numero", "testo", "codice", "creata"]`; `OSError` e `sqlite3.Error` → `ErroreNote(f"archivio delle note non valido: {percorso} ({motivo}).")` con `motivo` = `strerror` o `str(errore)`.
  - una funzione privata `_connetti()` con `sqlite3.connect(self._percorso, timeout=ATTESA_LOCK)`, usata con `contextlib.closing` e `with conn:` (transazione); la connessione si chiude sempre.
  - pulizia: ogni carattere con `unicodedata.category(c) == "Cc"` → spazio, poi `" ".join(testo.split())`.
  - data mostrata: `creata[:16].replace("T", " ")`; salvata: `adesso().replace(microsecond=0).isoformat()`.

- [ ] **Step 5: Eseguire** lo stesso comando → PASS; poi `.venv/Scripts/python.exe -m pytest -q` → tutti passati.

- [ ] **Step 6: Commit** `feat(archivio): database delle note e aggiunta con codice dell'inventario` (`git add src/archivio/inventario.py src/archivio/note.py tests/test_archivio_inventario.py tests/test_archivio_note.py`).

### Task 2: elenco, eliminazione ed errori di esercizio

**Files:**
- Modify: `src/archivio/note.py`
- Test: `tests/test_archivio_note.py`

**Interfaces:**
- Consumes: `apri`, `Note.aggiungi`, `Inventario.codice_canonico` (Task 1).
- Produces: `Note.elenca(codice: str | None) -> str`, `Note.elimina(numero: int) -> str`; logger `logging.getLogger("archivio.note")`.

- [ ] **Step 1: Test** in `tests/test_archivio_note.py` (stessa fixture; per date diverse usare un orologio che avanza, per esempio una lista di istanti consumata con `iter`):
  - `test_elenco_dalla_piu_recente`: tre note (la 1 con `MIS-001`, la 2 senza codice, la 3 con `SAL-002`) → testo esatto
    ```
    Trovate 3 note:
    - 3 — <data> — SAL-002 — <testo>
    - 2 — <data> — <testo>
    - 1 — <data> — MIS-001 — <testo>
    ```
  - `test_elenco_una_nota`: prima riga `"Trovata 1 nota:"`.
  - `test_elenco_vuoto`: `"Nessuna nota."`; `elenca("mis-001")` senza note → `"Nessuna nota per l'articolo MIS-001."`
  - `test_elenco_filtrato` (parametrizzato `"MIS-001"`, `" mis-001 "`): solo le note di `MIS-001`.
  - `test_elenco_codice_sconosciuto`: `"Errore: nessun articolo con codice 'XYZ-9'."`; codice di 101 caratteri → errore di lunghezza 100.
  - `test_elenco_limite`: 23 note → prima riga `"Trovate 23 note:"`, 20 righe di note (dalla 23 alla 4), ultima riga `"(altre 3 note più vecchie non mostrate)"`.
  - `test_elimina`: nota 1 `"display difettoso"` con `MIS-001` → `"Nota 1 eliminata: «display difettoso» (MIS-001, 2026-11-09 14:32)."`; poi `elenca(None) == "Nessuna nota."`; senza codice → `"Nota 1 eliminata: «...» (2026-11-09 14:32)."`
  - `test_elimina_inesistente`: `elimina(12) == "Errore: nessuna nota con numero 12."`; eliminare due volte la stessa nota → la seconda volta lo stesso errore.
  - `test_elimina_numero_non_positivo` (parametrizzato `0`, `-1`) → `"Errore: il numero della nota deve essere un intero positivo."`
  - `test_numero_non_riusato`: aggiunta (1), aggiunta (2), elimina 2, aggiunta → `"Nota 3 salvata ..."`.
  - `test_errore_sqlite_in_esercizio` (parametrizzato sulle tre operazioni): dopo `apri`, sovrascrivere il file con `b"non sono un database" * 100` → risultato `"Errore: archivio delle note non disponibile."` e un record `WARNING` di `archivio.note` in `caplog`.

- [ ] **Step 2: Eseguire** `.venv/Scripts/python.exe -m pytest tests/test_archivio_note.py -q` → FAIL sui nuovi test.

- [ ] **Step 3: Implementare** `elenca` (`ORDER BY numero DESC LIMIT 20` più `COUNT(*)` con lo stesso filtro) ed `elimina` (`SELECT` poi `DELETE` nella stessa transazione). In tutte e tre le operazioni `sqlite3.Error` → `logger.warning("note: %s non riuscita: %r", operazione, errore)` e il testo `NON_DISPONIBILE = "Errore: archivio delle note non disponibile."`. Le validazioni degli argomenti avvengono prima di aprire la connessione.

- [ ] **Step 4: Eseguire** lo stesso comando → PASS; poi la suite intera → tutti passati.

- [ ] **Step 5: Commit** `feat(archivio): elenco ed eliminazione delle note`.

### Task 3: strumenti MCP, avvio del server e ambiente del client

**Files:**
- Modify: `src/archivio/server.py`, `src/archivio/__main__.py`, `src/assistente/mcp_client.py`
- Test: `tests/test_mcp_client.py`, `tests/reale/test_lmstudio.py` (solo la costruzione del client)

**Interfaces:**
- Consumes: `apri`, `Note`, `ErroreNote`, `PERCORSO_NOTE_PREDEFINITO`, `CARTELLA_PROGETTO` (Task 1–2).
- Produces:
  - `crea_server(inventario: Inventario, note: Note) -> MCPServer` con cinque strumenti, nell'ordine `cerca_inventario`, `dettaglio_articolo`, `aggiungi_nota`, `elenca_note`, `elimina_nota`.
  - `archivio.__main__.percorso_note(valore: str | None) -> Path` (vuoto → predefinito; relativo → `CARTELLA_PROGETTO / valore`) e `fuso_note(valore: str | None) -> ZoneInfo` (vuoto o non valido → `Europe/Rome`).
  - `ClientArchivio(comando: list[str] | None = None, timeout: float = 10.0, ambiente: dict[str, str] | None = None)`.

- [ ] **Step 1: Test** in `tests/test_mcp_client.py`:
  - fixture di modulo `client` con `ClientArchivio(ambiente={"NOTE_DB": str(tmp_path_factory.mktemp("note") / "note.db")})`; aggiungere `ambiente` con un `NOTE_DB` in `tmp_path` a **ogni** altra costruzione di `ClientArchivio` che avvia il server vero (righe 87, 159, 167 attuali) e in `tests/reale/test_lmstudio.py` (riga 32, con `tmp_path_factory` o `tempfile.TemporaryDirectory`).
  - `test_definizioni`: nomi `== ["cerca_inventario", "dettaglio_articolo", "aggiungi_nota", "elenca_note", "elimina_nota"]`; descrizioni dei tre nuovi strumenti e dei loro parametri uguali alla spec (costanti `DESCRIZIONE_AGGIUNGI`, `DESCRIZIONE_ELENCA`, `DESCRIZIONE_ELIMINA` e dei parametri copiate dalla spec); `aggiungi_nota` `required == ["testo"]`, `elenca_note` senza `required`, `elimina_nota` `required == ["numero"]`.
  - `test_note_end_to_end`: `aggiungi_nota({"testo": "batteria scarica", "codice": "mis-001"})` inizia con `"Nota 1 salvata (MIS-001, "`; `elenca_note({"codice": None})` inizia con `"Trovata 1 nota:"`; `elimina_nota({"numero": "1"})` (stringa) contiene `"eliminata"`; `elimina_nota({"numero": "tre"})` inizia con `"Errore:"`; prima dell'eliminazione una lettura `sqlite3` diretta del file `NOTE_DB` trova la nota `"batteria scarica"`.
  - `test_note_db_non_valido`: `NOTE_DB` su un file di testo → `pytest.raises(ErroreArchivio, match="archivio delle note non valido")`.
  - `test_percorso_note` (unitario su `main_archivio.percorso_note`): `None` e `""` → `PERCORSO_NOTE_PREDEFINITO`; `"x/n.db"` → `CARTELLA_PROGETTO / "x/n.db"`; un percorso assoluto in `tmp_path` resta invariato.
  - `test_fuso_note`: `None`, `""`, `"Marte/Olimpo"` → `ZoneInfo("Europe/Rome")`; `"UTC"` → `ZoneInfo("UTC")`.
  - `test_main_ignora_sigint`: aggiornare il finto a `lambda inventario, note: finto` e impostare `NOTE_DB` in `tmp_path`; i due test `test_main_inventario_*` impostano anch'essi `NOTE_DB`.
  - `test_main_note_non_valide`: `NOTE_DB` su un file di testo → `main() == 1` e stderr che inizia con `"Errore: archivio delle note non valido"`.

- [ ] **Step 2: Eseguire** `.venv/Scripts/python.exe -m pytest tests/test_mcp_client.py -q` → FAIL.

- [ ] **Step 3: Implementare.**
  - `server.py`: tre strumenti con descrizioni e `Annotated[..., Field(description=...)]` dalla spec; `codice: str | None = None` dove facoltativo, `numero: int` obbligatorio.
  - `__main__.py`: dopo l'inventario, `note = apri(percorso_note(os.environ.get("NOTE_DB")), inventario, lambda: datetime.now(fuso))`; `ErroreNote` → `print(f"Errore: {errore}", file=sys.stderr)` e `return 1`.
  - `mcp_client.py`: `_ambiente(extra)` restituisce il dizionario attuale aggiornato con `ambiente` (che non può sovrascrivere `PYTHONPATH`).

- [ ] **Step 4: Eseguire** `.venv/Scripts/python.exe -m pytest -q` → tutti passati; poi `ls dati 2>/dev/null && echo "ERRORE: dati/ creata dai test" || echo ok` → `ok`.

- [ ] **Step 5: Commit** `feat(archivio): strumenti MCP delle note e percorso del database dall'ambiente`.

### Task 4: configurazione, CLI e Docker

**Files:**
- Modify: `src/assistente/config.py`, `src/assistente/cli.py`, `compose.yaml`, `.gitignore`, `.dockerignore`, `.env.example`
- Test: `tests/test_config.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `ClientArchivio(..., ambiente=...)` (Task 3).
- Produces: `Config.note_db: Path` (campo con default, assoluto); `config.CARTELLA_PROGETTO = PERCORSO_ENV_PROGETTO.parent`, `config.NOTE_DB_PREDEFINITO = CARTELLA_PROGETTO / "dati" / "note.db"`.

- [ ] **Step 1: Test.**
  - `tests/test_config.py::test_note_db` parametrizzato: assente e `"  "` → `NOTE_DB_PREDEFINITO`; `"altro/n.db"` → `CARTELLA_PROGETTO / "altro" / "n.db"`; assoluto (`str(tmp_path / "n.db")`) → invariato. Sempre `is_absolute()`.
  - `tests/test_cli.py`: i finti diventano `lambda **kwargs: finto` (le tre occorrenze); nuovo `test_main_passa_note_db_e_fuso`: con `NOTE_DB` e `FUSO_PREDEFINITO=UTC` nell'ambiente (`monkeypatch.setenv`), il finto registra `kwargs["ambiente"] == {"NOTE_DB": <percorso assoluto>, "FUSO_PREDEFINITO": "UTC"}`.

- [ ] **Step 2: Eseguire** `.venv/Scripts/python.exe -m pytest tests/test_config.py tests/test_cli.py -q` → FAIL.

- [ ] **Step 3: Implementare** il campo in `Config` e in `carica_config` (relativo → rispetto a `CARTELLA_PROGETTO`), la chiamata in `cli.main()` come nella spec. Poi i file non Python:
  - `compose.yaml`: in `environment` `NOTE_DB: /app/dati/note.db` con un commento; `volumes: - ./dati:/app/dati`.
  - `.gitignore` e `.dockerignore`: riga `dati/` (in `.dockerignore` `dati`, come gli altri).
  - `.env.example`: `# Database delle note (SQLite); vuoto = dati/note.db nella cartella del progetto` e `# NOTE_DB=dati/note.db`.

- [ ] **Step 4: Eseguire** la suite intera → tutti passati; `ls dati` → assente; `docker compose config` → valido e mostra il volume (se Docker non è attivo, annotarlo nel resoconto).

- [ ] **Step 5: Commit** `feat(cli): passa all'archivio il percorso delle note; volume dati in Docker`.

### Task 5: prove reali con LM Studio

**Files:**
- Modify: `tests/reale/test_lmstudio.py`

**Interfaces:**
- Consumes: `esegui_domanda`, `chiamate_strumenti`, `risultati_strumenti` esistenti; `apri` (Task 1) per preparare le note.

- [ ] **Step 1: Test.** `esegui_domanda` riceve un parametro facoltativo `note_db: Path | None` passato come `ambiente={"NOTE_DB": ...}` (se `None`, un file in una cartella temporanea). Le note preesistenti si creano con `apri(note_db, carica(PERCORSO_INVENTARIO), adesso).aggiungi(...)` prima del turno. Quattro casi come nella spec, sezione «Verifiche reali»:
  - `test_il_modello_aggiunge_una_nota`: chiamata `aggiungi_nota` con `codice` `mis-001` (senza maiuscole), un risultato che inizia con `"Nota "` e contiene `"salvata"`.
  - `test_il_modello_elenca_le_note`: chiamata `elenca_note`, un risultato che inizia con `"Trovat"`.
  - `test_il_modello_elimina_una_nota`: nota preparata con numero N; «Elimina la nota N» → chiamata `elimina_nota` con `int(args["numero"]) == N`, un risultato che contiene `"eliminata"`.
  - `test_mostrare_le_note_non_elimina`: «Mostrami le note» → nessuna chiamata `elimina_nota`.

- [ ] **Step 2: Eseguire** con LM Studio attivo: `CITTA_PATRONO=Pordenone .venv/Scripts/python.exe -m pytest -m reale -v -s` (PowerShell: `$env:CITTA_PATRONO='Pordenone'; .venv\Scripts\python.exe -m pytest -m reale -v -s`). Atteso: tutte passate, la catena del calendario xfail. Se un caso fallisce: fermarsi, diagnosticare con il log, riportare all'utente prima di cambiare descrizioni o specifica. Se LM Studio non è attivo: riportarlo, non dichiarare il task concluso.

- [ ] **Step 3: Eseguire** `.venv/Scripts/python.exe -m pytest -q` → la suite automatica resta verde (i nuovi test sono deselezionati).

- [ ] **Step 4: Commit** `test(reale): prova le note dell'archivio con LM Studio`.

### Task 6: documentazione e verifica Docker

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/superpowers/2026-11-02-handoff.md`

- [ ] **Step 1: Verifica Docker manuale (PowerShell)** come nella spec: `docker compose build`; `docker compose run --rm assistente` con «Annota che il saldatore va pulito» ed `esci`; `python avvia.py` con «Quali note ci sono?» → la nota compare; eliminarla. Annotare esito e comandi usati.

- [ ] **Step 2: README**: i punti della sezione «Documentazione» della spec, solo con comandi eseguiti negli step precedenti (indicare la shell). Esempio d'uso preso da un'uscita reale.

- [ ] **Step 3: CLAUDE.md**: in «Obiettivo» una riga sulle note persistenti nel server «archivio»; in «Struttura» la cartella `dati/` (database delle note, fuori da Git, montata in Docker). Mettere nell'indice solo la propria versione, costruita su `git show HEAD:assistente-laboratorio/CLAUDE.md` e registrata con `git hash-object -w` + `git update-index --cacheinfo`; la modifica dell'utente nel file di lavoro va riapplicata e resta fuori dal commit (verificare con `git diff --cached` e `git diff`).

- [ ] **Step 4: Handoff**: ciclo 6 con stato, commit, decisioni, esiti delle prove e punti minori della revisione finale.

- [ ] **Step 5: Commit** `docs: documenta le note del laboratorio e chiude il ciclo 6`.
