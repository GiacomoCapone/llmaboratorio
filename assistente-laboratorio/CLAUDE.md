# Assistente del laboratorio

Progetto del corso «Deep Learning e LLM: costruire chatbot e agenti».
La cartella del progetto è `assistente-laboratorio/`.

## Struttura e comandi
- Codice in `src/assistente/` (`config`, `modello`, `strumenti/`, `router`, `revisore`, `riassunto`, `grafo`, `mcp_client`, `cli`); test in `tests/`,
  prove con LM Studio in `tests/reale/`; specifica e piano in `docs/superpowers/`.
- `strumenti/` è un pacchetto: un modulo per strumento e il registro (`crea_strumenti`) in
  `__init__.py`; il grafo esegue gli strumenti per nome senza conoscerli.
- `src/archivio/`: server MCP «archivio» (inventario CSV `inventario.csv`), avviato dall'assistente via stdio;
  `mcp_client` lo collega al registro degli strumenti, legge la resource delle categorie e i prompt.
- `dati/`: database SQLite delle note del laboratorio (`note.db`), creato al primo avvio, fuori da Git e da
  Docker; in Docker è montato su `/app/dati`.
- Test automatici (senza modello): `python -m pytest`.
- Prova reale con LM Studio attivo e `LMSTUDIO_BASE_URL`/`LMSTUDIO_MODEL` nel `.env` (o nell'ambiente):
  `python -m pytest -m reale -v` (esclusa di default).
- Avvio: `python avvia.py` da qualunque cartella (usa il `.venv`, legge il `.env` del progetto,
  senza variabili né `PYTHONPATH`);
  con Docker: `docker compose run --rm assistente`.
- Prova con Open-Meteo vero (Internet, senza modello): `python -m pytest -m rete -v` (esclusa di default).
- Dettagli di configurazione e diagnosi nel `README.md`.

## Obiettivo
Un'applicazione da terminale in Python che conversa con un modello locale e:
- organizza il flusso in un grafo LangGraph esplicito (stato, nodi, instradamento riconoscibili);
- un router all'inizio del turno rifiuta le domande fuori dall'ambito descritto in `ambito.txt`
  (`AMBITO_FILE`), senza raggiungere l'agente;
- un revisore rimanda all'agente, con il motivo, le risposte incomplete o fuori tema, fino a
  `MAX_REVISIONI` volte;
- all'inizio del turno riassume i turni più vecchi quando la cronologia stimata supera
  `RIASSUNTO_SOGLIA_TOKEN`, tenendo intatti gli ultimi 2;
- usa un modello servito da LM Studio, che resta sul computer host;
- conserva la cronologia della conversazione per la durata della sessione (nessuna persistenza);
- offre uno strumento orologio con fuso orario esplicito, richiesto dal modello tramite tool calling
  ed eseguito davvero dal programma;
- offre una calcolatrice sicura (quattro operazioni e parentesi, decimali esatti, senza `eval`);
- offre un convertitore di unità SI (unità di base e derivate con prefisso, aree, volumi, K e °C);
- offre un calendario: differenza fra date e data + N giorni, di calendario o lavorativi, con festività italiane e patrono;
- offre il meteo attuale di una località (Open-Meteo, richiede Internet);
- offre un catalogo dell'inventario del laboratorio (ricerca e dettaglio) tramite il server MCP «archivio»;
- all'avvio legge dal server «archivio» la resource MCP delle categorie dell'inventario e ne mette i nomi
  nella descrizione del filtro `categoria` di `cerca_inventario`;
- offre all'utente i prompt MCP dell'archivio come comandi `/nome argomenti` (`/prompt` li elenca), a
  partire da `scheda_articolo`;
- offre note del laboratorio persistenti (aggiunta, elenco, eliminazione), salvate in SQLite dallo stesso server;
- si avvia anche con Docker Compose.

## Confini
- Implementare solo i requisiti concordati.
- Niente interfacce grafiche, servizi cloud o framework non concordati.
- Lavorare solo dentro `assistente-laboratorio/`. La repository contiene altre lezioni:
  non leggerle per copiarne il codice e non modificarle.
- Lavorare nel branch corrente; nessun branch o worktree nuovo se non richiesto.

## Scelte tecniche
- Python 3.14 (venv locale e immagine Docker), codice sincrono e moduli piccoli, con una separazione semplice tra
  grafo, collegamento al modello, strumenti e interfaccia da terminale.
- LM Studio sull'host, raggiunto tramite la sua API compatibile con OpenAI.
- Indirizzo del server e identificativo del modello solo da variabili d'ambiente o dal file `.env`
  (letto con `python-dotenv`; una variabile già nell'ambiente prevale sul file).
  L'identificativo è quello restituito dal server (`GET /v1/models`), mai inventato.
- Un file di configurazione di esempio senza credenziali; il file reale resta fuori da Git.
- Docker Compose per l'applicazione; LM Studio non va containerizzato.
- Dipendenze motivate, concordate e con versioni fissate.
- Comandi documentati anche per PowerShell (Windows).

## Metodo: Superpowers
- Usare le skill di Superpowers per brainstorming, specifica, piano, implementazione e verifica.
- Non scrivere codice prima che io abbia approvato la specifica e poi il piano.
- Salvare specifica e piano in `assistente-laboratorio/docs/superpowers/`.
- Procedere per incrementi piccoli, ciascuno verificato prima del commit.

## Test e verifiche
- Test automatici ripetibili che non richiedono un modello attivo (grafo, cronologia,
  instradamento, strumento con istante controllato).
- Prove reali con LM Studio e con Docker tenute separate e attivate esplicitamente.
- Una risposta simulata non dimostra che il modello locale sappia usare lo strumento.
- Nel resoconto indicare che cosa è stato eseguito, con quale esito, e che cosa resta da provare.

## Git
- Conventional Commits in italiano, per esempio `feat(grafo): ...`, `test(strumenti): ...`,
  `docs: ...`.
- Prima di ogni commit: `git status`, controllo del diff, staging selettivo dei soli file pertinenti.
- Mai versionare credenziali, `.env`, ambienti virtuali, cache o pesi dei modelli.
- Push soltanto su mia richiesta.

## Documentazione
- Tenere aggiornato il README con configurazione, avvio, test e diagnosi, riportando solo
  comandi verificati.
- Aggiornare questo file quando cambiano convenzioni stabili (struttura, comandi di test,
  regole di lavoro), non per annotare l'avanzamento.
