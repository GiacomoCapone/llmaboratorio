"""Lettura e validazione della configurazione: file .env e variabili d'ambiente."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LIVELLI_RAGIONAMENTO = ("none", "low", "medium", "high")

# File .env nella cartella del progetto (src/assistente/config.py → ../../.env), qualunque sia
# la cartella da cui si avvia il programma. Nell'immagine Docker non esiste: lì vale l'ambiente.
PERCORSO_ENV_PROGETTO = Path(__file__).resolve().parents[2] / ".env"
PERCORSO_ENV = PERCORSO_ENV_PROGETTO


class ErroreConfigurazione(Exception):
    """Configurazione mancante o non valida."""


@dataclass(frozen=True)
class Config:
    base_url: str
    model: str
    max_passaggi: int
    log_level: str
    reasoning_effort: str
    fuso_predefinito: str


def _obbligatoria(env: Mapping[str, str], nome: str) -> str:
    valore = env.get(nome, "").strip()
    if not valore:
        raise ErroreConfigurazione(
            f"Variabile {nome} mancante o vuota: impostarla nel file .env "
            "(copiato da .env.example) o nell'ambiente."
        )
    return valore


def leggi_file_env(percorso: Path) -> dict[str, str]:
    """Variabili del file .env (vuoto se il file manca); le righe senza valore sono ignorate."""
    if not percorso.is_file():
        return {}
    return {k: v for k, v in dotenv_values(percorso).items() if v is not None}


def carica_config(env: Mapping[str, str] | None = None) -> Config:
    """Configurazione da `env`; se assente, dal file .env e dall'ambiente, che ha la precedenza."""
    if env is None:
        env = {**leggi_file_env(PERCORSO_ENV), **os.environ}
    base_url = _obbligatoria(env, "LMSTUDIO_BASE_URL").rstrip("/")
    model = _obbligatoria(env, "LMSTUDIO_MODEL")

    grezzo = env.get("MAX_PASSAGGI", "5")
    try:
        max_passaggi = int(grezzo)
    except ValueError:
        max_passaggi = 0
    if max_passaggi < 1:
        raise ErroreConfigurazione(
            f"MAX_PASSAGGI deve essere un intero positivo, trovato {grezzo!r}."
        )

    log_level = env.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    reasoning_effort = env.get("LMSTUDIO_REASONING_EFFORT", "").strip().lower() or "none"
    if reasoning_effort not in LIVELLI_RAGIONAMENTO:
        raise ErroreConfigurazione(
            f"LMSTUDIO_REASONING_EFFORT non valido: {reasoning_effort!r}. "
            f"Valori ammessi: {', '.join(LIVELLI_RAGIONAMENTO)}."
        )

    fuso_predefinito = env.get("FUSO_PREDEFINITO", "").strip() or "Europe/Rome"
    try:
        ZoneInfo(fuso_predefinito)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ErroreConfigurazione(
            f"FUSO_PREDEFINITO non valido: {fuso_predefinito!r}. "
            "Usare un nome IANA come Europe/Rome."
        ) from None

    return Config(
        base_url, model, max_passaggi, log_level, reasoning_effort, fuso_predefinito
    )
