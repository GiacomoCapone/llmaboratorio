import copy

import pytest

from assistente.strumenti.meteo import (
    CAMPI_ATTUALI,
    CODICI_WMO,
    DEFINIZIONE_METEO,
    URL_GEOCODING,
    URL_PREVISIONI,
    esegui_meteo,
)
from assistente.strumenti.rete import ErroreRete

GEOCODING = {
    "results": [
        {
            "id": 3171728,
            "name": "Pordenone",
            "latitude": 45.95689,
            "longitude": 12.66051,
            "country": "Italia",
            "admin1": "Friuli Venezia Giulia",
        }
    ],
    "generationtime_ms": 0.5,
}

ATTUALI = {
    "latitude": 45.95689,
    "longitude": 12.66051,
    "timezone": "Europe/Rome",
    "current": {
        "time": "2026-11-09T09:00",
        "interval": 900,
        "temperature_2m": 5.7,
        "apparent_temperature": 4.1,
        "relative_humidity_2m": 91,
        "precipitation": 0.0,
        "weather_code": 3,
        "wind_speed_10m": 1.5,
        "wind_direction_10m": 45,
    },
}

RISULTATO = (
    "Luogo: Pordenone, Friuli Venezia Giulia, Italia\n"
    "Rilevazione: 2026-11-09 09:00 (ora locale, Europe/Rome)\n"
    "Cielo: coperto\n"
    "Temperatura: 5,7 °C (percepita 4,1 °C)\n"
    "Umidità: 91 %\n"
    "Precipitazioni: 0,0 mm\n"
    "Vento: 1,5 km/h da nord-est"
)

