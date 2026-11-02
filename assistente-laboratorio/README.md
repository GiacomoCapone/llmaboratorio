# Assistente del laboratorio

Applicazione da terminale in Python che conversa con un modello locale servito da LM Studio.
Il flusso è un grafo LangGraph esplicito; la cronologia vale per la sola sessione (nessuna
persistenza). Il modello può chiamare lo strumento orologio (fuso orario esplicito), eseguito
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
`FUSO_PREDEFINITO` (default `Europe/Rome`, nome IANA). Un valore non ammesso per una delle ultime
due ferma l'avvio con un errore che cita la variabile (uscita 1).

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

## Test
```powershell
.venv\Scripts\python.exe -m pytest
```
I test non richiedono un modello attivo (esito verificato il 2026-11-02: 150 passati, 5 deselezionati).

## Da verificare (non ancora eseguito)
Su Python 3.14 sono verificati: l'installazione di `requirements.txt` in un `.venv` locale, i test
automatici, `docker compose build` (immagine con Python 3.14.9) e l'avvio del container senza
`LMSTUDIO_MODEL` (errore che cita la variabile, uscita 1). Il 2026-10-26 il container ha anche
conversato con LM Studio sull'host (`docker run -i` con le variabili passate con `-e`): il modello
ha chiamato `ora_corrente` con `Asia/Tokyo` e risposto con l'ora corretta. Non è stato eseguito
`docker compose run`, perché richiede un `.env` reale.

```powershell
docker compose build
docker compose run --rm assistente
```
Il servizio imposta `LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1`, che prevale
sul valore del file `.env`. Atteso senza `LMSTUDIO_MODEL`: errore che cita la variabile, uscita 1.

La prova in Docker (raggiungibilità di LM Studio dal container, log) non è stata eseguita.

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

Non verificato: avvio con Docker (vedi sezione precedente; il 2026-11-02 Docker Desktop non era attivo).
L'immagine va ricostruita (`docker compose build`) perché `requirements.txt` ora include `python-dotenv`.

## Diagnosi
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
  modello una volta senza strumenti, che produce la risposta. È atteso; se anche la seconda risposta è
  vuota, la CLI mostra `(il modello non ha prodotto una risposta)`.
- **Ctrl-C**: durante una risposta annulla solo il turno (`(turno annullato)`, cronologia
  invariata); all'avvio termina il programma con codice 130. Questi due comportamenti sono
  coperti dai test automatici, non provati a mano con LM Studio.
