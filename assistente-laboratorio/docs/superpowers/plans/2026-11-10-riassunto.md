# Riassunto della cronologia: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un nodo `riassunto` all'inizio del turno sostituisce i messaggi più vecchi con un riassunto del modello quando la cronologia stimata supera `RIASSUNTO_SOGLIA_TOKEN`, tenendo intatti gli ultimi 2 turni e la domanda corrente.

**Architecture:** nuovo modulo `riassunto.py` (stima, divisione per turni, trascrizione, prompt, chiamata senza strumenti), iniettato come callable in `build_graph`; il nodo decide se riassumere, riscrive la cronologia con `RemoveMessage(id=REMOVE_ALL_MESSAGES)` + `SystemMessage` del riassunto + recenti, e in caso di guasto la lascia invariata.

**Tech Stack:** Python 3.14, LangGraph 1.2.17 (`REMOVE_ALL_MESSAGES`, `add_messages`), langchain-openai, pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-riassunto-design.md`

## Global Constraints
- Comandi dalla cartella `assistente-laboratorio/` con `.venv\Scripts\python`.
- Nessuna dipendenza nuova.
- Costanti esatte: `CARATTERI_PER_TOKEN = 4`, `TURNI_RECENTI = 2`, `MAX_TOKEN_RIASSUNTO = 1024`, `PREFISSO_RIASSUNTO = "Riassunto della conversazione precedente: "`; `RIASSUNTO_SOGLIA_TOKEN` predefinito 3000, intero ≥ 1.
- Log esatti (logger `assistente.grafo`): DEBUG `riassunto: stima %d token, sotto la soglia %d`; INFO `riassunto: stima %d token sopra la soglia %d, niente da riassumere`; INFO `riassunto: %d messaggi riassunti, stima %d → %d token`; WARNING `riassunto non disponibile: %s`.
- Un solo commit a fine step (Task 6), nessun commit intermedio; ogni task termina con la suite verde.
- Staging selettivo: mai `lezione_3/`, file fuori da `assistente-laboratorio/`, `.env`.
- Heredoc dal tool Bash: le sequenze `\n` e `\`+a capo vengono alterate; per stringhe con escape usare lo strumento Edit.

## Review Focus
- Ultimo turno rifiutato dal router o arrivato al limite di revisioni: conta come turno e il taglio resta su un `HumanMessage` — Task 2, `test_dividi_conta_il_turno_rifiutato`.
- Cronologia sopra la soglia per un solo turno enorme (elenco lungo) con meno di 3 domande: nessuna chiamata, nessun errore — Task 3, `test_sopra_soglia_senza_vecchi`.
- Riassunto vuoto o di soli spazi dal modello: cronologia invariata, WARNING — Task 3, `test_guasto_lascia_la_cronologia` (parametrizzato).
- Revisione nello stesso turno di un riassunto: `scartati` contiene id dei soli messaggi nuovi, la pulizia finale non tocca il riassunto — Task 3, `test_riassunto_e_revisione_nello_stesso_turno`.
- `ToolMessage` con contenuto non stringa (lista) nella stima e nella trascrizione: nessuna eccezione — Task 2, `test_stima_contenuto_non_stringa`.

---

### Task 1: `RIASSUNTO_SOGLIA_TOKEN` in configurazione

**Files:** Modify `src/assistente/config.py`, `.env.example`; Test `tests/test_config.py`

**Interfaces:** Produces `Config.soglia_riassunto: int` (campo con predefinito `3000`, dopo `max_revisioni`).

- [ ] **Step 1: test che falliscono:**
  - `test_soglia_riassunto_predefinita`: `carica_config(BASE).soglia_riassunto == 3000`.
  - `test_soglia_riassunto_esplicita` parametrizzato `("500", 500), (" 500 ", 500), ("1", 1)`.
  - `test_soglia_riassunto_non_valida` parametrizzato `"0", "-1", "abc", "1.5"` → `ErroreConfigurazione` con `"RIASSUNTO_SOGLIA_TOKEN"` nel messaggio.
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_config.py -q` → FAIL.
- [ ] **Step 3:** lettura come `MAX_REVISIONI` (messaggio «RIASSUNTO_SOGLIA_TOKEN deve essere un intero positivo, trovato '...'.»); `.env.example`: `# Token stimati della cronologia oltre i quali i messaggi vecchi sono riassunti` + `RIASSUNTO_SOGLIA_TOKEN=3000`.
- [ ] **Step 4:** `.venv\Scripts\python -m pytest -q` → PASS.

