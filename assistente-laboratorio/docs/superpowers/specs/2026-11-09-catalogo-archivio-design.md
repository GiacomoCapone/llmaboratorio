# Catalogo dell'inventario (server MCP «archivio»): specifica

Data: 2026-11-09. Stato: in revisione.

## Contesto
Ciclo 5 di 6 (vedi `2026-11-02-calcolatrice-e-registro-design.md`). È il primo ciclo con MCP: un server
«archivio», avviato via stdio come sottoprocesso dell'assistente nello stesso container, espone la
ricerca e il dettaglio sull'inventario del laboratorio. Nel ciclo 6 lo stesso server ospiterà le note
persistenti (SQLite). L'assistente resta sincrono: l'asincronia di MCP è confinata in un solo modulo
client, che trasforma gli strumenti del server in voci del registro `Strumento`; il grafo non cambia.

## Obiettivo
Rispondere a domande come «Abbiamo dei multimetri? Dove sono?», «Quanti saldatori ci sono?»,
«Che cosa c'è fra gli strumenti di misura?» e «Dammi i dettagli di MIS-001» con dati presi da un file
CSV dell'inventario, tramite due strumenti MCP: `cerca_inventario` e `dettaglio_articolo`.

## Fuori ambito
- Note e SQLite (ciclo 6), volumi Docker.
- Scrittura o modifica dell'inventario, stato degli articoli, prestiti.
- Ricerca approssimata (tolleranza agli errori di battitura).
- Trasporti MCP diversi da stdio, risorse e prompt MCP, `langchain-mcp-adapters`.
- Variabile d'ambiente per il percorso del CSV; formato JSON per i dati.
- Riavvio automatico del server durante la sessione.

## Decisioni concordate
- Contenuto: inventario del laboratorio (attrezzature e componenti); dati di esempio creati nel ciclo.
- Formato: un solo file CSV (UTF-8, separatore `;`), dentro il pacchetto del server.
- Colonne: `codice`, `nome`, `categoria`, `quantita`, `collocazione`, `descrizione`. Nessuno stato;
  il catalogo è in sola lettura.
- Ricerca: testo libero senza distinzione di maiuscole e accenti, parole in AND, filtro facoltativo per
  categoria esatta, al massimo 10 risultati con l'indicazione dei restanti.
- Due strumenti MCP: `cerca_inventario(testo?, categoria?)` e `dettaglio_articolo(codice)`.
- Architettura A: pacchetto server `src/archivio/` separato; un client con sessione MCP persistente in
  un thread dedicato (`assistente/mcp_client.py`); schemi e descrizioni letti dal server.
- Se l'archivio non parte all'avvio, l'assistente si ferma con un messaggio chiaro (come per un modello
  non trovato o una città del patrono sconosciuta).
- Gli errori di argomento sono testi `Errore: ...` restituiti come risultato normale dello strumento,
  non errori del protocollo MCP.

## Dipendenza
- `mcp==2.3.0` (ultima versione su PyPI al 2026-11-09), con le dipendenze transitive fissate in
  `requirements.txt`. Motivo: SDK ufficiale del protocollo, per il server (`MCPServer`) e per il client
  (`stdio_client`, `ClientSession`).
- Verificato il 2026-11-09 con un'installazione di prova fuori dal progetto: `mcp==2.3.0` aggiunge 17
  pacchetti (`attrs`, `cffi`, `click`, `cryptography`, `jsonschema`, `jsonschema-specifications`,
  `mcp-types`, `opentelemetry-api`, `pycparser`, `PyJWT`, `python-multipart`, `pywin32` solo su
  Windows, `referencing`, `rpds-py`, `sse-starlette`, `starlette`, `uvicorn`), in gran parte per i
  trasporti HTTP e l'autenticazione, che qui non si usano; l'SDK non offre un'installazione ridotta.
  `pywin32` va fissato con il marcatore `; sys_platform == "win32"`.
