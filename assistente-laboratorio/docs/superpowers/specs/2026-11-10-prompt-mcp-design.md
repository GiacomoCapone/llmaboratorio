# Prompt MCP «scheda_articolo»: specifica

Data: 2026-11-10. Stato: approvata.

## Contesto
Step 5 del percorso a 9 step, dopo la resource delle categorie (`2026-11-10-resource-mcp-design.md`). Il
server MCP «archivio» (`src/archivio/`) espone strumenti e una resource; il client
(`src/assistente/mcp_client.py`) elenca e chiama gli strumenti e legge le resource. Lo step introduce la terza
primitiva MCP, il **prompt**, nel server e nel client, e un comando della CLI per usarla. Nessuna dipendenza
nuova (`mcp==2.3.0`).

## Obiettivo
L'utente richiama dalla CLI un prompt offerto dal server, con i suoi argomenti; il testo generato dal server
diventa la domanda del turno, come se l'utente l'avesse scritta.

## Fuori ambito
- Prompt oltre `scheda_articolo`; prompt con più messaggi, messaggi dell'assistente o risorse incorporate.
- Completamento automatico, argomenti fra virgolette, storico dei comandi.
- Dati dell'articolo copiati nel testo del prompt: li forniscono gli strumenti chiamati dall'agente.
- Modifiche a grafo, router, revisore, riassunto, strumenti e resource.

## Decisioni concordate
- **Ruolo:** comando dell'utente (uso previsto da MCP per i prompt), non istruzione per l'applicazione.
- **Prompt:** `scheda_articolo` con l'argomento obbligatorio `codice`; il testo chiede i dettagli dell'articolo
  e le sue note, così l'agente usa `dettaglio_articolo` ed `elenca_note`.
- **Sintassi:** una riga che comincia con `/` è un prompt del server: `/scheda_articolo MIS-001`; `/prompt`
  elenca i prompt offerti. Un prompt nuovo sul server non richiede codice nuovo nella CLI.
- **Turno:** il testo espanso passa da router, agente e revisore e resta in cronologia come `HumanMessage`.
- **Validazione:** il server normalizza e verifica il codice; un errore non avvia alcun turno.

## Architettura

### Server (`src/archivio/server.py`)
- Costanti `DESCRIZIONE_SCHEDA = "Scheda di un articolo dell'inventario con le sue note."` e
  `TESTO_SCHEDA = "Dammi i dettagli dell'articolo {codice} e le note che lo riguardano."`.
- In `crea_server`, `@server.prompt(name="scheda_articolo", description=DESCRIZIONE_SCHEDA)` su una funzione
  `scheda_articolo(codice: str) -> str`:
  - `canonico = inventario.codice_canonico(codice)` (spazi, maiuscole: `mis-001` → `MIS-001`);
  - codice vuoto o sconosciuto → solleva `MCPError(-32602, "nessun articolo con codice '<codice>'.")`
    (`mcp.shared.exceptions`; un'altra eccezione arriverebbe al client solo come «Error rendering prompt
    scheda_articolo», verificato con `mcp==2.3.0`);
  - altrimenti restituisce `TESTO_SCHEDA.format(codice=canonico)`, che l'SDK manda come un solo messaggio
    `user` testuale.
- Il codice mostrato nell'errore è quello ricevuto, senza spazi in testa e in coda.
- Strumenti e resource invariati; docstring del modulo aggiornata.

