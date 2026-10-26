"""Lettura e validazione della configurazione dalle variabili d'ambiente."""

import os
from collections.abc import Mapping
from dataclasses import dataclass


class ErroreConfigurazione(Exception):
    """Configurazione mancante o non valida."""


@dataclass(frozen=True)
class Config:
    base_url: str
    model: str
    max_passaggi: int
    log_level: str


def _obbligatoria(env: Mapping[str, str], nome: str) -> str:
    valore = env.get(nome, "").strip()
    if not valore:
        raise ErroreConfigurazione(
            f"Variabile d'ambiente {nome} mancante o vuota: impostarla (vedi .env.example)."
        )
    return valore


def carica_config(env: Mapping[str, str] | None = None) -> Config:
    if env is None:
        env = os.environ
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
    return Config(base_url, model, max_passaggi, log_level)
