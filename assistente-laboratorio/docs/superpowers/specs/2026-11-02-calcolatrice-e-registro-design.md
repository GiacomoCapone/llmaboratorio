# Calcolatrice sicura e registro degli strumenti: specifica

Data: 2026-11-02. Stato: approvata (2026-11-02).

## Contesto
Primo di sei cicli (specifica → piano → implementazione) concordati il 2026-11-02 per i nuovi strumenti:

| Ciclo | Strumento | Esecuzione |
| --- | --- | --- |
| 1 | Calcolatrice sicura | locale |
| 2 | Convertitore di unità SI | locale |
| 3 | Giorni e scadenze (date ISO, festività da file locale) | locale |
| 4 | Meteo (Open-Meteo, senza chiave) | API pubblica |
| 5 | Catalogo (ricerca e dettaglio su JSON/CSV) | server MCP «archivio» |
| 6 | Note persistenti (SQLite: aggiunta, elenco, eliminazione) | server MCP «archivio» |

Questo ciclo introduce anche il registro degli strumenti, su cui si appoggiano i successivi.

## Problema
- Un modello da 2B sbaglia facilmente i conti fatti «a mente».
- Il grafo conosce l'orologio per nome (`grafo.py` importa definizione e controlla `fuso`): aggiungere
  strumenti così renderebbe il grafo sempre più lungo e accoppiato.

## Obiettivo
- Uno strumento `calcola` che valuta espressioni con le quattro operazioni, in modo esatto e senza `eval`.
- Un registro di strumenti: il grafo li esegue per nome senza conoscerne i dettagli.

## Fuori ambito
Potenze, modulo, funzioni (`sqrt`, `abs`, …), costanti, unità di misura, percentuali come operatore,
variabili, memoria dei risultati. Gli altri cinque strumenti. Messaggio di sistema.

## Decisioni concordate
- Solo `+ - * /`, parentesi, segno unario `+`/`-`.
- Aritmetica decimale esatta con `Decimal`; separatore decimale punto o virgola.
- Parser scritto a mano (tokenizzatore + discesa ricorsiva); nessuna nuova dipendenza.
- `strumenti` diventa un pacchetto con un registro; il controllo degli argomenti passa agli strumenti.

## Registro degli strumenti
Pacchetto `src/assistente/strumenti/`:

| File | Contenuto |
| --- | --- |
| `__init__.py` | `Strumento`, `crea_strumenti` |
| `orologio.py` | `NOME_ORA_CORRENTE`, `definizione_ora_corrente`, `ora_corrente`, `esegui_ora_corrente` |
| `calcolatrice.py` | `NOME_CALCOLA`, `DEFINIZIONE_CALCOLA`, `calcola`, `esegui_calcola` |

```python
@dataclass(frozen=True)
class Strumento:
    definizione: dict              # schema "type": "function" per il tool calling
    esegui: Callable[[dict], str]  # argomenti (già un dict) → risultato o "Errore: ..."

    @property
    def nome(self) -> str: ...     # definizione["function"]["name"]
```

`crea_strumenti(adesso: Callable[[], datetime], fuso_predefinito: str) -> dict[str, Strumento]`
restituisce `{"ora_corrente": ..., "calcola": ...}`, con le dipendenze legate dentro `esegui`.

L'orologio non cambia comportamento: `esegui_ora_corrente(args, adesso, fuso_predefinito)` contiene le
regole oggi in `grafo._esegui_strumento` (fuso assente, `null` o vuoto → predefinito; stringa → quel fuso;
altro → `Errore: argomento 'fuso' non testuale. ...`).

## Grafo
- `build_graph(llm, strumenti: dict[str, Strumento], max_passaggi: int)`: collega al modello le
  definizioni di tutti gli strumenti, nell'ordine del registro.
- Per ogni tool call:
  - nome non nel registro → `Errore: strumento sconosciuto: '<nome>'.`;
  - argomenti non oggetto → `Errore: argomenti non validi, atteso un oggetto JSON.`;
  - altrimenti `strumento.esegui(args)`;
  - eccezione imprevista dentro `esegui` → log `ERROR` con traccia e risultato
    `Errore: errore interno dello strumento '<nome>'.`; il turno prosegue.
- Argomenti non JSON (`invalid_tool_calls`): `Errore: argomenti non in formato JSON valido. Riprovare con un oggetto JSON.`
- Log `tool_call` / `tool_result` invariati. Nodi, instradamento, limite di passaggi, cronologia invariati.
- `cli.main()` costruisce il registro con `crea_strumenti(...)` e lo passa a `build_graph`.

