# Note del laboratorio (SQLite nel server MCP «archivio»): specifica

Data: 2026-11-09. Stato: in revisione.

## Contesto
Ciclo 6 di 6 (vedi `2026-11-02-calcolatrice-e-registro-design.md`). Il server MCP «archivio» del
ciclo 5 (`2026-11-09-catalogo-archivio-design.md`) espone già l'inventario in sola lettura; in questo
ciclo ospita anche le note del laboratorio, salvate in un file SQLite che sopravvive alla sessione e
al container. L'assistente resta come è: il client MCP trasforma gli strumenti del server in voci del
registro, il grafo non cambia e non conosce gli strumenti.

## Obiettivo
Rispondere a richieste come «Annota che il multimetro MIS-001 ha la batteria scarica», «Quali note ci
sono?», «Ci sono note su MIS-001?» e «Elimina la nota 3» tramite tre strumenti MCP: `aggiungi_nota`,
`elenca_note`, `elimina_nota`.

## Fuori ambito
- Modifica di una nota, ricerca per parole nel testo delle note, ripristino di una nota eliminata.
- Autore, utenti, permessi; conferma nel terminale prima dell'eliminazione.
- Eliminazione logica (la nota eliminata sparisce dal database).
- Volumi Docker con nome; accesso contemporaneo dal container e dall'host.
- Migrazioni dello schema.
- Dipendenze nuove (si usa `sqlite3` della libreria standard).

## Decisioni concordate
- Note legate all'inventario: testo obbligatorio e codice articolo facoltativo, verificato contro
  l'inventario; l'elenco si può filtrare per articolo.
- Eliminazione diretta per numero; la risposta riporta il testo della nota eliminata.
- Database `dati/note.db` nella cartella del progetto (ignorata da Git), percorso modificabile con la
  variabile `NOTE_DB`. In Docker la cartella del progetto `./dati` è montata su `/app/dati`: container e
  avvio locale condividono lo stesso file. Le due modalità non vanno usate contemporaneamente.
- `sqlite3` della libreria standard, una connessione per operazione.
- Stesso server «archivio»: se il database delle note non si apre all'avvio, l'archivio non parte e
  l'assistente si ferma con il motivo (stessa regola dell'inventario).
- Gli errori di argomento e di esercizio sono testi `Errore: ...` restituiti come risultato normale
  dello strumento, non errori del protocollo MCP.

## Configurazione
- `NOTE_DB` (facoltativa): percorso del file SQLite. Vuota o assente → `dati/note.db` nella cartella
  del progetto. Un percorso relativo è risolto rispetto alla cartella del progetto (non alla cartella
  da cui si avvia), come il `.env`.
- `config.Config` ha un campo in più, `note_db: Path`, già risolto e assoluto. `carica_config` non
  verifica il file (lo fa il server all'avvio).
- `FUSO_PREDEFINITO` (esistente) dà il fuso delle date delle note.
- `.env.example`: una riga commentata `# NOTE_DB=dati/note.db` con la spiegazione.
- I valori del `.env` non sono nell'ambiente del processo (`python-dotenv` li legge senza esportarli),
  quindi la CLI li passa esplicitamente al sottoprocesso (vedi Client).

## Dati: tabella `note`
```sql
CREATE TABLE IF NOT EXISTS note (
    numero INTEGER PRIMARY KEY AUTOINCREMENT,
    testo  TEXT NOT NULL,
    codice TEXT,
    creata TEXT NOT NULL
)
```
- `AUTOINCREMENT`: un numero eliminato non viene mai riusato, così un numero ricordato dal modello non
  può colpire una nota più recente.
- `codice`: `NULL` o il codice nella forma canonica dell'inventario (`mis-001` → `MIS-001`).
- `creata`: istante ISO 8601 con scostamento, nel fuso `FUSO_PREDEFINITO`, al secondo
  (`2026-11-09T14:32:05+01:00`); mostrato come `2026-11-09 14:32`.
- L'ordine «dalla più recente» è l'ordine decrescente di `numero`.

## Strumenti MCP

### Testi in ingresso
- `testo`: spazi iniziali e finali tolti; ogni a capo, tabulazione o altro carattere di controllo
  (categoria Unicode `Cc`) diventa uno spazio, poi le sequenze di spazi diventano uno solo. Massimo
  500 caratteri dopo la pulizia.
- `codice`: spazi tolti, confronto con l'inventario come in `dettaglio_articolo` (senza maiuscole né
  accenti); massimo 100 caratteri. Vuoto o `null` → nessun codice.

