# Calendario (giorni e scadenze): specifica

Data: 2026-11-03. Stato: in revisione.

## Contesto
Ciclo 3 di 6 (vedi `2026-11-02-calcolatrice-e-registro-design.md`). Strumento locale, aggiunto al
registro come quarto strumento. Nessuna dipendenza nuova (solo `datetime` e `json` della libreria standard).

## Obiettivo
Uno strumento `calendario` che, su date ISO del calendario gregoriano, calcola la differenza fra due date
(giorni di calendario e giorni lavorativi) e la data che si ottiene aggiungendo N giorni di calendario o
lavorativi, tenendo conto di weekend, festività nazionali italiane, Pasqua e Pasquetta (calcolate) e del
santo patrono di una città configurabile.

## Fuori ambito
- La data di oggi: lo strumento vuole sempre date esplicite. Per «oggi» il modello chiama prima
  `ora_corrente` (scelta concordata).
- Festività storiche (lo strumento applica le festività del file a ogni anno dal 1583), festività di altri
  paesi, ponti e chiusure di un anno preciso.
- Ore, settimane, mesi come unità di somma («fra 2 mesi»).
- Nomi estesi delle date («25 dicembre»): il modello passa `AAAA-MM-GG`.

## Decisioni concordate
- Un solo strumento con il parametro `operazione` (`differenza` | `aggiungi`).
- Festività in un file JSON locale; Pasqua e Pasquetta calcolate; patrono scelto con `CITTA_PATRONO`
  da una tabella di città nel file (predefinita nell'esempio: Pordenone).
- Giorni lavorativi: da lunedì a venerdì, esclusi i festivi.
- Convenzione: **partenza esclusa, arrivo incluso**, in entrambe le direzioni.
- Parametri estranei all'operazione ignorati senza errore.

## File delle festività
`src/assistente/strumenti/festivita.json` (dentro il pacchetto: entra nell'immagine Docker con `src/` e
si trova a partire da `Path(__file__)`, qualunque sia la cartella di avvio). Contenuto iniziale:

```json
{
  "nazionali": {
    "01-01": "Capodanno",
    "01-06": "Epifania",
    "04-25": "Festa della Liberazione",
    "05-01": "Festa del Lavoro",
    "06-02": "Festa della Repubblica",
    "08-15": "Ferragosto",
    "11-01": "Ognissanti",
    "12-08": "Immacolata Concezione",
    "12-25": "Natale",
    "12-26": "Santo Stefano"
  },
  "patroni": {
    "Pordenone": {"data": "04-25", "santo": "San Marco"},
    "Udine": {"data": "07-12", "santo": "Santi Ermacora e Fortunato"},
    "Trieste": {"data": "11-03", "santo": "San Giusto"},
    "Venezia": {"data": "04-25", "santo": "San Marco"},
    "Roma": {"data": "06-29", "santo": "Santi Pietro e Paolo"}
  }
}
```

Validazione alla lettura: oggetto con le chiavi `nazionali` (mese-giorno `MM-GG` → nome non vuoto) e
`patroni` (città → `data` `MM-GG` e `santo` non vuoto). `MM-GG` deve essere una data valida in ogni anno
(`02-29` respinto).

## Pasqua e festività di un anno
- `pasqua(anno)`: algoritmo gregoriano anonimo (Meeus/Jones/Butcher), anni 1583–9999.
  Valori di controllo: 1583-04-10, 2024-03-31, 2025-04-20, 2026-04-05, 2038-04-25, 2285-03-22.
- Pasquetta = Pasqua + 1 giorno.
- `festivita_dell_anno(anno) -> dict[date, str]`: nazionali, `Pasqua`, `Lunedì dell'Angelo (Pasquetta)`,
  e il patrono come `<santo> (patrono di <città>)`. Più ricorrenze nello stesso giorno formano una sola voce,
  unite da `, ` nell'ordine nazionali → Pasqua/Pasquetta → patrono. Esempi:
  `2026-04-25` a Pordenone → `Festa della Liberazione, San Marco (patrono di Pordenone)`;
  `2038-04-25` → `Festa della Liberazione, Pasqua, San Marco (patrono di Pordenone)`.
- Un giorno è lavorativo se è da lunedì a venerdì e non è nelle festività del suo anno.

## Configurazione
- `config.py`: nuovo campo `citta_patrono: str | None` da `CITTA_PATRONO` (facoltativa; assente o vuota
  → `None`, nessun patrono). `carica_config` non legge il file JSON.
- `crea_strumenti(adesso, fuso_predefinito, citta_patrono=None)` carica il file una volta sola con
  `carica_festivita(citta_patrono)`.
- La città si confronta ignorando maiuscole e spazi esterni; nel testo si usa il nome scritto nel file
  (`pordenone` → `Pordenone`).
- Errori, come `ErroreConfigurazione` (già gestito da `cli.py` all'avvio):
  - città sconosciuta: `Città del patrono sconosciuta: '<valore>'. Città disponibili: Pordenone, Roma,
    Trieste, Udine, Venezia (file <percorso>).` (elenco in ordine alfabetico);
  - file mancante, JSON malformato o struttura non valida: `File delle festività non valido: <percorso>:
    <dettaglio>.`
- `.env.example`: `CITTA_PATRONO=Pordenone`, con un commento che rimanda alle città del file.

## Definizione per il modello
- `name`: `calendario`; parametri `operazione` (stringa, `enum: ["differenza", "aggiungi"]`), `data`
  (stringa), `data_fine` (stringa), `giorni` (intero), `lavorativi` (booleano);
  `required: ["operazione", "data"]`.
- `description` con città configurata (`<Città>` è il nome scritto nel file):
  "Calcola con le date del calendario italiano, tenendo conto di weekend e festività (nazionali, Pasqua,
  Pasquetta e patrono di <Città>). Operazione 'differenza': giorni di calendario e giorni lavorativi fra
  'data' e 'data_fine'. Operazione 'aggiungi': la data che si ottiene aggiungendo 'giorni' a 'data'
  (negativi per andare indietro); con 'lavorativi' true conta solo i giorni lavorativi. Le date sono nel
  formato AAAA-MM-GG: per oggi chiama prima ora_corrente. Chiamalo SEMPRE per domande su giorni
  lavorativi, scadenze o quanti giorni mancano a una data."
- `description` senza città: identica, con `(nazionali, Pasqua e Pasquetta)` al posto di
  `(nazionali, Pasqua, Pasquetta e patrono di <Città>)`.
- `operazione.description`: "'differenza' oppure 'aggiungi'."
- `data.description`: "Data di partenza, nel formato AAAA-MM-GG."
- `data_fine.description`: "Solo per 'differenza': data di arrivo, nel formato AAAA-MM-GG."
- `giorni.description`: "Solo per 'aggiungi': numero di giorni da aggiungere, negativo per andare indietro."
- `lavorativi.description`: "Solo per 'aggiungi': true per contare solo i giorni lavorativi. Facoltativo,
  predefinito false."

## Argomenti
| Argomento | Accettato | Respinto |
| --- | --- | --- |
| `operazione` | `differenza`, `aggiungi`, ignorando maiuscole e spazi esterni | ogni altro valore o tipo |
| `data`, `data_fine` | stringa `AAAA-MM-GG` esatta (spazi esterni ignorati), data esistente, anno 1583–9999 | `2026-2-5`, `05/02/2026`, `2026-02-30`, `oggi`, `1582-12-31`, non stringhe |
| `giorni` | intero JSON; numero JSON con valore intero (`10.0`); stringa `[+-]?[0-9]+` (`"10"`, `"-5"`) | `10.5`, `"dieci"`, `"10.0"`, booleani |
| `lavorativi` | `true`/`false`; stringhe `"true"`/`"false"` ignorando maiuscole; assente o `null` → falso | ogni altro valore |

Gli argomenti non richiesti dall'operazione (`giorni`/`lavorativi` con `differenza`, `data_fine` con
`aggiungi`) sono ignorati senza essere validati.

