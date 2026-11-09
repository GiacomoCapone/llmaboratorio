# Meteo attuale (Open-Meteo): specifica

Data: 2026-11-09. Stato: in revisione.

## Contesto
Ciclo 4 di 6 (vedi `2026-11-02-calcolatrice-e-registro-design.md`). È il primo strumento che usa dati
esterni: interroga le API pubbliche di Open-Meteo (senza chiave) per il geocoding e per le condizioni
attuali. Viene aggiunto al registro come quinto strumento. Nessuna dipendenza nuova: le richieste HTTP
usano `urllib.request` e `json` della libreria standard.

## Obiettivo
Uno strumento `meteo_attuale` che, dato il nome di una località, restituisce le condizioni meteo attuali
(cielo, temperatura e percepita, umidità, precipitazioni, vento), indicando il luogo effettivamente trovato
e l'ora locale della rilevazione.

## Fuori ambito
- Previsioni (giornaliere od orarie) e dati storici.
- Disambiguazione interattiva della località, filtro per paese, coordinate passate dal modello.
- Località predefinita: se l'utente non indica la località lo strumento risponde con un errore.
- Nuovi tentativi automatici, cache delle risposte, servizi meteo diversi da Open-Meteo.

## Decisioni concordate
- Solo condizioni attuali.
- Località indicata solo per nome; si usa il primo risultato del geocoding e la risposta riporta il luogo
  trovato (nome, regione, nazione), così uno scambio di città è visibile.
- Località obbligatoria; nessuna variabile nuova nel `.env`.
- HTTP con `urllib.request` (nessuna dipendenza nuova; su Windows usa i certificati di sistema).
- La funzione che scarica è iniettata: i test automatici non usano la rete.
- Nuovo marcatore `rete` (Open-Meteo vero, senza modello), escluso di default; la prova `reale` con
  LM Studio usa Open-Meteo vero.

## Servizi usati
- Geocoding: `https://geocoding-api.open-meteo.com/v1/search` con parametri
  `name=<località>`, `count=1`, `language=it`, `format=json`.
  Con risultati: `{"results": [{"name", "latitude", "longitude", "admin1"?, "country"?, ...}], ...}`.
  Senza risultati la chiave `results` manca (verificato il 2026-11-09).
- Condizioni attuali: `https://api.open-meteo.com/v1/forecast` con parametri `latitude`, `longitude`
  (quelli del geocoding), `current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,wind_direction_10m`
  e `timezone=auto`. La risposta contiene `timezone` (es. `Europe/Rome`) e `current` con `time`
  (`AAAA-MM-GGTHH:MM`, ora locale) e i sette campi; unità predefinite: °C, %, mm, km/h, gradi.
- Gli indirizzi sono costanti nel modulo `meteo.py`.

## Definizione per il modello
```python
{
    "type": "function",
    "function": {
        "name": "meteo_attuale",
        "description": (
            "Restituisce le condizioni meteo attuali di una località: cielo, temperatura, "
            "umidità, precipitazioni e vento. Chiamalo SEMPRE quando l'utente chiede che tempo "
            "fa, se piove o quanti gradi ci sono in un luogo. Non fornisce previsioni."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "localita": {
                    "type": "string",
                    "description": "Nome della città o località, per esempio Pordenone o Parigi.",
                }
            },
            "required": ["localita"],
        },
    },
}
```
La descrizione è fissata alla lettera: dopo ogni modifica si rilanciano le prove reali.

## Argomenti
- `localita`: testo; gli spazi iniziali e finali sono tolti; dopo la pulizia deve essere non vuoto e
  lungo al massimo 100 caratteri.
- Parametri estranei ignorati senza errore.

## Calcolo
1. Validazione di `localita`.
2. Geocoding con i parametri sopra; si usa `results[0]`. `results` assente o vuoto → errore
   «località non trovata».
3. Condizioni attuali con `latitude` e `longitude` del primo risultato.
4. Formattazione del risultato.

Una risposta a cui manca un campo usato, o con un campo del tipo sbagliato (numeri: `int` o `float`,
esclusi i `bool`; testi: `str`), produce l'errore «risposta non valida». `admin1` e `country` sono
facoltativi.