### Task 2: Modulo riassunto

**Files:** Create `src/assistente/riassunto.py`, `tests/test_riassunto.py`; Modify `tests/finti.py`

**Interfaces:**
- Produces (`riassunto.py`): le costanti dei Global Constraints; `PROMPT_RIASSUNTO: str`; `stima_token(messaggi: list[AnyMessage]) -> int`; `dividi(messaggi) -> tuple[list[AnyMessage], list[AnyMessage]]` (vecchi, recenti); `trascrivi(vecchi) -> str`; `crea_riassuntore(llm) -> Callable[[list[AnyMessage]], str]`.
- Produces (`finti.py`): `LlmFinto.bind(**opzioni)` che registra `self.opzioni_bind` e restituisce una vista le cui invocazioni risultano **senza** strumenti; `RiassuntoreFinto(testo="riassunto di prova", errore: Exception | None = None)`, callable, registra i messaggi in `self.chiamate`, solleva `errore` se dato.

- [ ] **Step 1: test che falliscono** in `tests/test_riassunto.py` (helper `conversazione(n)` = n turni `HumanMessage(f"D{i}")`, `AIMessage(f"R{i}")`):
  - `test_stima_token`: `stima_token([HumanMessage("abcde")]) == 2` (per eccesso); un `AIMessage` con tool call conta anche `str(tool_calls)` (stima maggiore di quella del solo testo vuoto).
  - `test_stima_contenuto_non_stringa`: `ToolMessage(content=[{"type": "text", "text": "x"}], tool_call_id="c1")` → intero > 0, nessuna eccezione.
  - `test_dividi_pochi_turni`: `conversazione(2) + [HumanMessage("D3")]` → vecchi `[]`, recenti = tutto.
  - `test_dividi_confine`: `conversazione(4) + [HumanMessage("D5")]` → contenuti dei vecchi `["D1", "R1", "D2", "R2"]`, recenti cominciano da `"D3"` e finiscono con `"D5"`.
  - `test_dividi_tiene_le_coppie`: il turno D3 contiene `richiesta_ora("Asia/Tokyo")` + `ToolMessage` + risposta → entrambi nei recenti.
  - `test_dividi_riassunto_precedente_fra_i_vecchi`: `[SystemMessage(PREFISSO_RIASSUNTO + "x")] + conversazione(3) + [HumanMessage("D4")]` → il `SystemMessage` è il primo dei vecchi.
  - `test_dividi_conta_il_turno_rifiutato`: un turno con `AIMessage` di rifiuto del router conta come turno (stesso confine di `test_dividi_confine`).
  - `test_trascrivi`: righe esatte per `[SystemMessage(PREFISSO_RIASSUNTO + "prima"), HumanMessage("Che ore sono?"), richiesta_ora("Asia/Tokyo"), ToolMessage("21:00", tool_call_id=..., name="ora_corrente"), AIMessage("Sono le 21.")]` → `"Riassunto precedente: prima\nUtente: Che ore sono?\nStrumento ora_corrente: 21:00\nAssistente: Sono le 21."`.
  - `test_crea_riassuntore`: con `LlmFinto([AIMessage("sintesi")])` → restituisce `"sintesi"`; `llm.strumenti == []`; `llm.opzioni_bind == {"max_tokens": MAX_TOKEN_RIASSUNTO}`; `llm.con_strumenti == [False]`; inviati `[SystemMessage(PROMPT_RIASSUNTO), HumanMessage(trascrivi(vecchi))]`.
  - `test_prompt_regole`: `PROMPT_RIASSUNTO` contiene `"numeri delle note"`, `"codici"`, `"non inventare"`, `"riassunto precedente"`.
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_riassunto.py -q` → errore di import.
- [ ] **Step 3:** implementare secondo la specifica; testo dei messaggi con `str(m.content)`; il riconoscimento del riassunto precedente è `isinstance(m, SystemMessage) and str(m.content).startswith(PREFISSO_RIASSUNTO)`. Aggiungere `bind` e `RiassuntoreFinto` a `finti.py`.
- [ ] **Step 4:** `.venv\Scripts\python -m pytest -q` → PASS.

### Task 3: Nodo riassunto nel grafo

**Files:** Modify `src/assistente/grafo.py`, `tests/test_grafo.py` (helper `esegui`), `tests/test_cli.py` (helper `crea_grafo`)

**Interfaces:**
- Consumes: `stima_token`, `dividi`, `PREFISSO_RIASSUNTO` (Task 2); `RiassuntoreFinto` (Task 2).
- Produces: `build_graph(llm, strumenti, max_passaggi, router, revisore, max_revisioni, riassuntore, soglia_riassunto)`; archi `START → riassunto → router`; limite di ricorsione `+ 1`.

- [ ] **Step 1: test che falliscono** in `tests/test_grafo.py`. Lo helper `esegui` acquista `riassuntore=None` (→ `RiassuntoreFinto()`), `soglia_riassunto=100000` e `cronologia=()` (messaggi prima della domanda):
  - `test_sotto_soglia_nessun_riassunto`: `riassuntore.chiamate == []`, messaggi finali `[domanda, risposta]`.
  - `test_sopra_soglia_riassume(caplog)`: `cronologia=conversazione(4)`, `soglia_riassunto=1`, testo `"D5"`, agente `AIMessage("R5")` → il riassuntore riceve i contenuti `["D1", "R1", "D2", "R2"]`; messaggi finali: `SystemMessage(PREFISSO_RIASSUNTO + "riassunto di prova")` primo e unico `SystemMessage`, poi `"D3"`…`"R5"`; log `"riassunto: 4 messaggi riassunti, stima "`; il router (`RouterFinto`) riceve la cronologia compatta (nessun `"D1"`).
  - `test_sopra_soglia_senza_vecchi(caplog)`: `cronologia=conversazione(1)`, `soglia_riassunto=1` → nessuna chiamata, log `"niente da riassumere"`.
  - `test_secondo_riassunto_cumulativo`: `cronologia=[SystemMessage(PREFISSO_RIASSUNTO + "vecchio")] + conversazione(3)`, `soglia_riassunto=1` → il riassuntore riceve per primo il `SystemMessage` vecchio; nei messaggi finali c'è un solo `SystemMessage`, col testo nuovo.
  - `test_guasto_lascia_la_cronologia(caplog)` parametrizzato su `RiassuntoreFinto(errore=RuntimeError("guasto"))`, `RiassuntoreFinto(testo="")`, `RiassuntoreFinto(testo="   ")` → nessun `SystemMessage`, `"D1"` ancora presente, WARNING `"riassunto non disponibile"`.
  - `test_riassunto_e_revisione_nello_stesso_turno`: soglia 1, `cronologia=conversazione(3)`, `RevisoreFinto([False, True])`, agente `[AIMessage("bozza"), AIMessage("finale")]` → messaggi finali: un `SystemMessage`, nessuna `"bozza"`, ultimo `"finale"`.
  - Le chiamate esistenti a `build_graph` in `test_grafo.py` e `test_cli.py` passano `RiassuntoreFinto()` e `100000`.
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_grafo.py -q` → FAIL.
- [ ] **Step 3:** implementare il nodo secondo la specifica (`REMOVE_ALL_MESSAGES` da `langgraph.graph.message`, id del riassunto `str(uuid4())`).
- [ ] **Step 4:** `.venv\Scripts\python -m pytest -q` → PASS.

