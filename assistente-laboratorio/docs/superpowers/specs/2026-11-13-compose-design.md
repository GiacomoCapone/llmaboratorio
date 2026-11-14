# Step 9 — Docker Compose a 4 servizi (specifica breve)

Stato: approvata il 2026-11-13 (progetto approvato nella conversazione: «va bene, procedi pure»).

## Intento
Ultimo step del percorso a 9 step: con un solo comando Docker Compose si avvia l'applicazione completa
(database, agente, back-end, pagina web), raggiungibile solo da questo computer; LM Studio resta sull'host.
Oggi `compose.yaml` ha `assistente` (CLI interattiva), `agente`, `backend` e `postgres`; manca `frontend`, e
all'avvio il back-end risponde 502 per qualche secondo finché l'agente non è pronto (`depends_on` attende solo
l'avvio del container).

## Obiettivi
- `docker compose up -d` avvia esattamente `postgres`, `agente`, `backend`, `frontend`.
- Ogni servizio parte quando quelli da cui dipende **rispondono**, non solo quando il container è avviato;
  `docker compose up -d --wait` ritorna quando tutti e quattro sono sani.
- La CLI in Docker resta disponibile: `docker compose run --rm assistente` (decisione dell'utente: opzione A).
- Porte pubblicate solo su `127.0.0.1`: 8000 (agente), 8001 (back-end), 5433 (PostgreSQL) restano per le prove
  documentate; si aggiunge 8002 (front-end) (decisione dell'utente: opzione A).

## Non obiettivi
- Nessun codice Python nuovo né modifiche a `Dockerfile` o immagine; nessuna dipendenza nuova.
- Nessuna politica di riavvio automatico (`restart:`), nessun reverse proxy, nessun TLS.
- LM Studio non va containerizzato; il suo stato non entra nei controlli di salute.

## Approcci considerati
- **Scelto: solo `compose.yaml`** — profilo `cli` per `assistente`, `healthcheck` e `depends_on` con
  `condition: service_healthy`. Usa ciò che Compose offre già.
- Script di attesa dentro i container: codice in più che duplica Compose.
- `restart: on-failure`: maschera gli errori invece di evitare il 502 iniziale.

## Progetto
1. Servizio `frontend`: `build: .`, `command: ["python", "-m", "frontend"]`, `env_file: .env`,
   `environment` con `BACKEND_URL: http://backend:8001` e `FRONTEND_HOST: 0.0.0.0` (prevalgono sul `.env`),
   `ports: ["127.0.0.1:8002:8002"]`, `depends_on: backend` con `condition: service_healthy`.
2. `assistente` riceve `profiles: ["cli"]`: escluso da `up`, avviato da `docker compose run --rm assistente`
   (Compose attiva da sé il profilo del servizio nominato).
3. Controlli di salute con Python dell'immagine (la slim non ha `curl`), in forma `CMD`:
   `python -c "import urllib.request; urllib.request.urlopen('<url>', timeout=3)"` (un codice HTTP non 2xx o
   una connessione rifiutata fanno uscire con codice ≠ 0):
   - `agente`: `http://127.0.0.1:8000/salute`; `backend`: `http://127.0.0.1:8001/salute`;
     `frontend`: `http://127.0.0.1:8002/`.
   - `/salute` di agente e back-end non interroga LM Studio né il database: «sano» significa «il processo
     risponde». Con LM Studio spento la catena parte comunque e gli errori arrivano nei turni come oggi.
   - Tempi (scelta mia): `interval: 5s`, `timeout: 5s`, `retries: 10`, `start_period: 10s` (come `postgres`, più
     il periodo iniziale per l'avvio del server MCP nell'agente).
4. Dipendenze: `backend` → `postgres` (healthy) e `agente` (healthy, oggi `service_started`);
   `frontend` → `backend` (healthy).
5. Porte invariate più la 8002, tutte con prefisso `127.0.0.1:`.

## Verifiche
- **Automatiche (senza Docker):** `tests/test_compose.py` legge `compose.yaml` con PyYAML e controlla: insieme
  dei servizi, servizi senza profilo = i 4, profilo `cli` di `assistente`, ogni porta con prefisso `127.0.0.1:`,
  porta del front-end, comando e variabili del front-end, condizioni di `depends_on`, presenza e URL dei
  controlli di salute.
- **Reale (Docker + LM Studio, manuale):** `docker compose config` valido; `docker compose build`;
  `docker compose up -d --wait` → 4 servizi `healthy` in `docker compose ps`; pagina su
  `http://127.0.0.1:8002` con un turno vero (Edge headless, script di prova dello step 8 fuori da Git);
  `docker compose run --rm assistente` con una domanda da pipe; `docker compose down` e di nuovo
  `up -d --wait` → la conversazione creata è ancora presente (volume `pgdati`).

## Documentazione
README: sezione Docker Compose con l'avvio dei 4 servizi, `--wait`, profilo `cli`, porte; CLAUDE.md: comandi
Docker; handoff: step 9 fatto, percorso completato.

## Lasciato al costruttore
Ordine delle chiavi in YAML, commenti in `compose.yaml`, formulazione del README.

## Revisione del 2026-11-14 (esecuzione)
- **Correzione:** «con LM Studio spento la catena parte comunque» era sbagliato. L'agente controlla il modello
  (`GET /v1/models`) all'avvio ed esce con 1 se LM Studio non risponde: `docker compose up -d --wait` esce con 1 e
  `backend` e `frontend` non partono (attendono un agente sano). Decisione presa in esecuzione: resta
  `service_healthy` (obiettivo principale: niente 502 iniziale; niente codice Python); il README documenta il ripiego
  verificato `docker compose up -d --no-deps --wait postgres backend frontend` per consultare le conversazioni
  senza LM Studio (un nuovo messaggio dà 502). Alternative non scelte: `agente` con `service_started` (torna il 502
  iniziale) o agente che parte anche senza modello (codice Python, fuori da questo step).