### `aggiungi_nota(testo, codice=None)`
Descrizione (alla lettera):
«Salva una nota del laboratorio (promemoria, guasto, osservazione), facoltativamente legata al codice
di un articolo dell'inventario, per esempio MIS-003. Chiamalo SEMPRE quando l'utente chiede di
annotare, ricordare o segnare qualcosa.»

Parametri:
- `testo` (stringa, obbligatorio): «Testo della nota, per esempio display difettoso.»
- `codice` (stringa o `null`, facoltativo): «Codice dell'articolo a cui si riferisce la nota, per
  esempio MIS-003.»

Risultato:
- con codice: `Nota 7 salvata (MIS-003, 2026-11-09 14:32): display difettoso.`
- senza codice: `Nota 7 salvata (2026-11-09 14:32): ordinare fusibili da 2 A.`

Il punto finale è aggiunto solo se il testo non termina già con `.`, `!` o `?`.

### `elenca_note(codice=None)`
Descrizione (alla lettera):
«Elenca le note del laboratorio, dalla più recente, con numero, data, codice dell'articolo e testo;
con un codice mostra solo le note di quell'articolo. Chiamalo quando l'utente chiede le note o i
promemoria salvati.»

Parametri:
- `codice` (stringa o `null`, facoltativo): «Codice di un articolo per vedere solo le sue note, per
  esempio MIS-003.»

Risultato (al massimo 20 note, dalla più recente):
```
Trovate 3 note:
- 7 — 2026-11-09 14:32 — MIS-003 — display difettoso
- 5 — 2026-11-08 09:10 — ordinare fusibili da 2 A
- 2 — 2026-11-07 17:45 — MIS-001 — batteria scarica
```
- una sola nota: `Trovata 1 nota:`;
- oltre 20: in coda `(altre N note più vecchie non mostrate)`;
- nessuna nota: `Nessuna nota.`; con codice: `Nessuna nota per l'articolo MIS-003.` (codice canonico).

### `elimina_nota(numero)`
Descrizione (alla lettera):
«Elimina definitivamente una nota del laboratorio dato il suo numero, visibile con elenca_note. Usalo
solo quando l'utente chiede esplicitamente di eliminare una nota.»

Parametri:
- `numero` (intero, obbligatorio): «Numero della nota da eliminare, per esempio 3.»

Risultato:
- `Nota 7 eliminata: «display difettoso» (MIS-003, 2026-11-09 14:32).`
- senza codice: `Nota 5 eliminata: «ordinare fusibili da 2 A» (2026-11-08 09:10).`

### Errori (tutti iniziano con `Errore:`)
- testo vuoto dopo la pulizia → `Errore: indicare il testo della nota.`
- testo oltre 500 caratteri → `Errore: testo troppo lungo (massimo 500 caratteri).`
- codice oltre 100 caratteri → `Errore: testo troppo lungo (massimo 100 caratteri).`
- codice sconosciuto → `Errore: nessun articolo con codice 'XYZ-9'.` (la nota non è salvata)
- numero minore di 1 → `Errore: il numero della nota deve essere un intero positivo.`
- numero inesistente (anche già eliminato) → `Errore: nessuna nota con numero 12.`
- errore di `sqlite3` durante un'operazione (file bloccato oltre il timeout, disco pieno, file rimosso
  o danneggiato) → `Errore: archivio delle note non disponibile.`; il dettaglio va nel log del server
  (stderr, livello `WARNING`), nessuna eccezione verso MCP.
