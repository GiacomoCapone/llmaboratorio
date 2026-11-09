# Assistente del laboratorio

Applicazione da terminale in Python che conversa con un modello locale servito da LM Studio.
Il flusso è un grafo LangGraph esplicito; la cronologia vale per la sola sessione (nessuna
persistenza); solo le note del laboratorio (vedi «Strumenti») restano in un database SQLite. Il modello può chiamare lo strumento orologio (fuso orario esplicito), eseguito
davvero dal programma. LM Studio resta sul computer host e non è containerizzato.

## Prerequisiti
- Python 3.14 (il container usa `python:3.14-slim`; in locale verificato con 3.14.7).
  Creazione dell'ambiente: `py -3.14 -m venv .venv`.
- LM Studio con il server locale attivo (porta 1234 di default) e un modello caricato.
- Docker Desktop, solo per l'avvio con Compose.

## Configurazione
Copiare il file di esempio (il file `.env` reale non va versionato):

```powershell
Copy-Item .env.example .env
```
```bash
cp .env.example .env
```

Impostare `LMSTUDIO_MODEL` con un identificativo restituito dal server, mai inventato:

```powershell
Invoke-RestMethod http://localhost:1234/v1/models
```
```bash
curl http://localhost:1234/v1/models
```

I quattro comandi sopra sono stati eseguiti il 2026-10-26 (il `.env` creato per la prova è stato
poi rimosso); `curl` va lanciato da bash, perché in Windows PowerShell 5.1 `curl` è un alias di
`Invoke-WebRequest`.

Il programma legge il file `.env` della cartella del progetto (con `python-dotenv`), da qualunque
cartella venga avviato: non serve impostare variabili nella sessione. Una variabile già presente nell'ambiente prevale sul
valore del file; così Docker Compose imposta l'indirizzo dell'host per il container.

Variabili: `LMSTUDIO_BASE_URL` (default nell'esempio `http://localhost:1234/v1`), `LMSTUDIO_MODEL`
(obbligatoria), `MAX_PASSAGGI` (default 5), `LOG_LEVEL` (default INFO),
`LMSTUDIO_REASONING_EFFORT` (default `none`; ammessi `none`, `low`, `medium`, `high`) e
`FUSO_PREDEFINITO` (default `Europe/Rome`, nome IANA), `CITTA_PATRONO` (facoltativa, per esempio
`Pordenone`), `NOTE_DB` (facoltativa, percorso del database delle note; vedi «Note del laboratorio») e
`AMBITO_FILE` (facoltativa, file che descrive l'ambito del router; default `ambito.txt`, vedi «Ambito e
router»). Un valore non ammesso per `LMSTUDIO_REASONING_EFFORT` o `FUSO_PREDEFINITO`, o una città
non presente in `src/assistente/strumenti/festivita.json`, ferma l'avvio con un errore (uscita 1). Per
una città sconosciuta il messaggio è `Città del patrono sconosciuta: '<valore>'. Città disponibili: ...
(file ...)`; verificato il 2026-11-03 con `CITTA_PATRONO=Milano` (uscita 1).

`CITTA_PATRONO` aggiunge ai giorni festivi del calendario la festa del patrono della città (maiuscole
e spazi esterni ignorati). Per aggiungere una città: aggiungere in `patroni` di
`src/assistente/strumenti/festivita.json` una voce come `"Pordenone": {"data": "04-25", "santo": "San Marco"}`
(data `MM-GG`) e rilanciare i test.

`FUSO_PREDEFINITO` è il fuso usato dall'orologio quando la domanda non indica un luogo
(«che ore sono»); il modello lo legge nella definizione dello strumento.

`LMSTUDIO_REASONING_EFFORT` regola il ragionamento nascosto del modello: con `none` ogni chiamata
dura pochi secondi; `low` (o superiore) può rendere più affidabile la scelta dello strumento con
domande insolite, ma con `google/gemma-4-e2b` su questo computer porta ogni chiamata a 20–80 s.

## Installazione locale
```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Avvio locale
Con il file `.env` compilato e il `.venv` installato:

```powershell
python avvia.py
```

Il comando funziona da qualunque cartella (indicando il percorso dello script, per esempio
`python .\assistente-laboratorio\avvia.py`) e con qualunque Python 3: se non è quello del `.venv`,
`avvia.py` si rilancia con `.venv\Scripts\python.exe`, dove sono installate le dipendenze; aggiunge
anche `src` al percorso, quindi non serve `PYTHONPATH`. Verificato il 2026-11-02 in PowerShell senza
variabili impostate, con il Python di sistema, con quello del `.venv` e dalla cartella superiore.
In alternativa resta `python -m assistente` con `$env:PYTHONPATH = "src"` e il Python del `.venv`.

Scrivere `esci` (o `exit`, `quit`) per terminare. Senza `LMSTUDIO_MODEL` (né nel `.env` né
nell'ambiente) il programma stampa un errore che cita la variabile e il file `.env` ed esce con
codice 1.

## Ambito e router
Ogni domanda passa prima da un nodo **router**, che usa lo stesso modello con un prompt di sistema
diverso e la classifica come `conversazione` (in ambito) o `fuori_ambito`:

```
START → router ─┬─ conversazione → modello ⇄ strumenti / limite → END
                └─ fuori_ambito  → rifiuto → END
```

Le domande fuori ambito ricevono «Posso rispondere solo a domande sul laboratorio e sui suoi
strumenti. Motivo: ...» senza raggiungere l'agente (nodo `modello`) e senza strumenti. Il router non
decide gli strumenti: lo fa l'agente, come prima. Domanda e rifiuto restano nella cronologia.

L'ambito è descritto in `ambito.txt` (testo libero, versionato) nella cartella del progetto; per usarne
un altro impostare `AMBITO_FILE` (percorso relativo alla cartella del progetto, o assoluto). Modificare
il file cambia l'ambito senza toccare il codice; file mancante o vuoto ferma l'avvio con
`Errore: File dell'ambito <percorso> mancante o vuoto: ...`. In Docker il file è copiato nell'immagine:
dopo una modifica serve `docker compose build`.

Il router vede l'ultima domanda e fino a 3 messaggi precedenti fra utente e assistente (senza i
passaggi con gli strumenti), così una domanda di seguito come «e a Londra?» resta in ambito.

