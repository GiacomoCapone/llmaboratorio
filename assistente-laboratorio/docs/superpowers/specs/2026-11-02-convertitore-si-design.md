# Convertitore di unità SI: specifica

Data: 2026-11-02. Stato: approvata (2026-11-02).

## Contesto
Ciclo 2 di 6 (vedi `2026-11-02-calcolatrice-e-registro-design.md`). Strumento locale, aggiunto al
registro introdotto nel ciclo 1.

## Obiettivo
Uno strumento `converti_unita` che converte un valore fra unità del Sistema Internazionale con i loro
prefissi, in modo esatto (`Decimal`), e rifiuta in modo chiaro unità sconosciute, non SI o di grandezze
diverse.

## Fuori ambito
Unità non SI (ore, minuti, litri, tonnellate, ettari, km/h), unità imperiali, °F. Unità composte
(`m/s`, `N·m`, `kW·h`). Potenze diverse da aree e volumi di lunghezza. Differenze di temperatura.
Nomi estesi delle unità («chilometri»): il modello passa i simboli.

## Decisioni concordate
- Solo unità SI con prefissi: le 7 di base e le 22 derivate con nome.
- In più aree e volumi di lunghezza: `cm²`, `km²`, `mm³`, `m³`, …
- Temperatura: `K` (con prefissi) e `°C` (senza prefissi), conversione con lo scostamento 273,15.

## Unità
Ogni unità ha una grandezza (in italiano) e un fattore verso l'unità SI coerente; si converte solo fra
unità della stessa grandezza.

| Grandezza | Unità (simbolo, fattore) |
| --- | --- |
| lunghezza | `m` (1) |
| massa | `g` (0,001: l'unità SI è `kg`, i prefissi si applicano al grammo) |
| tempo | `s` |
| corrente elettrica | `A` |
| temperatura | `K` (1), `°C` (1, scostamento +273,15; nessun prefisso) |
| quantità di sostanza | `mol` |
| intensità luminosa | `cd` |
| angolo piano | `rad` |
| angolo solido | `sr` |
| frequenza | `Hz` |
| forza | `N` |
| pressione | `Pa` |
| energia | `J` |
| potenza | `W` |
| carica elettrica | `C` |
| tensione elettrica | `V` |
| capacità elettrica | `F` |
| resistenza elettrica | `Ω` |
| conduttanza elettrica | `S` |
| flusso magnetico | `Wb` |
| induzione magnetica | `T` |
| induttanza | `H` |
| flusso luminoso | `lm` |
| illuminamento | `lx` |
| attività (radionuclidi) | `Bq` |
| dose assorbita | `Gy` |
| dose equivalente | `Sv` |
| attività catalitica | `kat` |
| area | lunghezza al quadrato |
| volume | lunghezza al cubo |

`Hz` e `Bq`, come `Gy` e `Sv`, hanno la stessa dimensione ma grandezze diverse: non si convertono fra
loro (raccomandazione del BIPM).

Alias accettati: `ohm` per `Ω`; `degC` per `°C`; `u`, `µ` (U+00B5) e `μ` (U+03BC) per il prefisso micro.

## Prefissi
Tutti i 24 prefissi SI: `q` 10⁻³⁰, `r` 10⁻²⁷, `y` 10⁻²⁴, `z` 10⁻²¹, `a` 10⁻¹⁸, `f` 10⁻¹⁵, `p` 10⁻¹²,
`n` 10⁻⁹, `µ` 10⁻⁶, `m` 10⁻³, `c` 10⁻², `d` 10⁻¹, `da` 10¹, `h` 10², `k` 10³, `M` 10⁶, `G` 10⁹,
`T` 10¹², `P` 10¹⁵, `E` 10¹⁸, `Z` 10²¹, `Y` 10²⁴, `R` 10²⁷, `Q` 10³⁰.

## Lettura di un simbolo
- I simboli distinguono maiuscole e minuscole (`mW` milliwatt, `MW` megawatt). Spazi iniziali e finali ignorati.
- Aree e volumi: un'unità di lunghezza seguita da `²`, `2` o `^2` (`³`, `3`, `^3`). Il prefisso è elevato
  insieme all'unità: `cm²` = (0,01 m)² = 0,0001 m².
- Un simbolo si legge prima come unità senza prefisso; altrimenti come prefisso più unità. Un solo prefisso.
  Ogni combinazione prefisso + unità ammessa ha una sola lettura (verificato da un test su tutte le combinazioni).
- Non ammessi: prefisso su `°C`, prefisso su `kg` (`mkg`), doppio prefisso (`kkm`), potenza su unità che non
  sono lunghezze (`s²`).

## Definizione per il modello
- `name`: `converti_unita`; parametri `valore` (numero o stringa), `da` (stringa), `a` (stringa);
  `required: ["valore", "da", "a"]`.
- `description`: "Converte una misura fra unità del Sistema Internazionale (SI). Chiamalo SEMPRE quando
  l'utente chiede di convertire una misura, per esempio 'quanti metri sono 2,5 km' o '300 K in gradi
  Celsius'. Accetta solo simboli SI con prefisso (km, mg, µs, kPa, MW), aree e volumi come cm² o m³,
  K e °C; non accetta ore, litri, km/h né unità imperiali."
- `valore.description`: "Valore da convertire, per esempio 2.5 (punto o virgola decimale, senza
  separatore delle migliaia)."