## Calcolo
- Giorni di calendario di `differenza` = `data_fine − data` (negativo se `data_fine` precede `data`).
- Intervallo considerato (partenza esclusa, arrivo incluso): `(data, data_fine]` in avanti,
  `[data_fine, data)` all'indietro, vuoto se le date coincidono. I giorni lavorativi di `differenza` sono
  quelli lavorativi dell'intervallo, con il segno dei giorni di calendario; le festività elencate sono quelle
  che cadono nell'intervallo (anche di sabato o domenica), in ordine di data.
- `aggiungi` senza lavorativi: `data + giorni`. Con lavorativi: si avanza (o si arretra, se `giorni < 0`) di
  un giorno alla volta contando solo i lavorativi, finché il conteggio raggiunge `|giorni|`; la data di arrivo
  è quindi sempre lavorativa. `giorni = 0` restituisce `data` (anche se festiva).
- Coerenza: per ogni `data` e `N`, `differenza(data, aggiungi(data, N, lavorativi))` dà `N` giorni lavorativi.
- Limiti: `differenza` con le date distanti più di 36525 giorni (100 anni) e `aggiungi` lavorativo con
  `|giorni| > 25000` sono respinti; una data di arrivo fuori dagli anni 1583–9999 è respinta (controllata
  prima di costruire la data, senza eccezioni di overflow).

