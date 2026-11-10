# Resource MCP delle categorie dell'inventario: specifica

Data: 2026-11-10. Stato: approvata; **rivista durante le prove reali** e riapprovata (posizione del
contesto: nella descrizione del parametro `categoria` invece che in un `SystemMessage`, vedi «Revisione del
2026-11-10»).

## Contesto
Step 4 del percorso a 9 step, dopo router (`2026-11-09-router-design.md`), revisore
(`2026-11-09-revisore-design.md`) e riassunto (`2026-11-10-riassunto-design.md`). Il server MCP «archivio»
(`src/archivio/`) espone oggi solo strumenti (catalogo e note); il client (`src/assistente/mcp_client.py`) sa
solo elencarli e chiamarli. Lo step introduce la seconda primitiva MCP, la **resource**, nel server e nel
client. Nessuna dipendenza nuova (`mcp==2.3.0` già presente).

## Obiettivo
Dare all'agente, come contesto, l'elenco esatto delle categorie dell'inventario, letto dall'applicazione
tramite una resource MCP all'avvio, così che il modello conosca i nomi da usare nel filtro `categoria` di
`cerca_inventario` e sappia rispondere a «quali categorie ci sono?».

## Fuori ambito
- Resource consultabili dall'utente o dal modello (nessuno strumento «leggi resource», nessun comando).
- Rilettura durante la sessione: il CSV non cambia mentre l'assistente è attivo.
- Resource template, sottoscrizioni, notifiche di modifica.
- Prompt MCP, servizio HTTP (step successivi).
- Modifiche agli strumenti del server e alle loro descrizioni statiche (i nomi delle categorie sono aggiunti
  dal client, all'avvio, nella copia della definizione inviata al modello).
- Modifiche al grafo.

## Decisioni concordate
- **Ruolo:** contesto per il modello; la resource è letta dall'applicazione, non dal modello.
- **Contenuto:** categorie dell'inventario generate dal CSV, con i nomi esatti e il numero di articoli
  (circa 50 token); nessun testo scritto a mano (nessun regolamento).
- **Posizione (rivista):** i nomi delle categorie letti dalla resource sono aggiunti, all'avvio, alla
  descrizione del parametro `categoria` di `cerca_inventario` nella definizione inviata al modello. Nessun
  `SystemMessage`: anteposto a ogni chiamata dell'agente faceva perdere il tool calling (vedi «Revisione»).
- **Guasto della lettura:** l'assistente parte senza i nomi (descrizione invariata), con un avviso; un
  archivio che non parte ferma l'assistente come oggi.

## Architettura

### Inventario (`src/archivio/inventario.py`)
- `Inventario.categorie() -> list[tuple[str, int]]`: coppie (nome della categoria come scritto nel CSV,
  numero di articoli), in ordine alfabetico del nome senza maiuscole e accenti. Il conteggio è il numero di
  righe (articoli), non la somma delle quantità. Come nel filtro di `cerca`, nomi che differiscono solo per
  maiuscole o accenti sono una sola categoria (nome mostrato: quello usato nei messaggi di `cerca`; dalla
  revisione finale).

### Server (`src/archivio/server.py`)
- Costanti `URI_CATEGORIE = "archivio://inventario/categorie"` e
  `INTESTAZIONE_CATEGORIE = "Categorie dell'inventario (nomi esatti per il filtro categoria di cerca_inventario):"`.
- In `crea_server`, una resource registrata con `URI_CATEGORIE`, nome `categorie`, `mime_type="text/plain"`
  e una descrizione breve. Il testo è generato a **ogni lettura** da `inventario.categorie()`:
  ```
  Categorie dell'inventario (nomi esatti per il filtro categoria di cerca_inventario):
  - alimentatori (3 articoli)
  - attrezzi (4 articoli)
  ...
  ```
  Con un solo articolo: `(1 articolo)`. Inventario senza articoli: la sola intestazione.
- Strumenti invariati.

### Client (`src/assistente/mcp_client.py`)
- `ClientArchivio.leggi_risorsa(uri: str) -> str`: sincrona; invia `read_resource(uri)` alla sessione
  persistente con lo stesso meccanismo e lo stesso timeout di `_chiama` (coroutine sul loop del thread,
  `futuro.result(timeout)`). Restituisce il testo del **primo** contenuto.
- Solleva `ErroreArchivio` con una causa leggibile se: il client è chiuso; la risposta non arriva entro il
  timeout (la richiesta viene annullata); il server risponde con un errore (per esempio URI sconosciuto);
  la risposta non ha contenuti o il primo non è testuale.
- A differenza di `_chiama` (che restituisce testi `Errore: ...` al modello) qui l'errore è un'eccezione,
  perché chi legge è l'applicazione.
- `nomi_categorie(testo: str) -> list[str]`: dalle righe del testo della resource che cominciano con `- `,
  il nome fino all'ultima ` (`; intestazione e righe di altra forma ignorate.
- `con_categorie(strumenti: list[Strumento], nomi: list[str]) -> list[Strumento]`: restituisce la lista con
  la definizione di `cerca_inventario` copiata (le altre voci invariate, l'originale non modificato) e
  `" Categorie esistenti: " + ", ".join(nomi) + "."` aggiunto alla descrizione della proprietà `categoria`.
  Con `nomi` vuoto, o senza `cerca_inventario` o senza proprietà `categoria`, la lista è restituita
  invariata.

### CLI (`src/assistente/cli.py`)
- Subito dopo l'apertura di `ClientArchivio`, prima di `verifica_modello`, `cli` legge
  `mcp_client.URI_CATEGORIE`. La costante è definita sia nel client sia nel server, perché l'assistente non
  importa il pacchetto `archivio` (regola già seguita per `NOTE_DB`); la coincidenza dei due valori è
  verificata dal test di `leggi_risorsa` sul server vero.
- Successo → log INFO `contesto: letta la resource <uri> (<n> categorie)`; gli strumenti esterni passati a
  `crea_strumenti` sono `con_categorie(archivio.strumenti(), nomi)`.
- `ErroreArchivio` → log WARNING `contesto non disponibile: <causa>`; strumenti esterni invariati;
  l'assistente parte.

## Log (evidenze)
- `assistente.cli`: INFO `contesto: letta la resource <uri> (<n> categorie)`; WARNING
  `contesto non disponibile: <causa>`.

## Test
(a) Automatici, senza LM Studio (`python -m pytest`):
- `tests/test_archivio_inventario.py`: `categorie()` con l'inventario di esempio (nomi e conteggi, ordine
  alfabetico) e con un CSV di prova (categoria con un solo articolo, nomi scritti diversamente).
- `tests/test_archivio_server.py`: la resource è elencata con URI, nome e `mime_type`; la lettura restituisce
  intestazione e righe attese; singolare `1 articolo`; inventario vuoto; testo generato a ogni lettura;
  strumenti invariati.
- `tests/test_mcp_client.py`: `leggi_risorsa(URI_CATEGORIE)` sul server vero restituisce il testo con tutte le
  categorie dell'inventario di esempio; URI sconosciuto, client chiuso, server morto, contenuto non testuale
  → `ErroreArchivio`; `nomi_categorie` (testo vero, intestazione sola, righe estranee, nome con parentesi);
  `con_categorie` (descrizione attesa, altre voci e originale invariati, nomi vuoti, strumento assente).
- `tests/test_cli.py`: `main` legge la resource e passa a `crea_strumenti` la definizione arricchita (log
  INFO); se `leggi_risorsa` solleva `ErroreArchivio`, WARNING `contesto non disponibile: ...`, definizioni
  invariate, l'assistente parte e risponde.

(b) Prove reali con LM Studio (`python -m pytest -m reale -v -s`), in `tests/reale/test_lmstudio.py`:
- le prove reali che costruiscono il grafo usano gli strumenti arricchiti come la CLI;
- **vincolante:** «Quali categorie ci sono nell'inventario?» → la risposta contiene tutti i nomi delle
  categorie;
- **osservazione** (`pytest.xfail` se non riesce): «Che cosa c'è fra gli strumenti di misura?» →
  `cerca_inventario` con `categoria` uguale a `strumenti di misura`;
- **osservazione:** «Che componenti passivi abbiamo in laboratorio?» → `cerca_inventario` con `categoria` esatta e un
  risultato che comincia con `Trovat` (nella sonda il modello aggiungeva `testo: 'tutti'` → nessun articolo);
- l'intera suite `-m reale` rilanciata: le descrizioni degli strumenti cambiano il comportamento del
  modello.

(c) Prove manuali: avvio con `LOG_LEVEL=INFO python avvia.py` (PowerShell) e con Docker
(`docker compose run --rm -T -e LOG_LEVEL=INFO assistente`): riga INFO del contesto e risposta corretta a
«Quali categorie ci sono nell'inventario?», uscita 0.

## Revisione del 2026-11-10 (durante le prove reali)
- Con il contesto in un `SystemMessage` in testa a ogni chiamata dell'agente (prima versione della
  specifica) la suite reale ha dato 3 regressioni vere: `test_il_modello_cerca_per_categoria`,
  `test_il_modello_aggiunge_una_nota_senza_codice`, `test_il_modello_elenca_le_note`, tutte senza alcuno
  strumento chiamato (altre 11 fallite per LM Studio non raggiungibile, guasto dell'ambiente).
- Sonda con una sola chiamata all'agente (`gemma-4-e2b`, tre domande: «Annota che il saldatore va pulito»,
  «Quali note ci sono?», «Che cosa c'è fra gli strumenti di misura?»): senza contesto strumenti 9/9 (e
  categoria esatta 3/3 già senza contesto); con il `SystemMessage` del contesto 0/9 («ho bisogno di sapere
  …», «non ho abbastanza informazioni»).
