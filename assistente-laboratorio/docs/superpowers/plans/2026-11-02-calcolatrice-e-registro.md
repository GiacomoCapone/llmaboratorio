# Calcolatrice sicura e registro degli strumenti: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** strumento `calcola` (quattro operazioni, `Decimal`, senza `eval`) e un registro di strumenti
che rende il grafo indipendente dai singoli strumenti.

**Architecture:** `strumenti` diventa un pacchetto: `orologio.py` e `calcolatrice.py` espongono
definizione e funzione `esegui_*(args) -> str`; `__init__.py` le riunisce in `Strumento` e
`crea_strumenti`. `build_graph` riceve il registro e cerca lo strumento per nome. La calcolatrice è
un tokenizzatore più un parser a discesa ricorsiva.

**Tech Stack:** Python 3.14 (`decimal`, `re`), LangGraph 1.2.17, pytest.

**Spec:** `docs/superpowers/specs/2026-11-02-calcolatrice-e-registro-design.md`

## Global Constraints
- Nessuna nuova dipendenza; nessun uso di `eval`, `exec`, `compile` o `ast` nella calcolatrice.
- Testi per il modello e messaggi d'errore copiati alla lettera dalla specifica; ogni errore di uno
  strumento inizia con `Errore:` e nessuna funzione `esegui_*` solleva eccezioni per input del modello.
- Cifre ammesse solo `[0-9]` (non `\d`, che in Python accetta cifre Unicode).
- Comportamento dell'orologio invariato (stesse regole di `fuso`, stessi testi).
- Conventional Commits in italiano su `feature`; `git status`, diff e staging selettivo prima di ogni commit;
  mai `.env` né `lezione_3/`. Comandi documentati per PowerShell; nel README solo comandi eseguiti.
- Test automatici: `python -m pytest`; prove reali: `python -m pytest -m reale -v -s`.

## Review Focus
1. **Simboli non ammessi ma plausibili** (`12,5 x 4`, `50%`, `2 = `): l'errore deve elencare cosa è
   ammesso, perché il modello possa correggersi. Test nel Task 2.
2. **Annidamento profondo entro il limite** (`"(" * 99 + "1" + ")" * 99`, 199 caratteri): nessun
   `RecursionError`, risultato `1`. Test nel Task 2.
3. **Cifre Unicode** (`١ + 1`, cifra araba): respinte come carattere non ammesso. Test nel Task 2.
4. **Risultati grandi o arrotondati** (`99999999999999999999999999999 + 1`): nessuna notazione con
   esponente nel risultato. Test nel Task 2.
5. **Separatore delle migliaia** (`1.000,50`): errore, non un valore silenziosamente sbagliato. Test nel Task 2.

---

### Task 1: Pacchetto `strumenti`, orologio spostato, registro e grafo generico

**Files:**
- Delete: `src/assistente/strumenti.py`
- Create: `src/assistente/strumenti/__init__.py`, `src/assistente/strumenti/orologio.py`
- Modify: `src/assistente/grafo.py`, `src/assistente/cli.py`, `tests/finti.py`
- Rename: `tests/test_strumenti.py` → `tests/test_orologio.py`; Create: `tests/test_strumenti.py` (registro)
- Modify: `tests/test_grafo.py`, `tests/test_cli.py`, `tests/reale/test_lmstudio.py` (solo la chiamata a `build_graph`)

**Interfaces:**
- Produces:
  - `assistente.strumenti.orologio`: `NOME_ORA_CORRENTE`, `definizione_ora_corrente(fuso_predefinito) -> dict`,
    `ora_corrente(fuso, adesso) -> str` (invariati), `esegui_ora_corrente(args: dict, adesso, fuso_predefinito: str) -> str`.
  - `assistente.strumenti`: `Strumento(definizione: dict, esegui: Callable[[dict], str])` frozen dataclass con
    property `nome`; `crea_strumenti(adesso: Callable[[], datetime], fuso_predefinito: str) -> dict[str, Strumento]`
    (in questo task solo `ora_corrente`).
  - `assistente.grafo.build_graph(llm, strumenti: dict[str, Strumento], max_passaggi: int)`.
  - `tests/finti.py`: `richiesta(nome: str, args, id: str = "c1") -> AIMessage` (una tool call); `richiesta_ora` resta.

