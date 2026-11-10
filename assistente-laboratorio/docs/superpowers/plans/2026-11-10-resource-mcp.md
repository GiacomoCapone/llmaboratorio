# Resource MCP delle categorie: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** il server «archivio» espone la resource `archivio://inventario/categorie`; l'assistente la legge all'avvio e ne aggiunge i nomi alla descrizione del parametro `categoria` di `cerca_inventario`.

> **Revisione del 2026-11-10:** i Task 1 e 2 sono fatti. La prima versione dei Task 3–5 (contesto in un `SystemMessage` nel nodo `modello`) è stata eseguita e scartata dopo le prove reali (perdita del tool calling, vedi la specifica, «Revisione»); i Task 3–5 qui sotto sono la versione rivista.

**Architecture:** `Inventario.categorie()` + resource registrata in `crea_server` (testo generato a ogni lettura); `ClientArchivio.leggi_risorsa(uri)` sincrona sulla sessione persistente, errori → `ErroreArchivio`; `nomi_categorie` e `con_categorie` nel client; `cli` legge la resource dopo l'apertura dell'archivio (guasto → WARNING, definizioni invariate) e passa a `crea_strumenti` gli strumenti esterni arricchiti. Il grafo non cambia.

**Tech Stack:** Python 3.14, `mcp==2.3.0` (`MCPServer.resource`, `ClientSession.read_resource`), LangGraph, pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-resource-mcp-design.md`

## Global Constraints
- Comandi dalla cartella `assistente-laboratorio/` con `.venv\Scripts\python` (da Bash: `.venv/Scripts/python.exe`).
- Nessuna dipendenza nuova; strumenti e loro descrizioni invariati.
- Costanti esatte (identiche in `archivio/server.py` e `assistente/mcp_client.py`, l'assistente non importa `archivio`):
  `URI_CATEGORIE = "archivio://inventario/categorie"`.
- Server: `INTESTAZIONE_CATEGORIE = "Categorie dell'inventario (nomi esatti per il filtro categoria di cerca_inventario):"`;
  righe `- <categoria> (<n> articoli)`, singolare `(1 articolo)`; resource con `name="categorie"`, `mime_type="text/plain"`.
- Log esatti (logger `assistente.cli`): INFO `contesto: letta la resource %s (%d categorie)`; WARNING `contesto non disponibile: %s`.
- Testo aggiunto alla descrizione di `categoria`: `" Categorie esistenti: " + ", ".join(nomi) + "."`.
- `grafo.py` e `tests/test_grafo.py` restano come nel commit `185f02d`.
- Un solo commit a fine step (Task 5), nessun commit intermedio; ogni task termina con `python -m pytest` verde.
- Staging selettivo: mai `lezione_3/`, file fuori da `assistente-laboratorio/`, `.env`.
- Heredoc dal tool Bash: le sequenze `\n` vengono alterate; per sorgenti con escape usare lo strumento Edit.

## Review Focus
- Categoria scritta con maiuscole o accenti diversi in righe del CSV (per esempio `Attrezzi` e `attrezzi`): una sola voce, come nel filtro di `cerca_inventario` (rivisto dopo la revisione finale) — Task 1, `test_categorie_scritte_diversamente`.
- Lettura della resource quando il server è morto a metà sessione: `ErroreArchivio`, non un blocco o un'eccezione grezza — Task 2, `test_leggi_risorsa_server_morto`.
- Nome di categoria con parentesi (per esempio `cavi (rame)`): `nomi_categorie` taglia all'ultima ` (` — Task 3, `test_nomi_categorie_con_parentesi`.
- La definizione originale di `cerca_inventario` non va modificata (è condivisa con il client): `con_categorie` lavora su una copia — Task 3, `test_con_categorie_non_modifica_l_originale`.
- Archivio aperto ma lettura fallita: l'assistente risponde comunque al primo turno — Task 4, `test_main_senza_contesto`.

---

### Task 1: categorie dell'inventario e resource del server

**Files:** Modify `src/archivio/inventario.py`, `src/archivio/server.py`; Test `tests/test_archivio_inventario.py`, Create `tests/test_archivio_server.py`

**Interfaces:**
- Produces: `Inventario.categorie(self) -> list[tuple[str, int]]`; in `archivio.server`: `URI_CATEGORIE`, `INTESTAZIONE_CATEGORIE`, `testo_categorie(inventario: Inventario) -> str`; resource registrata in `crea_server`.

- [ ] **Step 1: test che falliscono** in `tests/test_archivio_inventario.py` (usare l'helper `inventario(tmp_path, righe)` esistente):
  - `test_categorie_ordinate_con_conteggio`: CSV con 2 articoli `strumenti di misura`, 1 `alimentatori`, 2 `attrezzi` → `[("alimentatori", 1), ("attrezzi", 2), ("strumenti di misura", 2)]`.
  - `test_categorie_inventario_di_esempio`: `carica(PERCORSO_INVENTARIO).categorie()` ==
    `[("alimentatori", 3), ("attrezzi", 4), ("cavi e connettori", 4), ("componenti passivi", 4), ("schede e microcontrollori", 4), ("sicurezza", 4), ("strumenti di misura", 4)]`.
  - `test_categorie_scritte_diversamente`: righe con `Attrezzi` e `attrezzi` → due voci, ciascuna con conteggio 1, nessuna eccezione.
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_archivio_inventario.py -k categorie -v` → FAIL (`AttributeError: categorie`).
- [ ] **Step 3:** implementare `categorie()` (conteggio di righe con `collections.Counter`, `sorted` sul nome).
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: test che falliscono** in `tests/test_archivio_server.py` (nuovo), in-process senza sottoprocesso: `server = crea_server(inv, apri(tmp_path / "note.db", inv, lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)))`, poi `asyncio.run(server.list_resources())` e `asyncio.run(server.read_resource(URI_CATEGORIE))` (restituisce oggetti con `.content` e `.mime_type`; verificato con `mcp==2.3.0`):
  - `test_resource_elencata`: una sola resource con `str(uri) == URI_CATEGORIE`, `name == "categorie"`, `mime_type == "text/plain"`.
  - `test_resource_testo`: con un inventario di prova di 2 `attrezzi` e 1 `alimentatori`, il contenuto è esattamente
    `INTESTAZIONE_CATEGORIE + "\n- alimentatori (1 articolo)\n- attrezzi (2 articoli)"`.
  - `test_resource_inventario_vuoto`: `testo_categorie(Inventario([])) == INTESTAZIONE_CATEGORIE`.
  - `test_resource_generata_a_ogni_lettura`: dopo `inv.articoli.append(...)` (o equivalente sul campo usato da `categorie()`) una seconda lettura riflette il nuovo conteggio.
  - `test_strumenti_invariati`: `[t.name for t in asyncio.run(server.list_tools())]` ==
    `["cerca_inventario", "dettaglio_articolo", "aggiungi_nota", "elenca_note", "elimina_nota"]`.
- [ ] **Step 6:** `.venv\Scripts\python -m pytest tests/test_archivio_server.py -v` → FAIL (`ImportError: URI_CATEGORIE`).
- [ ] **Step 7:** in `server.py` aggiungere le costanti, `testo_categorie` (intestazione + righe unite da `"\n"`) e in `crea_server` la resource
  `@server.resource(URI_CATEGORIE, name="categorie", mime_type="text/plain", description="Categorie dell'inventario del laboratorio con il numero di articoli.")` che restituisce `testo_categorie(inventario)`. Aggiornare la docstring del modulo (strumenti e resource).
- [ ] **Step 8:** `.venv\Scripts\python -m pytest` → tutto verde.

### Task 2: `ClientArchivio.leggi_risorsa`

**Files:** Modify `src/assistente/mcp_client.py`; Test `tests/test_mcp_client.py`

**Interfaces:**
- Consumes: resource del Task 1 (server vero via stdio).
- Produces: `mcp_client.URI_CATEGORIE: str`; `ClientArchivio.leggi_risorsa(self, uri: str) -> str` (solleva `ErroreArchivio`).

- [ ] **Step 1: test che falliscono** (fixture `client` a livello di modulo già esistente; per i casi che chiudono o rompono il client, un `ClientArchivio` proprio come in `test_chiusura` / `test_server_morto_a_meta_sessione`):
  - `test_leggi_risorsa_categorie(client)`: il testo comincia con `"Categorie dell'inventario (nomi esatti per il filtro categoria di cerca_inventario):"` e contiene `"- strumenti di misura (4 articoli)"` e `"- alimentatori (3 articoli)"` (conferma che `URI_CATEGORIE` del client coincide con quello del server).
  - `test_leggi_risorsa_uri_sconosciuto(client)`: `leggi_risorsa("archivio://altro")` → `ErroreArchivio`; il client resta usabile (subito dopo `leggi_risorsa(URI_CATEGORIE)` riesce).
  - `test_leggi_risorsa_client_chiuso(tmp_path)`: dopo l'uscita dal `with` → `ErroreArchivio`.
  - `test_leggi_risorsa_server_morto(tmp_path)`: con lo stesso server finto di `test_server_morto_a_meta_sessione` (`tests/server_finti/muore_dopo_una_chiamata.py`, adattato se serve perché muoia anche alla lettura) → `ErroreArchivio` entro il timeout, nessun blocco.
  - `test_leggi_risorsa_contenuto_non_testuale(monkeypatch, client)`: sessione la cui `read_resource` restituisce un `ReadResourceResult` con un solo `BlobResourceContents` (o `contents=[]`) → `ErroreArchivio`.
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_mcp_client.py -k leggi_risorsa -v` → FAIL (`AttributeError`).
- [ ] **Step 3:** implementare `leggi_risorsa` con lo stesso schema di `_chiama` (`self._chiuso` → errore; `run_coroutine_threadsafe(self._sessione.read_resource(uri), self._loop)`; `futuro.result(self._timeout)`; su `TimeoutError` `futuro.cancel()`; coroutine mai inviata → `close()`), ma sollevando `ErroreArchivio` con una causa leggibile invece di restituire testi `Errore: ...`. Testo = `contents[0].text`; nessun contenuto o primo contenuto senza `text` → `ErroreArchivio("la resource <uri> non ha contenuto testuale")`. Cause per gli altri casi: `"archivio non disponibile"`, `"l'archivio non ha risposto entro <t> secondi"`, `"lettura di <uri> fallita: <errore>"`.
- [ ] **Step 4:** `.venv\Scripts\python -m pytest tests/test_mcp_client.py -v` e poi `.venv\Scripts\python -m pytest` → verde.

### Task 3: ritiro del contesto nel grafo; `nomi_categorie` e `con_categorie`

**Files:** Revert `src/assistente/grafo.py`, `tests/test_grafo.py` (`git checkout -- ` dei due file); Modify `src/assistente/mcp_client.py`; Test `tests/test_mcp_client.py`

**Interfaces:**
- Consumes: `Strumento(definizione: dict, esegui)` dal registro; testo della resource (Task 1).
- Produces: `nomi_categorie(testo: str) -> list[str]`; `con_categorie(strumenti: list[Strumento], nomi: list[str]) -> list[Strumento]` in `assistente.mcp_client`.

- [ ] **Step 1:** `git checkout -- src/assistente/grafo.py tests/test_grafo.py`; `git diff --stat` non elenca più i due file.
- [ ] **Step 2: test che falliscono** in `tests/test_mcp_client.py`:
  - `test_nomi_categorie(client)`: `nomi_categorie(client.leggi_risorsa(URI_CATEGORIE))` == i 7 nomi dell'inventario di esempio in ordine alfabetico.
  - `test_nomi_categorie_senza_righe`: solo intestazione → `[]`; righe estranee (`"testo"`, `"-senza spazio"`) ignorate.
  - `test_nomi_categorie_con_parentesi`: `"- cavi (rame) (2 articoli)"` → `["cavi (rame)"]`.
  - `test_con_categorie`: con una `Strumento` finta `cerca_inventario` la cui proprietà `categoria` ha descrizione `"Nome esatto."` e una seconda voce `altro`, `con_categorie(..., ["a", "b"])` → descrizione `"Nome esatto. Categorie esistenti: a, b."`; `altro` è lo stesso oggetto; `esegui` conservato.
  - `test_con_categorie_non_modifica_l_originale`: dopo la chiamata la descrizione della definizione originale è ancora `"Nome esatto."`.
  - `test_con_categorie_invariata` parametrizzato: `nomi=[]`; nessun `cerca_inventario`; `cerca_inventario` senza proprietà `categoria` → lista uguale (stessi oggetti).
- [ ] **Step 3:** `.venv\Scripts\python -m pytest tests/test_mcp_client.py -k "nomi_categorie or con_categorie" -v` → FAIL (`ImportError`).
- [ ] **Step 4:** implementare le due funzioni (copia con `copy.deepcopy` della sola definizione modificata; `Strumento(nuova_definizione, s.esegui)`).
- [ ] **Step 5:** `.venv\Scripts\python -m pytest` → verde.

### Task 4: lettura all'avvio nella CLI

**Files:** Modify `src/assistente/cli.py`; Test `tests/test_cli.py`

**Interfaces:**
- Consumes: `URI_CATEGORIE`, `ClientArchivio.leggi_risorsa`, `nomi_categorie`, `con_categorie` (Task 2–3).

- [ ] **Step 1:** in `tests/test_cli.py` togliere `contesto=""` dai `grafo_finto` e i test del contesto nel grafo; `ArchivioFinto` resta con `leggi_risorsa` (contesto predefinito: un testo di resource con le righe `- attrezzi (2 articoli)` e `- sicurezza (1 articolo)`). **Test che falliscono:**
  - `test_main_arricchisce_cerca_inventario(monkeypatch, caplog)`: `ArchivioFinto` con una `Strumento` `cerca_inventario` (proprietà `categoria` con descrizione `"Nome esatto."`); `grafo_finto` registra `strumenti` e solleva `KeyboardInterrupt` → `main() == 130`; descrizione di `categoria` nel registro ricevuto `"Nome esatto. Categorie esistenti: attrezzi, sicurezza."`; `finto.letti == [URI_CATEGORIE]`; log INFO `contesto: letta la resource archivio://inventario/categorie (2 categorie)`.
  - `test_main_contesto_non_disponibile(monkeypatch, caplog)`: `errore_lettura=ErroreArchivio("l'archivio non ha risposto entro 10 secondi")` → descrizione invariata `"Nome esatto."`; unico WARNING `contesto non disponibile: l'archivio non ha risposto entro 10 secondi`.
  - `test_main_senza_contesto(monkeypatch, capsys)`: invariato (guardia: l'assistente risponde anche senza resource).
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_cli.py -v` → i nuovi FAIL.
- [ ] **Step 3:** `leggi_contesto(archivio) -> list[str]` in `cli.py` (nomi o `[]` su `ErroreArchivio`, con i due log); `esterni=con_categorie(archivio.strumenti(), nomi)`; nessun argomento `contesto` a `build_graph`.
- [ ] **Step 4:** `.venv\Scripts\python -m pytest` → verde.

### Task 5: prove reali, prove manuali, documentazione e commit

**Files:** Modify `tests/reale/test_lmstudio.py`, `README.md`, `CLAUDE.md`, `docs/superpowers/2026-11-02-handoff.md`, intestazione della specifica

- [ ] **Step 1:** in `tests/reale/test_lmstudio.py`: `grafo_vero` costruisce gli esterni come la CLI, `con_categorie(archivio.strumenti(), nomi_categorie(archivio.leggi_risorsa(URI_CATEGORIE)))`, senza `contesto`; togliere `test_tre_messaggi_di_sistema` (forma non più usata). Tenere `test_il_modello_elenca_le_categorie` (**vincolante**) e `test_osserva_categoria_esatta` (**osservazione**); aggiungere `test_osserva_componenti_passivi` (**osservazione**): «Che componenti passivi abbiamo?» → se nessuna chiamata `cerca_inventario` con `categoria == "componenti passivi"` o nessun risultato che comincia con `Trovat` → `pytest.xfail` con le chiamate.
- [ ] **Step 2:** con LM Studio attivo: prima le tre prove nuove (`-k "elenca_le_categorie or categoria_esatta or componenti_passivi"`), poi l'intera suite `-m reale -v -s` con `CITTA_PATRONO=Pordenone`. Se LM Studio smette di rispondere (ReadTimeout su `/v1/models`), rilanciare le prove interessate e annotarlo. Se una prova fallisce per il comportamento del modello: fermarsi e riportare.
- [ ] **Step 3:** prove manuali con output mostrato: PowerShell `$env:LOG_LEVEL="INFO"; "Quali categorie ci sono nell'inventario?","esci" | .venv\Scripts\python avvia.py` → INFO `contesto: letta la resource ... (7 categorie)`, risposta con le categorie, uscita 0. Docker: `docker compose build` e `"Quali categorie ci sono nell'inventario?","esci" | docker compose run --rm -T -e LOG_LEVEL=INFO assistente` → stessa evidenza, uscita 0.
- [ ] **Step 4:** documentazione: README (sezione sulla resource: URI, contenuto, uso nella descrizione di `cerca_inventario`, righe di log, misura del `SystemMessage` scartato; diagnosi `contesto non disponibile`); `CLAUDE.md` (resource nell'obiettivo e in `src/archivio/`); specifica `Stato: approvata` con la revisione; handoff con lo step 4 fatto ed evidenze.
- [ ] **Step 5:** `.venv\Scripts\python -m pytest` → verde; revisione indipendente dell'intero step; correzioni.
- [ ] **Step 6:** `git status`, `git diff`, staging selettivo (spec, piano, `src/`, `tests/`, README, CLAUDE.md, handoff), commit unico `feat(archivio): resource MCP delle categorie dell'inventario` con il trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
