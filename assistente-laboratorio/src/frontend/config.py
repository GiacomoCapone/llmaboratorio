"""Configurazione del front-end: file .env e variabili d'ambiente (l'ambiente prevale)."""

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

# File .env nella cartella del progetto (src/frontend/config.py → ../../.env).
PERCORSO_ENV = Path(__file__).resolve().parents[2] / ".env"


class ErroreConfigurazione(Exception):
    """Configurazione non valida."""


@dataclass(frozen=True)
class ConfigFrontend:
    backend_url: str = "http://127.0.0.1:8001"
    backend_timeout: float = 960.0
    host: str = "127.0.0.1"
    porta: int = 8002
    log_level: str = "INFO"


def _leggi_file_env(percorso: Path) -> dict[str, str]:
    if not percorso.is_file():
        return {}
    return {k: v for k, v in dotenv_values(percorso).items() if v is not None}


def carica_config(env: Mapping[str, str] | None = None) -> ConfigFrontend:
    """Configurazione da `env`; se assente, dal file .env e dall'ambiente, che ha la precedenza."""
    if env is None:
        env = {**_leggi_file_env(PERCORSO_ENV), **os.environ}

    backend_url = env.get("BACKEND_URL", "").strip().rstrip("/") or "http://127.0.0.1:8001"

    grezzo_timeout = env.get("BACKEND_TIMEOUT", "960")
    try:
        backend_timeout = float(grezzo_timeout.strip() or "960")
    except ValueError:
        backend_timeout = 0.0
    if not backend_timeout > 0 or not math.isfinite(backend_timeout):
        raise ErroreConfigurazione(
            f"BACKEND_TIMEOUT deve essere un numero positivo di secondi, trovato {grezzo_timeout!r}."
        )

    host = env.get("FRONTEND_HOST", "").strip() or "127.0.0.1"

    grezza_porta = env.get("FRONTEND_PORTA", "8002")
    try:
        porta = int(grezza_porta.strip() or "8002")
    except ValueError:
        porta = 0
    if not 1 <= porta <= 65535:
        raise ErroreConfigurazione(
            f"FRONTEND_PORTA deve essere un intero fra 1 e 65535, trovato {grezza_porta!r}."
        )

    log_level = env.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    return ConfigFrontend(
        backend_url=backend_url,
        backend_timeout=backend_timeout,
        host=host,
        porta=porta,
        log_level=log_level,
    )
