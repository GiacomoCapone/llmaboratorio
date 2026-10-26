# Assistente del laboratorio: specifica

Data: 2026-10-26. Stato: approvata (con il campo `interrotto` aggiunto in fase di piano).

## Obiettivo
Applicazione Python da terminale che conversa con un modello servito da LM Studio sull'host.
Il flusso è un grafo LangGraph esplicito. La cronologia vive solo durante la sessione.
Il modello può richiedere uno strumento orologio con fuso orario esplicito; il programma lo esegue
davvero e restituisce il risultato al modello, che produce la risposta finale.

## Fuori ambito
MCP, RAG, interfacce web o grafiche, altri strumenti, persistenza della cronologia, servizi cloud,
containerizzazione di LM Studio.

## Decisioni concordate
- Al raggiungimento del limite di passaggi il grafo si ferma, scrive un warning nel log e mostra un
  messaggio esplicito all'utente. La conversazione resta utilizzabile.
- Collegamento al modello con `langchain-openai` (`ChatOpenAI` con `base_url` verso LM Studio).
- Il contatore dei passaggi riparte da zero a ogni domanda.
- Approccio al grafo: ciclo esplicito `modello` / `strumenti` / `limite`, con nodo strumenti scritto
  nel progetto (non `create_react_agent`, non `ToolNode`).

## Struttura
```
assistente-laboratorio/
  src/assistente/
    config.py      # variabili d'ambiente
    modello.py     # ChatOpenAI verso LM Studio, verifica via GET /v1/models
    strumenti.py   # ora_corrente(fuso), istante iniettabile
    grafo.py       # stato, nodi, instradamento, build_graph(llm, orologio, max_passaggi)
    cli.py         # ciclo di input, cronologia, uscita
  tests/
  docs/superpowers/{specs,plans}/
  Dockerfile, compose.yaml, .env.example, requirements.txt, README.md
```

## Grafo
Stato: `messaggi` (reducer `add_messages`), `passaggi` (int) e `interrotto` (bool, vero solo se il turno è finito in `limite`).

- `START -> modello`.
- Dopo `modello`:
  - nessun `tool_calls` -> `END`;
  - `tool_calls` e `passaggi < max_passaggi` -> `strumenti`;
  - `tool_calls` e limite raggiunto -> `limite`, che aggiunge il messaggio di errore e va a `END`.
- `strumenti -> modello`; ogni esecuzione di `strumenti` incrementa `passaggi`.

La CLI conserva la lista dei messaggi e la passa al grafo a ogni domanda. Nessun checkpointer.
Se un turno termina in `limite`, il messaggio di errore viene mostrato ma non entra nella
cronologia come risposta del modello. Per mantenere coerente la cronologia (ogni `tool_calls`
dev'essere seguito dai relativi `ToolMessage`), la CLI conserva solo i messaggi fino all'ultima
risposta completa: il turno interrotto viene scartato e l'utente ne è informato.

## Strumento orologio
`ora_corrente(fuso: str)`: richiede un nome IANA (per esempio `Europe/Rome`). Restituisce data e ora
ISO 8601 nel fuso richiesto. Fuso mancante o non valido: restituisce al modello un testo di errore
leggibile, senza sollevare eccezioni. L'istante viene da una funzione orologio iniettata, così i test
lo controllano. Ogni esecuzione scrive nel log nome, argomenti e risultato.

## Configurazione
Solo variabili d'ambiente, lette in `config.py`:
- `LMSTUDIO_BASE_URL` (per esempio `http://localhost:1234/v1`; in Docker
  `http://host.docker.internal:1234/v1`);
- `LMSTUDIO_MODEL`: obbligatoria, nessun valore predefinito;
- `MAX_PASSAGGI`: predefinito 5, intero positivo;
- `LOG_LEVEL`: predefinito `INFO`.

All'avvio `modello.py` chiama `GET /v1/models`:
- modello assente o non presente nell'elenco: stampa gli identificativi disponibili ed esce con errore;
- server non raggiungibile: messaggio con l'indirizzo provato ed uscita con errore.
La chiave API è un segnaposto fisso (richiesta dalla libreria, ignorata da LM Studio).
`.env.example` senza credenziali; `.env`, ambienti virtuali e cache restano fuori da Git.

## Log
`logging` standard su stderr (`ora livello nome messaggio`). La conversazione va su stdout.
- `INFO tool_call nome=ora_corrente args={...}` e `INFO tool_result ...` per ogni strumento eseguito;
- `WARNING` al raggiungimento del limite;
- livello da `LOG_LEVEL`.

## Docker
- `Dockerfile` da `python:3.12-slim`, dipendenze da `requirements.txt` con versioni fissate, più
  `tzdata` (assente nell'immagine slim).
- `compose.yaml` con un solo servizio `assistente`: `stdin_open`, `tty`, `env_file: .env`,
  `LMSTUDIO_BASE_URL` verso `host.docker.internal`, `extra_hosts: host.docker.internal:host-gateway`.
- Avvio con `docker compose run --rm assistente` (sessione interattiva).
- Il server di LM Studio deve essere raggiungibile dal container (ascolto su rete locale, non solo
  loopback): sarà indicato nel README.

## Dipendenze
`langgraph`, `langchain-openai`, `pytest`, più `tzdata` per i fusi su Windows e in Docker.
Versioni esatte fissate nel piano dopo l'installazione verificata. Su Python 3.10 pip risolve
`langgraph 1.2.17` e `langchain-openai 1.7.2`; l'immagine Docker usa Python 3.12.

## Test automatici (senza modello attivo)
Con un LLM finto che restituisce risposte predeterminate:
- grafo: risposta diretta senza strumenti; una chiamata allo strumento seguita dalla risposta finale;
  più chiamate in sequenza;
- limite: con `max_passaggi` basso e un LLM che chiede sempre lo strumento, il flusso termina in
  `limite` con il messaggio di errore e il warning nel log;
- instradamento: funzione di instradamento testata sui tre casi;
- cronologia: due domande successive, la seconda vede i messaggi della prima; turno interrotto scartato;
- strumento: istante fisso, fuso valido (`Europe/Rome`, `UTC`), fuso non valido o vuoto;
- log: `caplog` verifica `tool_call` e `tool_result`;
- configurazione: variabile mancante, `MAX_PASSAGGI` non valido, verifica elenco modelli con risposta HTTP simulata.
Comando: `python -m pytest` (PowerShell e Bash).

## Verifiche reali (attivate esplicitamente, separate dai test)
Documentate nel README e contrassegnate in pytest (`-m reale`, escluse di default):
1. LM Studio: con server attivo e modello caricato, la domanda «che ore sono a Tokyo?» deve produrre
   nel log una `tool_call` con fuso valido e una risposta finale coerente con il risultato.
   Se `google/gemma-4-e2b` non supporta il tool calling, l'esito va riportato così com'è.
2. Docker: `docker compose build` e `docker compose run --rm assistente` con la stessa domanda,
   verificando che il container raggiunga LM Studio sull'host.
Una risposta simulata non dimostra che il modello locale sappia usare lo strumento: il resoconto
finale indica che cosa è stato eseguito, con quale esito, e che cosa resta da provare.

## Criteri di successo
- Test automatici verdi senza LM Studio.
- Prova reale con LM Studio: strumento richiesto dal modello, eseguito, visibile nel log.
- Prova reale in Docker Compose con LM Studio sull'host.
- Limite di passaggi dimostrato da test automatico.
- README con soli comandi verificati, anche per PowerShell.
