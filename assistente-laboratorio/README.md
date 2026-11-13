# Assistente del laboratorio

Applicazione da terminale in Python che conversa con un modello locale servito da LM Studio.
Il flusso è un grafo LangGraph esplicito; la cronologia vale per la sola sessione (nessuna
persistenza); solo le note del laboratorio (vedi «Strumenti») restano in un database SQLite; un back-end
separato (vedi «Back-end delle conversazioni») conserva più conversazioni in PostgreSQL. Il modello può chiamare lo strumento orologio (fuso orario esplicito), eseguito
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
router»), `MAX_REVISIONI` (default 2, intero ≥ 1; vedi «Revisore delle risposte») e
`RIASSUNTO_SOGLIA_TOKEN` (default 3000, intero ≥ 1; vedi «Riassunto della cronologia»),
`HTTP_HOST` (default `127.0.0.1`, indirizzo di ascolto del servizio HTTP) e `HTTP_PORTA` (default 8000,
intero da 1 a 65535; vedi «Servizio HTTP»). Un valore non
ammesso per `LMSTUDIO_REASONING_EFFORT` o `FUSO_PREDEFINITO`, o una città non presente in `src/assistente/strumenti/festivita.json`, ferma l'avvio con un errore (uscita 1). Per
una città sconosciuta il messaggio è `Città del patrono sconosciuta: '<valore>'. Città disponibili: ...
(file ...)`; verificato il 2026-11-03 con `CITTA_PATRONO=Milano` (uscita 1).

`CITTA_PATRONO` aggiunge ai giorni festivi del calendario la festa del patrono della città (maiuscole
e spazi esterni ignorati). Per aggiungere una città: aggiungere in `patroni` di
`src/assistente/strumenti/festivita.json` una voce come `"Pordenone": {"data": "04-25", "santo": "San Marco"}`
(data `MM-GG`) e rilanciare i test.

`FUSO_PREDEFINITO` è il fuso usato dall'orologio quando la domanda non indica un luogo
(«che ore sono»); il modello lo legge nella definizione dello strumento.

Per il back-end delle conversazioni (vedi «Back-end delle conversazioni») servono anche queste variabili,
tutte nel `.env`:
- `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD`: utente, nome e password del database PostgreSQL;
  li legge Compose per creare il servizio `postgres` e per costruire il `DATABASE_URL` del servizio `backend`.
  `.env.example` ha utente e nome di esempio; la password va scelta da chi configura (il `.env` non si versiona).
  Nella password usare solo lettere, cifre, `-` e `_`: altri caratteri rompono gli indirizzi (`DATABASE_URL`) e
  `$` è espanso da Compose.