- [ ] **Step 1: Write the failing tests**
  - `git mv tests/test_strumenti.py tests/test_orologio.py`; import da `assistente.strumenti.orologio`.
    Aggiungere su `esegui_ora_corrente(args, ADESSO, "Europe/Rome")` i casi oggi nel grafo, poi rimuoverli da
    `test_grafo.py`: `test_fuso_assente_usa_predefinito` (`{}`, `{"fuso": None}`, `{"fuso": ""}`, `{"fuso": "  "}`
    → `"2026-01-15T13:00:00+01:00"`), `test_predefinito_diverso_da_roma` (`"Asia/Tokyo"` → `"2026-01-15T21:00:00+09:00"`),
    `test_fuso_esplicito_ha_precedenza`, `test_fuso_esplicito_non_valido_non_ripiega`, `test_argomento_fuso_non_stringa`
    (`5`, `["Europe/Rome"]`, `{"a": 1}` → `startswith("Errore:")`), `test_argomenti_extra_ignorati`.
  - Nuovo `tests/test_strumenti.py`: `test_registro_contiene_orologio` (`list(crea_strumenti(ADESSO, "Europe/Rome")) == ["ora_corrente"]`);
    `test_nome_coincide_con_definizione` (per ogni voce: chiave == `s.nome` == `s.definizione["function"]["name"]`);
    `test_registro_usa_il_fuso_predefinito` (`crea_strumenti(ADESSO, "Asia/Tokyo")["ora_corrente"].esegui({})` → `"2026-01-15T21:00:00+09:00"`).
  - `test_grafo.py`: l'helper `esegui(llm, max_passaggi=5, testo=..., strumenti=None)` usa
    `crea_strumenti(ADESSO, "Europe/Rome")` se `strumenti` è `None`. Nuovi test:
    - `test_strumento_che_solleva`: registro `{"rotto": Strumento(definizione_rotta, esegui=solleva)}` con `solleva`
      che fa `raise RuntimeError("guasto")`; LLM finto `[richiesta("rotto", {}), AIMessage("Mi dispiace.")]` →
      ToolMessage `"Errore: errore interno dello strumento 'rotto'."`, `stato["interrotto"] is False`, ultima risposta
      `"Mi dispiace."`, nel log (`caplog`, livello ERROR) `"guasto"`.
    - `test_argomenti_non_oggetto`: `richiesta("ora_corrente", ["x"])` → `"Errore: argomenti non validi, atteso un oggetto JSON."`.
    - `test_definizioni_nell_ordine_del_registro`: `llm.strumenti == [s.definizione for s in registro.values()]`.
    - `test_strumento_sconosciuto`: atteso esattamente `"Errore: strumento sconosciuto: 'meteo'."`.
    - `test_argomenti_json_malformati`: contenuto esattamente
      `"Errore: argomenti non in formato JSON valido. Riprovare con un oggetto JSON."`.
  - `test_cli.py` e `tests/reale/test_lmstudio.py`: `build_graph(llm, crea_strumenti(ADESSO, "Europe/Rome"), n)`
    (nel test reale: `crea_strumenti(lambda: datetime.now(timezone.utc), config.fuso_predefinito)`).

- [ ] **Step 2: Run** `python -m pytest -q`. Expected: errori di import (`assistente.strumenti.orologio`, `crea_strumenti`).

- [ ] **Step 3: Implement**
  - `orologio.py`: contenuto dell'attuale `strumenti.py` più `esegui_ora_corrente`, che riceve un `dict` e applica
    le regole di `fuso` oggi in `grafo._esegui_strumento` (stessi messaggi).
  - `__init__.py`: `Strumento`, `crea_strumenti` (con `functools.partial` o lambda per legare `adesso` e `fuso_predefinito`).
  - `grafo.py`: nessun import da `assistente.strumenti` tranne il tipo `Strumento`; `_esegui_strumento(strumenti, nome, args)`
    implementa le quattro regole della specifica; l'eccezione imprevista è registrata con `logger.exception`
    (`"strumento %s fallito"`). `bind_tools([s.definizione for s in strumenti.values()])`.
  - `cli.main()`: `build_graph(crea_llm(config), crea_strumenti(lambda: datetime.now(timezone.utc), config.fuso_predefinito), config.max_passaggi)`.
  - Cancellare `src/assistente/strumenti.py` (`git rm`), altrimenti oscura il pacchetto.

- [ ] **Step 4: Run** `python -m pytest -q`. Expected: tutto PASS (3 deselezionati).

- [ ] **Step 5: Commit** `refactor(strumenti): introduce il registro degli strumenti e rende generico il grafo`
  (`git add -A src/assistente/strumenti src/assistente/strumenti.py src/assistente/grafo.py src/assistente/cli.py tests/finti.py tests/test_orologio.py tests/test_strumenti.py tests/test_grafo.py tests/test_cli.py tests/reale/test_lmstudio.py`).