- API 2.x verificata con un prototipo usa e getta: il server è `mcp.server.MCPServer` (FastMCP è stato
  rinominato), con `MCPServer("archivio", log_level="WARNING")`, il decoratore
  `@server.tool(description=...)` e `server.run("stdio")`; le descrizioni dei parametri si danno con
  `Annotated[..., Field(description=...)]`. Il client usa `mcp.client.stdio.stdio_client(
  StdioServerParameters(command, args, env), errlog=<file>)` e `mcp.ClientSession`; gli attributi sono
  `tool.input_schema` e `risultato.is_error`. `env` si aggiunge a un sottoinsieme sicuro dell'ambiente,
  quindi `PYTHONPATH` va passato esplicitamente.

## Dati: `src/archivio/inventario.csv`
- UTF-8 (senza BOM; un BOM eventuale è tollerato in lettura), separatore `;`, prima riga di intestazione
  con le sei colonne nell'ordine sopra; campi fra virgolette ammessi secondo il modulo `csv`.
- Circa 25 articoli in 7 categorie, con codici a prefisso per categoria:
  | Prefisso | Categoria |
  | --- | --- |
  | `MIS` | strumenti di misura |
  | `ALI` | alimentatori |
  | `PAS` | componenti passivi |
  | `MCU` | schede e microcontrollori |
  | `CAV` | cavi e connettori |
  | `ATT` | attrezzi |
  | `SIC` | sicurezza |
- Nei dati di esempio: `MIS-001` è un multimetro digitale (quantità maggiore di 1, collocazione
  esplicita) e almeno un articolo ha quantità 0. Il limite di 10 risultati si prova nei test con un CSV
  dedicato, non con i dati di esempio.

### Validazione al caricamento
Il server carica e valida il file all'avvio. Errori (ognuno con il numero di riga del file, contando
l'intestazione come riga 1):
- intestazione diversa dalle sei colonne attese;
- riga con un numero di campi diverso da sei;
- `codice`, `nome`, `categoria` o `collocazione` vuoti dopo la pulizia degli spazi;
- `codice` ripetuto (confronto senza distinzione di maiuscole);
- `quantita` non intera o negativa.
I campi sono ripuliti dagli spazi iniziali e finali; `descrizione` può essere vuota. Con un errore il
server non parte: scrive su stderr `Errore: inventario non valido, riga N: <motivo>.` ed esce con
codice 1. Il client lo rileva come avvio fallito (vedi sotto).

## Strumenti MCP

### Normalizzazione per i confronti
`normalizza(t)`: `unicodedata.normalize("NFD", t)`, rimozione dei segni combinanti, `casefold()`.
Si applica sia ai campi sia a ciò che arriva dal modello.

### `cerca_inventario`
Descrizione (fissata alla lettera):
> Cerca nell'inventario del laboratorio (strumenti, componenti, attrezzi) per parole e/o categoria e
> restituisce codice, nome, quantità e collocazione degli articoli trovati. Chiamalo SEMPRE quando
> l'utente chiede se in laboratorio c'è qualcosa, quanti pezzi ci sono o dove si trova.

Parametri (entrambi facoltativi, testo o `null`, predefinito `null`, trattato come stringa vuota:
i modelli piccoli passano spesso `null` per i parametri facoltativi):
- `testo` — «Parole da cercare nel nome, nella categoria, nella descrizione o nella collocazione,
  per esempio multimetro.»
- `categoria` — «Nome esatto di una categoria, per esempio strumenti di misura.»

Comportamento:
1. Pulizia degli spazi; ciascun parametro più lungo di 100 caratteri → errore.
2. Entrambi vuoti → errore.
3. Se `categoria` non è vuota, deve coincidere (dopo `normalizza`) con una categoria dei dati;
   altrimenti errore con l'elenco delle categorie in ordine alfabetico.