Righe di log (`LOG_LEVEL=INFO`, su stderr) da cercare:
- in ambito: `router categoria=conversazione motivo=... → agente` seguita da
  `agente: chiamata al modello`;
- fuori ambito: `router categoria=fuori_ambito motivo=... → rifiuto` e nessuna riga `agente:`.

Il router chiede la classificazione tramite uno strumento obbligatorio (`tool_choice="required"`,
al massimo 256 token in uscita). Non usa `response_format` con schema JSON: con lo schema LM Studio
ignora `LMSTUDIO_REASONING_EFFORT=none` e `google/gemma-4-e2b` ragiona per migliaia di token (misurati
fino a 688 s per una sola classificazione, contro circa 3 s con lo strumento obbligatorio).

## Strumenti
Il modello li richiede tramite tool calling; il programma li esegue davvero (registro in
`src/assistente/strumenti/`).

- **Orologio** (`ora_corrente`): data e ora attuali nel fuso IANA richiesto; senza luogo usa
  `FUSO_PREDEFINITO`.
- **Calcolatrice** (`calcola`): le quattro operazioni `+ - * /`, parentesi e segno, con decimali
  esatti (`0.1 + 0.2` dà `0.3`) e il punto o la virgola come separatore. Non usa `eval`: l'espressione
  è solo analizzata da un piccolo parser. Massimo 200 caratteri, 28 cifre significative. Tutto il resto
  è respinto con un messaggio che il modello può usare per correggersi, per esempio
  `Errore: carattere non ammesso 'x' in posizione 3. Sono ammessi numeri, + - * / e parentesi.`

- **Convertitore** (`converti_unita`): converte fra unità SI con i loro prefissi (le 7 di base e le
  22 derivate con nome, per esempio km, mg, µs, kPa, MW, GHz, kΩ), aree e volumi di lunghezza
  (`cm²`, `m³`, anche `cm2` o `cm^2`) e temperature in `K` e `°C`; decimali esatti. I simboli
  distinguono maiuscole e minuscole (`mW` milliwatt, `MW` megawatt); `u` vale come `µ`, `ohm` come
  `Ω`. Non accetta unità non SI (ore, litri, km/h, unità imperiali) né conversioni fra grandezze
  diverse, per esempio `Errore: non si può convertire 'kg' (massa) in 'm' (lunghezza): grandezze diverse.`

