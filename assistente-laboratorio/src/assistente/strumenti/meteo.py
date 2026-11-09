"""Strumento meteo: condizioni attuali di una località tramite Open-Meteo."""

import math
from typing import Callable

from assistente.strumenti.rete import ErroreRete

URL_GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"
URL_PREVISIONI = "https://api.open-meteo.com/v1/forecast"
CAMPI_ATTUALI = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,"
    "precipitation,weather_code,wind_speed_10m,wind_direction_10m"
)
LUNGHEZZA_MASSIMA = 100

DEFINIZIONE_METEO = {
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

CODICI_WMO: dict[int, str] = {
    0: "sereno",
    1: "prevalentemente sereno",
    2: "parzialmente nuvoloso",
    3: "coperto",
    45: "nebbia",
    48: "nebbia con brina",
    51: "pioviggine leggera",
    53: "pioviggine moderata",
    55: "pioviggine intensa",
    56: "pioviggine gelata leggera",
    57: "pioviggine gelata intensa",
    61: "pioggia leggera",
    63: "pioggia moderata",
    65: "pioggia forte",
    66: "pioggia gelata leggera",
    67: "pioggia gelata forte",
    71: "neve leggera",
    73: "neve moderata",
    75: "neve forte",
    77: "neve granulosa",
    80: "rovesci di pioggia leggeri",
    81: "rovesci di pioggia moderati",
    82: "rovesci di pioggia violenti",
    85: "rovesci di neve leggeri",
    86: "rovesci di neve forti",
    95: "temporale",
    96: "temporale con grandine leggera",
    99: "temporale con grandine forte",
}

PUNTI_CARDINALI = (
    "nord",
    "nord-est",
    "est",
    "sud-est",
    "sud",
    "sud-ovest",
    "ovest",
    "nord-ovest",
)

ERRORE_LOCALITA = "Errore: indicare la località, per esempio Pordenone."
ERRORE_LUNGA = "Errore: nome di località troppo lungo (massimo 100 caratteri)."
ERRORE_RISPOSTA = "Errore: risposta del servizio meteo non valida."


class _RispostaNonValida(Exception):
    """Campo mancante o di tipo sbagliato in una risposta di Open-Meteo."""


def _numero(valori: dict, chiave: str) -> float:
    valore = valori.get(chiave)
    if isinstance(valore, bool) or not isinstance(valore, (int, float)):
        raise _RispostaNonValida(chiave)
    try:
        finito = math.isfinite(float(valore))
    except OverflowError:
        finito = False
    if not finito:
        raise _RispostaNonValida(chiave)
    return valore


def _testo(valori: dict, chiave: str) -> str:
    valore = valori.get(chiave)
    if not isinstance(valore, str):
        raise _RispostaNonValida(chiave)
    return valore


def _decimale(x: float) -> str:
    testo = format(x, ".1f")
    if testo == "-0.0":
        testo = "0.0"
    return testo.replace(".", ",")


def _direzione(gradi: float) -> str:
    return PUNTI_CARDINALI[int(((gradi % 360) + 22.5) // 45) % 8]


def _luogo(risultato: dict) -> str:
    parti = [_testo(risultato, "name")]
    for chiave in ("admin1", "country"):
        if risultato.get(chiave) in (None, ""):
            continue
        parte = _testo(risultato, chiave)
        if parte not in parti:
            parti.append(parte)
    return ", ".join(parti)


def _cielo(codice: float) -> str:
    return CODICI_WMO.get(codice, f"condizione non classificata (codice {codice})")


def _vento(velocita: float, gradi: float) -> str:
    if velocita == 0:
        return "calmo (0,0 km/h)"
    return f"{_decimale(velocita)} km/h da {_direzione(gradi)}"


def _formatta(risultato: dict, attuali: dict) -> str:
    luogo = _luogo(risultato)
    corrente = attuali.get("current")
    if not isinstance(corrente, dict):
        raise _RispostaNonValida("current")
    ora = _testo(corrente, "time").replace("T", " ")
    fuso = _testo(attuali, "timezone")
    temperatura = _numero(corrente, "temperature_2m")
    percepita = _numero(corrente, "apparent_temperature")
    umidita = _numero(corrente, "relative_humidity_2m")
    precipitazioni = _numero(corrente, "precipitation")
    codice = _numero(corrente, "weather_code")
    velocita = _numero(corrente, "wind_speed_10m")
    gradi = _numero(corrente, "wind_direction_10m")
    return "\n".join(
        [
            f"Luogo: {luogo}",
            f"Rilevazione: {ora} (ora locale, {fuso})",
            f"Cielo: {_cielo(codice)}",
            f"Temperatura: {_decimale(temperatura)} °C (percepita {_decimale(percepita)} °C)",
            f"Umidità: {round(umidita)} %",
            f"Precipitazioni: {_decimale(precipitazioni)} mm",
            f"Vento: {_vento(velocita, gradi)}",
        ]
    )


def esegui_meteo(args: dict, scarica: Callable[[str, dict], dict]) -> str:
    """Condizioni meteo attuali di una località; in caso di errore un testo 'Errore: ...'."""
    localita = args.get("localita")
    if not isinstance(localita, str) or not localita.strip():
        return ERRORE_LOCALITA
    localita = localita.strip()
    if len(localita) > LUNGHEZZA_MASSIMA:
        return ERRORE_LUNGA
    try:
        geocoding = scarica(
            URL_GEOCODING,
            {"name": localita, "count": 1, "language": "it", "format": "json"},
        )
        risultati = geocoding.get("results")
        if not risultati:
            return f"Errore: località non trovata: '{localita}'."
        if not isinstance(risultati, list) or not isinstance(risultati[0], dict):
            return ERRORE_RISPOSTA
        primo = risultati[0]
        latitudine = _numero(primo, "latitude")
        longitudine = _numero(primo, "longitude")
        _luogo(primo)
        attuali = scarica(
            URL_PREVISIONI,
            {
                "latitude": latitudine,
                "longitude": longitudine,
                "current": CAMPI_ATTUALI,
                "timezone": "auto",
            },
        )
        return _formatta(primo, attuali)
    except ErroreRete as errore:
        return f"Errore: {errore}"
    except _RispostaNonValida:
        return ERRORE_RISPOSTA