## Risultato
Giorni della settimana in italiano, minuscoli: lunedì, martedì, mercoledì, giovedì, venerdì, sabato, domenica.

- `differenza`:
  `dal <data> (<giorno>) al <data_fine> (<giorno>): <n> giorni di calendario, <m> lavorativi; <festività>`,
  dove `<festività>` è
  - `festività nell'intervallo: <AAAA-MM-GG> <nome>, <AAAA-MM-GG> <nome>, ...` (voci separate da `, `)
    se sono da 1 a 15;
  - `<k> festività nell'intervallo` se sono più di 15;
  - `nessuna festività nell'intervallo` se non ce ne sono.

  Esempio: `dal 2026-12-01 (martedì) al 2026-12-31 (giovedì): 30 giorni di calendario, 20 lavorativi;
  festività nell'intervallo: 2026-12-08 Immacolata Concezione, 2026-12-25 Natale, 2026-12-26 Santo Stefano`.
- `aggiungi`: `<data> (<giorno>) <+|-> <|giorni|> <giorni|giorno>[ lavorativi|lavorativo] = <arrivo> (<giorno>)`
  (`giorno`/`lavorativo` al singolare per 1; `+` per 0). Esempi:
  `2026-12-18 (venerdì) + 10 giorni lavorativi = 2027-01-05 (martedì)`;
  `2026-12-18 (venerdì) - 1 giorno = 2026-12-17 (giovedì)`;
  `2026-12-18 (venerdì) + 0 giorni = 2026-12-18 (venerdì)`.

## Errori (tutti iniziano con `Errore:`)
`esegui_calendario` non solleva eccezioni.

| Caso | Messaggio |
| --- | --- |
| operazione mancante o non valida | `Errore: operazione non valida: '<valore>'. Usare 'differenza' oppure 'aggiungi'.` |
| `data` mancante | `Errore: l'argomento 'data' (AAAA-MM-GG) è obbligatorio.` |
| `data_fine` mancante con `differenza` | `Errore: l'operazione 'differenza' richiede 'data_fine' (AAAA-MM-GG).` |
| data non valida (`data` o `data_fine`) | `Errore: data non valida: '<valore>'. Usare il formato AAAA-MM-GG con un anno fra 1583 e 9999; per la data di oggi chiamare prima ora_corrente.` |
| `giorni` mancante con `aggiungi` | `Errore: l'operazione 'aggiungi' richiede 'giorni' (numero intero).` |
| `giorni` non intero | `Errore: 'giorni' deve essere un numero intero: '<valore>'.` |
| `lavorativi` non valido | `Errore: 'lavorativi' deve essere true o false: '<valore>'.` |
| intervallo troppo lungo | `Errore: intervallo troppo lungo per contare i giorni lavorativi (massimo 100 anni).` |
| data di arrivo fuori intervallo | `Errore: la data risultante è fuori dagli anni 1583-9999.` |

Un argomento `null` vale come mancante.

## Moduli
- `strumenti/festivita.py` (funzioni pure): `pasqua(anno)`, `carica_festivita(citta, percorso=...)`
  → oggetto `Festivita` con il nome della città (o `None`) e il metodo `dell_anno(anno) -> dict[date, str]`
  (con cache per anno), `lavorativo(giorno)`.
- `strumenti/calendario.py`: `definizione_calendario(citta)`, `differenza(...)`, `aggiungi(...)`,
  `esegui_calendario(args, festivita)`.
- `strumenti/__init__.py`: `crea_strumenti` riceve `citta_patrono` e registra `calendario` per quarto.
- `cli.py`: passa `config.citta_patrono` a `crea_strumenti`.

