"""Note del laboratorio salvate in SQLite: logica pura, senza MCP."""

import logging
import sqlite3
import unicodedata
from collections.abc import Callable
from contextlib import closing
from datetime import datetime
from pathlib import Path

from archivio.inventario import LUNGHEZZA_MASSIMA, Inventario

logger = logging.getLogger("archivio.note")

CARTELLA_PROGETTO = Path(__file__).resolve().parents[2]
PERCORSO_NOTE_PREDEFINITO = CARTELLA_PROGETTO / "dati" / "note.db"

NON_DISPONIBILE = "Errore: archivio delle note non disponibile."
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


def _non_disponibile(operazione: str, errore: sqlite3.Error) -> str:
    logger.warning("note: %s non riuscita: %r", operazione, errore)
    return NON_DISPONIBILE


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

    def _canonico(self, codice: str | None) -> tuple[str | None, str | None]:
        """(codice canonico o None, errore o None); un codice vuoto equivale a nessuno."""
        codice = (codice or "").strip()
        if len(codice) > LUNGHEZZA_MASSIMA:
            return None, f"Errore: testo troppo lungo (massimo {LUNGHEZZA_MASSIMA} caratteri)."
        if not codice:
            return None, None
        canonico = self._inventario.codice_canonico(codice)
        if canonico is None:
            return None, f"Errore: nessun articolo con codice '{codice}'."
        return canonico, None

    def aggiungi(self, testo: str | None, codice: str | None) -> str:
        """Salva una nota; testo di conferma o di errore che inizia con «Errore:»."""
        testo = _pulisci(testo)
        if not testo:
            return "Errore: indicare il testo della nota."
        if len(testo) > LUNGHEZZA_TESTO:
            return f"Errore: testo troppo lungo (massimo {LUNGHEZZA_TESTO} caratteri)."
        canonico, errore = self._canonico(codice)
        if errore:
            return errore
        creata = self._adesso().replace(microsecond=0).isoformat()
        try:
            with closing(self._connetti()) as conn, conn:
                cursore = conn.execute(
                    "INSERT INTO note (testo, codice, creata) VALUES (?, ?, ?)",
                    (testo, canonico, creata),
                )
                numero = cursore.lastrowid
        except sqlite3.Error as errore_db:
            return _non_disponibile("aggiunta", errore_db)
        dove = f"{canonico}, " if canonico else ""
        return f"Nota {numero} salvata ({dove}{_data_mostrata(creata)}): {_con_punto(testo)}"

    def elenca(self, codice: str | None) -> str:
        """Le note più recenti (al massimo NOTE_MASSIME), filtrate per articolo se indicato."""
        canonico, errore = self._canonico(codice)
        if errore:
            return errore
        filtro, parametri = ("WHERE codice = ?", (canonico,)) if canonico else ("", ())
        try:
            with closing(self._connetti()) as conn, conn:
                totale = conn.execute(f"SELECT COUNT(*) FROM note {filtro}", parametri).fetchone()[0]
                righe = conn.execute(
                    f"SELECT numero, testo, codice, creata FROM note {filtro} "
                    "ORDER BY numero DESC LIMIT ?",
                    (*parametri, NOTE_MASSIME),
                ).fetchall()
        except sqlite3.Error as errore_db:
            return _non_disponibile("elenco", errore_db)
        if totale == 0:
            return f"Nessuna nota per l'articolo {canonico}." if canonico else "Nessuna nota."
        intestazione = "Trovata 1 nota:" if totale == 1 else f"Trovate {totale} note:"
        linee = [intestazione]
        for numero, testo, cod, creata in righe:
            dove = f" — {cod}" if cod else ""
            linee.append(f"- {numero} — {_data_mostrata(creata)}{dove} — {testo}")
        nascoste = totale - len(righe)
        if nascoste:
            linee.append(f"(altre {nascoste} note più vecchie non mostrate)")
        return "\n".join(linee)

    def elimina(self, numero: int) -> str:
        """Elimina la nota con quel numero e ne riporta il contenuto."""
        if isinstance(numero, bool) or not isinstance(numero, int) or numero <= 0:
            return "Errore: il numero della nota deve essere un intero positivo."
        try:
            with closing(self._connetti()) as conn, conn:
                riga = conn.execute(
                    "SELECT testo, codice, creata FROM note WHERE numero = ?", (numero,)
                ).fetchone()
                if riga is not None:
                    conn.execute("DELETE FROM note WHERE numero = ?", (numero,))
        except sqlite3.Error as errore_db:
            return _non_disponibile("eliminazione", errore_db)
        if riga is None:
            return f"Errore: nessuna nota con numero {numero}."
        testo, codice, creata = riga
        dove = f"{codice}, " if codice else ""
        return f"Nota {numero} eliminata: «{testo}» ({dove}{_data_mostrata(creata)})."
