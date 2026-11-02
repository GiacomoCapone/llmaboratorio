# Convertitore di unità SI: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** strumento `converti_unita` (unità SI con prefissi, aree e volumi di lunghezza, K/°C) e
controllo dei nomi duplicati nel registro.

**Architecture:** tabelle di unità e prefissi in `strumenti/convertitore.py`; un simbolo è letto come
unità esatta oppure prefisso + unità, con un eventuale esponente 2/3 per le lunghezze. Formato dei numeri
e contesto decimale condivisi con la calcolatrice in `strumenti/numeri.py`.

**Tech Stack:** Python 3.14 (`decimal`, `re`), pytest. Nessuna nuova dipendenza.

**Spec:** `docs/superpowers/specs/2026-11-02-convertitore-si-design.md`

## Global Constraints
- Testi per il modello e messaggi d'errore copiati alla lettera dalla specifica; ogni errore inizia con
  `Errore:`; `converti` ed `esegui_converti` non sollevano eccezioni per input del modello.
- Simboli sensibili a maiuscole e minuscole; cifre ammesse nei valori testuali solo `[0-9]`.
- Aritmetica in `localcontext(prec=28, rounding=ROUND_HALF_EVEN)`; risultato senza esponente.
- Comportamento di orologio e calcolatrice invariato.
- Conventional Commits in italiano su `feature`; staging selettivo; mai `.env` né `lezione_3/`; per
  `CLAUDE.md` solo le proprie righe (la modifica dell'utente resta fuori). Comandi PowerShell; nel README
  solo comandi eseguiti.
- Test: `python -m pytest`; prove reali: `python -m pytest -m reale -v -s` (leggono il `.env`).

## Review Focus
1. **Simboli che il modello scrive in modo plausibile ma errato** (`KM`, `Km`, `°c`, `celsius`, `metri`):
   errore che elenca esempi validi, nessuna lettura sbagliata in silenzio (`Km` non è kelvin·m). Test nel Task 2.
2. **Ambiguità prefisso/unità** (`mm`, `Pa`, `cd`, `dam`, `T`, `min`, `h`): lettura univoca garantita da un
   test su tutte le combinazioni, alias compresi. Test nel Task 2.
3. **Valore JSON float o in notazione esponenziale** (`2.5`, `1e-06` come numero JSON, `1e3` come stringa):
   un numero JSON passa da `str()` (quindi `1e-06` è accettato); una stringa con esponente è respinta come
   non numerica, coerente con la calcolatrice. Test nel Task 2.
4. **Risultati estremi** (`1 Qm → qm`, `1 qm → Qm`): nessun esponente, nessuna eccezione. Test nel Task 2.
5. **Temperatura con aree o prefissi** (`k°C`, `°C²`, `mK → °C`): i primi due respinti, il terzo convertito
   (`1000 mK → °C` = `-272.15 °C`). Test nel Task 2.

---

### Task 1: Modulo `numeri` condiviso

**Files:**
- Create: `src/assistente/strumenti/numeri.py`, `tests/test_numeri.py`
- Modify: `src/assistente/strumenti/calcolatrice.py` (usa `numeri`)

**Interfaces:**
- Produces: `formatta(valore: Decimal) -> str` (zero → `"0"`, altrimenti `format(valore.normalize(), "f")`);
  `contesto()` → `localcontext(prec=28, rounding=ROUND_HALF_EVEN)`.

- [ ] **Step 1: Write the failing tests** `tests/test_numeri.py`: `test_formatta` parametrizzato su
  `Decimal("2.50")`→`"2.5"`, `Decimal("1E+3")`→`"1000"`, `Decimal("-0")`→`"0"`, `Decimal("0.000")`→`"0"`,
  `Decimal("1E+60")`→`"1" + "0" * 60`, `Decimal("1E-30")`→`"0." + "0" * 29 + "1"`;
  `test_contesto`: dentro `with contesto():` `Decimal(1) / Decimal(3)` ha 28 cifre e `getcontext().rounding == ROUND_HALF_EVEN`.
- [ ] **Step 2: Run** `python -m pytest tests/test_numeri.py -q`. Expected: errore di import.
- [ ] **Step 3: Implement** `numeri.py`; in `calcolatrice.py` sostituire `_formatta` e il `localcontext` con `formatta` e `contesto()`.
- [ ] **Step 4: Run** `python -m pytest -q`. Expected: tutto PASS (test della calcolatrice invariati).
- [ ] **Step 5: Commit** `refactor(strumenti): estrae il formato dei numeri in un modulo condiviso`.

### Task 2: Convertitore

**Files:**
- Create: `src/assistente/strumenti/convertitore.py`, `tests/test_convertitore.py`

**Interfaces:**
- Consumes: `formatta`, `contesto` (Task 1).
- Produces: `NOME_CONVERTI = "converti_unita"`, `DEFINIZIONE_CONVERTI: dict`, `PREFISSI: dict[str, Decimal]`
  (24 prefissi più alias `u`, `μ`), `UNITA: dict[str, Unita]` (unità senza prefisso più alias `ohm`, `degC`),
  `Unita(grandezza: str, fattore: Decimal, scostamento: Decimal = 0, prefissabile: bool = True)` NamedTuple,
  `leggi_unita(simbolo: str) -> Unita | None`, `converti(valore, da: str, a: str) -> str`,
  `esegui_converti(args: dict) -> str`.

- [ ] **Step 1: Write the failing tests** in `tests/test_convertitore.py`:
  - `test_conversioni` parametrizzato (valore, da, a, atteso) con gli esempi della specifica: `(2.5,"km","m","2500 m")`,
    `(1500,"m","km","1.5 km")`, `(1,"kg","g","1000 g")`, `(300,"K","°C","26.85 °C")`, `(0,"°C","K","273.15 K")`,
    `(1,"m²","cm²","10000 cm²")`, `(1,"m³","mm³","1000000000 mm³")`, `(1,"kPa","Pa","1000 Pa")`,
    `(1,"µs","ns","1000 ns")`, `(1,"MW","mW","1000000000 mW")`, `(1000,"mK","°C","-272.15 °C")`,
    `(1,"m2","cm^2","10000 cm^2")`, `(1,"km3","m³","1000000000 m³")`, più una riga per ogni altra grandezza
    (`(1,"kA","A","1000 A")`, `(1,"mmol","mol","0.001 mol")`, `(1,"kcd","cd","1000 cd")`, `(1,"mrad","rad","0.001 rad")`,
    `(1,"msr","sr","0.001 sr")`, `(1,"GHz","Hz","1000000000 Hz")`, `(1,"kN","N","1000 N")`, `(1,"kJ","J","1000 J")`,
    `(1,"nC","C","0.000000001 C")`, `(1,"mV","V","0.001 V")`, `(1,"µF","nF","1000 nF")`, `(1,"kΩ","Ω","1000 Ω")`,
    `(1,"mS","S","0.001 S")`, `(1,"mWb","Wb","0.001 Wb")`, `(1,"mT","T","0.001 T")`, `(1,"mH","H","0.001 H")`,
    `(1,"klm","lm","1000 lm")`, `(1,"klx","lx","1000 lx")`, `(1,"kBq","Bq","1000 Bq")`, `(1,"mGy","Gy","0.001 Gy")`,
    `(1,"mSv","Sv","0.001 Sv")`, `(1,"mkat","kat","0.001 kat")`).
  - `test_alias`: `(1,"kohm","Ω","1000 Ω")`, `(1,"us","ns","1000 ns")`, `(1,"μs","ns","1000 ns")`, `(0,"degC","K","273.15 K")`.
  - `test_valori`: `"2,5"` e `"2.5"` → `2500 m` (km→m); `-1.5` km→m → `-1500 m`; JSON `1e-06` (float) km→m → `0.001 m`;
    `" km "` come `da` funziona e il risultato usa `"m"` senza spazi se `a` è `" m "`.
  - `test_prefissi_estremi`: `converti(1,"Qm","qm") == "1" + "0" * 60 + " qm"`; `converti(1,"qm","Qm")` inizia con `"0."` e non contiene `"E"`.
  - `test_unita_non_riconosciute` parametrizzato su `h`, `min`, `L`, `l`, `t`, `ha`, `km/h`, `°F`, `mi`, `kkm`, `mkg`,
    `k°C`, `°C²`, `s²`, `KM`, `Km`, `°c`, `celsius`, `metri`, `""`: come `da` (con `a="m"`) il risultato è esattamente
    il messaggio «unità non riconosciuta» della specifica con il simbolo citato.
  - `test_grandezze_diverse`: `converti(1,"kg","m")` == `"Errore: non si può convertire 'kg' (massa) in 'm' (lunghezza): grandezze diverse."`;
    `Hz→Bq`, `Gy→Sv`, `m²→m³`, `m→m²` iniziano con `"Errore: non si può convertire"`.
  - `test_valori_non_numerici` parametrizzato su `"abc"`, `"1.000,5"`, `"nan"`, `"inf"`, `"1e3"`, `"١"`: esattamente
    `f"Errore: valore non numerico: '{v}'."`.
  - `test_esegui_argomenti_mancanti` parametrizzato su `{}`, `{"valore": 1, "da": "m"}`, `{"valore": True, "da": "m", "a": "km"}`,
    `{"valore": 1, "da": 5, "a": "m"}`, `{"valore": None, "da": "m", "a": "km"}`: esattamente il messaggio
    «argomenti obbligatori» della specifica.
  - `test_lettura_univoca`: per ogni prefisso `p` di `PREFISSI` e unità `u` di `UNITA` con `prefissabile`, `leggi_unita(p + u)`
    ha la grandezza di `u` e fattore `PREFISSI[p] * UNITA[u].fattore`; inoltre, raccogliendo tutte le stringhe `u` e `p + u`,
    nessuna stringa compare due volte con letture diverse.
  - `test_definizione`: `name == "converti_unita"`, `required == ["valore", "da", "a"]`, `"SEMPRE" in description`,
    `"300 K in gradi Celsius" in description`.
- [ ] **Step 2: Run** `python -m pytest tests/test_convertitore.py -q`. Expected: errore di import.
- [ ] **Step 3: Implement** `convertitore.py`
  - Tabelle dalla specifica (grandezze in italiano, `g` con fattore `Decimal("0.001")`, `°C` con scostamento `Decimal("273.15")` e
    `prefissabile=False`).
  - `leggi_unita`: `strip()`; separare un esponente finale con `re.fullmatch(r"(.+?)(?:\^?([23])|([²³]))", ...)`; leggere la base come
    unità esatta, altrimenti provare ogni prefisso noto come inizio (con il resto unità esatta e `prefissabile`); con esponente
    la base deve essere di lunghezza e il risultato ha grandezza `area`/`volume` e fattore elevato alla potenza.
  - `_leggi_valore`: `bool` respinto; `int`/`float` → `Decimal(str(v))`; `str` → `re.fullmatch(r"[+-]?[0-9]+(?:[.,][0-9]+)?", v.strip())`;
    risultato non finito respinto.
  - `converti` calcola dentro `contesto()` con la formula della specifica e restituisce `f"{formatta(r)} {a.strip()}"`.
- [ ] **Step 4: Run** `python -m pytest tests/test_convertitore.py -q`, poi `python -m pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(strumenti): aggiunge il convertitore di unità SI`.

### Task 3: Registro con tre strumenti e nomi univoci

**Files:**
- Modify: `src/assistente/strumenti/__init__.py`, `tests/test_strumenti.py`, `tests/test_grafo.py`

**Interfaces:**
- Consumes: `DEFINIZIONE_CONVERTI`, `esegui_converti` (Task 2).
- Produces: `registro(strumenti: list[Strumento]) -> dict[str, Strumento]` (solleva `ValueError` con
  `"nome duplicato nel registro: '<nome>'"`); `crea_strumenti` lo usa e restituisce `["ora_corrente", "calcola", "converti_unita"]`.

- [ ] **Step 1: Write the failing tests**: `test_registro_contiene_gli_strumenti` con le tre chiavi; `test_nomi_duplicati`
  (`pytest.raises(ValueError, match="calcola")` con due `Strumento(DEFINIZIONE_CALCOLA, esegui_calcola)`); in `test_grafo.py`
  `test_tool_call_converti_unita` (`richiesta("converti_unita", {"valore": 2.5, "da": "km", "a": "m"})` → ToolMessage `"2500 m"`).
- [ ] **Step 2: Run** `python -m pytest tests/test_strumenti.py tests/test_grafo.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `registro` e l'aggiunta in `crea_strumenti`.
- [ ] **Step 4: Run** `python -m pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(strumenti): registra il convertitore e rifiuta nomi duplicati`.

### Task 4: Prove reali e documentazione

**Files:** Modify `tests/reale/test_lmstudio.py`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: Aggiungere** `test_il_modello_usa_il_convertitore`, parametrizzato su
  (`"Quanti metri sono 2,5 km?"`, `"2500 m"`, `("2500", "2.500")`) e
  (`"Quanti gradi Celsius sono 300 K?"`, `"26.85 °C"`, `("26,85", "26.85")`), con lo stesso helper e gli stessi controlli
  del test della calcolatrice (`tool_call nome=converti_unita`).
- [ ] **Step 2: Run** `python -m pytest -q` (reali deselezionati), poi `python -m pytest -m reale -v -s`. Expected: 7 PASS.
  Se un caso fallisce: fermarsi, diagnosticare con il log e riportare; non cambiare le descrizioni senza riaprire la specifica.
- [ ] **Step 3: Prova manuale** `.venv\Scripts\python.exe avvia.py`: «Quanti metri sono 2,5 km?», «Quanto fa 12,5 * 4?»,
  «che ore sono» nella stessa sessione. Docker solo se Docker Desktop è attivo.
- [ ] **Step 4: README** (sezione «Strumenti», conteggio dei test, esiti con data) e **CLAUDE.md** («Obiettivo»: convertitore
  di unità SI con prefissi), staging solo delle proprie righe.
- [ ] **Step 5: Commit** `test(reale): prova il convertitore con LM Studio` e `docs: documenta il convertitore di unità SI`.