### Client (`src/assistente/mcp_client.py`)
- `PromptArchivio` (dataclass congelata): `nome: str`, `descrizione: str`, `argomenti: list[str]` (nomi degli
  argomenti nell'ordine dichiarato dal server).
- Nel compito `_vivi`, dopo `list_tools`, anche `list_prompts` (stesso `fail_after`); il risultato è
  conservato come gli strumenti.
- `ClientArchivio.prompt_disponibili() -> list[PromptArchivio]`: l'elenco letto all'avvio.
- `ClientArchivio.testo_prompt(nome: str, argomenti: dict[str, str]) -> str`: `get_prompt(nome, argomenti)`
  con lo stesso meccanismo e timeout di `leggi_risorsa`; restituisce il testo dell'unico messaggio `user`
  testuale. Solleva `ErroreArchivio`:
  - client chiuso → `archivio non disponibile.`;
  - timeout → `l'archivio non ha risposto entro <t> secondi.`;
  - errore del server → il messaggio del server (per esempio `nessun articolo con codice 'XYZ'.`);
  - connessione chiusa (server terminato a metà sessione) → `archivio non disponibile.` (dalla revisione
    finale: l'SDK direbbe `Connection closed`);
  - risposta senza un messaggio `user` testuale → `il prompt <nome> non ha prodotto una domanda.`
- La logica comune di invio e attesa di `leggi_risorsa` e `testo_prompt` può stare in un aiuto privato; la
  scelta è del piano.

### CLI (`src/assistente/cli.py`)
- `ciclo(grafo, leggi, scrivi, prompt=None)`: `prompt` è un oggetto con `prompt_disponibili()` e
  `testo_prompt()`; in `main` è il `ClientArchivio`. Con `prompt=None` il ciclo è quello di oggi (una riga
  `/...` va al modello).
- Riga che comincia con `/` (dopo la pulizia di BOM e spazi), con `prompt` presente:
  - `/prompt` → una riga per prompt: `/<nome> <arg1> <arg2> — <descrizione>` (argomenti fra `<>`); nessun
    prompt → `Nessun prompt disponibile.`; nessun turno;
  - `/<nome> resto`: nome sconosciuto → `Errore: prompt sconosciuto '/<nome>'. Scrivere /prompt per
    l'elenco.`; il resto è diviso sugli spazi in al più N parti, con N il numero di argomenti dichiarati
    (l'ultimo prende il resto della riga); meno di N parti → `Errore: /<nome> richiede: <arg1> <arg2>.`;
    un prompt senza argomenti con testo in più → `Errore: /<nome> non ha argomenti.`;
  - argomenti validi → `testo_prompt`; `ErroreArchivio` → `Errore: <causa>`; successo → log INFO
    `prompt: /<nome> <argomenti come dict>`, `scrivi("(prompt) " + testo)` e turno normale con `testo` come
    domanda (stessa gestione di Ctrl-C ed errori del turno). Ctrl-C mentre si attende il server →
    `(turno annullato)`, sessione viva (dalla revisione finale).
  - Gli errori non avviano turni e non toccano la cronologia.
- `main` passa `prompt=archivio` a `ciclo`. Il messaggio di benvenuto cita `/prompt`:
  `Assistente del laboratorio. Scrivere 'esci' per terminare, '/prompt' per i prompt dell'archivio.`

## Log (evidenze)
- `assistente.cli`: INFO `prompt: /scheda_articolo {'codice': 'MIS-001'}`.

## Test
(a) Automatici, senza LM Studio (`python -m pytest`):
- `tests/test_archivio_server.py`: il prompt è elencato con nome, descrizione e argomento `codice` obbligatorio;
  `mis-001` e ` MIS-001 ` → testo con `MIS-001`; codice sconosciuto e vuoto → `MCPError` con
  `nessun articolo con codice`.
- `tests/test_mcp_client.py` (server vero via stdio): `prompt_disponibili()` contiene
  `PromptArchivio("scheda_articolo", DESCRIZIONE, ["codice"])`; `testo_prompt("scheda_articolo",
  {"codice": "mis-001"})` → testo atteso; codice sconosciuto → `ErroreArchivio` con il messaggio del server;
  prompt sconosciuto, client chiuso → `ErroreArchivio`; risposta senza messaggio `user` (sessione finta) →
  `ErroreArchivio`.
- `tests/test_cli.py` (archivio finto e grafo che registra): `/prompt` elenca senza turno; `/scheda_articolo
  mis-001` → riga `(prompt) ...` e turno con il testo come `HumanMessage`, che resta in cronologia; argomento
  mancante, nome sconosciuto, testo in più per un prompt senza argomenti, `ErroreArchivio` → messaggio
  d'errore, nessun turno; argomento con spazi preso intero dall'ultimo argomento; con `prompt=None` la riga
  `/...` va al grafo; `main` passa l'archivio a `ciclo` e mostra il benvenuto nuovo.

(b) Prove reali con LM Studio (`python -m pytest -m reale -v -s`), in `tests/reale/test_lmstudio.py`:
- **vincolante:** con il testo di `testo_prompt("scheda_articolo", {"codice": "MIS-001"})` e un database delle
  note con una nota su MIS-001, il router classifica `conversazione` e l'agente chiama `dettaglio_articolo`
  con `MIS-001`;
- **osservazione** (`pytest.xfail`): nello stesso turno l'agente chiama anche `elenca_note` con `MIS-001`;
- l'intera suite `-m reale` rilanciata.

(c) Prove manuali da PowerShell (`.venv\Scripts\python.exe avvia.py`) e con Docker
(`docker compose run --rm -T -e LOG_LEVEL=INFO assistente`), input `/prompt`, `/scheda_articolo MIS-001`,
`esci`: elenco, riga `(prompt) ...`, risposta con i dati dell'articolo, uscita 0.

## Documentazione
README: sezione sui prompt (comandi `/prompt` e `/<nome>`, prompt `scheda_articolo`, errori, riga di log).
`CLAUDE.md`: prompt nell'obiettivo e in `src/archivio/`. Handoff aggiornato. Un solo commit a fine step con
specifica, piano, codice, test e documenti (`feat(archivio): ...`).
