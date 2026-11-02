"""Strumenti a disposizione del modello."""

from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

NOME_ORA_CORRENTE = "ora_corrente"


def definizione_ora_corrente(fuso_predefinito: str) -> dict:
    """Definizione dello strumento orologio; il fuso predefinito è indicato nella descrizione."""
    return {
        "type": "function",
        "function": {
            "name": NOME_ORA_CORRENTE,
            "description": (
                "Restituisce la data e l'ora attuali (formato ISO 8601). "
                "Chiamalo SEMPRE quando l'utente chiede l'ora, la data o il giorno, "
                "per esempio 'che ore sono', 'che ora è', 'che giorno è oggi'. "
                "Non chiedere mai il fuso all'utente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fuso": {
                        "type": "string",
                        "description": (
                            "Nome IANA del fuso orario, per esempio America/New_York. "
                            "Facoltativo: se l'utente non indica un luogo, omettilo e "
                            f"verrà usato {fuso_predefinito}."
                        ),
                    }
                },
                "required": [],
            },
        },
    }


def ora_corrente(fuso: str, adesso: Callable[[], datetime]) -> str:
    """Data e ora ISO 8601 nel fuso richiesto; in caso di errore un testo 'Errore: ...'."""
    try:
        zona = ZoneInfo(fuso)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return f"Errore: fuso orario non valido: '{fuso}'. Usare un nome IANA come Europe/Rome."
    istante = adesso()
    if istante.tzinfo is None:
        istante = istante.replace(tzinfo=timezone.utc)
    return istante.astimezone(zona).isoformat()