### Task 4: CLI

**Files:** Modify `src/assistente/cli.py`, `tests/test_cli.py`

**Interfaces:** Consumes `crea_riassuntore(llm)` (Task 2), `build_graph(...)` (Task 3), `Config.soglia_riassunto` (Task 1).

- [ ] **Step 1: test che falliscono:**
  - `test_main_passa_il_riassuntore`: come `test_main_passa_il_revisore`, con `crea_riassuntore` sostituito e `grafo_finto(..., riassuntore, soglia_riassunto)`; verifica `riassuntore` e `soglia_riassunto == 3000`. Aggiornare la firma di `grafo_finto` negli altri test di `main` e sostituirvi `assistente.cli.crea_riassuntore`.
  - `test_cronologia_compatta_al_turno_dopo`: grafo con soglia 1 e `RiassuntoreFinto()`; quattro turni con `esegui_turno` → la cronologia dopo il quarto comincia con il `SystemMessage` del riassunto; al quinto turno l'agente riceve per primo quel `SystemMessage`.
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_cli.py -q` → FAIL.
- [ ] **Step 3:** `main`: `build_graph(..., crea_revisore(llm), config.max_revisioni, crea_riassuntore(llm), config.soglia_riassunto)`.
- [ ] **Step 4:** `.venv\Scripts\python -m pytest -q` → PASS.

### Task 5: Prove reali con LM Studio

**Files:** Modify `tests/reale/test_lmstudio.py`

- [ ] **Step 1:** `esegui_domanda` passa `crea_riassuntore(llm)` e `config.soglia_riassunto`; accetta `cronologia` (messaggi prima della domanda, predefinito vuoto) e `soglia` (predefinito quella della configurazione); stampa i `prompt_tokens` della prima risposta dell'agente (`response_metadata["token_usage"]`) quando presenti.
- [ ] **Step 2:** nuove prove:
  - `test_riassunto_conserva_la_nota`: sessione con archivio vero e soglia 300: turni «Annota che il saldatore va pulito», «Che ore sono a Tokyo?», «Quanto fa 12 * 4?», poi «Che numero ha la nota che ho aggiunto?» → log `"messaggi riassunti"`, nessun `"riassunto non disponibile"`, risposta finale non vuota che contiene il numero della nota (letto dal `ToolMessage` di `aggiungi_nota` del primo turno); stampa tempo e testo del riassunto.
  - `test_system_message_in_testa`: cronologia `[SystemMessage(PREFISSO_RIASSUNTO + "L'utente ha chiesto l'ora a Roma: erano le 13:00.")]` + domanda «Quanto fa 2 + 3?» → risposta non vuota (nessun HTTP 400).
- [ ] **Step 3:** `.venv\Scripts\python -m pytest -q` → PASS (le prove `reale` restano escluse).
- [ ] **Step 4 (LM Studio attivo):** `.venv\Scripts\python -m pytest -m reale -v -s -k "riassunto or system_message"`, poi l'intera `-m reale` in background; annotare tempi, `prompt_tokens` osservati e se la soglia 3000 va confermata. Se un caso fallisce: fermarsi e riportare.

### Task 5b (2026-11-10): riassunto per concatenazione

Motivo: nelle prove reali il modello, chiamato a integrare il riassunto precedente, lo perde (specifica,
«Revisione del 2026-11-10»). Firma di `build_graph` e `RiassuntoreFinto` invariate.

**Files:** Modify `src/assistente/riassunto.py`, `src/assistente/grafo.py`, `tests/test_riassunto.py`,
`tests/test_grafo.py`, `tests/reale/test_lmstudio.py`

**Interfaces:** Produces `unisci(precedente: str, nuovo: str, limite_token: int) -> tuple[str, int]`.

- [ ] **Step 1: test che falliscono:**
  - `test_riassunto.py`: `test_unisci_concatena` (`unisci("a", "b", 100) == ("a\nb", 0)`, `unisci("", "b", 100) == ("b", 0)`); `test_unisci_toglie_le_righe_piu_vecchie` (tre righe da 40 caratteri, limite 20 → restano le ultime due, 1 tolta); `test_unisci_tiene_l_ultima_riga` (una riga da 400 caratteri, limite 1 → invariata, 0 tolte). `test_trascrivi` senza la riga del riassunto precedente; `test_prompt_regole` senza `"riassunto precedente"` e con `assert "riassunto precedente" not in PROMPT_RIASSUNTO.lower()`.
  - `test_grafo.py`: `test_secondo_riassunto_cumulativo` → il riassuntore riceve `["D1", "R1"]` (nessun `SystemMessage`), il riassunto finale è `PREFISSO_RIASSUNTO + "vecchio\nnuovo"`; `test_solo_riassunto_fra_i_vecchi` (`[riassunto] + conversazione(2) + [D]` sopra soglia → nessuna chiamata, `"niente da riassumere"`); `test_riassunto_troppo_lungo(caplog)` (precedente di 3 righe lunghe, soglia piccola → WARNING `"righe più vecchie"`, resta la riga nuova).
- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_riassunto.py tests/test_grafo.py -q` → FAIL.
- [ ] **Step 3:** implementare secondo la specifica (nodo punti 3–6, `unisci`, prompt e `trascrivi` senza riassunto precedente).
- [ ] **Step 4:** `.venv\Scripts\python -m pytest -q` → PASS.
- [ ] **Step 5: prove reali:** `test_riassunto_conserva_la_nota` diventa la sessione di sei turni della specifica (soglia 100; vincoli: «messaggi riassunti», nessun «non disponibile», numero nel riassunto finale, «saldatore» nella risposta a «Che cosa ti avevo chiesto di annotare?»; osservazione con `pytest.xfail`: numero nella risposta a «Che numero ha la nota che ho aggiunto?»). `.venv\Scripts\python -m pytest -m reale -v -s -k "riassunto or system_message"`, poi l'intera `-m reale`. Se un caso fallisce: fermarsi e riportare.