DEFINIZIONE = {
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


class ScaricaFinta:
    def __init__(self, risposte):
        self.risposte = list(risposte)
        self.chiamate = []

    def __call__(self, url, parametri):
        self.chiamate.append((url, parametri))
        risposta = self.risposte.pop(0)
        if isinstance(risposta, Exception):
            raise risposta
        return risposta


def finta(geocoding=GEOCODING, attuali=ATTUALI):
    return ScaricaFinta([copy.deepcopy(geocoding), copy.deepcopy(attuali)])


def con_current(**campi):
    attuali = copy.deepcopy(ATTUALI)
    attuali["current"].update(campi)
    return attuali


def riga(testo, prefisso):
    return next(r for r in testo.split("\n") if r.startswith(prefisso))


def test_risultato_completo():
    assert esegui_meteo({"localita": "Pordenone"}, finta()) == RISULTATO


def test_parametri_inviati():
    scarica = finta()
    esegui_meteo({"localita": "Pordenone"}, scarica)
    assert scarica.chiamate == [
        (URL_GEOCODING, {"name": "Pordenone", "count": 1, "language": "it", "format": "json"}),
        (
            URL_PREVISIONI,
            {
                "latitude": 45.95689,
                "longitude": 12.66051,
                "current": CAMPI_ATTUALI,
                "timezone": "auto",
            },
        ),
    ]


def test_localita_ripulita():
    scarica = finta()
    esegui_meteo({"localita": "  Trieste "}, scarica)
    assert scarica.chiamate[0][1]["name"] == "Trieste"


@pytest.mark.parametrize(
    "args", [{}, {"localita": None}, {"localita": ""}, {"localita": "   "}, {"localita": 42}]
)
def test_localita_mancante(args):
    scarica = ScaricaFinta([])
    assert esegui_meteo(args, scarica) == "Errore: indicare la località, per esempio Pordenone."
    assert scarica.chiamate == []


def test_localita_troppo_lunga():
    scarica = ScaricaFinta([])
    assert (
        esegui_meteo({"localita": "a" * 101}, scarica)
        == "Errore: nome di località troppo lungo (massimo 100 caratteri)."
    )
    assert scarica.chiamate == []
    scarica = finta()
    esegui_meteo({"localita": "a" * 100}, scarica)
    assert len(scarica.chiamate) == 2


@pytest.mark.parametrize("geocoding", [{"generationtime_ms": 0.1}, {"results": []}])
@pytest.mark.parametrize("nome", ["L'Aquilaa", "Forlì"])
def test_non_trovata(geocoding, nome):
    scarica = ScaricaFinta([geocoding])
    assert (
        esegui_meteo({"localita": nome}, scarica)
        == f"Errore: località non trovata: '{nome}'."
    )


@pytest.mark.parametrize("fallisce", [0, 1])
def test_errore_di_rete(fallisce):
    errore = ErroreRete("il servizio meteo non ha risposto entro 5 secondi.")
    risposte = [errore] if fallisce == 0 else [copy.deepcopy(GEOCODING), errore]
    assert (
        esegui_meteo({"localita": "Pordenone"}, ScaricaFinta(risposte))
        == "Errore: il servizio meteo non ha risposto entro 5 secondi."
    )


def _geo(**modifiche):
    geo = copy.deepcopy(GEOCODING)
    for chiave, valore in modifiche.items():
        if valore is None:
            del geo["results"][0][chiave]
        else:
            geo["results"][0][chiave] = valore
    return geo


def _att(**modifiche):
    att = copy.deepcopy(ATTUALI)
    for chiave, valore in modifiche.items():
        if valore is None:
            del att["current"][chiave]
        else:
            att["current"][chiave] = valore
    return att


def _senza(chiave):
    att = copy.deepcopy(ATTUALI)
    del att[chiave]
    return att


@pytest.mark.parametrize(
    "geocoding, attuali",
    [
        (_geo(latitude=None), ATTUALI),
        (_geo(latitude=True), ATTUALI),
        (_geo(name=42), ATTUALI),
        (_geo(country=7), ATTUALI),
        (GEOCODING, _senza("current")),
        (GEOCODING, _att(temperature_2m="5,7")),
        (GEOCODING, _att(weather_code=None)),
        (GEOCODING, _senza("timezone")),
    ],
)
def test_risposta_non_valida(geocoding, attuali):
    scarica = ScaricaFinta([copy.deepcopy(geocoding), copy.deepcopy(attuali)])
    assert (
        esegui_meteo({"localita": "Pordenone"}, scarica)
        == "Errore: risposta del servizio meteo non valida."
    )


def test_luogo():
    senza = esegui_meteo({"localita": "x"}, finta(_geo(admin1=None, country=None)))
    assert riga(senza, "Luogo") == "Luogo: Pordenone"
    roma = _geo(name="Roma", admin1="Roma", country="Italia")
    assert riga(esegui_meteo({"localita": "x"}, finta(roma)), "Luogo") == "Luogo: Roma, Italia"
    vuoto = _geo(admin1="")
    assert riga(esegui_meteo({"localita": "x"}, finta(vuoto)), "Luogo") == "Luogo: Pordenone, Italia"


@pytest.mark.parametrize("codice, descrizione", sorted(CODICI_WMO.items()))
def test_codici_wmo(codice, descrizione):
    risultato = esegui_meteo({"localita": "x"}, finta(attuali=con_current(weather_code=codice)))
    assert riga(risultato, "Cielo") == f"Cielo: {descrizione}"


def test_codici_wmo_numero_e_sconosciuto():
    assert len(CODICI_WMO) == 28
    risultato = esegui_meteo({"localita": "x"}, finta(attuali=con_current(weather_code=4)))
    assert riga(risultato, "Cielo") == "Cielo: condizione non classificata (codice 4)"


@pytest.mark.parametrize(
    "gradi, direzione",
    [(0, "nord"), (22.4, "nord"), (22.5, "nord-est"), (180, "sud"), (337.5, "nord"), (360, "nord")],
)
def test_direzione_vento(gradi, direzione):
    risultato = esegui_meteo({"localita": "x"}, finta(attuali=con_current(wind_direction_10m=gradi)))
    assert riga(risultato, "Vento") == f"Vento: 1,5 km/h da {direzione}"


def test_vento_calmo():
    risultato = esegui_meteo({"localita": "x"}, finta(attuali=con_current(wind_speed_10m=0)))
    assert riga(risultato, "Vento") == "Vento: calmo (0,0 km/h)"


def test_numeri():
    risultato = esegui_meteo(
        {"localita": "x"},
        finta(attuali=con_current(temperature_2m=-3.2, apparent_temperature=12)),
    )
    assert riga(risultato, "Temperatura") == "Temperatura: -3,2 °C (percepita 12,0 °C)"
    risultato = esegui_meteo({"localita": "x"}, finta(attuali=con_current(temperature_2m=-0.04)))
    assert riga(risultato, "Temperatura") == "Temperatura: 0,0 °C (percepita 4,1 °C)"
    risultato = esegui_meteo(
        {"localita": "x"},
        finta(attuali=con_current(relative_humidity_2m=90.6, precipitation=12)),
    )
    assert riga(risultato, "Umidità") == "Umidità: 91 %"
    assert riga(risultato, "Precipitazioni") == "Precipitazioni: 12,0 mm"


def test_parametri_estranei():
    assert esegui_meteo({"localita": "Pordenone", "giorni": 3}, finta()) == RISULTATO


def test_definizione():
    assert DEFINIZIONE_METEO == DEFINIZIONE


@pytest.mark.parametrize(
    "campo, valore",
    [
        ("temperature_2m", float("nan")),
        ("temperature_2m", float("inf")),
        ("temperature_2m", 10**400),
        ("relative_humidity_2m", float("nan")),
        ("wind_direction_10m", float("inf")),
    ],
)
def test_numeri_non_finiti(campo, valore):
    risultato = esegui_meteo({"localita": "x"}, finta(attuali=con_current(**{campo: valore})))
    assert risultato == "Errore: risposta del servizio meteo non valida."