- **Calendario** (`calendario`): due operazioni su date `AAAA-MM-GG` (anni 1583-9999).
  `differenza` conta i giorni fra due date, `aggiungi` somma o sottrae N giorni a una data, di
  calendario o solo lavorativi. Non sono lavorativi sabato, domenica, le festività italiane (Pasqua calcolata,
  Pasquetta, 1/1, 6/1, 25/4, 1/5, 2/6, 15/8, 1/11, 8/12, 25/12, 26/12) e il patrono di `CITTA_PATRONO`.
  Convenzione: la data di partenza è esclusa e quella di arrivo inclusa, quindi per i lavorativi di
  dicembre si parte dal 30 novembre. Per «oggi» il modello deve prima chiamare l'orologio. Esempio:
  `dal 2026-12-01 (martedì) al 2026-12-31 (giovedì): 30 giorni di calendario, 20 lavorativi;
  festività nell'intervallo: 2026-12-08 Immacolata Concezione, 2026-12-25 Natale, 2026-12-26 Santo Stefano`.
  Errori in forma `Errore: ...`, per esempio `Errore: data non valida: '05/02/2026'. ...`.

- **Meteo** (`meteo_attuale`): condizioni attuali di una località da Open-Meteo; **richiede Internet**.
  Il nome è cercato con il geocoding di Open-Meteo e si usa il primo risultato, mostrato nella riga
  `Luogo:` (controllare che sia la località voluta). Niente previsioni: solo l'ora della rilevazione.
  Esempio (uscita reale di `esegui_meteo` per Pordenone, 2026-11-09):
  ```
  Luogo: Pordenone, Friuli Venezia Giulia, Italia
  Rilevazione: 2026-11-09 09:30 (ora locale, Europe/Rome)
  Cielo: coperto
  Temperatura: 7,0 °C (percepita 5,6 °C)
  Umidità: 87 %
  Precipitazioni: 0,0 mm
  Vento: 1,6 km/h da sud-est
  ```
  Errori in forma `Errore: ...`.

- **Catalogo dell'inventario** (`cerca_inventario`, `dettaglio_articolo`): ricerca per testo o
  categoria e scheda di un articolo dall'inventario del laboratorio (`src/archivio/inventario.csv`).
  Gli strumenti sono offerti dal server MCP «archivio» (`src/archivio/`), che l'assistente avvia da sé
  come sottoprocesso via stdio all'avvio: nessuna configurazione. Se non parte, l'assistente non si
  avvia (vedi «Diagnosi»). Esempi di domande: «Abbiamo dei multimetri? Dove sono?», «Dammi i dettagli
  dell'articolo MIS-001», «Che cosa c'è fra gli strumenti di misura?».