### Task 6: Documentazione, verifica, revisione, commit

**Files:** Modify `README.md`, `CLAUDE.md`, `docs/superpowers/2026-11-02-handoff.md`

- [ ] **Step 1:** README: sezione «Riassunto della cronologia» dopo «Revisore delle risposte» (grafo aggiornato, `RIASSUNTO_SOGLIA_TOKEN`, stima caratteri/4, turni tenuti, righe di log, limiti), variabile nell'elenco, diagnosi (`riassunto non disponibile`). Solo comandi verificati.
- [ ] **Step 2:** `CLAUDE.md`: `riassunto` nell'elenco dei moduli; nell'obiettivo una riga sul riassunto oltre `RIASSUNTO_SOGLIA_TOKEN`.
- [ ] **Step 3: prova manuale (LM Studio attivo):** PowerShell, `$env:LOG_LEVEL='INFO'; $env:RIASSUNTO_SOGLIA_TOKEN='300'`, quattro domande in pipe a `.venv\Scripts\python avvia.py` → riga `riassunto: ... messaggi riassunti`; Docker: `docker compose build` e `docker compose run --rm -T -e LOG_LEVEL=INFO -e RIASSUNTO_SOGLIA_TOKEN=300 assistente` con le stesse domande.
- [ ] **Step 4: verifica finale:** `.venv\Scripts\python -m pytest` → PASS; mostrare l'output.
- [ ] **Step 5: revisione** indipendente (superpowers:requesting-code-review) sul working tree; correzioni Critical/Important con test RED→GREEN.
- [ ] **Step 6: commit unico** dopo `git status` e `git diff`: `.env.example README.md CLAUDE.md src/assistente/config.py src/assistente/riassunto.py src/assistente/grafo.py src/assistente/cli.py tests/finti.py tests/test_config.py tests/test_riassunto.py tests/test_grafo.py tests/test_cli.py tests/reale/test_lmstudio.py docs/superpowers/specs/2026-11-10-riassunto-design.md docs/superpowers/plans/2026-11-10-riassunto.md docs/superpowers/2026-11-02-handoff.md`. Messaggio: `feat(grafo): riassunto della cronologia oltre una soglia di token`.