## Risultato
Sette righe, separate da `\n`, in quest'ordine:
```
Luogo: Pordenone, Friuli Venezia Giulia, Italia
Rilevazione: 2026-11-09 09:00 (ora locale, Europe/Rome)
Cielo: coperto
Temperatura: 5,7 °C (percepita 4,1 °C)
Umidità: 91 %
Precipitazioni: 0,0 mm
Vento: 1,5 km/h da nord-est
```
- **Luogo:** `name`, `admin1`, `country` del geocoding, separati da `, `; si omettono le parti assenti,
  vuote o uguali a una parte precedente.
- **Rilevazione:** `current.time` con la `T` sostituita da uno spazio; fra parentesi `ora locale, ` e il
  `timezone` della risposta delle condizioni attuali.
- **Cielo:** descrizione italiana del `weather_code` dalla tabella sotto; un codice non in tabella dà
  `condizione non classificata (codice N)`.
- **Temperatura, percepita, precipitazioni, velocità del vento:** una cifra decimale, virgola come
  separatore decimale (es. `-0,5`, `12,0`).
- **Umidità:** intero (se arriva decimale, `round()` di Python).
- **Vento:** con velocità 0 la riga è `Vento: calmo (0,0 km/h)`; altrimenti
  `Vento: <velocità> km/h da <direzione>`, con la direzione fra 8 punti:
  settore = `int(((gradi % 360) + 22.5) // 45) % 8` → `nord`, `nord-est`, `est`, `sud-est`, `sud`,
  `sud-ovest`, `ovest`, `nord-ovest` (0 → nord, 22,4 → nord, 22,5 → nord-est, 337,5 → nord, 360 → nord).

### Tabella dei codici WMO
| Codice | Cielo | Codice | Cielo |
| --- | --- | --- | --- |
| 0 | sereno | 63 | pioggia moderata |
| 1 | prevalentemente sereno | 65 | pioggia forte |
| 2 | parzialmente nuvoloso | 66 | pioggia gelata leggera |
| 3 | coperto | 67 | pioggia gelata forte |
| 45 | nebbia | 71 | neve leggera |
| 48 | nebbia con brina | 73 | neve moderata |
| 51 | pioviggine leggera | 75 | neve forte |
| 53 | pioviggine moderata | 77 | neve granulosa |
| 55 | pioviggine intensa | 80 | rovesci di pioggia leggeri |
| 56 | pioviggine gelata leggera | 81 | rovesci di pioggia moderati |
| 57 | pioviggine gelata intensa | 82 | rovesci di pioggia violenti |
| 61 | pioggia leggera | 85 | rovesci di neve leggeri |
| 95 | temporale | 86 | rovesci di neve forti |
| 96 | temporale con grandine leggera | 99 | temporale con grandine forte |

## Errori (tutti iniziano con `Errore:`)
| Caso | Messaggio |
| --- | --- |
| `localita` assente, nulla, non testuale o vuota dopo la pulizia | `Errore: indicare la località, per esempio Pordenone.` |
| `localita` più lunga di 100 caratteri | `Errore: nome di località troppo lungo (massimo 100 caratteri).` |
| geocoding senza risultati | `Errore: località non trovata: '<località pulita>'.` |
| rete assente, DNS fallito, connessione rifiutata | `Errore: servizio meteo non raggiungibile (<motivo>).` |
| nessuna risposta entro 5 secondi | `Errore: il servizio meteo non ha risposto entro 5 secondi.` |
| stato HTTP diverso da 200 | `Errore: il servizio meteo ha risposto con stato <N>.` |
| corpo non JSON, campi mancanti o di tipo sbagliato | `Errore: risposta del servizio meteo non valida.` |

Lo strumento non solleva eccezioni verso il grafo. Un errore arriva al modello una sola volta (nessun
nuovo tentativo); la ripetizione del grafo per la risposta vuota dopo gli strumenti resta invariata.

## Moduli
- `src/assistente/strumenti/rete.py`: `ErroreRete(Exception)` e
  `scarica_json(url: str, parametri: dict) -> dict`. Costruisce l'URL con `urllib.parse.urlencode`,
  invia una GET con `User-Agent: assistente-laboratorio` e timeout di 5 secondi, decodifica il corpo
  in UTF-8 e lo interpreta come JSON (deve essere un oggetto). Traduce ogni guasto in `ErroreRete` con il
  testo finale del messaggio d'errore (senza il prefisso `Errore: `): `HTTPError` → stato,
  `TimeoutError` (anche dentro `URLError.reason`) → timeout, altri `URLError`/`OSError` → non
  raggiungibile con il motivo, JSON non valido o non oggetto → risposta non valida. Registra ogni guasto
  a livello `WARNING` con l'URL senza parametri e il tipo di guasto (non la località).
  Non sa nulla di meteo.
