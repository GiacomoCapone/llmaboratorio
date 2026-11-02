# Orologio senza luogo e ragionamento disattivato: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** risposte in pochi secondi (ragionamento `none` per default) e orologio usato anche senza
luogo, con un fuso predefinito configurabile.

**Architecture:** due nuovi campi in `Config`, letti e validati da variabili d'ambiente; `crea_llm`
inoltra `reasoning_effort`; la definizione dello strumento diventa una funzione del fuso predefinito e
il grafo lo usa quando il modello omette `fuso`. Nodi, instradamento e cronologia non cambiano.

**Tech Stack:** Python 3.14, LangGraph 1.2.17, langchain-openai 1.7.2, pytest.

**Spec:** `docs/superpowers/specs/2026-10-28-orologio-e-ragionamento-design.md`

Primo passo di una sequenza: dopo questo piano seguono sei cicli separati (specifica → piano →
implementazione), uno per ciascun nuovo strumento.

## Global Constraints
- Nessuna nuova dipendenza; `requirements.txt` invariato.
- Nessun messaggio di sistema: il fuso predefinito arriva al modello solo dalla definizione dello strumento.
- Default: `LMSTUDIO_REASONING_EFFORT=none`, `FUSO_PREDEFINITO=Europe/Rome`; valore vuoto o assente → default.
- Valori ammessi per il ragionamento: `none`, `low`, `medium`, `high` (dopo `strip().lower()`).
- Testi rivolti all'utente e al modello in italiano; i messaggi d'errore degli strumenti iniziano con `Errore:`.
- Comandi documentati per PowerShell; nel README solo comandi verificati.
- Conventional Commits in italiano; prima di ogni commit `git status`, controllo del diff, staging
  selettivo. Non aggiungere mai `.env` né la cartella non tracciata `lezione_3/`.
- Test automatici: `python -m pytest`. Prove reali: `python -m pytest -m reale -v`.

## Review Focus
1. **Il modello manda `"fuso": null` o `"fuso": ""`.** I modelli piccoli lo fanno spesso con i parametri
   facoltativi; chi usa l'assistente si aspetta l'ora di Roma, non un errore. **Correzione della
   specifica (da confermare):** `null`, stringa vuota o di soli spazi vanno trattati come `fuso`
   assente. Test nel Task 3.
2. **`FUSO_PREDEFINITO` con spazi o non valido** (`" Europe/Rome "`, `Europe/Roma`): spazi rimossi;
   nome inesistente → errore all'avvio che cita la variabile, uscita 1, invece di un errore a ogni
   domanda. Test nel Task 1.
3. **`LMSTUDIO_REASONING_EFFORT` in maiuscolo o con spazi** (`" Low "`): normalizzato in `low`.
   Test nel Task 1.
4. **Fuso predefinito diverso da Roma**: sia la definizione dello strumento sia l'esecuzione devono
   usarlo, non solo una delle due. Test nei Task 2 e 3.
5. **Fuso esplicito non valido** (`"Europe/Roma"`): resta un `Errore: ...` e non si ripiega in
   silenzio sul predefinito, altrimenti l'utente riceverebbe l'ora del luogo sbagliato. Test nel Task 3.

---

### Task 1: Configurazione del ragionamento e del fuso predefinito

**Files:**
- Modify: `src/assistente/config.py`
- Modify: `tests/test_config.py`, `tests/test_modello.py:15` (`_config`)
- Modify: `.env.example`
- Modify: `docs/superpowers/specs/2026-10-28-orologio-e-ragionamento-design.md` (stato «approvata»,
  regola su `null`/stringa vuota del Review Focus 1, se confermata)