- **Note del laboratorio** (`aggiungi_nota`, `elenca_note`, `elimina_nota`): note di testo libero,
  con un codice articolo facoltativo (verificato contro l'inventario), salvate in un database SQLite
  e quindi **persistenti fra una sessione e l'altra**. Sono offerte dallo stesso server «archivio».
  Ogni nota ha un numero progressivo e la data di salvataggio (nel fuso `FUSO_PREDEFINITO`);
  `elenca_note` può filtrare per articolo; `elimina_nota` cancella per numero e riporta il testo
  eliminato, senza chiedere conferma. Esempi di domande: «Annota che il multimetro MIS-001 ha la
  batteria scarica», «Quali note ci sono?», «Elimina la nota 1».
  Esempio (uscita reale, 2026-11-09, PowerShell, `google/gemma-4-e2b`; riga `tool_result` del log):
  ```
  tool_call nome=aggiungi_nota args={'testo': 'il saldatore va pulito'}
  tool_result nome=aggiungi_nota risultato=Nota 1 salvata (2026-11-09 15:14): il saldatore va pulito.
  ```
  Errori in forma `Errore: ...`, per esempio `Errore: nessuna nota con numero 7.`

### Note del laboratorio: database e Docker
- Il database è `dati/note.db` nella cartella del progetto (la cartella `dati/` è ignorata da Git e da
  Docker, ed è creata al primo avvio). `NOTE_DB` nel `.env` ne cambia il percorso; un percorso relativo
  è risolto rispetto alla cartella del progetto, non a quella da cui si avvia.
- Con Docker Compose `./dati` è montata su `/app/dati` e `NOTE_DB` vale `/app/dati/note.db` (prevale
  sul `.env`): container e avvio locale **condividono lo stesso file**, quindi le note create in uno
  compaiono nell'altro (verificato, vedi «Docker: verificato e da verificare»).
- **Non usare container e avvio locale nello stesso momento**: il lock di SQLite su un mount di Docker
  Desktop non è affidabile. Un lock trattenuto oltre 5 secondi dà `Errore: archivio delle note non
  disponibile.`
- Per azzerare le note si chiude l'assistente e si cancella il file:
  ```powershell
  Remove-Item dati\note.db
  ```
  (verificato il 2026-11-09 da PowerShell: dopo il comando `elenca_note` risponde `Nessuna nota.` e il
  file si ricrea al primo avvio). Le note eliminate a voce si tolgono con «Elimina la nota N»
  (verificato); il numero di una nota eliminata non è riusato (osservato: dopo l'eliminazione della
  nota 1 la nota successiva è la 2) e riparte da 1 solo cancellando il file.
- Una nota salvata con un fuso diverso da quello attuale mostra l'ora con cui è stata salvata.

### Modificare l'inventario
`src/archivio/inventario.csv` è un file UTF-8 con separatore `;` e prima riga di intestazione
`codice;nome;categoria;quantita;collocazione;descrizione`. Regole (il file è riletto a ogni avvio
del server; un errore ferma l'avvio con il numero di riga): sei campi per riga; `codice`, `nome`,
`categoria` e `collocazione` obbligatori; `quantita` intera non negativa; `codice` non ripetuto
(esempio verificato: `inventario non valido, riga 29: codice ripetuto 'MIS-001'.`); `descrizione`
facoltativa.

### Server archivio da solo (diagnosi)
```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -m archivio
```
Il server parla MCP su stdin/stdout. Verificato il 2026-11-09 con un CSV valido e
`"" | .venv\Scripts\python.exe -m archivio`: termina con uscita 0 alla fine dell'input. Con un CSV
non valido stampa l'errore con la riga ed esce con 1. Il comportamento con Ctrl-C a mano non è
stato verificato.

### Dipendenza `mcp`
Il catalogo usa l'SDK ufficiale `mcp==2.3.0` (`requirements.txt`). Porta 17 pacchetti in più, tutti
con versione fissata, per lo più per i trasporti HTTP e l'autenticazione (`starlette`, `uvicorn`, `sse-starlette`,
`PyJWT`, `cryptography`, ...) che qui non si usano: si usa solo lo stdio. `pywin32` è solo per Windows.

## Test
```powershell
.venv\Scripts\python.exe -m pytest
```
I test non richiedono un modello attivo né Internet (esito verificato il 2026-11-09: 535 passati, 23
deselezionati: 21 `reale` e 2 `rete`).

Prova con Open-Meteo vero (Internet, senza modello; esclusa di default, marker `rete`):
```powershell
.venv\Scripts\python.exe -m pytest -m rete -v
```
Esito del 2026-11-09, eseguito da PowerShell: 2 passati.

## Docker: verificato e da verificare
Su Python 3.14 sono verificati: l'installazione di `requirements.txt` in un `.venv` locale, i test
automatici, `docker compose build` (immagine con Python 3.14.9) e l'avvio del container senza
`LMSTUDIO_MODEL` (errore che cita la variabile, uscita 1). Il 2026-10-26 il container ha anche
conversato con LM Studio sull'host (`docker run -i` con le variabili passate con `-e`): il modello
ha chiamato `ora_corrente` con `Asia/Tokyo` e risposto con l'ora corretta. Il 2026-11-03 è stato eseguito
anche `docker compose run --rm -T -e CITTA_PATRONO=Pordenone assistente` con input da pipe: il
container ha raggiunto LM Studio, chiamato gli strumenti e terminato con uscita 0 (dettagli in
«Verifiche reali»).

```powershell
docker compose build
docker compose run --rm assistente
```
Il servizio imposta `LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1`, che prevale
sul valore del file `.env`. Atteso senza `LMSTUDIO_MODEL`: errore che cita la variabile, uscita 1.

Il 2026-11-09 il container ha risposto anche con il meteo (vedi «Verifiche reali»).

Il 2026-11-09 il container ha risposto anche con il catalogo (il server «archivio» parte dentro il
container, `src/` è nell'immagine): vedi «Verifiche reali».

Il 2026-11-09 è stata verificata la condivisione delle note fra container e host, da PowerShell
(`$env:PYTHONIOENCODING = "utf-8"`), dopo `docker compose build` (uscita 0) e senza `dati/`:
```powershell
"Annota che il saldatore va pulito", "esci" | docker compose run --rm -T assistente
"Quali note ci sono?", "esci" | .venv\Scripts\python.exe avvia.py
"Elimina la nota 1", "esci" | .venv\Scripts\python.exe avvia.py
"Quali note ci sono?", "esci" | .venv\Scripts\python.exe avvia.py
```
Tutte con uscita 0. Il container ha chiamato `aggiungi_nota` («Nota 1 salvata (2026-11-09 15:14): il
saldatore va pulito.») e creato `dati/note.db`; dall'host `elenca_note` ha restituito `Trovata 1 nota:`
con la stessa nota; `elimina_nota` l'ha eliminata e l'elenco successivo ha dato `Nessuna nota.`

Ancora da verificare: l'avvio interattivo senza `-T` (con terminale) di `docker compose run --rm
assistente`, l'esame dei log del container e Ctrl-C a metà turno con il catalogo attivo (la domanda
successiva sull'inventario deve funzionare; non eseguibile da una shell non interattiva).

## Verifiche reali
Eseguite il 2026-10-26 con LM Studio sull'host (`http://localhost:1234/v1`) e il modello
`google/gemma-4-e2b` (id restituito da `GET /v1/models`), variabili impostate nella sessione.
Python 3.10, ambiente locale (non Docker). Dopo il passaggio a Python 3.14 la prova
`pytest -m reale` è stata ripetuta con lo stesso modello: 1 passato.

Prova automatica con modello reale (esclusa dall'esecuzione di default, marker `reale`):

```powershell
$env:LMSTUDIO_BASE_URL = "http://localhost:1234/v1"
$env:LMSTUDIO_MODEL = "google/gemma-4-e2b"
.venv\Scripts\python.exe -m pytest -m reale -v
```
Esito: `1 passed, 53 deselected in 37.66s`; ripetuta dopo l'aggiunta dei controlli sul turno non
interrotto e sull'offset `+09:00`: `1 passed, 60 deselected in 34.64s`. Il modello ha emesso la
tool call `ora_corrente`, lo strumento ha restituito l'ora di Tokyo, il turno non è stato
interrotto dal limite e la risposta finale non era vuota.

Prova manuale (`python -m assistente`, input da pipe: «Che ore sono a Tokyo?», poi «Qual era la
città di cui ti ho appena chiesto l'ora?», poi `esci`; uscita 0). Estratto da stderr (le righe
reali iniziano anche con data e ora, nel formato `%(asctime)s %(levelname)s %(name)s %(message)s`):

```
INFO assistente.grafo tool_call nome=ora_corrente args={'fuso': 'Asia/Tokyo'}
INFO assistente.grafo tool_result nome=ora_corrente risultato=2026-10-27T01:16:35.884258+09:00
```
Risposte: «Attualmente a Tokyo sono le ore **01:16** del 27 ottobre 2026.» e, per la seconda
domanda, «La città di cui mi hai appena chiesto l'ora era **Tokyo**.» (cronologia di sessione
funzionante). Una sola esecuzione per prova: non è una misura di affidabilità del modello.

Il 2026-11-02, con fuso facoltativo e `LMSTUDIO_REASONING_EFFORT=none` (default), stesso modello:

```powershell
.venv\Scripts\python.exe -m pytest -m reale -v -s
```
Esito: `3 passed, 79 deselected in 32.77s` con le domande «che ore sono», «Che giorno è oggi?» e
«Che ore sono a Tokyo?»; ogni turno (due chiamate al modello) ha richiesto circa 7–15 s. Prova
manuale con `python -m assistente` e «che ore sono»: `tool_call nome=ora_corrente args={}`,
risultato con l'offset di Roma (`+01:00`), risposta «Ora sono le 16:38:46.», 15 s compreso l'avvio.

Il 2026-11-02, dopo l'aggiunta della calcolatrice (due strumenti collegati al modello):
`.venv\Scripts\python.exe -m pytest -m reale -v -s` → `5 passed`: le tre domande sull'ora e
«Quanto fa 12,5 * 4?» (risultato dello strumento `50`), «Quanto fa (3 + 7) / 4?» (`2.5`). Tempi per
turno fra 6 e 11 s, tranne l'ultima domanda (42,5 s). Prova manuale nella stessa sessione:
«Quanto fa 12,5 * 4?» → «12,5 moltiplicato per 4 fa **50**.», poi «che ore sono» → ora di Roma; nel
log è comparsa una volta la riga `risposta vuota dopo gli strumenti` (vedi Diagnosi).

Dal 2026-11-02 le prove reali leggono anch'esse il `.env`: `.venv\Scripts\python.exe -m pytest -m reale`
senza variabili impostate → `5 passed, 147 deselected in 68.10s`.

Il 2026-11-02, con tre strumenti (orologio, calcolatrice, convertitore): `python -m pytest -m reale -v -s`
→ 7 passate, compresi «Quanti metri sono 2,5 km?» (`2500 m`) e «Quanti gradi Celsius sono 300 K?»
(`26.85 °C`); turni fra 3 e 8 s. Prova manuale con `python avvia.py` e le tre domande «Quanti metri
sono 2,5 km?», «Quanto fa 12,5 * 4?», «che ore sono» nella stessa sessione: risposte corrette, ognuna
con la tool call dello strumento giusto.

Il 2026-11-03, con il calendario (quattro strumenti) e `CITTA_PATRONO=Pordenone` nell'ambiente del
processo (non nel `.env`): `.venv\Scripts\python.exe -m pytest -q` → `353 passed, 11 deselected in 6.67s`;
```powershell
$env:CITTA_PATRONO='Pordenone'; .venv\Scripts\python.exe -m pytest -m reale -v -s
```
→ `10 passed, 353 deselected, 1 xfailed in 110.41s` (eseguito in PowerShell il 2026-11-03; una prima
esecuzione in bash con `CITTA_PATRONO=Pordenone` davanti al comando: `109.22s`, stesso esito). Passano le sette prove precedenti, le due del calendario («Quanti giorni lavorativi ci sono
dal 1° al 31 dicembre 2026?» → `calendario` con `operazione=differenza`, `20 lavorativi`; «Che data è 10
giorni lavorativi dopo il 18 dicembre 2026?» → `2027-01-05`) e la catena «Che giorno sarà tra 30 giorni
a partire da oggi?» (`ora_corrente` poi `calendario`, data di arrivo corretta). È un fallimento atteso
(`xfail`) la catena con la domanda «Che giorno sarà fra 30 giorni?»: in contesto nuovo `google/gemma-4-e2b`
non chiama alcuno strumento e chiede la data odierna (fallita 5 volte su 5, con temperatura 0 l'esito è
stabile). Limite noto della catena: dipende dalla formulazione. Riesce quando l'utente nomina «oggi» o
quando la data è già nella conversazione; altrimenti il modello può chiedere la data o addirittura
inventarla (osservato: «Che data sarà fra 30 giorni?» ha chiamato `calendario` con una data di partenza
inventata, 2024-05-17).

Prova manuale 2026-11-03 con `python avvia.py` (stessa sessione): «Quanti giorni lavorativi mancano dal
3 novembre 2026 a Natale?» → `calendario` (differenza dal 2026-11-03 al 2026-12-25 con lavorativi),
risultato `52 giorni di calendario, 36 lavorativi`; «Quanto fa 12,5 * 4?» → `calcola`, `50`;
«che ore sono» → `ora_corrente`.

Docker 2026-11-03 (Docker Desktop attivo): `docker compose build` riuscito; `docker compose run --rm -T
-e CITTA_PATRONO=Pordenone assistente` con input da pipe («Quanti giorni lavorativi mancano dal 3
novembre 2026 a Natale?», «che ore sono», `esci`): il container raggiunge LM Studio, chiama `calendario`
(36 lavorativi) e `ora_corrente`, uscita 0.

Con il meteo (strumento `meteo_attuale`, 2026-11-09), `CITTA_PATRONO=Pordenone` nell'ambiente
(il `.env` non la contiene), eseguito da Git Bash (non PowerShell):
```bash
CITTA_PATRONO=Pordenone .venv/Scripts/python.exe -m pytest -m reale -v -s
```
→ `12 passed, 438 deselected, 1 xfailed in 125.73s`. Le due prove nuove passano: «Che tempo fa a
Trieste?» (9,1 s) chiama `meteo_attuale` con `localita` Trieste, il risultato inizia con `Luogo:` e
la risposta riporta la temperatura; «Che tempo farà domani a Trieste?» (2,8 s) è solo osservata:
il modello non ha chiamato alcuno strumento e ha risposto «Per darti le previsioni del tempo per domani
a Trieste, ho bisogno di sapere la data di oggi. Per favore, dimmi oggi.» (una sola esecuzione).

Docker 2026-11-09, da Git Bash (con `PYTHONIOENCODING=utf-8`), dopo `docker compose build`:
```bash
echo "Che tempo fa a Pordenone?" | PYTHONIOENCODING=utf-8 docker compose run --rm -T -e CITTA_PATRONO=Pordenone assistente
```
→ uscita 0; `tool_call nome=meteo_attuale args={'localita': 'Pordenone'}` e risposta «A Pordenone il
tempo è **coperto**, la temperatura è di **6,3 °C** (percepita 4,9 °C), l'umidità è dell'**89 %**, ...»:
il container raggiunge sia LM Studio sia Open-Meteo.

Catalogo (server MCP «archivio», 2026-11-09), `CITTA_PATRONO=Pordenone` nell'ambiente, da Git Bash:
```bash
CITTA_PATRONO=Pordenone .venv/Scripts/python.exe -m pytest -m reale -v -s
```
→ `15 passed, 1 xpassed` in 209 s (`xpassed`: la catena orologio→calendario senza «oggi», marcata
`xfail` non rigida, stavolta è passata; non è una garanzia). Tre prove nuove, modello
`google/gemma-4-e2b`: «Abbiamo dei multimetri? Dove sono?» → `cerca_inventario`, risposta con la
collocazione; «Dammi i dettagli dell'articolo MIS-001» → `dettaglio_articolo`; «Che cosa c'è fra gli
strumenti di misura?» → `cerca_inventario` con categoria «strumenti di misura».

Prova manuale 2026-11-09 da PowerShell: `"esci" | .venv\Scripts\python.exe avvia.py` con LM Studio
attivo → saluto, uscita 0; `tasklist /FI "IMAGENAME eq python.exe"` prima e dopo: nessun processo
`python.exe`, quindi il server dell'archivio non resta attivo. Con un codice duplicato nel CSV:
`Errore: archivio non avviato: inventario non valido, riga 29: codice ripetuto 'MIS-001'.`, uscita 1.

Docker 2026-11-09, da PowerShell, dopo `docker compose build` (riuscito):
```powershell
$env:PYTHONIOENCODING = "utf-8"
"Abbiamo dei multimetri? Dove sono?", "esci" | docker compose run --rm -T assistente
```
→ uscita 0; `tool_call nome=cerca_inventario args={'testo': 'multimetro'}`, risultato
`MIS-001 — Multimetro digitale — 4 pezzi — Armadio A, ripiano 2` e risposta con «Armadio A, ripiano 2».

Note del laboratorio (2026-11-09, `google/gemma-4-e2b`, `CITTA_PATRONO=Pordenone` nell'ambiente), da
Git Bash:
```bash
CITTA_PATRONO=Pordenone .venv/Scripts/python.exe -m pytest -m reale -v -s
```
→ 20 passate, 1 xfailed (la catena orologio→calendario senza «oggi»), 292 s. Cinque prove nuove, con un
database temporaneo (`NOTE_DB` in una cartella temporanea): «Annota che il multimetro MIS-001 ha la
batteria scarica» → `aggiungi_nota` con `codice` MIS-001 e `testo` «batteria scarica»; «Annota che il
saldatore va pulito» → `aggiungi_nota` con il solo `testo`; «Quali note ci sono?» → `elenca_note`;
«Elimina la nota 1» → `elimina_nota` con `numero` 1; «Mostrami le note» → `elenca_note` senza
cancellazioni. La prima esecuzione era fallita (il modello chiedeva il codice facoltativo e, dopo
«Annota che…», rispondeva con un testo vuoto): sono state riformulate le descrizioni degli strumenti e
il grafo richiama il modello con un'istruzione (vedi «Diagnosi»).

## Diagnosi
- **`WARNING assistente.router router non disponibile: ...`**: la classificazione non è riuscita
  (server non raggiungibile, risposta senza tool call, argomenti non validi, limite di 256 token). La
  domanda passa comunque all'agente come `conversazione`; il motivo segue i due punti.
- **`WARNING assistente.router categoria non valida '<valore>': considerata conversazione`**:
  `google/gemma-4-e2b` scrive a volte l'argomento («meteo», «inventario») al posto della categoria, ma
  solo per domande in ambito; la domanda passa all'agente con il motivo del modello. È atteso.
- **Domanda in ambito rifiutata** (`router categoria=fuori_ambito` per una domanda pertinente):
  descrivere meglio quell'argomento in `ambito.txt` (o nel file di `AMBITO_FILE`) e riavviare.
- **`Errore: archivio non avviato: archivio delle note non valido: <percorso> (...)`**: il database
  delle note non si apre o non ha lo schema atteso (file di un altro programma, percorso in una cartella
  non scrivibile, `NOTE_DB` sbagliato). Correggere `NOTE_DB` o spostare/cancellare il file (le note
  vanno perse). Per isolare il problema avviare il server da solo (vedi sopra).
- **`Errore: archivio delle note non disponibile.`** durante una conversazione: il database è bloccato
  da oltre 5 secondi, tipicamente perché container e avvio locale sono attivi insieme; chiuderne uno.
- **`Errore: ... servizio meteo non raggiungibile (...)` o `il servizio meteo non ha risposto entro N secondi`**: manca la connessione a Internet o è
  bloccata (proxy, firewall, rete aziendale); in Docker verificare che il container abbia uscita
  verso Internet. La prova `pytest -m rete -v` isola il problema dal modello.
- **`Errore: archivio non avviato: ...`**: il server dell'inventario non è partito; il motivo segue i
  due punti. Cause: `inventario non valido, riga N: ...` (correggere il CSV, vedi «Modificare
  l'inventario»); `inventario non leggibile: <percorso> (No such file or directory).` (il CSV manca
  o non si apre). Per isolare il problema avviare il server da solo (vedi sopra).
- **`Errore: archivio non avviato: il server non ha risposto entro 10 secondi.`**: il server non ha
  completato l'avvio in tempo (per esempio un primo avvio molto lento o un antivirus che analizza i
  file). Riprovare; se si ripete, avviare il server da solo (vedi sopra) per vederne gli errori.
- **Variabile mancante nonostante il `.env`**: il file letto è `assistente-laboratorio/.env`; una
  riga `NOME` senza `=valore` conta come mancante, e una variabile impostata (anche vuota) nella
  sessione prevale sul file.
- **`Errore: dipendenza mancante`** all'avvio: manca il `.venv` del progetto; crearlo come in
  «Installazione locale».
- **«esci» inviato con una pipe da PowerShell**: PowerShell antepone un BOM alla prima riga; il
  programma lo ignora.
- **Server non raggiungibile**: verificare che il server locale di LM Studio sia attivo e che
  `LMSTUDIO_BASE_URL` punti alla porta giusta.
- **Modello non trovato**: `LMSTUDIO_MODEL` deve coincidere con un id di `GET /v1/models`.
- **Container che non vede l'host**: usare `host.docker.internal` (già impostato in `compose.yaml`
  con `extra_hosts`), non `localhost`.
- **LM Studio in ascolto solo su loopback**: dal container l'host non è raggiungibile; abilitare
  in LM Studio l'ascolto sulla rete locale (serve su `0.0.0.0`).
- **Tool calling non supportato dal modello**: il modello non richiamerà l'orologio; scegliere
  un modello che supporti l'uso di strumenti.
- **Argomenti della tool call non in JSON valido**: il programma risponde al modello con un
  errore (riga `WARNING ... tool_call non valida` nel log) e il modello può riprovare, entro
  `MAX_PASSAGGI`.
- **Risposte lente (decine di secondi)**: controllare che il ragionamento sia disattivato. Con
  `lms ps` si vede il modello caricato; nell'ultimo log del server LM Studio il campo
  `reasoning_tokens` deve valere 0 con `LMSTUDIO_REASONING_EFFORT=none`:
  ```powershell
  lms ps
  $log = Get-ChildItem "$env:USERPROFILE\.lmstudio\server-logs" -Recurse -File | Sort-Object LastWriteTime | Select-Object -Last 1
  Select-String -Path $log.FullName -Pattern '"reasoning_tokens"' | Select-Object -Last 2
  ```
- **«che ore sono» senza strumento**: un modello da 2B senza ragionamento resta sensibile alla
  formulazione; provare `LMSTUDIO_REASONING_EFFORT=low`, accettando tempi molto più lunghi.
- **`WARNING ... risposta vuota dopo gli strumenti`**: con più strumenti collegati,
  `google/gemma-4-e2b` risponde spesso ai risultati con un testo vuoto. Il programma richiama allora il
  modello una volta senza strumenti, con in testa un messaggio di sistema («Rispondi all'utente
  riferendo il risultato degli strumenti.», non salvato nella cronologia), che produce la risposta. Con
  le note è frequente: in una prova manuale del 2026-11-09 la ripetizione senza l'istruzione era vuota
  15 volte su 15, con l'istruzione 0 volte su 9. È atteso; se anche la seconda risposta è
  vuota, la CLI mostra `(il modello non ha prodotto una risposta)`.
- **Input accentato corrotto con una pipe da Git Bash (Windows)**: senza `PYTHONIOENCODING=utf-8`
  la CLI riceve «sarÃ » al posto di «sarà» (osservato il 2026-11-03; con la variabile impostata il
  testo arriva corretto). Da PowerShell il testo arriva corretto. Il modello può rispondere in modo
  diverso a testo corrotto: le prove manuali con input accentato vanno fatte con input ben codificato.
- **Ctrl-C**: durante una risposta annulla solo il turno (`(turno annullato)`, cronologia
  invariata); all'avvio termina il programma con codice 130. Questi due comportamenti sono
  coperti dai test automatici, non provati a mano con LM Studio (con il catalogo attivo la prova a
  mano di Ctrl-C resta da fare).
