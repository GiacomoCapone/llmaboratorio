"""Strumenti a disposizione del modello (per ora solo l'orologio)."""

from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

NOME_ORA_CORRENTE = "ora_corrente"

DEFINIZIONE_ORA_CORRENTE = {
    "type": "function",
    "function": {
        "name": NOME_ORA_CORRENTE,
        "description": (
            "Restituisce la data e l'ora correnti nel fuso orario richiesto, "
            "in formato ISO 8601."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fuso": {
                    "type": "string",
                    "description": "Nome IANA del fuso orario, per esempio Europe/Rome.",
                }
            },
            "required": ["fuso"],
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
