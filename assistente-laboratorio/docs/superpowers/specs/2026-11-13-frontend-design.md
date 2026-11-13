# Step 8 — Front-end delle conversazioni

Data: 2026-11-13. Stato: approvata.

## Intento
Lo step 7 ha dato al progetto un back-end che conserva più conversazioni in PostgreSQL e chiama l'agente HTTP.
Lo step 8 aggiunge una **pagina web** da cui usare l'assistente senza terminale: elenco delle conversazioni,
chat, comandi dei prompt dell'archivio. Lo step 9 metterà i quattro servizi (postgres, agente, back-end,
front-end) in Docker Compose.

## Decisioni dell'utente (brainstorming del 2026-11-13)
- **HTML, CSS e JavaScript semplici**, senza build né framework, serviti da un piccolo servizio Python che
  inoltra `/api/...` al back-end (approccio A, vedi «Approcci»).
- **Disposizione A** fra le tre bozze mostrate: elenco delle conversazioni a sinistra, chat a destra, comandi
  `/nome argomenti` scritti nella casella con un menu che compare digitando `/`.
- **Solo su questo computer:** il servizio ascolta su `127.0.0.1`, come tutti gli altri.
- Proposte esposte all'utente e non contestate: conferma prima di eliminare; scomposizione dei comandi uguale
  alla CLI, con errori mostrati senza chiamare il back-end; in caso di errore la domanda resta nella casella;
  risposte mostrate come testo semplice; pacchetto `src/frontend/`; variabili `BACKEND_URL`, `FRONTEND_HOST`,
  `FRONTEND_PORTA`; avvio `python avvia.py --frontend`; servizio Compose rimandato allo step 9; JavaScript
  provato a mano nel browser (non c'è Node); aggiornamento della regola «niente interfacce grafiche» in
  CLAUDE.md.

## Obiettivi
- Pacchetto `src/frontend/` con un servizio Starlette + uvicorn (già dipendenze) che:
  - serve i file statici della pagina da `src/frontend/statico/` (`index.html`, `app.js`, `stile.css`);
  - inoltra ogni richiesta `/api/<percorso>` a `BACKEND_URL/<percorso>` con `httpx` (già dipendenza).
- Una pagina che copre tutta l'API del back-end: elenco, creazione, apertura, eliminazione delle conversazioni,
  invio di domande e di prompt, elenco dei prompt.
- Test automatici ripetibili del servizio Python senza back-end; prova manuale della pagina nel browser con
  una lista di controllo scritta.

## Non obiettivi
- Servizio Compose del front-end (step 9).
- CORS sul back-end (la pagina e `/api` hanno la stessa origine).
- Accesso da altri computer, utenti, autenticazione.
- Rinomina delle conversazioni, ricerca, paginazione, streaming delle risposte.
- Resa di Markdown o HTML nelle risposte.
- Test automatici del JavaScript (richiederebbero Node o un browser pilotato: dipendenze non concordate).
- Nuove dipendenze Python o librerie JavaScript esterne (niente CDN: la pagina funziona anche senza Internet).

## Anti-obiettivi (sarebbe un fallimento anche se funziona)
- Il front-end che importa `assistente` o `backend`, o che parla direttamente con l'agente o con PostgreSQL.
- Una risposta del modello che, contenendo `<...>`, altera la pagina (testo inserito come HTML).
- Un turno lungo che blocca il servizio del front-end: mentre si aspetta una risposta, la pagina deve poter
  ancora elencare e aprire le conversazioni.
- Una domanda persa: se l'invio fallisce, il testo scritto non deve sparire.
- Una pagina che dice «salvato» quando il back-end non ha salvato nulla.

## Approcci
- **A — HTML/CSS/JS semplici, servizio Starlette con proxy (scelto).** Nessuna build, nessuna dipendenza
  nuova, stessa origine per pagina e API quindi niente CORS; il servizio Python è testabile con pytest. Il
  JavaScript si prova solo a mano.
- B — Streamlit o Gradio: pagina scritta in Python, ma dipendenza grande e non concordata, poco controllo su
  attesa ed errori, e il modello di esecuzione di Streamlit (rilancio dello script a ogni interazione) si
  adatta male a turni di minuti.
- C — React o Vue con Vite: richiede Node, una build e molte dipendenze; sproporzionato per una pagina sola.

## Architettura
```
browser ──► front-end :8002 ──/api/*──► back-end :8001 ──► agente :8000 ──► LM Studio
              │ file statici               │
              └ src/frontend/statico/       └► PostgreSQL :5433
```

### Pacchetto `src/frontend/`
- `config.py`: `ConfigFrontend` (dataclass congelata) e `carica_config(env=None)`, sullo stesso schema di
  `backend/config.py` (`.env` del progetto + ambiente, l'ambiente prevale; `ErroreConfigurazione`).
  | Variabile | Predefinito | Note |
  |---|---|---|
  | `BACKEND_URL` | `http://127.0.0.1:8001` | barra finale tolta |
  | `BACKEND_TIMEOUT` | `960` | secondi, numero positivo finito; più di `AGENTE_TIMEOUT` (900) così l'errore del back-end arriva prima del timeout del proxy |
  | `FRONTEND_HOST` | `127.0.0.1` | |
  | `FRONTEND_PORTA` | `8002` | intero 1–65535 |
  | `LOG_LEVEL` | `INFO` | |
  Nessuna variabile è obbligatoria. Messaggi di errore sullo stile di quelli del back-end
  (`FRONTEND_PORTA deve essere un intero fra 1 e 65535, trovato '...'.`).
- `app.py`: `crea_app(backend_url: str, timeout: float, transport: httpx.AsyncBaseTransport | None = None)
  -> Starlette`. Il `transport` serve ai test.
- `__main__.py`: `servi(config)` e `main(argv)` come in `backend/__main__.py`.
- `statico/index.html`, `statico/app.js`, `statico/stile.css`.
- Non importa `assistente` né `backend`.

### Rotte del servizio
- `GET /` → `index.html`; `GET /app.js`, `GET /stile.css` → i file. Tipi: `text/html; charset=utf-8`,
  `text/javascript; charset=utf-8`, `text/css; charset=utf-8` (il charset evita il mojibake già visto con
  Windows). Nessun altro file servito; altri percorsi fuori da `/api` → 404.
- `/api/{percorso:path}` con metodi `GET`, `POST`, `DELETE` → stessa richiesta a `BACKEND_URL/{percorso}`:
  metodo, percorso, query string, corpo e `Content-Type` inoltrati; della risposta del back-end si
  restituiscono **invariati** codice di stato, corpo e `Content-Type` (204 senza corpo compreso). Gli altri
  metodi su `/api` → 405 di Starlette.
- Il proxy è **asincrono** (`httpx.AsyncClient`, un client per l'app creato all'avvio e chiuso alla fine con
  il lifespan di Starlette): un turno di minuti non deve bloccare le altre richieste.
- Back-end irraggiungibile o errore di rete → `502 {"errore": "back-end non disponibile: <causa>"}`;
  tempo scaduto → `502 {"errore": "back-end non disponibile: tempo scaduto dopo <n> s"}`. JSON con
  `charset=utf-8`, come nel back-end.

### Avvio
- `python avvia.py --frontend` (in `avvia.py` un ramo come quello di `--backend`). La riga d'uso di tutti i
  `main` diventa `Uso: python avvia.py [--http | --backend | --frontend]`.
- Il servizio scrive nel log `frontend in ascolto su http://127.0.0.1:8002`. Non serve PostgreSQL né il
  back-end per avviarlo: se il back-end manca, la pagina mostra l'errore 502.

## La pagina

### Disposizione (bozza A)
```
┌──────────────────────┬───────────────────────────────────────────────┐
│ + Nuova conversazione│ Quanti multimetri abbiamo in…        Elimina │
│ ▸ Quanti multimetri… │                                               │
│   oggi 10:42         │                   Quanti multimetri…   10:41 │
│   /scheda_articolo…  │ 10:42 Nell'inventario risultano 4…           │
│   ieri 16:05         │ L'assistente sta rispondendo… (1:12)          │
│                      ├───────────────────────────────────────────────┤
│                      │ [/sch ▾ /scheda_articolo <codice> — …] Invia │
└──────────────────────┴───────────────────────────────────────────────┘
```

### Elenco delle conversazioni
- Da `GET /api/conversazioni`, nell'ordine del back-end (più recente prima). Ogni voce: titolo e data/ora di
  `aggiornata` in forma breve (oggi → `10:42`, altrimenti `gg/mm hh:mm`, ora locale del browser).
- «+ Nuova conversazione» → `POST /api/conversazioni`, la nuova va in cima e si apre.
- Un clic apre la conversazione (`GET /api/conversazioni/{id}`) e ne mostra i messaggi con ora e ruolo.
- La conversazione aperta è evidenziata. L'elenco si ricarica dopo ogni turno riuscito (titolo e ordine
  cambiano) e dopo un'eliminazione.
- Senza conversazioni o senza una aperta, la chat mostra un invito; scrivere e inviare in questo stato crea
  prima la conversazione e poi invia il messaggio.

### Chat
- Messaggi dell'utente a destra, dell'assistente a sinistra, con l'ora. Testo inserito con `textContent`
  (mai `innerHTML` con dati del back-end), a capo conservati (`white-space: pre-wrap`).
- «Elimina» in testata: `confirm("Eliminare la conversazione «<titolo>»?")`, poi
  `DELETE /api/conversazioni/{id}`; la chat torna all'invito.
- Casella di testo su più righe: **Invio** invia, **Maiusc+Invio** va a capo. Testo vuoto o solo spazi → non
  si invia nulla.

### Invio e attesa
1. La domanda compare subito in chat (provvisoria) e sotto «L'assistente sta rispondendo… (m:ss)», con il
   tempo che avanza ogni secondo.
2. Casella, «Invia» ed «Elimina» della conversazione in corso sono disabilitati. **Un solo turno alla volta
   per pagina**: anche aprendo un'altra conversazione la casella resta disabilitata finché il turno non
   finisce; navigare fra le conversazioni resta possibile.
3. Risposta 200: si mostrano i due messaggi restituiti (`messaggi[utente, assistente]`, con le ore del
   back-end) al posto di quello provvisorio, la casella si svuota e si riabilita, l'elenco si ricarica. Se nel
   frattempo si è aperta un'altra conversazione, la risposta non si mostra lì: comparirà riaprendo quella
   giusta.
4. Errore (qualsiasi codice diverso da 200, o rete): il messaggio provvisorio sparisce, compare un avviso
   rosso nella chat con il testo `errore` del back-end (o `errore di rete: <dettaglio>` se la richiesta non
   è arrivata) seguito da «Il messaggio non è stato salvato.»; la casella si riabilita **con la domanda
   ancora scritta**. L'avviso sparisce al prossimo invio o cambiando conversazione. Casi attesi: 400, 404,
   409 (`turno in corso…`, per esempio da un'altra scheda), 422, 500, 502.
   Eccezione (scelta mia dopo la revisione): se la risposta non viene dal back-end, cioè errore di rete del
   browser o 502 del proxy con testo che inizia per `back-end non disponibile:`, il back-end potrebbe aver
   salvato il turno comunque; allora la frase è «Il messaggio potrebbe non essere stato salvato: riapri la
   conversazione per controllare.» (la domanda resta comunque nella casella).
- Ricaricare la pagina durante un turno: il turno continua nel back-end; la pagina riparte senza stato di
  attesa e la risposta compare riaprendo la conversazione quando è pronta. Accettato, da scrivere nel README.

### Comandi dei prompt
- All'avvio della pagina, `GET /api/prompt` → `{"prompt": [{"nome", "argomenti", "descrizione"}]}`. Se
  fallisce, i comandi non sono disponibili: digitando `/` il menu mostra «Comandi non disponibili: <errore>»
  e una riga `/...` inviata dà lo stesso avviso, senza chiamare il back-end. Un nuovo tentativo di
  `GET /api/prompt` avviene a ogni invio di una riga `/...` finché non riesce.
- **Menu:** quando il testo della casella inizia con `/` e non contiene ancora spazi, sopra la casella compare
  l'elenco dei prompt il cui nome inizia con quanto scritto, più la voce `/prompt`, nel formato della CLI:
  `/scheda_articolo <codice> — <descrizione>`. Clic o Tab completano `/<nome> ` nella casella; Esc chiude.
- **Scomposizione all'invio** di una riga che inizia con `/` (stessa regola e stessi testi della CLI,
  `src/assistente/cli.py`):
  - `nome` = testo fino al primo spazio, `resto` = il resto senza spazi ai bordi;
  - `/prompt` senza resto → l'elenco dei prompt (stesso formato del menu) compare in chat come avviso
    informativo locale, non salvato e senza chiamare il back-end;
  - nome sconosciuto → `Errore: prompt sconosciuto '/<nome>'. Scrivere /prompt per l'elenco.`;
  - prompt senza argomenti e `resto` non vuoto → `Errore: /<nome> non ha argomenti.`;
  - con N argomenti: `resto` diviso sugli spazi in al più N parti (l'ultima tiene il resto, come
    `str.split(maxsplit=N-1)`); meno di N parti → `Errore: /<nome> richiede: <a1> <a2>.`;
  - altrimenti `POST /api/conversazioni/{id}/messaggi` con `{"prompt": {"nome", "argomenti": {a1: v1, …}}}`.
  Gli errori di scomposizione compaiono come avviso (come al punto 4, ma senza «non è stato salvato»), la riga
  resta nella casella.
- Ogni altra riga va come `{"domanda": "<testo>"}`. In chat la riga di un prompt compare come la mostra il
  back-end (`/scheda_articolo MIS-001`).

### Aspetto
- Sobrio, come le bozze: colori in variabili CSS, font di sistema, nessuna immagine o libreria esterna.
- Larghezza minima ragionevole per una finestra desktop; sotto i 700 px l'elenco si nasconde dietro un
  pulsante «Conversazioni» (scelta del builder sul dettaglio).
- Titolo della scheda del browser: «Assistente del laboratorio».

## Test e verifiche
- **Automatici (pytest, inclusi di default, senza back-end):**
  - `tests/test_frontend_config.py`: predefiniti, precedenza dell'ambiente, valori non validi.
  - `tests/test_frontend_app.py` con `TestClient` di Starlette e un back-end finto via
    `httpx.MockTransport`: file statici con tipo e charset giusti, 404 per altri percorsi, inoltro di metodo,
    percorso, query, corpo e `Content-Type`; codice, corpo e tipo della risposta invariati (200, 201, 204,
    400, 404, 409, 502); 405 per `PUT`; back-end irraggiungibile e tempo scaduto → 502 con i testi fissati.
  - Avvio: riga d'uso aggiornata, `avvia.py --frontend` instradato a `frontend.__main__.main` (sullo schema
    dei test di avvio già presenti).
  - Controlli statici sui file della pagina: `index.html` referenzia `app.js` e `stile.css`; `app.js` non usa
    `innerHTML` (test di grep: la regola anti-iniezione resta vera nel tempo).
