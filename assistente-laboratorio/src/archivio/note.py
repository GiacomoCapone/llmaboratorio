"""Note del laboratorio salvate in SQLite: logica pura, senza MCP."""

import sqlite3
import unicodedata
from collections.abc import Callable
from contextlib import closing
from datetime import datetime
from pathlib import Path

from archivio.inventario import LUNGHEZZA_MASSIMA, Inventario

CARTELLA_PROGETTO = Path(__file__).resolve().parents[2]
PERCORSO_NOTE_PREDEFINITO = CARTELLA_PROGETTO / "dati" / "note.db"

LUNGHEZZA_TESTO = 500
NOTE_MASSIME = 20
ATTESA_LOCK = 5  # secondi di attesa se il database è bloccato

COLONNE = ["numero", "testo", "codice", "creata"]
SCHEMA = """
CREATE TABLE IF NOT EXISTS note (
    numero INTEGER PRIMARY KEY AUTOINCREMENT,
    testo  TEXT NOT NULL,
    codice TEXT,
    creata TEXT NOT NULL
)
"""


class ErroreNote(Exception):
    """Il database delle note non è utilizzabile all'avvio."""


def _pulisci(testo: str | None) -> str:
    """Caratteri di controllo in spazi, poi spazi multipli ridotti a uno."""
    testo = "".join(" " if unicodedata.category(c) == "Cc" else c for c in testo or "")
    return " ".join(testo.split())


def _con_punto(testo: str) -> str:
    return testo if testo.endswith((".", "!", "?")) else testo + "."


def _data_mostrata(creata: str) -> str:
    return creata[:16].replace("T", " ")


def apri(percorso: Path, inventario: Inventario, adesso: Callable[[], datetime]) -> "Note":
    """Crea cartella e tabella se mancano e verifica lo schema; ErroreNote se non va."""
    note = Note(percorso, inventario, adesso)
    try:
        percorso.parent.mkdir(parents=True, exist_ok=True)
        with closing(note._connetti()) as conn, conn:
            conn.execute(SCHEMA)
            colonne = [riga[1] for riga in conn.execute("PRAGMA table_info(note)")]
        if colonne != COLONNE:
            raise ErroreNote(
                f"archivio delle note non valido: {percorso} "
                f"(colonne trovate: {', '.join(colonne)})."
            )
    except OSError as errore:
        raise ErroreNote(
            f"archivio delle note non valido: {percorso} ({errore.strerror or errore})."
        ) from errore
    except sqlite3.Error as errore:
        raise ErroreNote(f"archivio delle note non valido: {percorso} ({errore}).") from errore
    return note


class Note:
    """Note del laboratorio; ogni operazione usa una connessione propria."""

    def __init__(self, percorso: Path, inventario: Inventario, adesso: Callable[[], datetime]):
        self._percorso = percorso
        self._inventario = inventario
        self._adesso = adesso

    def _connetti(self) -> sqlite3.Connection:
        return sqlite3.connect(self._percorso, timeout=ATTESA_LOCK)

    def aggiungi(self, testo: str | None, codice: str | None) -> str:
        """Salva una nota; testo di conferma o di errore che inizia con «Errore:»."""
        testo = _pulisci(testo)
        codice = (codice or "").strip()
        if not testo:
            return "Errore: indicare il testo della nota."
        if len(testo) > LUNGHEZZA_TESTO:
            return f"Errore: testo troppo lungo (massimo {LUNGHEZZA_TESTO} caratteri)."
        if len(codice) > LUNGHEZZA_MASSIMA:
            return f"Errore: testo troppo lungo (massimo {LUNGHEZZA_MASSIMA} caratteri)."
        canonico = None
        if codice:
            canonico = self._inventario.codice_canonico(codice)
            if canonico is None:
                return f"Errore: nessun articolo con codice '{codice}'."
        creata = self._adesso().replace(microsecond=0).isoformat()
        with closing(self._connetti()) as conn, conn:
            cursore = conn.execute(
                "INSERT INTO note (testo, codice, creata) VALUES (?, ?, ?)",
                (testo, canonico, creata),
            )
            numero = cursore.lastrowid
        dove = f"{canonico}, " if canonico else ""
        return f"Nota {numero} salvata ({dove}{_data_mostrata(creata)}): {_con_punto(testo)}"