4. `testo` è diviso sugli spazi in parole. Per una parola normalizzata di almeno 4 caratteri si toglie
   l'ultimo carattere (radice approssimata, così singolare e plurale italiani si equivalgono:
   `multimetri` → `multimetr` trova «Multimetro»; `cavi` → `cav` trova «Cavo»). Un articolo è trovato se
   ogni parola (o radice) è sottostringa di almeno uno fra `nome`, `categoria`, `descrizione`,
   `collocazione` normalizzati.
5. Risultati in ordine di codice (confronto normalizzato); se ne mostrano al massimo 10.

Risultato:
```
Trovati 3 articoli:
- MIS-001 — Multimetro digitale — 4 pezzi — Armadio A, ripiano 2
- MIS-002 — ...
- MIS-003 — ...
```
- Intestazione `Trovato 1 articolo:` oppure `Trovati N articoli:` (N = totale, anche oltre 10).
- Quantità: `1 pezzo`, altrimenti `N pezzi` (anche `0 pezzi`).
- Oltre 10: ultima riga `(altri M risultati: restringere la ricerca)`.
- Nessun articolo (non è un errore): `Nessun articolo trovato per «<testo>».`, oppure con la sola
  categoria `Nessun articolo trovato nella categoria «<categoria>».`, oppure con entrambi
  `Nessun articolo trovato per «<testo>» nella categoria «<categoria>».` (valori ripuliti, come scritti
  dal modello).

### `dettaglio_articolo`
Descrizione (fissata alla lettera):
> Restituisce tutti i dati di un articolo dell'inventario del laboratorio dato il suo codice, per
> esempio MIS-001. Usalo dopo cerca_inventario o quando l'utente indica un codice.

Parametro obbligatorio `codice` (testo) — «Codice dell'articolo, per esempio MIS-001.»

Comportamento: pulizia degli spazi; vuoto → errore; più lungo di 100 caratteri → errore; ricerca senza
distinzione di maiuscole. Risultato, sei righe:
```
Codice: MIS-001
Nome: Multimetro digitale
Categoria: strumenti di misura
Quantità: 4
Collocazione: Armadio A, ripiano 2
Descrizione: Fluke 115: tensione, corrente, resistenza, continuità
```
Con descrizione vuota la riga è `Descrizione: (nessuna)`.

Le descrizioni sono fissate alla lettera: dopo ogni modifica si rilanciano le prove reali.

### Errori (tutti iniziano con `Errore:`)
| Caso | Messaggio |
| --- | --- |
| `testo` e `categoria` vuoti | `Errore: indicare un testo da cercare o una categoria.` |
| un parametro oltre 100 caratteri | `Errore: testo troppo lungo (massimo 100 caratteri).` |
| categoria sconosciuta | `Errore: categoria sconosciuta 'X'. Categorie: a, b, c.` |
| `codice` vuoto | `Errore: indicare il codice dell'articolo, per esempio MIS-001.` |
| codice sconosciuto | `Errore: nessun articolo con codice 'X'.` |

Gli argomenti di tipo sbagliato o mancanti sono respinti dalla validazione di `MCPServer` con `is_error`;
il client li presenta come `Errore: <testo del server>` (vedi sotto).

## Moduli del server: `src/archivio/`
- `inventario.py`: logica pura, senza MCP. `Articolo` (dataclass immutabile), `ErroreInventario`,
  `carica(percorso) -> Inventario`, e sull'inventario `cerca(testo, categoria) -> str` e
  `dettaglio(codice) -> str`, che restituiscono il testo del risultato o dell'errore.
- `server.py`: crea il server `MCPServer` chiamato `archivio`, carica l'inventario del pacchetto e dichiara i
  due strumenti con le descrizioni sopra (le descrizioni dei parametri con
  `Annotated[..., Field(description=...)]`). Il livello di log del server è `WARNING`, così le
  richieste normali non scrivono sul terminale.
- `__main__.py`: `python -m archivio` ignora `SIGINT` (il Ctrl-C dato nel terminale arriva anche al
  sottoprocesso: il server deve sopravvivere a un turno annullato e termina quando l'assistente chiude
  lo stdin), carica i dati (uscita 1 con il messaggio su stderr se non validi o non leggibili) e avvia il server su
  stdio.