### Risposta vuota dopo gli strumenti (aggiunto il 2026-11-02)
Prova reale: con due strumenti collegati `google/gemma-4-e2b` risponde ai risultati degli strumenti con
un solo token (risposta vuota, `finish_reason=stop`), in 3 esecuzioni su 3; con un solo strumento no.
Non dipende dall'ordine né da una singola frase; spariscono il problema accorciando entrambe le
descrizioni (ma l'orologio torna a chiedere il fuso), con ragionamento `low` (20–80 s per chiamata) o
richiamando il modello senza strumenti.

Regola nel nodo `modello`: se l'ultimo messaggio dello stato è un `ToolMessage` e la risposta del modello
non ha tool call (valide o non valide) e ha contenuto vuoto (stringa vuota o di soli spazi, o lista vuota),
la risposta è scartata e il modello è richiamato una sola volta **senza strumenti** sugli stessi messaggi;
si conserva il risultato di questa seconda chiamata, anche se vuoto. Log `WARNING`
`risposta vuota dopo gli strumenti: nuova chiamata senza strumenti`. `passaggi` non cambia.
Una risposta vuota a una domanda senza strumenti non è ripetuta.

## Calcolatrice
### Definizione per il modello
- `name`: `calcola`; parametro `espressione` (stringa), `required: ["espressione"]`.
- `description`: "Calcola il risultato esatto di un'espressione aritmetica con le quattro operazioni
  (+, -, *, /) e le parentesi. Chiamalo SEMPRE quando l'utente chiede un calcolo, invece di farlo a
  mente, per esempio 'quanto fa 12,5 * 4' o '(3 + 7) / 4'. Per le percentuali scrivi la moltiplicazione,
  per esempio 50 * 20 / 100."
- `espressione.description`: "Espressione da calcolare, per esempio (3 + 7) / 4. Numeri con il punto o
  la virgola decimale; niente unità di misura, simboli di percentuale o funzioni."

### Grammatica
```
espressione := termine (("+" | "-") termine)*
termine     := fattore (("*" | "/") fattore)*
fattore     := ("+" | "-") fattore | numero | "(" espressione ")"
numero      := cifre ([.,] cifre)?        cifre := [0-9]+
```
Spazi e tabulazioni ignorati. Operatori associativi a sinistra (`8 - 3 - 2` = 3, `8 / 4 / 2` = 1).
Ogni numero diventa `Decimal` dal suo testo (virgola sostituita dal punto).

### Calcolo e risultato
- `localcontext` con precisione 28 cifre significative, arrotondamento `ROUND_HALF_EVEN`.
- Risultato in notazione decimale semplice, senza zeri finali né esponente, separatore punto:
  `0.1 + 0.2` → `0.3`; `10 / 4` → `2.5`; `2,50 * 2` → `5`; `1 / 3` → `0.3333333333333333333333333333`;
  `100 * 10` → `1000`; un risultato zero (anche `-0`) → `0`.
- `calcola(espressione: str) -> str` restituisce il risultato o un testo `Errore: ...`; non solleva eccezioni.

### Errori (tutti iniziano con `Errore:`)
| Caso | Messaggio |
| --- | --- |
| vuota o solo spazi | `Errore: espressione vuota.` |
| più di 200 caratteri | `Errore: espressione troppo lunga (massimo 200 caratteri).` |
| carattere non ammesso | `Errore: carattere non ammesso '<c>' in posizione <n>. Sono ammessi numeri, + - * / e parentesi.` |
| sintassi | `Errore: espressione non valida: <dettaglio>.` (es. `parentesi ')' mancante`, `atteso un numero o '(' in posizione <n>`, `testo inatteso in posizione <n>`) |
| divisione per zero, anche `0 / 0` | `Errore: divisione per zero.` |
| argomento `espressione` assente o non stringa | `Errore: argomento 'espressione' mancante o non testuale.` |

Le posizioni sono contate da 1 sul testo ricevuto. Esempi respinti: `2 ** 3`, `2 ^ 3`, `1e5`, `0x10`,
`abs(-2)`, `__import__('os')`, `3.5.1`, `.5`, `5.`, `2 3`, `(2 + 3`, `2 + 3)`.

## Test automatici (senza modello attivo)
- Calcolatrice (`tests/test_calcolatrice.py`): precedenza (`2 + 3 * 4` = 14), associatività a sinistra,
  parentesi, segno unario (`-3 + 5`, `-(2 + 3)`, `--2`, `2 * -3`), decimali esatti, virgola, formato
  del risultato (esempi sopra), ogni riga della tabella errori, gli esempi respinti, il limite di 200
  caratteri (200 ammessi, 201 respinti), `esegui_calcola` con argomenti mancanti o non testuali.
- Orologio (`tests/test_orologio.py`, ex `test_strumenti.py`): test esistenti più quelli spostati dal
  grafo sulle regole di `fuso`, ora su `esegui_ora_corrente`.
- Registro (`tests/test_strumenti.py`): chiavi `ora_corrente` e `calcola`; per ogni voce la chiave
  coincide con `nome` e con `definizione["function"]["name"]`.
- Grafo, con modello finto: tool call `calcola` → ToolMessage `14`; due strumenti diversi nella stessa
  risposta; strumento sconosciuto; strumento finto che solleva → `Errore: errore interno ...`, turno non
  interrotto, risposta finale del modello presente; i test esistenti adattati alla nuova firma.

## Verifiche reali (marcatore `reale`, LM Studio attivo)
- `Quanto fa 12,5 * 4?` → nel log `tool_call nome=calcola`, un ToolMessage `50`, risposta finale con `50`.
- `Quanto fa (3 + 7) / 4?` → ToolMessage `2.5`, risposta con `2,5` o `2.5`.
- I tre test reali dell'orologio restano: con due strumenti il modello deve ancora scegliere l'orologio.
- Avvio manuale con `python -m assistente`; con Docker Compose se Docker Desktop è attivo.

## Documentazione
- README: sezione «Strumenti» con orologio e calcolatrice, cosa accetta e un esempio d'errore; esiti
  delle verifiche, solo comandi eseguiti.
- CLAUDE.md: in «Struttura» `strumenti/` come pacchetto; in «Obiettivo» la calcolatrice sicura.

## Criteri di successo
- `python -m pytest` verde; `python -m pytest -m reale -v` verde con `google/gemma-4-e2b`.
- Nessuna espressione, nemmeno malevola, può eseguire codice: il testo è solo tokenizzato e analizzato.
- Il grafo non importa nessuno strumento specifico.

## Limiti noti
- Risultati oltre 28 cifre significative sono arrotondati.
- Il modello può scrivere l'espressione in forme non ammesse (`x` per moltiplicare, `%`): riceve un
  errore che elenca i simboli ammessi e può riprovare entro `MAX_PASSAGGI`.
