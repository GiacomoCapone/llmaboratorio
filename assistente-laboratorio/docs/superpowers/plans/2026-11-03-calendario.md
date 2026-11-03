# Calendario (giorni e scadenze): piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** strumento `calendario` (operazioni `differenza` e `aggiungi`, giorni di calendario e lavorativi)
con festività nazionali da JSON, Pasqua e Pasquetta calcolate e patrono configurabile con `CITTA_PATRONO`.

**Architecture:** `strumenti/festivita.py` legge e valida `festivita.json`, calcola la Pasqua e sa dire se un
giorno è lavorativo (funzioni pure); `strumenti/calendario.py` contiene la definizione per il modello, i due
calcoli e la validazione degli argomenti. `crea_strumenti` carica le festività una volta e registra
`calendario` per quarto; la città arriva da `config.py`.

**Tech Stack:** Python 3.14 (`datetime`, `json`, `re`, `pathlib`), pytest. Nessuna nuova dipendenza.

**Spec:** `docs/superpowers/specs/2026-11-03-calendario-design.md`

## Global Constraints
- Testi per il modello, nomi delle ricorrenze, formati dei risultati e messaggi d'errore copiati alla lettera
  dalla specifica; ogni errore dello strumento inizia con `Errore:`; `esegui_calendario` non solleva eccezioni.