- un argomento di tipo sbagliato (per esempio `numero` non intero) è rifiutato dalla validazione
  dell'SDK: il client lo restituisce già come testo che inizia con `Errore:` (ciclo 5).

## Moduli del server: `src/archivio/`
- `note.py` (nuovo): logica pura, senza MCP.
  - `PERCORSO_NOTE_PREDEFINITO = <cartella del progetto>/dati/note.db`, ricavato dalla posizione del
    pacchetto (`src/archivio/note.py` → `../../dati/note.db`).
  - `ErroreNote(Exception)`: database non utilizzabile all'avvio.
  - `apri(percorso, inventario, adesso) -> Note`: crea la cartella se manca, si collega, crea la
    tabella se manca e verifica lo schema (colonne `numero, testo, codice, creata` nell'ordine). Ogni
    problema → `ErroreNote("archivio delle note non valido: <percorso> (<motivo>).")` (file non SQLite,
    schema diverso, cartella non creabile, permessi).
  - `Note.aggiungi(testo, codice) -> str`, `Note.elenca(codice) -> str`, `Note.elimina(numero) -> str`.
    `adesso` è una funzione che restituisce un `datetime` consapevole del fuso (iniettata per i test).
  - Ogni operazione apre una connessione con `sqlite3.connect(percorso, timeout=5)`, esegue in una
    transazione e chiude la connessione (anche in caso di errore).
- `inventario.py`: un metodo pubblico in più, `Inventario.codice_canonico(codice) -> str | None`, che
  restituisce il codice come scritto nel CSV o `None`; `dettaglio` lo usa al posto della ricerca
  interna (comportamento invariato).
- `server.py`: `crea_server(inventario, note)` dichiara anche i tre strumenti con le descrizioni sopra.
- `__main__.py`: legge `NOTE_DB` (vuota o assente → percorso predefinito; relativa → rispetto alla
  cartella del progetto) e `FUSO_PREDEFINITO` (vuota, assente o non valida → `Europe/Rome`)
  dall'ambiente, apre le note dopo l'inventario; `ErroreNote` → messaggio `Errore: ...` su stderr e
  uscita 1, come per l'inventario.
- Il pacchetto `archivio` continua a non importare nulla da `assistente`.

## Client e CLI
- `ClientArchivio(comando=None, timeout=10.0, ambiente=None)`: `ambiente` (dizionario) si aggiunge a
  `PYTHONPATH` e `PYTHONIOENCODING` nell'ambiente del sottoprocesso.
- `cli.main()` passa `ambiente={"NOTE_DB": str(config.note_db), "FUSO_PREDEFINITO":
  config.fuso_predefinito}`.
- Registro e grafo invariati: i tre strumenti arrivano come `esterni` (10 strumenti in tutto).

## Docker
- `compose.yaml`: `volumes: - ./dati:/app/dati` e `NOTE_DB: /app/dati/note.db` in `environment`
  (prevale sull'`.env`, che può contenere un percorso dell'host).
- `.gitignore` e `.dockerignore`: `dati/`.
- `Dockerfile` invariato.

## Test automatici (senza modello né Internet)
- `tests/test_archivio_note.py` (database in `tmp_path`, orologio fisso, inventario piccolo):
  - aggiunta con e senza codice; codice in minuscolo salvato canonico; codice sconosciuto non salva
    nulla; pulizia di a capo, tabulazioni e spazi multipli; testo vuoto, di soli spazi e oltre 500
    caratteri; codice oltre 100 caratteri; punto finale non raddoppiato;
  - elenco: ordine dalla più recente, filtro per codice (anche minuscolo), `Trovata 1 nota`, limite di
    20 con la riga «altre N», le due varianti di «nessuna nota», codice sconosciuto;
  - eliminazione: testo e dati nella risposta, nota sparita dall'elenco, numero inesistente, numero
    zero o negativo, numero non riusato dopo l'eliminazione dell'ultima nota;
  - persistenza: una seconda `apri` sullo stesso file vede le note;
  - avvio: cartella creata se manca, file non SQLite → `ErroreNote`, tabella `note` con colonne
    diverse → `ErroreNote`;
  - esercizio: un errore di `sqlite3` (file sostituito o bloccato) → `Errore: archivio delle note non
    disponibile.` e un `WARNING` nel log.
- `tests/test_archivio_inventario.py`: `codice_canonico` (minuscole, spazi, sconosciuto).
- `tests/test_mcp_client.py` (server vero come sottoprocesso, `NOTE_DB` in `tmp_path`):
  - i cinque strumenti esposti; descrizioni dei tre nuovi uguali alla lettera alla specifica;
    `testo` e `numero` obbligatori; `codice` accetta `null`;
  - aggiunta, elenco ed eliminazione veri; il file indicato da `NOTE_DB` contiene la nota;
  - `NOTE_DB` su un file non SQLite → `ErroreArchivio` con il motivo.
- `tests/test_config.py`: `NOTE_DB` assente, vuota, relativa (risolta rispetto al progetto) e
  assoluta.
- `tests/test_cli.py`: `ClientArchivio` riceve `NOTE_DB` e `FUSO_PREDEFINITO` dalla configurazione.

## Verifiche reali (marcatore `reale`, LM Studio attivo, `NOTE_DB` in `tmp_path`)
- «Annota che il multimetro MIS-001 ha la batteria scarica» → chiamata a `aggiungi_nota` con codice
  `MIS-001` (senza maiuscole), ToolMessage che inizia con `Nota ` e contiene `salvata`.
- Con una nota già presente: «Quali note ci sono?» → chiamata a `elenca_note`, ToolMessage che inizia
  con `Trovat`.
- Con una nota numero N già presente: «Elimina la nota N» → chiamata a `elimina_nota` con numero N,
  ToolMessage che contiene `eliminata`.
- Con una nota già presente: «Mostrami le note» → nessuna chiamata a `elimina_nota`.
- Si rilanciano tutte le prove reali esistenti: con 10 strumenti il modello potrebbe confondersi. Se un
  caso fallisce ci si ferma, si diagnostica con il log e si riporta prima di cambiare descrizioni o
  specifica.

## Verifica Docker (manuale, da PowerShell)
Dopo `docker compose build`: `docker compose run --rm assistente`, «Annota che il saldatore va
pulito», `esci`; poi `python avvia.py` dall'host e «Quali note ci sono?» → la nota del container è
nell'elenco (mount condiviso). Infine la nota si elimina.

## Documentazione
- README: note del laboratorio (che cosa fanno i tre strumenti), `NOTE_DB` e cartella `dati/`, mount
  in Docker e avvertenza sull'uso contemporaneo, come azzerare le note (cancellare `dati/note.db`),
  diagnosi «archivio delle note non valido», prove reali delle note. Solo comandi verificati, anche
  per PowerShell.
- CLAUDE.md: obiettivo (note persistenti nel server «archivio») e struttura (`dati/`); nell'indice solo
  la propria versione, senza la modifica dell'utente non in commit.

## Criteri di successo
- `python -m pytest` passa senza modello né Internet, compresi i test del client con il server vero.
- `python -m pytest -m reale -v` passa con LM Studio (la catena del calendario resta xfail).
- La verifica Docker mostra dall'host una nota creata nel container.
- Le note sopravvivono al riavvio dell'assistente.

## Limiti noti
- Uso contemporaneo dal container e dall'host sullo stesso file: non supportato (lock di SQLite su un
  mount di Docker Desktop non affidabile); un lock trattenuto oltre 5 s dà «archivio delle note non
  disponibile».
- Nessuna conferma prima dell'eliminazione: la sicurezza dipende dalla descrizione dello strumento e
  dalla risposta, che riporta il testo eliminato.
- Le date mostrate sono nel fuso `FUSO_PREDEFINITO` attuale: una nota salvata con un fuso diverso
  mostra l'ora con cui è stata salvata.