### Task 2: Calcolatrice

**Files:**
- Create: `src/assistente/strumenti/calcolatrice.py`, `tests/test_calcolatrice.py`

**Interfaces:**
- Produces: `NOME_CALCOLA = "calcola"`, `DEFINIZIONE_CALCOLA: dict`, `calcola(espressione: str) -> str`,
  `esegui_calcola(args: dict) -> str`, `LUNGHEZZA_MASSIMA = 200`.

- [ ] **Step 1: Write the failing tests** in `tests/test_calcolatrice.py`:
  - `test_risultati` parametrizzato (espressione → atteso): `"2 + 3 * 4"`→`"14"`, `"8 - 3 - 2"`→`"3"`,
    `"8 / 4 / 2"`→`"1"`, `"(2 + 3) * 4"`→`"20"`, `"-3 + 5"`→`"2"`, `"-(2 + 3)"`→`"-5"`, `"--2"`→`"2"`,
    `"2 * -3"`→`"-6"`, `"+4"`→`"4"`, `"0.1 + 0.2"`→`"0.3"`, `"12,5 * 4"`→`"50"`, `"10 / 4"`→`"2.5"`,
    `"2,50 * 2"`→`"5"`, `"1 / 3"`→`"0.3333333333333333333333333333"`, `"100 * 10"`→`"1000"`, `"-0"`→`"0"`,
    `"7 - 7"`→`"0"`, `"\t1 +  1 "`→`"2"`, `"(" * 99 + "1" + ")" * 99`→`"1"`.
  - `test_risultato_grande_senza_esponente`: `calcola("99999999999999999999999999999 + 1")` non contiene `"E"` e inizia con `"1"`.
  - `test_errori_esatti` parametrizzato: `""` e `"   "` → `"Errore: espressione vuota."`; `"1+" * 100 + "1"` (201 car.)
    → `"Errore: espressione troppo lunga (massimo 200 caratteri)."`; `"5 / 0"`, `"5 / (2 - 2)"`, `"0 / 0"` →
    `"Errore: divisione per zero."`; `"2 x 3"` → `"Errore: carattere non ammesso 'x' in posizione 3. Sono ammessi numeri, + - * / e parentesi."`.
  - `test_limite_esatto`: un'espressione di 200 caratteri (`"1+" * 99 + "11"`) → `"110"`.
  - `test_errori_di_sintassi` parametrizzato (espressione, dettaglio): `"(2 + 3"`→`"parentesi ')' mancante"`,
    `"2 +"`→`"atteso un numero o '(' in posizione 4"`, `"2 3"`→`"testo inatteso in posizione 3"`,
    `"2 + 3)"`→`"testo inatteso in posizione 6"`, `"2 ** 3"`→`"atteso un numero o '(' in posizione 4"`; atteso
    `f"Errore: espressione non valida: {dettaglio}."`.
  - `test_respinti` parametrizzato, `startswith("Errore:")`: `"2 ^ 3"`, `"1e5"`, `"0x10"`, `"abs(-2)"`,
    `"__import__('os')"`, `"3.5.1"`, `".5"`, `"5."`, `"50%"`, `"2 ="`, `"١ + 1"`, `"1.000,50"`.
  - `test_errore_elenca_simboli_ammessi`: `"12,5 x 4"` → contiene `"+ - * /"`.
  - `test_esegui_calcola`: `{"espressione": "2+2"}` → `"4"`; `{}`, `{"espressione": 12}`, `{"espressione": None}` →
    `"Errore: argomento 'espressione' mancante o non testuale."`.
  - `test_definizione`: `name == "calcola"`, `required == ["espressione"]`, `"SEMPRE" in description`,
    `"50 * 20 / 100" in description`.

- [ ] **Step 2: Run** `python -m pytest tests/test_calcolatrice.py -q`. Expected: errore di import del modulo.

- [ ] **Step 3: Implement** `calcolatrice.py`
  - Tokenizzatore con `re` su `[0-9]+(?:[.,][0-9]+)?|[-+*/()]|[ \t]+`, avanzando con `match` alla posizione corrente;
    nessun match → errore «carattere non ammesso» con posizione 1-based. Token: (tipo, testo, posizione).
  - Parser: una funzione per regola della grammatica (`_espressione`, `_termine`, `_fattore`), con indice sul token
    corrente; a fine input una posizione pari a `len(testo) + 1`. Errori interni con un'eccezione privata
    `_ErroreCalcolo(messaggio)` convertita in `"Errore: ..."` solo in `calcola`.
  - Valutazione direttamente nel parser dentro `decimal.localcontext(prec=28, rounding=ROUND_HALF_EVEN)`;
    divisore zero → «divisione per zero» prima di dividere.
  - Formato: zero → `"0"`; altrimenti `format(risultato.normalize(), "f")`.
  - `DEFINIZIONE_CALCOLA` con i due testi della specifica, alla lettera.