- Varianti (una chiamata per domanda): system breve neutro 3/3; system con il riassunto dello step 3 2/3
  («Annota…» senza strumento); contesto + «usa sempre gli strumenti» 2/3; sole righe delle categorie 1/3;
  coppia utente/assistente 0/3.
- Nomi delle categorie nella descrizione del parametro `categoria`, senza `SystemMessage`: 12/12 chiamate
  corrette (sei domande, due volte); «Quali categorie ci sono nell'inventario?» risposto dalla descrizione,
  senza strumenti. Una volta per domanda «Che componenti passivi abbiamo?» → `testo: 'tutti'` oltre alla
  categoria (risultato «Nessun articolo trovato»): osservazione nella prova reale.
- Decisione dell'utente: nomi delle categorie nella descrizione del parametro; resource, client e lettura
  all'avvio invariati; il grafo non cambia.
- Prove reali dopo la revisione: elenco delle categorie (vincolante) e le due osservazioni riuscite; la
  domanda dell'osservazione è «Che componenti passivi abbiamo in laboratorio?», perché «Che componenti
  passivi abbiamo?» è stata rifiutata dal router come fuori ambito (1/1; il router non vede le descrizioni).
  Suite intera: 30 passate, 1 fallita (`test_riassunto_conserva_la_nota`, nota tolta dal tetto del
  riassunto; poi 2/2 da sola), 5 xfailed, 1 xpassed.
- Da notare per lo step 3: anche il `SystemMessage` del riassunto fa perdere una chiamata («Annota…») nella
  sonda; limite noto, non trattato in questo step.

## Documentazione
README: sezione sulla resource (URI, contenuto, uso nella descrizione di `cerca_inventario`, righe di log,
limite del `SystemMessage` misurato) e diagnosi (`contesto non disponibile`). `CLAUDE.md`: resource
nell'obiettivo e nella descrizione di `src/archivio/`. Handoff aggiornato. Un solo commit a fine step con
specifica, piano, codice, test e documenti (`feat(archivio): ...`).
