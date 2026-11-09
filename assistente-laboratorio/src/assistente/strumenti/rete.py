"""Richieste HTTP GET che restituiscono JSON, con errori di rete leggibili."""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT_SECONDI = 5
USER_AGENT = "assistente-laboratorio"

logger = logging.getLogger(__name__)


class ErroreRete(Exception):
    """Guasto di rete o risposta non valida; str(e) è il messaggio, senza il prefisso 'Errore: '."""


def _guasto(url: str, tipo: str, messaggio: str) -> ErroreRete:
    """Registra il guasto (solo URL senza parametri e tipo) e crea l'eccezione da sollevare."""
    logger.warning("richiesta a %s fallita: %s", url, tipo)
    return ErroreRete(messaggio)


def scarica_json(url: str, parametri: dict) -> dict:
    """GET su url con i parametri indicati; restituisce l'oggetto JSON o solleva ErroreRete."""
    richiesta = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(parametri),
        headers={"User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(richiesta, timeout=TIMEOUT_SECONDI) as risposta:
            corpo = risposta.read()
    except urllib.error.HTTPError as e:
        raise _guasto(
            url, "stato HTTP", f"il servizio meteo ha risposto con stato {e.code}."
        ) from e
    except (TimeoutError, urllib.error.URLError) as e:
        motivo = e.reason if isinstance(e, urllib.error.URLError) else e
        if isinstance(motivo, TimeoutError):
            raise _guasto(
                url, "timeout",
                f"il servizio meteo non ha risposto entro {TIMEOUT_SECONDI} secondi."
            ) from e
        raise _guasto(
            url, "non raggiungibile", f"servizio meteo non raggiungibile ({motivo})."
        ) from e
    except OSError as e:
        raise _guasto(
            url, "non raggiungibile", f"servizio meteo non raggiungibile ({e})."
        ) from e

    try:
        dati = json.loads(corpo.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise _guasto(url, "risposta non valida", "risposta del servizio meteo non valida.") from e
    if not isinstance(dati, dict):
        raise _guasto(
            url, "risposta non valida", "risposta del servizio meteo non valida."
        )
    return dati
