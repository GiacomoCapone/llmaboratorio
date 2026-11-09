"""Avvio del server «archivio» su stdio: `python -m archivio`."""

import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from archivio.inventario import PERCORSO_INVENTARIO, ErroreInventario, carica
from archivio.note import CARTELLA_PROGETTO, PERCORSO_NOTE_PREDEFINITO, ErroreNote, apri
from archivio.server import crea_server

FUSO_PREDEFINITO = "Europe/Rome"


def percorso_note(valore: str | None) -> Path:
    """Percorso del database delle note: vuoto = predefinito, relativo = dalla cartella del progetto."""
    if not valore:
        return PERCORSO_NOTE_PREDEFINITO
    return CARTELLA_PROGETTO / valore  # un percorso assoluto sostituisce la cartella


def fuso_note(valore: str | None) -> ZoneInfo:
    """Fuso orario delle date delle note; vuoto o non valido = Europe/Rome."""
    try:
        return ZoneInfo(valore or FUSO_PREDEFINITO)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo(FUSO_PREDEFINITO)


def main() -> int:
    # Il Ctrl-C del terminale arriva anche al sottoprocesso: il server sopravvive a un turno
    # annullato e termina quando l'assistente chiude lo stdin.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        inventario = carica(PERCORSO_INVENTARIO)
    except ErroreInventario as errore:
        print(f"Errore: {errore}", file=sys.stderr)
        return 1
    except OSError as errore:
        dettaglio = errore.strerror or str(errore)
        print(f"Errore: inventario non leggibile: {PERCORSO_INVENTARIO} ({dettaglio}).", file=sys.stderr)
        return 1
    fuso = fuso_note(os.environ.get("FUSO_PREDEFINITO"))
    try:
        note = apri(percorso_note(os.environ.get("NOTE_DB")), inventario, lambda: datetime.now(fuso))
    except ErroreNote as errore:
        print(f"Errore: {errore}", file=sys.stderr)
        return 1
    crea_server(inventario, note).run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
