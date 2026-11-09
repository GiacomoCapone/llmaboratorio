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
CARTELLA_PROGETTO = PERCORSO_ENV_PROGETTO.parent
# Database delle note: il server «archivio» lo riceve dall'ambiente (assistente non importa archivio).
NOTE_DB_PREDEFINITO = CARTELLA_PROGETTO / "dati" / "note.db"
# Descrizione dell'ambito usata dal router (testo libero, versionato).
AMBITO_PREDEFINITO = CARTELLA_PROGETTO / "ambito.txt"


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
    citta_patrono: str | None = None
    note_db: Path = NOTE_DB_PREDEFINITO
    ambito: str = ""


def _obbligatoria(env: Mapping[str, str], nome: str) -> str:
    valore = env.get(nome, "").strip()
    if not valore:
        raise ErroreConfigurazione(
            f"Variabile {nome} mancante o vuota: impostarla nel file .env "
            "(copiato da .env.example) o nell'ambiente."
        )
    return valore


def _leggi_ambito(grezzo: str) -> str:
    """Testo del file dell'ambito; percorso relativo alla cartella del progetto."""
    percorso = Path(grezzo or AMBITO_PREDEFINITO.name)
    if not percorso.is_absolute():
        percorso = CARTELLA_PROGETTO / percorso
    try:
        testo = percorso.read_text(encoding="utf-8-sig").strip()
    except OSError:
        testo = ""
    if not testo:
        raise ErroreConfigurazione(
            f"File dell'ambito {percorso} mancante o vuoto: descrivere l'ambito "
            "dell'assistente in ambito.txt o indicare un altro file con AMBITO_FILE."
        )
    return testo


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

    citta_patrono = env.get("CITTA_PATRONO", "").strip() or None

    grezzo_note = env.get("NOTE_DB", "").strip()
    if grezzo_note:
        note_db = Path(grezzo_note)
        if not note_db.is_absolute():
            note_db = CARTELLA_PROGETTO / note_db
    else:
        note_db = NOTE_DB_PREDEFINITO

    ambito = _leggi_ambito(env.get("AMBITO_FILE", "").strip())

    return Config(
        base_url,
        model,
        max_passaggi,
        log_level,
        reasoning_effort,
        fuso_predefinito,
        citta_patrono,
        note_db,
        ambito,
    )