- `DATABASE_URL` (obbligatoria solo per `python avvia.py --backend`): indirizzo del database per l'avvio locale,
  per esempio `postgresql://laboratorio:<password>@127.0.0.1:5433/laboratorio`. **Va tenuto allineato a
  `POSTGRES_*`** (stessi utente, password e nome): se la password è diversa, il database rifiuta l'accesso
  (vedi «Diagnosi»). La porta dell'host è la **5433** perché la 5432 è spesso occupata da un PostgreSQL
  installato sul computer (sul computer di sviluppo c'è un servizio PostgreSQL di Windows sulla 5432).
- `AGENTE_URL` (default `http://127.0.0.1:8000`, una `/` finale è tolta), `AGENTE_TIMEOUT` (default 900, secondi
  di attesa di un turno, numero maggiore di 0), `BACKEND_HOST` (default `127.0.0.1`) e `BACKEND_PORTA` (default
  8001, intero da 1 a 65535). Un valore non ammesso ferma l'avvio con `Errore: ...` (uscita 1).

Da quando `compose.yaml` ha il servizio `postgres`, **Compose richiede `POSTGRES_USER`, `POSTGRES_DB` e
`POSTGRES_PASSWORD` nel `.env` per qualunque comando**, anche per `docker compose run --rm assistente`
(la sostituzione `${POSTGRES_...:?}` fa fallire il comando se mancano). Il percorso `docker compose run --rm
assistente` con queste variabili presenti non è stato riprovato dopo lo step 7.

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

## Revisore delle risposte
Prima di arrivare all'utente, ogni risposta finale dell'agente passa da un nodo **revisore** (stesso modello,
prompt diverso), che controlla se tratta tutte le parti della domanda. Il modello chiama lo strumento
obbligatorio `Giudizio` elencando le `richieste` della domanda e quelle `mancanti` (senza risposta o con
una risposta che parla d'altro); la risposta è coerente se non manca nulla, e lo decide il programma.
Il motivo nei log è `richieste trattate: ...` oppure `manca la risposta a: ...`; una risposta vuota
torna all'agente senza chiamare il modello (motivo `risposta vuota`). Non verifica l'esattezza
dei dati: non vede i risultati degli strumenti.

```
… modello ⇄ strumenti / limite
      ↓ risposta finale
   revisore ─┬─ coerente → END
             ├─ non coerente, revisioni < MAX_REVISIONI → modello (con l'indicazione del revisore)
             └─ non coerente, limite raggiunto → END (ultima risposta)
```

Se la risposta non è coerente, il motivo torna all'agente come messaggio «Indicazione del revisore: ...»
e l'agente risponde di nuovo. `MAX_REVISIONI` (default 2) è il numero massimo di ritorni all'agente: con 2
l'agente risponde al massimo 3 volte; al limite l'utente riceve l'ultima risposta. A fine turno bozze
scartate e indicazioni sono tolte dalla cronologia (restano nei log): i turni successivi vedono solo
domanda, strumenti e risposta finale. Il revisore non interviene sul rifiuto del router né al limite dei
passaggi con gli strumenti. Ogni revisione aggiunge due chiamate al modello (revisore e agente).

Righe di log (`LOG_LEVEL=INFO`) da cercare:
- approvata: `revisore coerente=sì motivo=... → fine`;
- rimandata: `revisore coerente=no motivo=... → agente (revisione 1/2)` seguita da
  `agente: chiamata al modello`;
- limite: `revisore coerente=no motivo=... → fine` e
  `WARNING ... limite di revisioni raggiunto (2): restituita l'ultima risposta`.

Il revisore riceve domanda, risposta proposta e fino a due messaggi precedenti come testo in un solo
messaggio utente: con l'ultimo messaggio dell'assistente e lo strumento obbligatorio LM Studio risponde
`400 ... Unexpected empty grammar stack`. Il limite è di 1024 token in uscita: nonostante
`LMSTUDIO_REASONING_EFFORT=none`, `google/gemma-4-e2b` a volte ragiona fino a circa 300 token prima
della tool call (con 256 la valutazione veniva troncata); una valutazione dura circa 7–15 s.

Scelte misurate con `google/gemma-4-e2b` (specifica del revisore, «Revisione del 2026-11-10»): un
giudizio diretto «coerente sì/no» rifiutava risposte corrette (ora come timestamp, «quali festività?»);
lo schema `richieste`/`mancanti` le approva e rifiuta quelle parziali o fuori tema.
**Limiti noti:**
- una domanda di seguito («Che ore sono a Roma?» … «e a Londra?») è giudicata senza risposta anche
  quando la risposta è corretta, quindi può tornare all'agente fino a `MAX_REVISIONI` volte (prova reale
  `test_revisore_approva_risposta_di_seguito`, segnata `xfail`);
- il verdetto su risposte corrette a una sola richiesta (elenchi, «non ci sono note», «non ho accesso
  alle previsioni», «mi serve la data») cambia da una sessione di LM Studio all'altra: il modello ragiona
  in modo nascosto prima del giudizio. Le prove reali di approvazione
  (`test_revisore_approva_risposta_a_una_richiesta`) sono quindi osservazioni (`pytest.xfail` quando il
  verdetto è sbagliato); restano vincolanti il rifiuto di risposte parziali e fuori tema e l'approvazione
  di quella completa.

## Riassunto della cronologia
La cronologia della sessione (domande, passaggi con gli strumenti, risposte) va al modello a ogni turno, e
`google/gemma-4-e2b` è caricato con 8192 token di contesto. All'inizio di ogni turno un nodo **riassunto**
stima i token della cronologia (caratteri / 4). Se la stima supera `RIASSUNTO_SOGLIA_TOKEN` (default
3000), i turni più vecchi diventano un riassunto e restano intatti solo gli ultimi 2 turni più la domanda
corrente.

```
START → riassunto → router ─┬─ conversazione → modello ⇄ strumenti … → revisore → END
                             └─ fuori_ambito → rifiuto → END
```

- Il riassunto è un messaggio di sistema in testa alla cronologia, che comincia con «Riassunto della
  conversazione precedente:». Router, agente e revisore vedono già la cronologia compatta.
- Il modello (senza strumenti) riassume solo i turni appena usciti dalla parte intatta, compresi i
  risultati degli strumenti. Il programma accoda quel testo al riassunto precedente, che resta alla
  lettera: chiamato a fondere i due riassunti, il modello perdeva i fatti precedenti.
- Se il riassunto supera metà della soglia, il programma toglie le righe più vecchie.
- Se il riassunto non riesce (errore del modello o testo vuoto), la cronologia resta invariata e il turno
  prosegue.

Righe di log (`LOG_LEVEL=INFO`) da cercare:
- `riassunto: <k> messaggi riassunti, stima <n> → <m> token`;
- `riassunto: stima <n> token sopra la soglia <s>, niente da riassumere` (pochi turni, ma lunghi);
- `WARNING ... riassunto oltre <n> token: tolte <k> righe più vecchie`.

La soglia predefinita è stata scelta misurando: una domanda breve con una cronologia minima costa già circa
1750 `prompt_tokens`, quasi tutti per le definizioni dei 10 strumenti; 3000 token stimati di cronologia
restano entro gli 8192. La stima è grossolana: con testi molto diversi dall'italiano può sbagliare.

**Limiti noti:** dal riassunto in prosa `gemma-4-e2b` riprende i fatti («Che cosa ti avevo chiesto di
annotare?») ma non sempre un dato puntuale: «Che numero ha la nota che ho aggiunto?» ha fallito 6 volte su
6 nelle sonde con il riassunto, contro 2 su 2 con il turno intatto; nelle prove reali l'esito varia da
un'esecuzione all'altra. La prova reale `test_riassunto_conserva_la_nota` lo tratta come osservazione (`pytest.xfail`). Un riassunto
aggiunge una chiamata al modello (circa 3–6 s nelle sonde).

## Categorie dell'inventario (resource MCP)
Oltre agli strumenti, il server «archivio» espone una **resource** MCP, `archivio://inventario/categorie`
(`text/plain`), generata dal CSV a ogni lettura:
```
Categorie dell'inventario (nomi esatti per il filtro categoria di cerca_inventario):
- alimentatori (3 articoli)
- attrezzi (4 articoli)
...
```
La legge l'applicazione, non il modello: all'avvio, subito dopo l'apertura dell'archivio, l'assistente
legge la resource e aggiunge i nomi alla descrizione del parametro `categoria` di `cerca_inventario`
(«… Categorie esistenti: alimentatori, attrezzi, …»), nella copia della definizione inviata al modello. Così
il modello conosce i nomi esatti del filtro e risponde a «Quali categorie ci sono nell'inventario?».

Righe di log (`LOG_LEVEL=INFO`):
- `INFO assistente.cli contesto: letta la resource archivio://inventario/categorie (7 categorie)`;
- `WARNING assistente.cli contesto non disponibile: <causa>` (vedi «Diagnosi»).

Perché non un messaggio di sistema: la prima versione anteponeva il testo della resource come messaggio di
sistema a ogni chiamata dell'agente. Con `google/gemma-4-e2b` il modello smetteva di chiamare gli strumenti
(sonda su tre domande, «Annota che il saldatore va pulito», «Quali note ci sono?», «Che cosa c'è fra gli
strumenti di misura?»: strumenti chiamati 9 volte su 9 senza il messaggio, 0 su 9 con il messaggio). Con i
nomi nella descrizione del parametro: 12 chiamate corrette su 12 (sei domande, due volte ciascuna).

## Prompt dell'archivio (prompt MCP)
Il server «archivio» offre anche dei **prompt** MCP: modelli di domanda che sceglie l'utente. Nella CLI una
riga che comincia con `/` è un prompt:
- `/prompt` elenca i prompt offerti con i loro argomenti, per esempio
  `/scheda_articolo <codice> — Scheda di un articolo dell'inventario con le sue note.`;
- `/scheda_articolo MIS-001` chiede al server il testo del prompt, lo mostra come
  `(prompt) Dammi i dettagli dell'articolo MIS-001 e le note che lo riguardano.` e lo usa come domanda del
  turno: passa da router, agente e revisore e resta in cronologia come se l'utente l'avesse scritto.

Il server normalizza il codice (`mis-001` → `MIS-001`). Gli argomenti sono separati da spazi; l'ultimo prende
il resto della riga. Errori (nessun turno, cronologia invariata):
- `Errore: prompt sconosciuto '/xyz'. Scrivere /prompt per l'elenco.` (i nomi distinguono le maiuscole);
- `Errore: /scheda_articolo richiede: <codice>.`;
- `Errore: nessun articolo con codice 'XYZ'.` (dal server);
- `Errore: archivio non disponibile.` se il server «archivio» è terminato a metà sessione.

Ctrl-C mentre si attende il prompt annulla solo la richiesta (`(turno annullato)`), come durante un turno.

Riga di log (`LOG_LEVEL=INFO`): `prompt: /scheda_articolo {'codice': 'MIS-001'}`. Un prompt nuovo aggiunto al
server compare in `/prompt` senza modifiche alla CLI.

## Servizio HTTP
Lo stesso agente (router, agente con strumenti, revisore, riassunto) è offerto anche come servizio HTTP
**senza stato**, pensato per essere chiamato da un altro programma (il back-end dei prossimi step). Il servizio
non conserva conversazioni: ogni richiesta porta la `cronologia` e la risposta restituisce quella aggiornata,
che chi chiama custodisce e rimanda al turno successivo, tale e quale (sono i messaggi del grafo serializzati
con `messages_to_dict`: domande, risposte, chiamate e risultati degli strumenti, riassunto). Si serve **un solo
turno alla volta**: le richieste concorrenti attendono in fila. Starlette + uvicorn, già in `requirements.txt`
(dipendenze di `mcp`); nessuna autenticazione né HTTPS: per questo l'indirizzo predefinito è solo locale.

Avvio (stessi prerequisiti e `.env` della CLI; il servizio resta in primo piano, Ctrl-C lo ferma):
```powershell
python avvia.py --http
```
Ascolta su `http://127.0.0.1:8000` (`HTTP_HOST`, `HTTP_PORTA`). Configurazione, modello e archivio sono
verificati prima dell'avvio: un errore stampa `Errore: ...` ed esce con 1, come per la CLI. Un argomento
diverso da `--http`, `--backend` e `--frontend` stampa `Uso: python avvia.py [--http | --backend | --frontend]` ed esce con 2. Righe di log (`LOG_LEVEL=INFO`, su
stderr): `servizio in ascolto su http://127.0.0.1:8000`, `turno: <n> messaggi in ingresso, <s> s`,
`prompt: <nome> <argomenti>`, `WARNING ... turno fallito: <causa>`.

### Endpoint
Corpi JSON in UTF-8; gli errori hanno la forma `{"errore": "<messaggio>"}`.

- `GET /salute` → `200 {"stato": "ok"}`. Non chiama il modello.
- `GET /prompt` → `200 {"prompt": [{"nome": "scheda_articolo", "argomenti": ["codice"], "descrizione": "..."}]}`
  (i prompt MCP dell'archivio, gli stessi di `/prompt` nella CLI).
- `POST /turno`, con **esattamente uno** fra `domanda` e `prompt`:
  ```json
  {"cronologia": [], "domanda": "Che ore sono a Tokyo?"}
  {"cronologia": [], "prompt": {"nome": "scheda_articolo", "argomenti": {"codice": "MIS-001"}}}
  ```
  `cronologia` è facoltativa (default `[]`); `domanda` è un testo non vuoto; gli `argomenti` del prompt sono
  testi non vuoti con i nomi dichiarati da `/prompt`. Risposta `200`:
  ```json
  {"domanda": "...", "risposta": "...", "cronologia": [], "interrotto": false}
  ```
  `domanda` è il testo eseguito (con un prompt, quello generato dall'archivio); `risposta` è il testo da
  mostrare (se il modello non produce nulla: `(il modello non ha prodotto una risposta)`); `cronologia` è
  quella da rimandare; con `interrotto: true` (tetto `MAX_PASSAGGI`) è la cronologia ricevuta, invariata.

Errori di `/turno`:
| Codice | Quando | Esempio di `errore` |
| --- | --- | --- |
| 400 | corpo non valido, `domanda`/`prompt` insieme o assenti, `domanda` vuota, `cronologia` non ricostruibile, prompt sconosciuto o argomenti errati; il turno non parte | `'domanda' deve essere un testo non vuoto.` |
| 422 | il server «archivio» rifiuta il prompt (codice inesistente, archivio non disponibile); il turno non parte | `nessun articolo con codice 'XYZ'.` |
| 500 | eccezione durante il turno; il servizio resta attivo e il lock è libero | `turno fallito: <causa>` |

Rotte o metodi sconosciuti: 404/405 predefiniti di Starlette.

### Esempi da PowerShell
In un'altra finestra, con il servizio attivo:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/salute
Invoke-RestMethod http://127.0.0.1:8000/prompt
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/turno -ContentType 'application/json; charset=utf-8' -Body (@{domanda='Che ore sono a Tokyo?'} | ConvertTo-Json) -TimeoutSec 600
$r.risposta
$r.cronologia.Count
$r2 = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/turno -ContentType 'application/json; charset=utf-8' -Body (@{domanda='E a Roma?'; cronologia=$r.cronologia} | ConvertTo-Json -Depth 20) -TimeoutSec 600
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/turno -ContentType 'application/json; charset=utf-8' -Body (@{prompt=@{nome='scheda_articolo'; argomenti=@{codice='MIS-001'}}} | ConvertTo-Json -Depth 5) -TimeoutSec 600
```
Verificato il 2026-11-13 (`google/gemma-4-e2b`): `/salute` → `{"stato":"ok"}`; due turni concatenati (Tokyo, poi
Roma con `cronologia=$r.cronologia`) hanno portato la cronologia da 4 a 8 messaggi; una `domanda` vuota ha dato
400; con Docker `/salute` ha risposto come in locale e `scheda_articolo` con codice `XYZ` ha dato 422
`nessun articolo con codice 'XYZ'.`

### Con Docker Compose
Il servizio `agente` (stessa immagine; ascolta su `0.0.0.0` dentro il container e la porta è pubblicata solo
sull'host locale, `127.0.0.1:8000`) si usa in secondo piano:
```powershell
docker compose build
docker compose up -d agente
Invoke-RestMethod http://127.0.0.1:8000/salute
docker compose logs agente
docker compose stop agente
```
Verificato il 2026-11-13: build riuscita, `/salute` → `{"stato":"ok"}`, due turni concatenati (4 → 9 messaggi,
con un `scheda_articolo`), `docker compose stop agente` → uscita 0 del container, con `Finished server process`
nei log. Il servizio `assistente` (CLI interattiva) è invariato. Come la CLI, il servizio e il container
`assistente` non vanno usati insieme con lo stesso `note.db`; per cambiare porta sull'host modificare la
mappatura `ports` di `compose.yaml`.

Ctrl-C su `python avvia.py --http` (uscita 0) è ancora da provare a mano: nelle prove il processo è stato
chiuso con `Stop-Process`.

## Back-end delle conversazioni
L'agente dello step precedente è senza stato: chi lo chiama deve custodire la cronologia. Il **back-end** è quel
chiamante: conserva in PostgreSQL più conversazioni (si creano, si elencano, si riaprono, si eliminano; nessun
login), chiama l'agente a ogni messaggio e offre un'API JSON pensata per il front-end del prossimo step. Il
codice è in `src/backend/` (`app.py`, `deposito.py`, `agente.py`, `config.py`); non importa `assistente` né
`archivio` e parla con l'agente solo via HTTP (`POST /turno`). Come l'agente, non ha autenticazione né HTTPS:
ascolta solo su `127.0.0.1`.

Per ogni conversazione il back-end salva **due cose diverse**:
- i **messaggi visibili** (domande e risposte come sono state scambiate): riaprendo una conversazione si vedono
  tutti, anche dopo che l'agente ha riassunto i turni vecchi;
- la **cronologia dell'agente**, opaca, che rimanda all'agente a ogni messaggio e che può essere più corta
  (riassunto) e più ricca (chiamate agli strumenti) della chat.

Un turno è salvato in una sola transazione dopo la risposta dell'agente: se l'agente fallisce non si salva
nulla. Il titolo di una conversazione è `Nuova conversazione` fino al primo messaggio, poi i primi 60 caratteri
della prima domanda (59 più `…` se è più lunga). Con un prompt MCP nella chat compare ciò che la persona ha
scritto, per esempio `/scheda_articolo MIS-001`. **Un solo turno alla volta per ogni conversazione**: un secondo
messaggio mentre il primo è in corso riceve `409` (non attende); conversazioni diverse non si bloccano.

### Avvio locale
Servono PostgreSQL attivo (`docker compose up -d postgres`) e `DATABASE_URL` nel `.env`; l'agente dev'essere avviato
a parte, in un'altra finestra, ma può partire anche dopo (la sua assenza emerge al primo messaggio come 502):
```powershell
python avvia.py --http
python avvia.py --backend
```
Il back-end ascolta su `http://127.0.0.1:8001` (`BACKEND_HOST`, `BACKEND_PORTA`) e, all'avvio, crea le tabelle se
mancano. Un database non raggiungibile stampa `Errore: database non raggiungibile: <causa>` ed esce con 1.
Righe di log (`LOG_LEVEL=INFO`, su stderr): `backend in ascolto su http://127.0.0.1:8001`,
`messaggio: conversazione <id>, <s> s`, `WARNING ... errore del database: <causa>`,
`WARNING ... agente non disponibile: <causa>`. I comandi sono stati provati chiudendo i processi con
`Stop-Process`: il comportamento con Ctrl-C e i relativi codici di uscita di `--backend` **non sono stati verificati**.

### Endpoint
Corpi JSON in UTF-8 (`Content-Type: application/json; charset=utf-8`); gli errori hanno la forma
`{"errore": "<messaggio>"}`; le date sono ISO 8601 con fuso.

| Metodo e percorso | Esito |
| --- | --- |
| `GET /salute` | `200 {"stato": "ok"}`; non tocca database né agente |
| `GET /prompt` | inoltra `GET /prompt` dell'agente (stesso corpo); agente non raggiungibile: 502 |
| `GET /conversazioni` | `200 {"conversazioni": [{"id", "titolo", "creata", "aggiornata"}]}`, la più recente per prima |
| `POST /conversazioni` | `201 {"id", "titolo", "creata", "aggiornata"}` (il corpo è ignorato) |
| `GET /conversazioni/{id}` | `200` con i campi precedenti più `"messaggi": [{"ruolo", "testo", "ora"}]` in ordine; 404 |
| `DELETE /conversazioni/{id}` | `204` senza corpo; 404 |
| `POST /conversazioni/{id}/messaggi` | corpo con **esattamente uno** fra `{"domanda": "<testo>"}` e `{"prompt": {"nome": "...", "argomenti": {...}}}`; `200 {"risposta": "...", "messaggi": [<utente>, <assistente>]}` |

Errori:
| Codice | Quando | `errore` |
| --- | --- | --- |
| 400 | corpo non valido, `domanda` e `prompt` insieme o assenti, `prompt` malformato; oppure 400 dell'agente (domanda vuota, prompt sconosciuto, argomenti errati), inoltrato tale e quale | `corpo della richiesta non valido: atteso un oggetto JSON.`, `indicare esattamente uno fra 'domanda' e 'prompt'.`, `'domanda' deve essere un testo non vuoto.`, `'prompt' non valido: atteso un oggetto con 'nome' e 'argomenti'.` |
| 404 | conversazione inesistente, anche con un `{id}` non intero o eliminata durante il turno (nulla è salvato) | `conversazione 999 inesistente.` |
| 409 | turno già in corso sulla stessa conversazione | `turno in corso per la conversazione 1.` |
| 422 | l'archivio rifiuta il prompt (inoltrato dall'agente) | `nessun articolo con codice 'XYZ'.` |
| 500 | errore del database; nulla è salvato | `errore del database: <causa>` |
| 500 | eccezione inattesa nel back-end (registrata nel log con la traccia) | `errore interno: <causa>` |
| 502 | agente spento, in avvio, lento oltre `AGENTE_TIMEOUT` o in errore (500 o risposta non JSON); nulla è salvato | `agente non disponibile: <causa>` |

Il controllo del 409 è in memoria nel processo: vale per un solo processo back-end, che è il caso previsto.

### Esempi da PowerShell
Con PostgreSQL, agente e back-end attivi, in un'altra finestra:
```powershell
Invoke-RestMethod http://127.0.0.1:8001/salute
Invoke-RestMethod http://127.0.0.1:8001/prompt
$c = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/conversazioni
$m1 = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/conversazioni/$($c.id)/messaggi" -ContentType 'application/json; charset=utf-8' -Body (@{domanda='Che ore sono a Tokyo?'} | ConvertTo-Json) -TimeoutSec 900
$m2 = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/conversazioni/$($c.id)/messaggi" -ContentType 'application/json; charset=utf-8' -Body (@{prompt=@{nome='scheda_articolo'; argomenti=@{codice='MIS-001'}}} | ConvertTo-Json -Depth 5) -TimeoutSec 900
Invoke-RestMethod http://127.0.0.1:8001/conversazioni
Invoke-RestMethod http://127.0.0.1:8001/conversazioni/1
Invoke-WebRequest -Method Delete -Uri http://127.0.0.1:8001/conversazioni/1 -UseBasicParsing
```
Verificato il 2026-11-13 in locale (`google/gemma-4-e2b`, la conversazione creata aveva id 1): `/salute` e `/prompt`
rispondono; `POST /conversazioni` → id 1 con titolo `Nuova conversazione`; «Che ore sono a Tokyo?» → 200 in 30 s con
l'ora giusta; il prompt `scheda_articolo` `MIS-001` → 200 in 71 s (la risposta riguardava solo le note: variabilità del
modello); l'elenco mostra il titolo uguale alla prima domanda; `GET /conversazioni/1` restituisce 4 messaggi (il terzo,
dell'utente, è `/scheda_articolo MIS-001`) con gli accenti corretti; una conversazione inesistente → 404
`conversazione 999 inesistente.`; un corpo `{}` → 400; con l'agente spento un messaggio → 502
`agente non disponibile: [WinError 10061] ...` e i messaggi della conversazione restano 4; `DELETE` → 204 e la
lettura successiva → 404. I turni lunghi richiedono `-TimeoutSec` alto (vedi «Diagnosi»).

### Con Docker Compose
Il servizio `postgres` (immagine `postgres:18.7`, porta pubblicata solo sull'host locale, `127.0.0.1:5433`, dati nel
volume con nome `pgdati`, quindi conservati fra un avvio e l'altro) e il servizio `backend` (stessa immagine
del progetto, `127.0.0.1:8001`, `DATABASE_URL` costruito da Compose con `POSTGRES_*` e host `postgres`, `AGENTE_URL`
`http://agente:8000`) si usano in secondo piano con l'agente:
```powershell
docker compose build
docker compose up -d postgres agente backend
Invoke-RestMethod http://127.0.0.1:8001/salute
docker compose logs backend
docker compose restart backend
docker compose stop backend agente
```
Verificato il 2026-11-13: build riuscita e avvio dei tre servizi; un messaggio inviato **subito** dopo l'avvio ha
avuto 502 (`Connection refused`: l'agente è ancora in avvio, atteso), mentre dopo la risposta di `/salute` dell'agente
(porta 8000) lo stesso messaggio ha dato 200 in 30 s; dopo `docker compose restart backend` la conversazione 2
(titolo «Che giorno è oggi?», 2 messaggi) era ancora presente grazie al volume; l'arresto ha dato uscita 0. In quella
prova il modello ha risposto «mercoledì» a «Che giorno è oggi?» mentre era venerdì: errore del modello, non del
back-end. Il comando `docker compose stop backend agente` lascia attivo `postgres`.

## Front-end (pagina web)
Una pagina web per usare le conversazioni del back-end senza terminale: elenco delle conversazioni a sinistra (la
più recente in cima, «+ Nuova conversazione»), chat a destra con l'ora di ogni messaggio, «Elimina» con conferma.
È scritta in HTML, CSS e JavaScript semplici, senza build né librerie esterne (funziona anche senza Internet), in
`src/frontend/statico/`. Un piccolo servizio Starlette (`src/frontend/app.py`) serve i tre file e **inoltra ogni
richiesta `/api/...` al back-end** (`/api/conversazioni` → `BACKEND_URL/conversazioni`): pagina e API hanno la
stessa origine, quindi il back-end non ha bisogno di CORS. Il front-end non importa `assistente` né `backend`.
Ascolta solo su `127.0.0.1`, senza autenticazione.

### Avvio locale
Servono il back-end e l'agente (in locale o con `docker compose up -d postgres agente backend`); il front-end
parte anche senza, e la loro assenza compare nella pagina come errore 502. In un'altra finestra:
```powershell
python avvia.py --frontend
```
Poi aprire `http://127.0.0.1:8002` nel browser. Variabili (tutte facoltative, nel `.env` o nell'ambiente):
`BACKEND_URL` (`http://127.0.0.1:8001`), `BACKEND_TIMEOUT` (`960` s, più dell'`AGENTE_TIMEOUT` del back-end così
l'errore del back-end arriva prima), `FRONTEND_HOST` (`127.0.0.1`), `FRONTEND_PORTA` (`8002`), `LOG_LEVEL`.
Una porta non valida stampa `Errore: FRONTEND_PORTA deve essere un intero fra 1 e 65535, trovato '...'.` ed esce
con 1. Nel log: `frontend in ascolto su http://127.0.0.1:8002` e, se il back-end non risponde,
`WARNING frontend back-end non disponibile: <causa>`.

### Uso della pagina
- **Invio** invia, **Maiusc+Invio** va a capo. Scrivendo senza aver aperto una conversazione se ne crea una.
- Durante un turno compare «L'assistente sta rispondendo… (m:ss)» e la casella resta bloccata: **un turno alla
  volta per pagina**; si possono intanto aprire le altre conversazioni.
- **Comandi dei prompt** come nella CLI: `/scheda_articolo MIS-001`; digitando `/` compare il menu dei comandi (Tab
  completa, Esc chiude); `/prompt` mostra l'elenco nella chat senza salvarlo. Un comando sbagliato dà subito lo
  stesso errore della CLI (`Errore: /scheda_articolo richiede: <codice>.`) senza chiamare il back-end.
- **Errori** (409 turno in corso, 502 agente o back-end non disponibile, 500, ...): avviso rosso nella chat con il
  testo del back-end e «Il messaggio non è stato salvato.»; la domanda resta nella casella per riprovare. Se la
  risposta non arriva dal back-end (rete, o 502 `back-end non disponibile`) il turno potrebbe essere stato salvato
  comunque: l'avviso dice di riaprire la conversazione per controllare.
- Le risposte sono mostrate come testo semplice (niente Markdown o HTML).
- **Ricaricare la pagina durante un turno** non lo interrompe: il back-end lo completa e la risposta compare
  riaprendo la conversazione quando è pronta.

### Lista di controllo manuale
Il JavaScript non ha test automatici (servirebbe Node o un browser pilotato, dipendenze non concordate): dopo una
modifica alla pagina provare nel browser, con PostgreSQL, agente, back-end e LM Studio attivi: nuova conversazione;
domanda con attesa e cronometro; risposta e titolo aggiornato nell'elenco; menu `/` e Tab; `/scheda_articolo`
senza codice, `/boh`, `/prompt`; `/scheda_articolo MIS-001`; riapertura identica; 409 (un turno avviato da
un'altra scheda sulla stessa conversazione); una domanda con `<b>` mostrata come testo; ricarica durante un turno;
eliminazione con conferma; back-end spento (502, domanda conservata); console del browser senza errori.

Verificato il 2026-11-13 (`google/gemma-4-e2b`, `docker compose up -d postgres agente backend` più
`python avvia.py --frontend`) pilotando Edge in modalità headless con uno script locale (Chrome DevTools Protocol,
non versionato): tutte le voci della lista sopra hanno dato l'esito atteso, compresi il 409 da una seconda richiesta,
la ricarica durante un turno (risposta presente riaprendo, 8 messaggi) e il back-end fermato con
`docker compose stop backend` (avviso «back-end non disponibile: All connection attempts failed», domanda rimasta
nella casella); nessuna eccezione JavaScript né errore di console. Con un back-end finto sono stati provati anche un
turno fallito mentre era aperta un'altra conversazione (la pagina torna alla conversazione del turno e mostra lì
l'avviso) e un comando inviato mentre i prompt si ricaricavano (va alla conversazione di partenza). **Non provati**:
un browser reale con interfaccia (solo headless), la vista sotto i 700 px, Ctrl-C su `python avvia.py --frontend`
(i processi sono stati chiusi con `Stop-Process`).

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
  dell'articolo MIS-001», «Che cosa c'è fra gli strumenti di misura?». I nomi delle categorie arrivano al
  modello dalla resource dell'archivio (vedi «Categorie dell'inventario (resource MCP)»).

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
con versione fissata, per lo più per i trasporti HTTP e l'autenticazione. `starlette` e `uvicorn` servono al servizio HTTP;
gli altri trasporti HTTP/SSE di `mcp` e l'autenticazione (`sse-starlette`, `PyJWT`, `cryptography`, ...)
non si usano: verso l'archivio si usa solo lo stdio. `pywin32` è solo per Windows.

## Test
```powershell
.venv\Scripts\python.exe -m pytest
```
I test non richiedono un modello attivo né Internet (esito verificato il 2026-11-13: 867 passati, 51
deselezionati: `reale`, `rete` e `postgres`).

Prove del back-end con PostgreSQL vero (senza modello; escluse di default, marcatore `postgres`): richiedono il
servizio `postgres` attivo e `DATABASE_URL` nel `.env`; ogni prova lavora in uno schema temporaneo, creato e
rimosso dalla prova stessa, quindi non tocca le conversazioni salvate. Il marcatore `postgres` seleziona anche la
prova reale del back-end, da escludere con `not reale`:
```powershell
docker compose up -d postgres
.venv\Scripts\python.exe -m pytest -m "postgres and not reale" -v
```
Esito del 2026-11-13: 8 passate (su `127.0.0.1:5433`); con `-m postgres` ne passano 9, perché è inclusa la prova reale.

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

Categorie dell'inventario (resource MCP, 2026-11-10, `google/gemma-4-e2b`), da Git Bash:
```bash
CITTA_PATRONO=Pordenone .venv/Scripts/python.exe -m pytest -m reale -v -s
```
→ 30 passate, 1 fallita, 5 xfailed, 1 xpassed, 1329 s. Prove nuove: «Quali categorie ci sono
nell'inventario?» → risposta con tutte e 7 le categorie; «Che cosa c'è fra gli strumenti di misura?» →
`cerca_inventario` con `categoria` «strumenti di misura»; «Che componenti passivi abbiamo in laboratorio?» →
`cerca_inventario` con `categoria` «componenti passivi» (2 su 2 anche da sola; «Che componenti passivi
abbiamo?», senza «in laboratorio», è stata rifiutata dal router come fuori ambito). La prova fallita è
`test_riassunto_conserva_la_nota`: il tetto a metà soglia aveva tolto la riga della nota dal riassunto;
rilanciata da sola è passata 2 volte su 2 (instabilità del limite noto, vedi «Riassunto della cronologia»).

Prova manuale da PowerShell e con Docker (dopo `docker compose build`, riuscito):
```powershell
$env:LOG_LEVEL = "INFO"
"Quali categorie ci sono nell'inventario?", "esci" | .venv\Scripts\python.exe avvia.py
"Quali categorie ci sono nell'inventario?", "esci" | docker compose run --rm -T -e LOG_LEVEL=INFO assistente
```
→ in entrambi i casi uscita 0, riga `contesto: letta la resource archivio://inventario/categorie (7 categorie)`
e risposta «Le categorie disponibili nell'inventario del laboratorio sono: alimentatori, attrezzi, cavi e
connettori, componenti passivi, schede e microcontrollori, sicurezza, strumenti di misura.»

Prompt dell'archivio (prompt MCP, 2026-11-10, `google/gemma-4-e2b`), da Git Bash:
```bash
CITTA_PATRONO=Pordenone .venv/Scripts/python.exe -m pytest -m reale -v -s
```
→ 31 passate, 6 xfailed (limiti noti del revisore e del riassunto), 1 xpassed, 1201 s. Prova nuova
`test_il_modello_usa_la_scheda_articolo`: il testo di `/scheda_articolo MIS-001` passa il router e l'agente
chiama `dettaglio_articolo` ed `elenca_note` con `MIS-001` (2 su 2 anche da sola).

Prova manuale da PowerShell e con Docker (dopo `docker compose build`, riuscito):
```powershell
$env:LOG_LEVEL = "INFO"
"/prompt", "/scheda_articolo mis-001", "/scheda_articolo XYZ", "esci" | .venv\Scripts\python.exe avvia.py
"/prompt", "/scheda_articolo MIS-001", "esci" | docker compose run --rm -T -e LOG_LEVEL=INFO assistente
```
→ uscita 0 in entrambi i casi: elenco `/scheda_articolo <codice> — Scheda di un articolo dell'inventario con
le sue note.`, riga `(prompt) Dammi i dettagli dell'articolo MIS-001 e le note che lo riguardano.`, chiamate a
`dettaglio_articolo` ed `elenca_note`, risposta con i dati del multimetro; da PowerShell
`/scheda_articolo XYZ` → `Errore: nessun articolo con codice 'XYZ'.` senza turno.

Servizio HTTP (2026-11-13, `google/gemma-4-e2b`). Prova reale del servizio, in-process (`TestClient` sul grafo
vero, database delle note temporaneo): due turni concatenati («Annota che il multimetro MIS-001 ha la
batteria scarica», poi «Quali note ci sono?» con la cronologia restituita → `elenca_note` e la nota nella
risposta) e il turno con il prompt `scheda_articolo` `MIS-001` (→ `dettaglio_articolo`):
```powershell
.venv\Scripts\python.exe -m pytest -m reale -v -s -k servizio
```
→ 2 passate in 163 s. Prove manuali da PowerShell e con Docker: vedi «Servizio HTTP» (esempi ed esiti).
Osservato: in una chiamata il revisore ha impiegato circa 10 minuti (turno di 613,7 s), per la lentezza del
modello in LM Studio; in Docker il turno «Che ore sono a Tokyo?» una volta ha avuto risposta senza chiamare
l'orologio (variabilità del modello).
Suite reale completa del passo (stesso comando della sezione precedente, eseguito in bash con
`CITTA_PATRONO=Pordenone` davanti, 2026-11-13): 34 passate, 5 xfailed (limiti noti di revisore e riassunto), 1 xpassed, 1993 s.

Back-end delle conversazioni (2026-11-13, `google/gemma-4-e2b`, PostgreSQL in Docker su `127.0.0.1:5433`). Prova reale
`test_backend_due_messaggi` (`tests/reale/test_backend_reale.py`): back-end e agente in-process (`TestClient` con il
grafo vero), schema PostgreSQL temporaneo; «Annota che il multimetro MIS-001 ha la batteria scarica», poi «Quali note
ci sono?» → entrambe 200, la seconda risposta contiene «batteria», la lettura mostra 4 messaggi e il titolo è la
prima domanda:
```powershell
.venv\Scripts\python.exe -m pytest -m "reale and postgres" -v -s -k backend
```
→ 1 passata in 119 s. Prove manuali da PowerShell e con Docker: vedi «Back-end delle conversazioni» (esempi ed esiti).
Suite reale completa del passo (stesso comando della sezione dello step 6, eseguito in bash con
`CITTA_PATRONO=Pordenone` davanti, PostgreSQL attivo, 2026-11-13): 34 passate, 6 xfailed (limiti noti di revisore
e riassunto; in più rispetto allo step 6 `test_riassunto_conserva_la_nota`, instabile dallo step 4), 1 xpassed, 1531 s.

## Diagnosi
- **Pagina: 502 `back-end non disponibile: ...`** (nell'elenco o in un avviso): il front-end non raggiunge il
  back-end. Avviarlo (`python avvia.py --backend` o `docker compose up -d postgres agente backend`) e controllare
  `BACKEND_URL`. Con un 502 `agente non disponibile: ...` il back-end risponde ma l'agente è spento o ancora in
  avvio; con `Comandi non disponibili: ...` digitando `/` i prompt non sono stati letti (stesse cause): la pagina
  riprova al successivo comando `/`.
- **Back-end: `Errore: database non raggiungibile: ...`** all'avvio di `python avvia.py --backend`: PostgreSQL non è
  attivo o `DATABASE_URL` è sbagliato. Avviare il database (`docker compose up -d postgres`) e controllare che
  `DATABASE_URL` abbia la porta **5433** e lo stesso utente, la stessa password e lo stesso nome di
  `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`. Con una password diversa il database rifiuta l'accesso: se il
  volume `pgdati` esiste già, la password con cui è stato creato resta quella di allora (non provato): rimettere
  nel `.env` quella originale oppure eliminare il volume, perdendo le conversazioni.
- **Back-end: porta 5432 occupata o database sbagliato**: sul computer di sviluppo la 5432 è di un servizio PostgreSQL
  di Windows, per questo il servizio `postgres` è pubblicato sulla 5433. Con `DATABASE_URL` sulla 5432 si raggiunge
  quel PostgreSQL, non il container, e l'accesso fallisce.
- **Compose: errore sulla variabile `POSTGRES_...` mancante** (messaggio non riprodotto) anche per
  `docker compose run --rm assistente`: mancano `POSTGRES_USER`, `POSTGRES_DB` o `POSTGRES_PASSWORD` nel `.env`; servono per qualunque comando Compose.
- **Back-end: 502 `agente non disponibile: ...`**: l'agente non risponde. Subito dopo `docker compose up -d` è
  normale, perché l'agente impiega qualche secondo ad avviarsi (apre l'archivio e controlla il modello): attendere
  che `Invoke-RestMethod http://127.0.0.1:8000/salute` risponda e ripetere il messaggio. Con l'agente spento
  (`[WinError 10061]`, `Connection refused`) avviarlo con `python avvia.py --http` o `docker compose up -d agente`.
  Un turno più lungo di `AGENTE_TIMEOUT` dà lo stesso 502. Nulla viene salvato e la conversazione resta libera;
  la causa è anche nel log `WARNING ... agente non disponibile`.
- **Back-end: 409 `turno in corso per la conversazione <id>.`**: un messaggio è già in elaborazione sulla stessa
  conversazione (con il modello locale può durare minuti). Attendere la risposta del primo; altre conversazioni
  non sono bloccate.
- **Back-end: 500 `errore del database: ...`**: il database ha rifiutato la scrittura o la lettura; nulla è salvato
  (il testo è anche nel log `WARNING ... errore del database`).
- **Servizio HTTP: porta occupata** (errore di uvicorn all'avvio di `python avvia.py --http`; non provato): un'altra
  applicazione, o un container `agente` ancora acceso, usa già la porta. Cambiare `HTTP_PORTA` nel `.env`
  (in Docker la porta dell'host si cambia in `ports` di `compose.yaml`) o fermare l'altro processo
  (`docker compose stop agente`).
- **Servizio HTTP: 422 o 500 da `/turno`**: 422 vuol dire che il server «archivio» ha rifiutato il prompt
  (codice inesistente, archivio non disponibile) e il turno non è partito; 500 che il turno è fallito (per
  esempio LM Studio non raggiungibile): la causa è nel campo `errore` e nel log `WARNING ... turno fallito`,
  il servizio resta attivo. Un 400 indica una richiesta da correggere (campo `errore`).
- **Servizio HTTP: turni lunghi**: con il modello locale un turno può durare minuti (osservato 613,7 s con una
  revisione molto lenta); `Invoke-RestMethod` ha un timeout proprio, quindi usare `-TimeoutSec 600` (o più).
  Intanto le altre richieste attendono in fila (un turno alla volta).
- **Servizio HTTP: lettere accentate sbagliate in Windows PowerShell 5.1** («QuantitÃ »): il servizio
  dichiara `Content-Type: application/json; charset=utf-8`; per la richiesta indicare
  `-ContentType 'application/json; charset=utf-8'` come negli esempi, altrimenti PowerShell invia il corpo
  in un'altra codifica.
- **`WARNING assistente.cli contesto non disponibile: ...`**: all'avvio la resource delle categorie non è
  stata letta (archivio che non risponde, resource assente). L'assistente parte comunque; la descrizione di
  `cerca_inventario` resta senza l'elenco delle categorie. Il motivo segue i due punti.
- **`WARNING assistente.grafo riassunto non disponibile: ...`**: il riassunto della cronologia non è
  riuscito. La cronologia resta intera e il turno prosegue; se la sessione è molto lunga il modello può
  superare il contesto. Il motivo segue i due punti.
- **`WARNING assistente.revisore revisore non disponibile: ...`**: la valutazione non è riuscita; la
  risposta è approvata comunque e arriva all'utente; il motivo segue i due punti.
- **`WARNING ... limite di revisioni raggiunto` frequente**: il modello non riesce a completare la
  risposta (domanda con troppe parti o ambigua, modello piccolo) oppure, con una domanda di seguito
  («e a Londra?»), il revisore rifiuta a torto (limite noto); la risposta resta l'ultima prodotta.
  Ogni revisione allunga il turno; `MAX_REVISIONI=1` lo accorcia.
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
