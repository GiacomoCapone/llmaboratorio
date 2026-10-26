# Assistente del laboratorio

Applicazione da terminale in Python che conversa con un modello locale servito da LM Studio.
Il flusso è un grafo LangGraph esplicito; la cronologia vale per la sola sessione (nessuna
persistenza). Il modello può chiamare lo strumento orologio (fuso orario esplicito), eseguito
davvero dal programma. LM Studio resta sul computer host e non è containerizzato.

## Prerequisiti
- Python (il container usa 3.12; l'ambiente locale verificato usa 3.10).
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

Variabili: `LMSTUDIO_BASE_URL` (default nell'esempio `http://localhost:1234/v1`), `LMSTUDIO_MODEL`
(obbligatoria), `MAX_PASSAGGI` (default 5), `LOG_LEVEL` (default INFO).

## Installazione locale
```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Avvio locale
L'applicazione legge solo le variabili d'ambiente (non carica il file `.env`): impostarle nella
sessione, poi avviare.

```powershell
$env:PYTHONPATH = "src"
$env:LMSTUDIO_BASE_URL = "http://localhost:1234/v1"
$env:LMSTUDIO_MODEL = "<id restituito da /v1/models>"
.venv\Scripts\python.exe -m assistente
```

Scrivere `esci` (o `exit`, `quit`) per terminare. Senza `LMSTUDIO_MODEL` il programma stampa un
errore che cita la variabile ed esce con codice 1.

## Test
```powershell
.venv\Scripts\python.exe -m pytest
```
I test non richiedono un modello attivo (esito verificato: 60 passati, 1 deselezionato).

## Da verificare (non ancora eseguito)
Il demone Docker non era in esecuzione al momento della scrittura: `Dockerfile`, `.dockerignore`
e `compose.yaml` sono scritti, e `docker compose config` ne conferma la validità, ma la build e
l'avvio **non sono stati eseguiti**. Anche l'installazione di `requirements.txt` su Python 3.12
non è verificata.

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
Python 3.10, ambiente locale (non Docker).

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

Non verificato: avvio con Docker (vedi sezione precedente).

## Diagnosi
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
- **Ctrl-C**: durante una risposta annulla solo il turno (`(turno annullato)`, cronologia
  invariata); all'avvio termina il programma con codice 130. Questi due comportamenti sono
  coperti dai test automatici, non provati a mano con LM Studio.
