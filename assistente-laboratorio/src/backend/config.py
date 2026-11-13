"""Configurazione del back-end: file .env e variabili d'ambiente (l'ambiente prevale)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

# File .env nella cartella del progetto (src/backend/config.py → ../../.env).
PERCORSO_ENV = Path(__file__).resolve().parents[2] / ".env"


class ErroreConfigurazione(Exception):
    """Configurazione mancante o non valida."""


@dataclass(frozen=True)
class ConfigBackend:
    database_url: str
    agente_url: str = "http://127.0.0.1:8000"
    agente_timeout: float = 900.0
    host: str = "127.0.0.1"
    porta: int = 8001
    log_level: str = "INFO"


def _leggi_file_env(percorso: Path) -> dict[str, str]:
    if not percorso.is_file():
        return {}
    return {k: v for k, v in dotenv_values(percorso).items() if v is not None}


def carica_config(env: Mapping[str, str] | None = None) -> ConfigBackend:
    """Configurazione da `env`; se assente, dal file .env e dall'ambiente, che ha la precedenza."""
    if env is None:
        env = {**_leggi_file_env(PERCORSO_ENV), **os.environ}

    database_url = env.get("DATABASE_URL", "").strip()
    if not database_url:
        raise ErroreConfigurazione(
            "Variabile DATABASE_URL mancante o vuota: impostarla nel file .env "
            "(copiato da .env.example) o nell'ambiente."
        )

    agente_url = env.get("AGENTE_URL", "").strip().rstrip("/") or "http://127.0.0.1:8000"

    grezzo_timeout = env.get("AGENTE_TIMEOUT", "900")
    try:
        agente_timeout = float(grezzo_timeout.strip() or "900")
    except ValueError:
        agente_timeout = 0.0
    if not agente_timeout > 0 or agente_timeout == float("inf"):
        raise ErroreConfigurazione(
            f"AGENTE_TIMEOUT deve essere un numero positivo di secondi, trovato {grezzo_timeout!r}."
        )

    host = env.get("BACKEND_HOST", "").strip() or "127.0.0.1"

    grezza_porta = env.get("BACKEND_PORTA", "8001")
    try:
        porta = int(grezza_porta.strip() or "8001")
    except ValueError:
        porta = 0
    if not 1 <= porta <= 65535:
        raise ErroreConfigurazione(
            f"BACKEND_PORTA deve essere un intero fra 1 e 65535, trovato {grezza_porta!r}."
        )

    log_level = env.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    return ConfigBackend(
        database_url=database_url,
        agente_url=agente_url,
        agente_timeout=agente_timeout,
        host=host,
        porta=porta,
        log_level=log_level,
    )