- `src/assistente/strumenti/meteo.py`: costanti degli indirizzi, tabella WMO, la costante
  `DEFINIZIONE_METEO`, funzioni pure per luogo, direzione del vento, numeri e formattazione,
  ed `esegui_meteo(args: dict, scarica: Callable[[str, dict], dict]) -> str`, che intercetta
  `ErroreRete` e lo restituisce come `Errore: <messaggio>`.

## Registro
`crea_strumenti(adesso, fuso_predefinito, citta_patrono=None, scarica=scarica_json)` aggiunge in coda
`Strumento(DEFINIZIONE_METEO, lambda args: esegui_meteo(args, scarica))`. Grafo, CLI, configurazione e
`compose.yaml` restano invariati.

## Test automatici (senza rete né modello)
- `tests/test_meteo.py`, con una `scarica` finta che registra le chiamate e restituisce JSON ricavati da
  risposte vere:
  - risultato completo confrontato come stringa intera;
  - parametri inviati: `count=1`, `language=it`, `format=json`, `timezone=auto`, i sette campi di
    `current`, latitudine e longitudine del geocoding passate alla seconda richiesta;
  - ogni riga della tabella degli errori, compresa una `scarica` che solleva `ErroreRete`;
  - luogo senza `admin1`/`country` e con parti ripetute;
  - tutti i codici WMO e un codice sconosciuto;
  - direzione a 0, 22,4, 22,5, 337,5 e 360 gradi; vento calmo;
  - virgola decimale, numeri negativi, umidità decimale;
  - definizione uguale alla lettera a quella della specifica.
- `tests/test_rete.py`, con `urlopen` sostituito tramite monkeypatch: URL e parametri, User-Agent,
  timeout di 5 secondi, traduzione di `HTTPError`, `TimeoutError`, `URLError` (con e senza timeout come
  motivo), corpo non JSON e JSON non oggetto in `ErroreRete`.
- `tests/test_strumenti.py`: il registro contiene `meteo_attuale` e usa la `scarica` iniettata.

## Verifiche con la rete (marcatore `rete`, Internet attivo, nessun modello)
`python -m pytest -m rete -v`:
- `Pordenone` → sette righe, `Italia` nel luogo, temperatura fra -50 e 60 °C;
- `Xqzwvtplk` → `Errore: località non trovata: 'Xqzwvtplk'.`

`pytest.ini`: nuovo marcatore `rete` e `addopts = -m "not reale and not rete"`.

## Verifiche reali (marcatore `reale`, LM Studio attivo, Internet attivo)
- «Che tempo fa a Trieste?» → almeno una chiamata a `meteo_attuale` con una località che contiene
  `Trieste`, un ToolMessage che inizia con `Luogo:` e nessun ToolMessage `Errore:`; la risposta finale
  contiene la parte intera della temperatura del ToolMessage oppure il suo arrotondamento all'intero.
- «Che tempo farà domani a Trieste?»: osservazione, non asserzione; la prova registra nel resoconto se il
  modello dichiara di non avere previsioni.

## Documentazione
- README: strumento meteo (che cosa fa, che richiede Internet, esempi), comandi `-m rete` e `-m reale`
  anche per PowerShell, diagnosi degli errori di rete (proxy, firewall, Docker senza uscita).
- CLAUDE.md: obiettivo con lo strumento meteo e comando della prova `rete` (solo la propria versione nel
  commit: la modifica non in commit dell'utente resta fuori).

## Docker
Nessuna modifica a `compose.yaml`: la rete predefinita di Compose permette l'uscita verso Internet. Prova
manuale non interattiva dopo `docker compose build` con la domanda «Che tempo fa a Pordenone?».

## Criteri di successo
- `python -m pytest` passa senza rete né modello.
- `python -m pytest -m rete -v` passa con Internet.
- `python -m pytest -m reale -v` passa con LM Studio e Internet (la catena del calendario resta xfail).
- La prova Docker restituisce le condizioni attuali.

## Limiti noti
- Il primo risultato del geocoding può non essere il luogo inteso (es. omonimi); la riga `Luogo:` lo rende
  visibile.
- Le condizioni attuali di Open-Meteo sono valori di modello a intervalli di 15 minuti, non osservazioni
  di una stazione.