- Convenzione: partenza esclusa, arrivo incluso (`(data, data_fine]` in avanti, `[data_fine, data)` all'indietro).
- Anni ammessi 1583–9999; cifre delle date e di `giorni` solo `[0-9]` ASCII.
- Errori del file o della città: `ErroreConfigurazione` (da `assistente.config`), mai all'interno dello strumento.
- Comportamento di orologio, calcolatrice e convertitore invariato; `Config` resta costruibile con i sei
  argomenti posizionali attuali (`citta_patrono` ultimo, predefinito `None`).
- Conventional Commits in italiano su `feature`; staging selettivo; mai `.env` né `lezione_3/`; per
  `CLAUDE.md` solo le proprie righe (la modifica dell'utente resta fuori: costruire la versione su
  `git show HEAD:assistente-laboratorio/CLAUDE.md` e registrarla con `git hash-object -w` +
  `git update-index --cacheinfo`). Comandi PowerShell; nel README solo comandi eseguiti.
- Test: `python -m pytest` (dal `.venv`); prove reali: `python -m pytest -m reale -v -s` (leggono il `.env`).

## Review Focus
1. **Data con ora o fuso** (`2026-12-18T00:00:00`, `2026-12-18 10:00`, `20261218`): respinta con il messaggio
   «data non valida», non accettata da `date.fromisoformat` (che in 3.14 accetta anche `20261218`). Test nel Task 2.
2. **Cifre non ASCII** (`２０２６-12-01`, `٢٠٢٦-12-01`, `"١٠"` per `giorni`): respinte. Test nel Task 2.
3. **Anni bisestili** (`2028-02-29` valida, `2027-02-29` respinta; `aggiungi` da `2028-02-28` + 1 = `2028-02-29`). Test nel Task 2.
4. **Intervalli a cavallo d'anno e su più anni** (Pasqua in anni diversi, cache per anno): la differenza
   `2025-12-31 → 2027-12-31` dà come lavorativi la somma dei due anni calcolati separatamente. Test nel Task 2.
5. **`giorni` enorme** (`"999999999999"`, `10**20`, stringa di 5000 cifre): errore «data risultante fuori»
   o «deve essere un numero intero», mai `OverflowError`/`ValueError` non gestiti. Test nel Task 2.

---

### Task 1: Festività e Pasqua

**Files:**
- Create: `src/assistente/strumenti/festivita.json` (contenuto esatto della specifica),
  `src/assistente/strumenti/festivita.py`, `tests/test_festivita.py`

**Interfaces:**
- Produces:
  - `PERCORSO_FESTIVITA: Path` (`Path(__file__).with_name("festivita.json")`).
  - `pasqua(anno: int) -> date`.
  - `carica_festivita(citta: str | None, percorso: Path = PERCORSO_FESTIVITA) -> Festivita` (solleva
    `ErroreConfigurazione` con i messaggi della specifica).
  - `class Festivita`: attributo `citta: str | None` (nome come scritto nel file); metodi
    `dell_anno(anno: int) -> dict[date, str]` (con cache per anno; voci unite con `", "` nell'ordine
    nazionali → `Pasqua`/`Lunedì dell'Angelo (Pasquetta)` → `<santo> (patrono di <città>)`) e
    `lavorativo(giorno: date) -> bool`.

- [ ] **Step 1: Write the failing tests** in `tests/test_festivita.py`:
  - `test_pasqua` parametrizzato: `1583→(4,10)`, `2024→(3,31)`, `2025→(4,20)`, `2026→(4,5)`, `2038→(4,25)`, `2285→(3,22)`.
  - `test_festivita_2026_pordenone`: `carica_festivita("Pordenone").dell_anno(2026)` ha 12 voci (San Marco si unisce alla Liberazione); `[date(2026,4,6)] == "Lunedì dell'Angelo (Pasquetta)"`;
    `[date(2026,4,5)] == "Pasqua"`; `[date(2026,4,25)] == "Festa della Liberazione, San Marco (patrono di Pordenone)"`; `[date(2026,12,8)] == "Immacolata Concezione"`.
  - `test_voce_unita_2038`: `[date(2038,4,25)] == "Festa della Liberazione, Pasqua, San Marco (patrono di Pordenone)"`.
  - `test_senza_patrono`: `carica_festivita(None)` e `carica_festivita("")` → `citta is None`, 12 voci nel 2026, `[date(2026,4,25)] == "Festa della Liberazione"`.
  - `test_patrono_altro_giorno`: Udine → `[date(2026,7,12)] == "Santi Ermacora e Fortunato (patrono di Udine)"`.
  - `test_citta_normalizzata`: `carica_festivita("  pordenone ").citta == "Pordenone"`.
  - `test_citta_sconosciuta`: `pytest.raises(ErroreConfigurazione)`; il messaggio inizia con
    `"Città del patrono sconosciuta: 'Milano'. Città disponibili: Pordenone, Roma, Trieste, Udine, Venezia (file "`.
  - `test_file_non_valido` parametrizzato (scritti in `tmp_path`): file assente; `"{"`; `[]`; senza `patroni`;
    `{"nazionali": {"13-01": "X"}, "patroni": {}}`; `{"nazionali": {"02-29": "X"}, "patroni": {}}`;
    nome vuoto; patrono senza `santo` → `ErroreConfigurazione` con messaggio che inizia con `"File delle festività non valido: "`.
  - `test_lavorativo`: Pordenone 2026 → `2026-12-01` (martedì) `True`; `2026-12-05` (sabato) `False`; `2026-12-06` (domenica) `False`;
    `2026-12-08` `False`; `2026-04-06` `False`; `2026-04-25` `False`.
- [ ] **Step 2: Run** `python -m pytest tests/test_festivita.py -q`. Expected: errore di import.
- [ ] **Step 3: Implement** `festivita.json` e `festivita.py`. Pasqua con l'algoritmo anonimo gregoriano
  (Meeus/Jones/Butcher). Validazione di `MM-GG` con `re.fullmatch(r"[0-9]{2}-[0-9]{2}", k)` e `date(2001, mm, gg)`
  (anno non bisestile, così `02-29` è respinto). Il dettaglio del messaggio «File delle festività non valido» è libero
  (per esempio l'eccezione JSON o «chiave 'patroni' mancante»).
- [ ] **Step 4: Run** `python -m pytest tests/test_festivita.py -q`, poi `python -m pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(strumenti): festività italiane con Pasqua calcolata e patrono`.

### Task 2: Strumento `calendario`

**Files:**
- Create: `src/assistente/strumenti/calendario.py`, `tests/test_calendario.py`

**Interfaces:**
- Consumes: `Festivita`, `carica_festivita` (Task 1).
- Produces:
  - `NOME_CALENDARIO = "calendario"`.
  - `definizione_calendario(citta: str | None) -> dict` (schema `"type": "function"` della specifica).
  - `differenza(inizio: date, fine: date, festivita: Festivita) -> str`.
  - `aggiungi(inizio: date, giorni: int, lavorativi: bool, festivita: Festivita) -> str`.
  - `esegui_calendario(args: dict, festivita: Festivita) -> str`.

- [ ] **Step 1: Write the failing tests** in `tests/test_calendario.py` (fixture `fest = carica_festivita("Pordenone")`):
  - `test_differenza_dicembre`: `differenza(date(2026,12,1), date(2026,12,31), fest)` è esattamente l'esempio della specifica.
  - `test_differenza_da_fine_novembre`: `2026-11-30 → 2026-12-31` contiene `"31 giorni di calendario, 21 lavorativi"`.
  - `test_differenza_negativa`: `2026-12-31 → 2026-12-01` == `"dal 2026-12-31 (giovedì) al 2026-12-01 (martedì): -30 giorni di calendario, -20 lavorativi; festività nell'intervallo: 2026-12-08 Immacolata Concezione, 2026-12-25 Natale, 2026-12-26 Santo Stefano"`
    (intervallo `[2026-12-01, 2026-12-31)`: il 1° contato, il 31 no).
  - `test_differenza_date_uguali`: `0 giorni di calendario, 0 lavorativi; nessuna festività nell'intervallo`.
  - `test_differenza_molte_festivita`: `2026-01-01 → 2027-12-31` termina con `"; 23 festività nell'intervallo"`
    (11 nel 2026 senza il 1° gennaio, + 12 nel 2027) e `2026-12-31 → 2027-12-31` elenca le 12 voci del 2027 (≤ 15).
  - `test_aggiungi` parametrizzato sugli esempi della specifica (`+10 lavorativi`, `-1 giorno`, `+0 giorni`) più
    `(2026-12-18, 1, True)` → `"2026-12-18 (venerdì) + 1 giorno lavorativo = 2026-12-21 (lunedì)"` e
    `(2027-01-05, -10, True)` → `"2027-01-05 (martedì) - 10 giorni lavorativi = 2026-12-18 (venerdì)"`.
  - `test_coerenza`: per `inizio` in `2026-01-01`, `2026-04-03`, `2026-12-24`, `2027-02-27` e `n` in `-40, -7, -1, 1, 7, 40`,
    ricavare la data di arrivo da `aggiungi(..., True, ...)` e verificare che `differenza(inizio, arrivo, fest)` contenga `f", {n} lavorativi;"`.
  - `test_limiti`: `differenza(date(1900,1,1), date(2000,1,3), fest)` (36526 giorni) è il messaggio «intervallo troppo lungo»;
    `aggiungi(date(2026,1,1), 25001, True, fest)` idem; `aggiungi(date(9999,12,31), 1, False, fest)` e
    `aggiungi(date(1583,1,1), -1, False, fest)` sono «data risultante fuori».
  - `test_esegui_errori` parametrizzato su ogni riga della tabella «Errori», con il messaggio esatto:
    `{}` e `{"operazione": "somma", "data": "2026-01-01"}` → operazione non valida (`'None'` e `'somma'`);
    `{"operazione": "aggiungi", "giorni": 1}` e con `"data": None` → `data` obbligatoria; `{"operazione": "differenza", "data": "2026-01-01"}` → `data_fine`;
    `{"operazione": "aggiungi", "data": "2026-01-01"}` → `giorni`; `giorni` `10.5`, `"dieci"`, `"10.0"`, `True`, `"١٠"` → non intero;
    `lavorativi` `"si"`, `1`, `"vero"` → non valido.
  - `test_date_non_valide` parametrizzato su `2026-2-5`, `05/02/2026`, `2026-02-30`, `oggi`, `1582-12-31`, `2027-02-29`,
    `2026-12-18T00:00:00`, `2026-12-18 10:00`, `20261218`, `２０２６-12-01`, `٢٠٢٦-12-01`, `5` (intero) → messaggio «data non valida» con il valore citato;
    lo stesso per `data_fine`.
  - `test_argomenti_tolleranti`: `operazione " Differenza "`; `data " 2026-12-01 "`; `giorni` `10`, `10.0`, `"10"`, `"-5"`, `"+3"`;
    `lavorativi` `"TRUE"`, `"false"`, `None`, assente; `2028-02-28 + 1` = `2028-02-29 (martedì)`.
  - `test_argomenti_estranei_ignorati`: `differenza` con `giorni: "x"` e `lavorativi: "x"` dà il risultato normale; `aggiungi` con `data_fine: "x"` idem.
  - `test_giorni_enormi`: `"999999999999"` e `10**20` → «data risultante fuori»; `"9" * 5000` → «deve essere un numero intero» o «fuori» (nessuna eccezione).
  - `test_definizione_con_citta` e `test_definizione_senza_citta`: `description` e le cinque descrizioni dei parametri uguali **parola
    per parola** alla specifica (stringhe complete nel test); `required == ["operazione", "data"]`;
    `enum == ["differenza", "aggiungi"]`; tipi `string`, `string`, `string`, `integer`, `boolean`.
- [ ] **Step 2: Run** `python -m pytest tests/test_calendario.py -q`. Expected: errore di import.
- [ ] **Step 3: Implement** `calendario.py`.
  - Date: `re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", s.strip())`, poi `date.fromisoformat`; anno ≥ 1583.
  - `giorni`: `bool` respinto; `int`; `float` con `is_integer()`; `str` con `re.fullmatch(r"[+-]?[0-9]+", s.strip())`
    e `int(...)` dentro `try` (oltre 4300 cifre → non intero).
  - Arrivo di `aggiungi` non lavorativo: controllare `abs(giorni)` contro `(date(9999,12,31) - date(1583,1,1)).days` prima di
    `timedelta`, poi intervallo; lavorativo: limite 25000 prima del ciclo.
  - Giorni della settimana da una tupla italiana indicizzata con `weekday()`.
- [ ] **Step 4: Run** `python -m pytest tests/test_calendario.py -q`, poi `python -m pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(strumenti): aggiunge lo strumento calendario`.

### Task 3: Configurazione e registro

**Files:**
- Modify: `src/assistente/config.py`, `src/assistente/strumenti/__init__.py`, `src/assistente/cli.py`,
  `.env.example`, `tests/test_config.py`, `tests/test_strumenti.py`, `tests/test_grafo.py`

**Interfaces:**
- Consumes: `carica_festivita` (Task 1); `definizione_calendario`, `esegui_calendario` (Task 2).
- Produces: `Config.citta_patrono: str | None = None` (ultimo campo); `crea_strumenti(adesso, fuso_predefinito,
  citta_patrono: str | None = None) -> dict[str, Strumento]` con chiavi `ora_corrente`, `calcola`, `converti_unita`, `calendario`.

- [ ] **Step 1: Write the failing tests**:
  - `test_config.py`: `test_citta_patrono` parametrizzato: `"Pordenone"` → `"Pordenone"`, `" Udine "` → `"Udine"`, `""` → `None`, assente → `None`
    (la città non è validata qui).
  - `test_strumenti.py`: aggiornare `test_registro_contiene_gli_strumenti` alle quattro chiavi; `test_registro_citta_sconosciuta`
    (`crea_strumenti(ADESSO, "Europe/Rome", "Milano")` → `ErroreConfigurazione`); `test_registro_cita_il_patrono`
    (con `"pordenone"` la descrizione di `calendario` contiene `"patrono di Pordenone"`).
  - `test_grafo.py`: `test_tool_call_calendario` (`richiesta("calendario", {"operazione": "aggiungi", "data": "2026-12-18", "giorni": 10, "lavorativi": True})`
    → ToolMessage `"2026-12-18 (venerdì) + 10 giorni lavorativi = 2027-01-05 (martedì)"`).
- [ ] **Step 2: Run** `python -m pytest tests/test_config.py tests/test_strumenti.py tests/test_grafo.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**: `CITTA_PATRONO` con `strip()` (vuota → `None`); `crea_strumenti` aggiunge
  `Strumento(definizione_calendario(f.citta), lambda args: esegui_calendario(args, f))`; `cli.main` passa
  `config.citta_patrono`; in `.env.example` dopo `FUSO_PREDEFINITO`:
  `# Città del santo patrono (festività locale): una di quelle in src/assistente/strumenti/festivita.json` e `CITTA_PATRONO=Pordenone`.
- [ ] **Step 4: Run** `python -m pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(strumenti): registra il calendario con il patrono da CITTA_PATRONO`.

### Task 4: Prove reali e documentazione

**Files:** Modify `tests/reale/test_lmstudio.py`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: Aggiornare** `esegui_domanda` per passare `config.citta_patrono` a `crea_strumenti` e aggiungere:
  - `test_il_modello_usa_il_calendario` parametrizzato su
    (`"Quanti giorni lavorativi ci sono dal 1° al 31 dicembre 2026?"`, `"20 lavorativi"`, `("20",)`) e
    (`"Che data è 10 giorni lavorativi dopo il 18 dicembre 2026?"`, `"2027-01-05"`, `("5 gennaio 2027", "2027-01-05")`):
    `"tool_call nome=calendario"` nel log, un ToolMessage valido che contiene il frammento atteso, risposta finale con una delle forme.
  - `test_catena_orologio_calendario` con `"Che giorno sarà fra 30 giorni?"`: nel log `tool_call nome=ora_corrente` compare prima di
    `tool_call nome=calendario`; un ToolMessage valido contiene `(datetime.now(ZoneInfo(config.fuso_predefinito)).date() + timedelta(30)).isoformat()`
    come data di arrivo (dopo `" = "`).
- [ ] **Step 2: Run** `python -m pytest -q` (reali deselezionati), poi `python -m pytest -m reale -v -s`. Expected: 10 PASS.
  Se un caso fallisce: fermarsi, diagnosticare con il log e riportare all'utente; non cambiare le descrizioni senza riaprire la specifica.
- [ ] **Step 3: Prova manuale** `.venv\Scripts\python.exe avvia.py`: «Quanti giorni lavorativi mancano dal 3 novembre 2026 a Natale?»,
  «Quanto fa 12,5 * 4?», «che ore sono» nella stessa sessione. Docker (`docker compose build`, poi `docker compose run --rm assistente`)
  solo se Docker Desktop è attivo.
- [ ] **Step 4: README** (sezione «Strumenti»: operazioni, convenzione di conteggio, esempio; `CITTA_PATRONO` nella configurazione;
  come aggiungere una città a `festivita.json`; conteggio dei test; esiti con data) e **CLAUDE.md** («Obiettivo»: una riga
  «offre un calendario: differenza fra date e data + N giorni, di calendario o lavorativi, con festività italiane e patrono»),
  staging solo delle proprie righe.
- [ ] **Step 5: Commit** `test(reale): prova il calendario con LM Studio` e `docs: documenta lo strumento calendario`.