**Interfaces:**
- Produces: `Config(base_url: str, model: str, max_passaggi: int, log_level: str, reasoning_effort: str, fuso_predefinito: str)`,
  dataclass frozen, campi senza default (l'ordine è questo).

- [ ] **Step 1: Write the failing tests** in `tests/test_config.py`:
  - `test_valori_predefiniti`: aggiungere `cfg.reasoning_effort == "none"` e `cfg.fuso_predefinito == "Europe/Rome"`.
  - `test_reasoning_effort_valido`, parametrizzato su `("low", "low")`, `(" Low ", "low")`, `("HIGH", "high")`, `("", "none")`.
  - `test_reasoning_effort_non_valido`, parametrizzato su `"massimo"` e `"0"`: `pytest.raises(ErroreConfigurazione, match="LMSTUDIO_REASONING_EFFORT")`.
  - `test_fuso_predefinito_valido`: `" Asia/Tokyo "` → `"Asia/Tokyo"`; `""` → `"Europe/Rome"`.
  - `test_fuso_predefinito_non_valido`, parametrizzato su `"Europe/Roma"`, `"Mars/Base"`, `"../etc/passwd"`: `match="FUSO_PREDEFINITO"`.
  - In `tests/test_modello.py` `_config` diventa `Config(URL, model, 5, "INFO", "none", "Europe/Rome")`.

- [ ] **Step 2: Run** `python -m pytest tests/test_config.py -v`. Expected: FAIL (`AttributeError` sui nuovi campi).

- [ ] **Step 3: Implement** in `config.py`: costante `LIVELLI_RAGIONAMENTO = ("none", "low", "medium", "high")`;
  validazione del fuso con `ZoneInfo(valore)`, intercettando `ZoneInfoNotFoundError`, `ValueError`,
  `OSError` come in `strumenti.ora_corrente`. Messaggi che citano la variabile e i valori ammessi.

- [ ] **Step 4: Run** `python -m pytest`. Expected: tutto PASS.

- [ ] **Step 5: Aggiornare `.env.example`** aggiungendo `LMSTUDIO_REASONING_EFFORT=none` e `FUSO_PREDEFINITO=Europe/Rome`.

- [ ] **Step 6: Commit** `feat(config): aggiunge ragionamento e fuso predefinito configurabili`
  (`git add src/assistente/config.py tests/test_config.py tests/test_modello.py .env.example docs/superpowers/specs/2026-10-28-orologio-e-ragionamento-design.md`).

### Task 2: `reasoning_effort` nel modello e definizione dello strumento con fuso predefinito

**Files:**
- Modify: `src/assistente/modello.py` (`crea_llm`), `src/assistente/strumenti.py`
- Test: `tests/test_modello.py`, `tests/test_strumenti.py`

**Interfaces:**
- Consumes: `Config.reasoning_effort`.
- Produces: `definizione_ora_corrente(fuso_predefinito: str) -> dict`, che sostituisce la costante
  `DEFINIZIONE_ORA_CORRENTE` (da rimuovere). `NOME_ORA_CORRENTE` e `ora_corrente` invariati.

- [ ] **Step 1: Write the failing tests**
  - `test_crea_llm_imposta_reasoning_effort`: con `_config` modificata con `reasoning_effort="low"`, `crea_llm(...).reasoning_effort == "low"`.
  - Sostituire `test_definizione_dichiara_fuso_obbligatorio` con `test_definizione_fuso_facoltativo`:
    `d = definizione_ora_corrente("Asia/Tokyo")`; `d["type"] == "function"`; `name == "ora_corrente"`;
    `parameters["required"] == []`; `"Asia/Tokyo" in parameters["properties"]["fuso"]["description"]`;
    `"SEMPRE" in description` e `"Non chiedere mai il fuso" in description`.

- [ ] **Step 2: Run** `python -m pytest tests/test_modello.py tests/test_strumenti.py -v`. Expected: FAIL (import di `definizione_ora_corrente`).

- [ ] **Step 3: Implement**
  - `crea_llm` passa `reasoning_effort=config.reasoning_effort` a `ChatOpenAI`.
  - `definizione_ora_corrente`, con i testi fissati dalla specifica, da copiare alla lettera:
    - description: `"Restituisce la data e l'ora attuali (formato ISO 8601). Chiamalo SEMPRE quando l'utente chiede l'ora, la data o il giorno, per esempio 'che ore sono', 'che ora è', 'che giorno è oggi'. Non chiedere mai il fuso all'utente."`
    - fuso: `f"Nome IANA del fuso orario, per esempio America/New_York. Facoltativo: se l'utente non indica un luogo, omettilo e verrà usato {fuso_predefinito}."`
  - Docstring del modulo: «Strumenti a disposizione del modello.».

- [ ] **Step 4: Run** `python -m pytest tests/test_modello.py tests/test_strumenti.py -v`. Expected: PASS.
  `grafo.py` ancora importa la costante: la suite completa fallisce fino al Task 3, che va eseguito subito dopo.

- [ ] **Step 5: Nessun commit separato**: il Task 2 lascia il grafo non importabile, quindi si committa insieme al Task 3.

### Task 3: Grafo e CLI usano il fuso predefinito

**Files:**
- Modify: `src/assistente/grafo.py` (`_esegui_strumento`, `build_graph`), `src/assistente/cli.py` (`main`)
- Modify: `tests/finti.py` (`LlmFinto.bind_tools` conserva gli strumenti in `self.strumenti`)
- Test: `tests/test_grafo.py`, `tests/test_cli.py` (tutte le chiamate a `build_graph`)

**Interfaces:**
- Consumes: `definizione_ora_corrente(fuso_predefinito)`, `Config.fuso_predefinito`.
- Produces: `build_graph(llm, adesso: Callable[[], datetime], max_passaggi: int, fuso_predefinito: str)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_grafo.py` (l'helper `esegui` riceve `fuso_predefinito="Europe/Rome"` e lo inoltra):
  - Sostituire `test_argomento_fuso_mancante` con `test_fuso_assente_usa_predefinito`, parametrizzato su
    args `{}`, `{"fuso": None}`, `{"fuso": ""}`, `{"fuso": "  "}` → il ToolMessage è `"2026-01-15T13:00:00+01:00"`.
  - `test_predefinito_diverso_da_roma`: `esegui(..., fuso_predefinito="Asia/Tokyo")` con args `{}` → `"2026-01-15T21:00:00+09:00"`.
  - `test_fuso_esplicito_ha_precedenza`: predefinito `"Asia/Tokyo"`, args `{"fuso": "UTC"}` → `"2026-01-15T12:00:00+00:00"`.
  - `test_fuso_esplicito_non_valido_non_ripiega`: args `{"fuso": "Europe/Roma"}` → il contenuto inizia con `"Errore:"`.
  - `test_argomento_fuso_non_stringa`: togliere `None` dai parametri (restano `5`, `["Europe/Rome"]`, `{"a": 1}`).
  - `test_definizione_passata_al_modello`: `LlmFinto` registra gli strumenti ricevuti da `bind_tools`
    (nuovo attributo `self.strumenti`); con predefinito `"Asia/Tokyo"` la descrizione di `fuso` contiene `"Asia/Tokyo"`.
  - `test_log_mostra_argomenti_ricevuti`: con `caplog` e args `{}`, il log contiene `"tool_call nome=ora_corrente args={}"`.
  - In `tests/test_cli.py` ogni `build_graph(llm, ADESSO, n)` diventa `build_graph(llm, ADESSO, n, "Europe/Rome")`.

- [ ] **Step 2: Run** `python -m pytest tests/test_grafo.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement**
  - `_esegui_strumento(nome, args, adesso, fuso_predefinito)`: se `fuso` è assente, `None` o una stringa
    vuota dopo `strip()` → `ora_corrente(fuso_predefinito, adesso)`; se è una stringa → `ora_corrente(fuso, adesso)`;
    altrimenti l'errore attuale. Il log `tool_call` resta sugli argomenti originali.
  - `build_graph` collega `definizione_ora_corrente(fuso_predefinito)`.
  - `main()` passa `config.fuso_predefinito`.
  - Il messaggio per JSON non valido resta quello attuale (l'esempio `{"fuso": "Europe/Rome"}` è ancora corretto).

- [ ] **Step 4: Run** `python -m pytest`. Expected: tutto PASS, nessun test `reale` eseguito.

- [ ] **Step 5: Commit** dei Task 2 e 3 insieme:
  `feat(strumenti): fuso facoltativo con predefinito e ragionamento configurabile`
  (`git add src/assistente/modello.py src/assistente/strumenti.py src/assistente/grafo.py src/assistente/cli.py tests/finti.py tests/test_modello.py tests/test_strumenti.py tests/test_grafo.py tests/test_cli.py`).

### Task 4: Prove reali e documentazione

**Files:**
- Modify: `tests/reale/test_lmstudio.py`, `README.md`

**Interfaces:**
- Consumes: `build_graph(..., fuso_predefinito)`, `carica_config()`.

- [ ] **Step 1: Sostituire il test reale** con `test_il_modello_usa_lo_strumento_orologio`, parametrizzato su
  `"che ore sono"`, `"Che giorno è oggi?"`, `"Che ore sono a Tokyo?"` (senza «Usa lo strumento orologio»).
  Per ciascuna: `"tool_call nome=ora_corrente"` nel log, `not stato["interrotto"]`, risposta finale non vuota,
  almeno un ToolMessage senza `Errore:`; per Tokyo anche `"+09:00"` in un ToolMessage. Misurare il tempo di
  ogni turno con `time.perf_counter()` e stamparlo (`print`), così con `-s` compare nel resoconto.

- [ ] **Step 2: Run** `python -m pytest` (il test reale resta escluso: `deselected`), poi con LM Studio attivo
  `python -m pytest -m reale -v -s`. Expected: 3 PASS con `google/gemma-4-e2b`; annotare i tempi.
  Se una domanda fallisce, fermarsi e riportarlo con il log: non modificare la descrizione senza riaprire la specifica.

- [ ] **Step 3: Prova manuale** `python -m assistente`: «che ore sono» deve dare l'ora di Roma senza chiedere il
  fuso, in pochi secondi. Poi, se Docker è disponibile, `docker compose run --rm assistente` con la stessa domanda.

- [ ] **Step 4: README**: aggiungere le due variabili all'elenco della configurazione, il compromesso
  `none` veloce / `low` più lento e più affidabile, e la diagnosi con `lms ps` e la ricerca di
  `reasoning_tokens` nei log di LM Studio. Solo i comandi effettivamente eseguiti negli step 2–3, con data ed esito.

- [ ] **Step 5: Commit** separati:
  `test(reale): prova l'orologio con e senza luogo` (`git add tests/reale/test_lmstudio.py`) e
  `docs: documenta ragionamento e fuso predefinito` (`git add README.md`).
