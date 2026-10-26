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
I test non richiedono un modello attivo (esito verificato: 53 passati).

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

Anche le prove reali con LM Studio (conversazione e uso dello strumento orologio da parte del
modello) restano da eseguire.

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