- Il pacchetto `archivio` non importa nulla da `assistente` e viceversa.

## Client: `src/assistente/mcp_client.py`
- `ErroreArchivio(Exception)`: avvio fallito.
- `ClientArchivio(comando: list[str] | None = None, timeout: float = 10.0)`, context manager sincrono.
  - Comando predefinito: `[sys.executable, "-m", "archivio"]`; ambiente del sottoprocesso: quello
    corrente con `PYTHONPATH` che inizia con la cartella `src/` (ricavata dalla posizione di
    `assistente`), così funziona dal `.venv` con `avvia.py`, con pytest e in Docker.
  - `__enter__`: avvia un thread (daemon) con un proprio event loop; nel thread apre `stdio_client` e
    `ClientSession`, esegue `initialize()` e `list_tools()`. La fase di protocollo (`initialize()` e
    `list_tools()`) ha un limite di `timeout` secondi; il thread principale attende in più al massimo
    `ATTESA_CHIUSURA` secondi, perché la pila si chiuda nel proprio compito. Un timeout dà il motivo
    `il server non ha risposto entro N secondi.`. Qualsiasi fallimento (comando inesistente, server uscito, timeout) chiude ciò che
    era aperto, ferma il loop e solleva `ErroreArchivio("archivio non avviato: <motivo>")`; se il server ha scritto su
    stderr, il motivo lo riporta (il messaggio di validazione del CSV deve arrivare all'utente).
  - Lo stderr del server va in un file temporaneo per tutta la sessione (non sul terminale della
    conversazione); all'avvio fallito il suo contenuto entra nel motivo.
  - `strumenti() -> list[Strumento]`: per ogni strumento del server, definizione
    `{"type": "function", "function": {"name", "description", "parameters": inputSchema}}` ed
    `esegui(args)` sincrono.
  - `esegui(args)`: invia `call_tool(nome, args)` al loop con `asyncio.run_coroutine_threadsafe` e attende
    al massimo `timeout` secondi. Il risultato è l'unione dei blocchi di testo del contenuto, separati da
    `\n`. Con `is_error` il testo è prefissato da `Errore: ` se non inizia già così.
    Timeout → `Errore: l'archivio non ha risposto.`; sessione chiusa, server terminato o altro errore di
    comunicazione → `Errore: archivio non disponibile.` con il dettaglio nel log (`WARNING`).
    Non solleva eccezioni verso il grafo.
  - `__exit__`: chiude sessione e sottoprocesso nel loop, ferma il loop e attende il thread (al massimo
    `timeout` secondi); nessun processo orfano.

## Registro e CLI
- `crea_strumenti(adesso, fuso_predefinito, citta_patrono=None, scarica=scarica_json, esterni=())`
  aggiunge in coda gli `esterni`; il controllo dei nomi duplicati vale anche per loro.
- `cli.main()`: dopo `carica_config` e prima di `verifica_modello`, apre `ClientArchivio` con un `with`
  che racchiude la creazione degli strumenti, del grafo e l'intero ciclo di conversazione.
  `ErroreArchivio` è gestito come `ErroreConfigurazione`/`ErroreModello`: `Errore: <messaggio>` su
  stderr e codice di uscita 1. Grafo, configurazione e `compose.yaml` restano invariati.

## Test automatici (senza modello né Internet)
- `tests/test_archivio_inventario.py` (logica pura, CSV scritti in `tmp_path`):
  - ogni caso della validazione, con numero di riga nel messaggio; BOM tollerato;
  - ricerca: maiuscole e accenti ignorati, radice singolare/plurale, parole in AND, parola corta (meno di
    4 caratteri) usata intera, filtro di categoria, categoria sconosciuta con elenco ordinato, limite di
    10 con «altri M», `Trovato 1 articolo`/`1 pezzo`, nessun risultato nelle tre varianti, parametri
    vuoti, parametri oltre 100 caratteri, ordine per codice;
  - dettaglio: codice con spazi e minuscole, descrizione vuota, codice vuoto e sconosciuto;
  - il file `inventario.csv` del pacchetto si carica senza errori e contiene `MIS-001`.
- `tests/test_mcp_client.py` (server vero come sottoprocesso, locale):
  - `list_tools` → `cerca_inventario` e `dettaglio_articolo`, definizioni nella forma del tool calling,
    descrizioni uguali alla lettera alla specifica, descrizioni dei parametri presenti, `codice`
    obbligatorio;
  - una ricerca e un dettaglio veri; un argomento di tipo sbagliato → testo che inizia con `Errore:`;
  - avvio fallito con un comando che non esiste e con un server che esce subito con un messaggio su
    stderr → `ErroreArchivio` con il motivo;
  - dopo l'uscita dal `with` il sottoprocesso è terminato; `esegui` dopo la chiusura →
    `Errore: archivio non disponibile.`
- `tests/test_strumenti.py`: gli `esterni` sono in coda nel registro; nome duplicato → `ValueError`.
- `tests/test_cli.py`: con un `ClientArchivio` finto, `ErroreArchivio` → messaggio su stderr e uscita 1
  (senza sottoprocessi né modello).

## Verifiche reali (marcatore `reale`, LM Studio attivo)
- «Abbiamo dei multimetri? Dove sono?» → almeno una chiamata a `cerca_inventario`, un ToolMessage che
  inizia con `Trovat`, nessun ToolMessage `Errore:`; la risposta finale contiene la collocazione di
  `MIS-001` (confronto senza maiuscole).
- «Dammi i dettagli dell'articolo MIS-001» → chiamata a `dettaglio_articolo` con codice `MIS-001`
  (senza maiuscole), ToolMessage che inizia con `Codice: MIS-001`.
- «Che cosa c'è fra gli strumenti di misura?» → chiamata a `cerca_inventario` con `categoria` o `testo`
  che contiene «misura», ToolMessage che inizia con `Trovat`.
- Si rilanciano tutte le prove reali esistenti: con 7 strumenti il modello potrebbe confondersi. Se un
  caso fallisce ci si ferma, si diagnostica con il log e si riporta prima di cambiare descrizioni o
  specifica.

## Docker
Nessuna modifica a `Dockerfile` e `compose.yaml`: `COPY src/ src/` include `archivio` e
`PYTHONPATH=/app/src` è già impostato. Prova manuale da PowerShell dopo `docker compose build`:
`docker compose run --rm assistente` con «Abbiamo dei multimetri? Dove sono?».

## Documentazione
- README: che cos'è l'archivio (server MCP via stdio avviato dall'assistente), come modificare
  `inventario.csv` (UTF-8, separatore `;`, colonne, validazione), come avviare il server da solo
  (`python -m archivio`, solo per diagnosi), diagnosi «archivio non avviato», prove reali del catalogo.
  Solo comandi verificati, anche per PowerShell.
- CLAUDE.md: struttura (pacchetto `src/archivio/`, `mcp_client`) e obiettivo (catalogo tramite il
  server MCP «archivio»); nell'indice solo la propria versione, senza la modifica dell'utente non in
  commit.

## Criteri di successo
- `python -m pytest` passa senza modello né Internet, compresi i test del client con il server vero.
- `python -m pytest -m reale -v` passa con LM Studio (la catena del calendario resta xfail).
- La prova Docker risponde sull'inventario.
- Nessun processo `archivio` resta attivo dopo l'uscita dall'assistente (anche con `esci` e con Ctrl-C).

## Limiti noti
- La radice approssimata (ultimo carattere tolto) può trovare articoli in più (per esempio `cavi` →
  `cav` trova anche «cavalletto»); è preferita alla mancata corrispondenza fra singolare e plurale.
- Un guasto del server durante la sessione rende gli strumenti dell'archivio indisponibili fino al
  riavvio dell'assistente.
