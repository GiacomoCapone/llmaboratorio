# Orologio senza luogo e ragionamento disattivato: specifica

Data: 2026-10-28. Stato: da approvare.

## Problema
L'assistente è lento e non usa lo strumento orologio quando l'utente non indica un luogo.

- Lentezza: `google/gemma-4-e2b` genera un ragionamento nascosto (85–97% dei token) su un computer
  che produce circa 10 token/s; ogni chiamata costa 20–80 s. Con `reasoning_effort: "none"` una
  chiamata passa da 31 s a 3 s (verificato su LM Studio).
- Orologio: `fuso` è obbligatorio e nessuno indica al modello un fuso predefinito; per domande come
  "che ore sono" il modello chiede il fuso all'utente, oppure chiama lo strumento con `{}`, che fallisce.

## Obiettivo
Risposte in pochi secondi e strumento usato anche per domande su ora, data o giorno senza luogo,
con un fuso predefinito configurabile.

## Fuori ambito
Messaggio di sistema, altri strumenti, cambio di modello o di hardware, persistenza, MCP, RAG.

## Decisioni concordate
- Ragionamento disattivato per default (`none`), riattivabile da variabile d'ambiente.
- Fuso predefinito `Europe/Rome`, configurabile.
- Il fuso predefinito è comunicato al modello solo tramite la definizione dello strumento,
  senza messaggio di sistema.
- `fuso` diventa facoltativo: se il modello lo omette, il programma usa il fuso predefinito.
- Descrizione dello strumento in italiano, con tono imperativo ed esempi di domande.

## Evidenze (prova del 2026-10-28)
Chiamata diretta all'API di LM Studio, `temperature=0`, `reasoning_effort="none"`, 14 domande × 3
esecuzioni per variante (7 senza luogo, 3 con luogo, 4 senza bisogno dello strumento). Si è misurata
solo la decisione di chiamare lo strumento, non la risposta finale.

| Variante | Corrette | Senza luogo |
| --- | --- | --- |
| Descrizione precedente ("usa Europe/Rome"), `fuso` obbligatorio | 21/42 | chiede il fuso o chiama con `{}` |
| Imperativa, `fuso` obbligatorio | 42/42 | `{"fuso": "Europe/Rome"}` |
| Imperativa, `fuso` facoltativo (scelta) | 42/42 | `{}` |
| Imperativa in inglese, `fuso` facoltativo | 42/42 | `{}` |

Le tre esecuzioni di ogni domanda hanno dato risultati identici. Domande con luogo: fuso IANA
corretto in tutte le varianti. Script fuori dalla repository (cartella scratchpad della sessione).

## Configurazione
Nuove variabili d'ambiente, documentate in `.env.example` e nel README:

| Variabile | Default | Validazione |
| --- | --- | --- |
| `LMSTUDIO_REASONING_EFFORT` | `none` | uno tra `none`, `low`, `medium`, `high` (spazi rimossi, minuscole); altrimenti `ErroreConfigurazione` |
| `FUSO_PREDEFINITO` | `Europe/Rome` | `ZoneInfo(valore)` deve riuscire; altrimenti `ErroreConfigurazione` |

Valore vuoto o assente: si usa il default. `Config` riceve i campi `reasoning_effort` e
`fuso_predefinito`.

## Modello
`crea_llm(config)` passa `reasoning_effort=config.reasoning_effort` a `ChatOpenAI`
(supportato da `langchain-openai` 1.7.2, già fissata; nessuna nuova dipendenza). LM Studio lo
inoltra nella richiesta come `"reasoning_effort"`.

## Strumento
La costante `DEFINIZIONE_ORA_CORRENTE` è sostituita da `definizione_ora_corrente(fuso_predefinito)`,
che restituisce:

- `name`: `ora_corrente`;
- `description`: "Restituisce la data e l'ora attuali (formato ISO 8601). Chiamalo SEMPRE quando
  l'utente chiede l'ora, la data o il giorno, per esempio 'che ore sono', 'che ora è',
  'che giorno è oggi'. Non chiedere mai il fuso all'utente.";
- parametro `fuso` (stringa): "Nome IANA del fuso orario, per esempio America/New_York.
  Facoltativo: se l'utente non indica un luogo, omettilo e verrà usato {fuso_predefinito}.";
- `required`: lista vuota.

`ora_corrente(fuso, adesso)` resta invariata.

## Grafo
- `build_graph(llm, adesso, max_passaggi, fuso_predefinito)` collega al modello
  `definizione_ora_corrente(fuso_predefinito)`.
- Esecuzione dello strumento:
  - `fuso` assente → `ora_corrente(fuso_predefinito, adesso)`;
  - `fuso` stringa → `ora_corrente(fuso, adesso)` (un nome non valido produce `Errore: ...`, come oggi);
  - `fuso` presente ma non stringa, o argomenti non oggetto → `Errore: ...`, come oggi.
- Il log `tool_call` resta con gli argomenti ricevuti dal modello, così un `{}` è visibile.
- Nodi, instradamento, limite di passaggi e cronologia invariati. Nessun messaggio di sistema.

## CLI
`main()` passa `config.fuso_predefinito` a `build_graph`.

## Test automatici (senza modello attivo)
- Configurazione: default dei due campi; valori validi accettati; ragionamento non ammesso e fuso
  inesistente producono `ErroreConfigurazione`.
- Modello: `crea_llm` imposta `reasoning_effort` dalla configurazione.
- Strumento: la definizione contiene il fuso predefinito nella descrizione del parametro, `fuso`
  non è in `required`, la descrizione invita a chiamare lo strumento senza chiedere il fuso.
- Grafo, con modello finto e istante controllato: `args={}` produce l'ora nel fuso predefinito
  (anche con un predefinito diverso da `Europe/Rome`); un fuso esplicito ha la precedenza;
  `fuso` non testuale produce ancora un errore. Il test che oggi attende un errore per `{}` va aggiornato.
- Le chiamate esistenti a `build_graph` e `Config` nei test sono aggiornate ai nuovi parametri.

## Verifiche reali (marcatore `reale`, LM Studio attivo)
Test parametrizzato in `tests/reale/` che usa il grafo vero con la configurazione dall'ambiente:
"che ore sono", "Che giorno è oggi?" (senza luogo) e "Che ore sono a Tokyo?" (con luogo).
Per ciascuna: almeno un `tool_call nome=ora_corrente` nel log, turno non interrotto, risposta finale
non vuota. Copre anche il secondo passaggio del modello, non misurato dalla prova preliminare.
Si annotano nel resoconto i tempi osservati. Seguono un avvio manuale con `python -m assistente`
e, se possibile, con Docker Compose.

## Documentazione
README: nuove variabili, compromesso velocità/affidabilità del ragionamento (`none` veloce,
`low` più lento), diagnosi con `lms ps` e ricerca di `reasoning_tokens` nei log di LM Studio.
Solo comandi verificati.

## Criteri di successo
- `python -m pytest` verde.
- `python -m pytest -m reale -v` verde con `google/gemma-4-e2b`.
- In una sessione manuale "che ore sono" restituisce l'ora di Roma senza chiedere il fuso, in
  pochi secondi invece di decine.

## Limiti noti
Un modello da 2B senza ragionamento resta sensibile alla formulazione: domande non provate possono
ancora non attivare lo strumento. In quel caso si può riattivare il ragionamento con
`LMSTUDIO_REASONING_EFFORT=low`, accettando tempi molto più lunghi.