- `da.description`: "Simbolo dell'unità di partenza, per esempio km."
- `a.description`: "Simbolo dell'unità di arrivo, per esempio m."

## Calcolo e risultato
- `valore`: numero JSON (non booleano) convertito con `Decimal(str(valore))`, oppure stringa con un numero
  decimale (virgola o punto, segno facoltativo, cifre `[0-9]`). Valori non finiti respinti.
- `risultato = (valore × fattore_da + scostamento_da − scostamento_a) / fattore_a`, in `localcontext` con 28
  cifre significative e `ROUND_HALF_EVEN`.
- Testo restituito: `<numero> <simbolo di arrivo come ricevuto, senza spazi esterni>`, con il numero nello
  stesso formato della calcolatrice (nessun esponente, nessuno zero finale, punto decimale).
  Esempi: `2,5 km → m` = `2500 m`; `1500 m → km` = `1.5 km`; `1 kg → g` = `1000 g`;
  `300 K → °C` = `26.85 °C`; `0 °C → K` = `273.15 K`; `1 m² → cm²` = `10000 cm²`;
  `1 m³ → mm³` = `1000000000 mm³`; `1 kPa → Pa` = `1000 Pa`; `1 µs → ns` = `1000 ns`.
- La funzione di formato è condivisa con la calcolatrice (nuovo modulo `strumenti/numeri.py`).

## Errori (tutti iniziano con `Errore:`)
| Caso | Messaggio |
| --- | --- |
| unità non riconosciuta | `Errore: unità non riconosciuta: '<simbolo>'. Sono ammessi solo simboli SI con prefisso, per esempio m, km, kg, mg, s, ms, A, K, °C, mol, cd, N, Pa, kPa, J, W, MW, Hz, V, Ω, e aree o volumi come cm² e m³.` |
| grandezze diverse | `Errore: non si può convertire '<da>' (<grandezza>) in '<a>' (<grandezza>): grandezze diverse.` |
| valore non numerico | `Errore: valore non numerico: '<valore>'.` |
| argomento mancante o di tipo sbagliato | `Errore: argomenti 'valore' (numero), 'da' e 'a' (simboli di unità) obbligatori.` |

Una temperatura sotto lo zero assoluto non è un errore (lo strumento converte, non valida la fisica).

## Registro
- `crea_strumenti` restituisce `ora_corrente`, `calcola`, `converti_unita`, in quest'ordine.
- Nomi duplicati: la costruzione del registro solleva `ValueError` con il nome ripetuto (errore di
  programmazione, non del modello). Rinviato dalla revisione del ciclo 1.

## Test automatici (senza modello)
- `tests/test_convertitore.py`: ogni esempio sopra; ogni grandezza almeno una volta; prefissi estremi
  (`1 Qm → qm` = 1 seguito da 60 zeri); tutti gli alias; maiuscole/minuscole (`1 MW → mW` = `1000000000 mW`);
  `valore` intero, decimale, stringa con virgola, negativo; ogni riga della tabella errori; respinti `h`,
  `min`, `L`, `l`, `t`, `ha`, `km/h`, `°F`, `mi`, `kkm`, `mkg`, `k°C`, `s²`, `KM`; `Hz → Bq` e `Gy → Sv`
  respinti come grandezze diverse; `valore` `true`, `"abc"`, `"1.000,5"`, `"nan"`, `"inf"` respinti; lettura
  univoca di ogni combinazione prefisso + unità.
- `tests/test_numeri.py`: il formato (spostato dai test della calcolatrice, che restano invariati).
- Registro: tre strumenti nell'ordine; nomi duplicati → `ValueError`.
- Grafo, con modello finto: una tool call `converti_unita` produce il ToolMessage atteso.

## Verifiche reali (marcatore `reale`, LM Studio attivo)
- `Quanti metri sono 2,5 km?` → `tool_call nome=converti_unita`, ToolMessage `2500 m`, risposta con `2500` o `2.500`.
- `Quanti gradi Celsius sono 300 K?` → ToolMessage `26.85 °C`, risposta con `26,85` o `26.85`.
- Le cinque prove esistenti (orologio e calcolatrice) devono continuare a passare con tre strumenti.
- Avvio manuale con `avvia.py`; Docker Compose se Docker Desktop è attivo.

## Documentazione
README: il convertitore nella sezione «Strumenti» (cosa accetta, cosa no, un esempio); esiti delle verifiche.
CLAUDE.md: il convertitore in «Obiettivo».

## Criteri di successo
- `python -m pytest` e `python -m pytest -m reale -v` verdi con `google/gemma-4-e2b`.
- Nessuna conversione fra grandezze diverse; nessuna unità non SI accettata.

## Limiti noti
- Il modello deve passare simboli corretti, maiuscole comprese: «KM» o «chilometri» producono un errore
  che elenca esempi validi, e il modello può riprovare entro `MAX_PASSAGGI`.
- Con un terzo strumento le definizioni crescono: la regola sulla risposta vuota del ciclo 1 resta
  necessaria e le prove reali verificano che basti.