## Registro
`crea_strumenti` restituisce `ora_corrente`, `calcola`, `converti_unita`, `calendario`, in quest'ordine.

## Test automatici (senza modello)
- `tests/test_festivita.py`: `pasqua` sui valori di controllo; Pasquetta; festività di un anno con e senza
  patrono; voci unite (2026-04-25 e 2038-04-25 a Pordenone); città con maiuscole e spazi; città assente;
  città sconosciuta (messaggio con l'elenco); file mancante, JSON malformato, struttura non valida, `02-29`;
  `lavorativo` su feriale, sabato, domenica, festivo, Pasquetta.
- `tests/test_calendario.py`: gli esempi della sezione «Risultato»; differenza negativa (`[data_fine, data)`);
  date uguali; differenza senza festività e con più di 15; `aggiungi` avanti e indietro, con e senza
  lavorativi, `giorni = 0`, singolare; coerenza `differenza(aggiungi(...))` su un campione di date e di N
  positivi e negativi; limiti (100 anni, 25000, anni fuori intervallo); ogni riga delle tabelle «Argomenti»
  ed «Errori»; parametri estranei ignorati; descrizioni confrontate parola per parola con questa specifica,
  con e senza città.
- `tests/test_config.py`: `CITTA_PATRONO` presente, assente, vuota.
- `tests/test_strumenti.py`: quattro strumenti nell'ordine; città sconosciuta → `ErroreConfigurazione`.
- `tests/test_grafo.py`, con modello finto: una tool call `calendario` produce il ToolMessage atteso.

## Verifiche reali (marcatore `reale`, LM Studio attivo, `CITTA_PATRONO=Pordenone`)
- `Quanti giorni lavorativi ci sono dal 1° al 31 dicembre 2026?` → tool call `calendario` con
  `operazione=differenza`, ToolMessage con `20 lavorativi`, risposta con `20`.
- `Che data è 10 giorni lavorativi dopo il 18 dicembre 2026?` → tool call `calendario` con
  `operazione=aggiungi` e `lavorativi` vero, ToolMessage con `2027-01-05`, risposta con `5 gennaio 2027`
  o `2027-01-05`.
- Catena, due formulazioni; in entrambe tool call `ora_corrente` e poi `calendario`, ToolMessage di
  `calendario` con la data di oggi (fuso predefinito) + 30 giorni:
  - `Che giorno sarà fra 30 giorni?`: fallimento atteso e documentato (`xfail`), perché con
    `google/gemma-4-e2b` e contesto nuovo il modello chiede la data senza chiamare strumenti;
  - `Che giorno sarà tra 30 giorni a partire da oggi?`: deve passare.
- Le sette prove esistenti devono continuare a passare con quattro strumenti.
- Se una prova fallisce: fermarsi, diagnosticare con il log e riportare prima di cambiare descrizioni o
  specifica.
- Avvio manuale con `avvia.py`; Docker Compose se Docker Desktop è attivo.

## Documentazione
- README: lo strumento nella sezione «Strumenti» (operazioni, convenzione di conteggio, un esempio),
  `CITTA_PATRONO` nella configurazione, come aggiungere una città al file, esiti delle verifiche.
- `.env.example`: `CITTA_PATRONO`.
- CLAUDE.md: il calendario in «Obiettivo» (in commit solo la propria modifica, costruita sulla versione di
  `HEAD`).

## Criteri di successo
- `python -m pytest` e `python -m pytest -m reale -v` tutte passate, salvo la catena senza «oggi» segnata `xfail` con `google/gemma-4-e2b`.
- Nessuna data non ISO accettata; conteggi coerenti fra `differenza` e `aggiungi`.

## Limiti noti
- Per «quanti giorni lavorativi ci sono a dicembre» il modello deve partire dall'ultimo giorno del mese
  precedente; partendo dal 1° il primo giorno non è contato (convenzione concordata).
- Per «oggi» servono due chiamate (`ora_corrente`, poi `calendario`) e con `google/gemma-4-e2b` la
  catena dipende dalla formulazione: riesce se la domanda nomina «oggi» o se la data è già nella
  conversazione; altrimenti il modello può chiedere la data o inventarla (misurato il 2026-11-03).
- Con un quarto strumento le definizioni crescono: la regola sulla risposta vuota del ciclo 1 resta
  necessaria e le prove reali verificano che basti.