- [ ] **Step 4: Run** `python -m pytest tests/test_calcolatrice.py -q`, poi `python -m pytest -q`. Expected: PASS.

- [ ] **Step 5: Commit** `feat(strumenti): aggiunge la calcolatrice sicura` (`git add src/assistente/strumenti/calcolatrice.py tests/test_calcolatrice.py`).

### Task 3: Calcolatrice nel registro

**Files:**
- Modify: `src/assistente/strumenti/__init__.py`, `tests/test_strumenti.py`, `tests/test_grafo.py`

**Interfaces:**
- Consumes: `DEFINIZIONE_CALCOLA`, `esegui_calcola` (Task 2); `crea_strumenti`, `richiesta` (Task 1).
- Produces: `crea_strumenti(...)` con chiavi `["ora_corrente", "calcola"]` in quest'ordine.

- [ ] **Step 1: Write the failing tests**
  - `test_registro_contiene_orologio` diventa `test_registro_contiene_gli_strumenti`: chiavi `["ora_corrente", "calcola"]`.
  - `test_grafo.py`: `test_tool_call_calcola` (`richiesta("calcola", {"espressione": "2 + 3 * 4"})` → ToolMessage `"14"`);
    `test_due_strumenti_nella_stessa_risposta` (una AIMessage con `ora_corrente` `{}` id `c1` e `calcola` `"1 / 4"` id `c2`
    → ToolMessage in ordine `"2026-01-15T13:00:00+01:00"`, `"0.25"`, con i rispettivi `tool_call_id`).

- [ ] **Step 2: Run** `python -m pytest tests/test_strumenti.py tests/test_grafo.py -q`. Expected: FAIL (registro senza `calcola`).

- [ ] **Step 3: Implement** l'aggiunta di `calcola` in `crea_strumenti`.

- [ ] **Step 4: Run** `python -m pytest -q`. Expected: tutto PASS.

- [ ] **Step 5: Commit** `feat(strumenti): registra la calcolatrice` (`git add src/assistente/strumenti/__init__.py tests/test_strumenti.py tests/test_grafo.py`).

### Task 4: Prove reali e documentazione

**Files:**
- Modify: `tests/reale/test_lmstudio.py`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: Aggiungere** `test_il_modello_usa_la_calcolatrice`, parametrizzato su
  (`"Quanto fa 12,5 * 4?"`, `"50"`, `("50",)`) e (`"Quanto fa (3 + 7) / 4?"`, `"2.5"`, `("2,5", "2.5")`):
  `"tool_call nome=calcola"` nel log, un ToolMessage uguale al valore atteso, turno non interrotto, risposta finale che
  contiene una delle forme ammesse; tempo stampato come per l'orologio. Usare un helper comune con il test dell'orologio
  per costruire grafo e stato (registro da `crea_strumenti`).

- [ ] **Step 2: Run** `python -m pytest -q` (Expected: reali deselezionati), poi con LM Studio
  `python -m pytest -m reale -v -s`. Expected: 5 PASS (3 orologio + 2 calcolatrice). Se un caso fallisce, fermarsi e
  riportarlo con il log: non cambiare le descrizioni senza riaprire la specifica.

- [ ] **Step 3: Prova manuale** con `PYTHONPATH=src` e `python -m assistente`: «Quanto fa 12,5 * 4?» e «che ore sono»
  nella stessa sessione. Docker Compose solo se Docker Desktop è attivo.

- [ ] **Step 4: README**: sezione «Strumenti» (orologio e calcolatrice: cosa accetta, esempio d'errore), conteggio dei
  test aggiornato, esiti degli step 2–3 con data. **CLAUDE.md**: in «Struttura» `strumenti/` (pacchetto con un modulo per
  strumento); in «Obiettivo» una riga per la calcolatrice sicura (quattro operazioni, senza `eval`).

- [ ] **Step 5: Commit** separati: `test(reale): prova la calcolatrice con LM Studio` (`git add tests/reale/test_lmstudio.py`)
  e `docs: documenta la calcolatrice e il registro degli strumenti` (`git add README.md`, e `CLAUDE.md` solo con le proprie
  modifiche: la modifica preesistente dell'utente resta fuori dal commit; separarla con una patch applicata con
  `git apply --cached` se l'utente non ha deciso diversamente).