- **Manuali nel browser** (con PostgreSQL, agente e back-end avviati, LM Studio attivo): lista di controllo
  nel README, eseguita e riportata nel resoconto — nuova conversazione, domanda e attesa col tempo, risposta,
  titolo e ordine dell'elenco aggiornati, riapertura, eliminazione con conferma, menu `/`, `/prompt`,
  `/scheda_articolo MIS-001`, errori di scomposizione, back-end spento (502 e domanda conservata), 409 da una
  seconda scheda, risposta con `<b>` mostrata come testo, ricarica durante un turno.
- La prova reale del modello resta quella dello step 7: il front-end non aggiunge logica sul modello.

## Documentazione
- README: avvio del front-end (PowerShell), variabili, ordine di avvio dei servizi, lista di controllo
  manuale, diagnosi (pagina con 502 → back-end spento; 502 «agente non disponibile» → agente spento o in
  avvio).
- CLAUDE.md: struttura (`src/frontend/`), comando di avvio, e la regola dei confini diventa «Niente servizi
  cloud o framework non concordati; l'unica interfaccia grafica è la pagina web di `src/frontend/`
  (HTML/CSS/JS senza build)».
- `.env.example`: le nuove variabili commentate con i predefiniti.

## Lasciato al builder
- Struttura interna di `app.js` (funzioni, nomi), stile visivo entro le indicazioni sopra.
- Formato preciso delle date nell'elenco oltre a quanto indicato.
- Dettagli della vista sotto i 700 px.

## Revisione del 2026-11-13 (esecuzione)
- I tre file statici hanno anche `Cache-Control: no-cache`: nelle prove Edge riusava la vecchia `app.js` dopo una
  modifica; così il browser riconvalida con l'ETag.
- Un turno è legato alla conversazione aperta **al momento dell'invio**; se il turno fallisce mentre è aperta
  un'altra conversazione, la pagina torna a quella del turno e mostra lì l'avviso (la domanda resta nella casella).
  Dopo un turno riuscito i messaggi si rileggono dal back-end invece di essere accodati.
