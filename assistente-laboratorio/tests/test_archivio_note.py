"""Logica pura delle note: apertura del database e aggiunta."""

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from archivio.inventario import Articolo, Inventario
from archivio.note import ErroreNote, apri


def adesso():
    return datetime(2026, 11, 9, 14, 32, 5, tzinfo=ZoneInfo("Europe/Rome"))


@pytest.fixture
def inventario():
    return Inventario(
        [
            Articolo("MIS-001", "Multimetro", "strumenti di misura", 3, "armadio A", ""),
            Articolo("SAL-002", "Saldatore", "attrezzi", 2, "banco 1", ""),
        ]
    )


@pytest.fixture
def note(tmp_path, inventario):
    return apri(tmp_path / "note.db", inventario, adesso)


def test_aggiungi_senza_codice(note):
    assert (
        note.aggiungi("ordinare fusibili da 2 A", None)
        == "Nota 1 salvata (2026-11-09 14:32): ordinare fusibili da 2 A."
    )


def test_aggiungi_con_codice_canonico(note):
    assert (
        note.aggiungi("display difettoso", "mis-001")
        == "Nota 1 salvata (MIS-001, 2026-11-09 14:32): display difettoso."
    )


@pytest.mark.parametrize("finale", ["!", ".", "?"])
def test_punto_finale_non_raddoppiato(note, finale):
    risultato = note.aggiungi(f"batteria scarica{finale}", None)
    assert risultato.endswith(f"batteria scarica{finale}")
    assert not risultato.endswith(f"{finale}.")


def test_pulizia_del_testo(tmp_path, note):
    note.aggiungi("  riga uno\nriga\t due   ", None)
    conn = sqlite3.connect(tmp_path / "note.db")
    try:
        assert conn.execute("SELECT testo FROM note").fetchone() == ("riga uno riga due",)
    finally:
        conn.close()


@pytest.mark.parametrize("testo", [None, "", "   ", "\n\t"])
def test_testo_vuoto(note, testo):
    assert note.aggiungi(testo, None) == "Errore: indicare il testo della nota."


def test_testo_troppo_lungo(note):
    assert (
        note.aggiungi("a" * 501, None) == "Errore: testo troppo lungo (massimo 500 caratteri)."
    )
    assert note.aggiungi("a" * 500, None).startswith("Nota 1 salvata")


def test_codice_troppo_lungo(note):
    assert (
        note.aggiungi("prova", "a" * 101) == "Errore: testo troppo lungo (massimo 100 caratteri)."
    )


def test_codice_sconosciuto_non_salva(note):
    assert note.aggiungi("prova", "XYZ-9") == "Errore: nessun articolo con codice 'XYZ-9'."
    assert note.aggiungi("prova", None).startswith("Nota 1 salvata")


def test_codice_vuoto_equivale_a_nessuno(note):
    assert note.aggiungi("prova", "  ") == "Nota 1 salvata (2026-11-09 14:32): prova."


def test_data_salvata_con_scostamento(tmp_path, note):
    note.aggiungi("prova", None)
    conn = sqlite3.connect(tmp_path / "note.db")
    try:
        assert conn.execute("SELECT creata FROM note").fetchone() == ("2026-11-09T14:32:05+01:00",)
    finally:
        conn.close()


def test_persistenza(tmp_path, inventario):
    apri(tmp_path / "note.db", inventario, adesso).aggiungi("prima", None)
    seconda = apri(tmp_path / "note.db", inventario, adesso)
    assert seconda.aggiungi("seconda", None).startswith("Nota 2 salvata")


def test_crea_la_cartella(tmp_path, inventario):
    apri(tmp_path / "a" / "b" / "note.db", inventario, adesso)
    assert (tmp_path / "a" / "b").is_dir()


def test_file_non_sqlite(tmp_path, inventario):
    percorso = tmp_path / "note.db"
    percorso.write_text("non sono un database")
    with pytest.raises(ErroreNote, match="archivio delle note non valido") as errore:
        apri(percorso, inventario, adesso)
    assert str(percorso) in str(errore.value)


def test_schema_diverso(tmp_path, inventario):
    percorso = tmp_path / "note.db"
    conn = sqlite3.connect(percorso)
    try:
        with conn:
            conn.execute("CREATE TABLE note (numero INTEGER, testo TEXT)")
    finally:
        conn.close()
    with pytest.raises(ErroreNote):
        apri(percorso, inventario, adesso)


def test_percorso_e_una_cartella(tmp_path, inventario):
    with pytest.raises(ErroreNote):
        apri(tmp_path, inventario, adesso)


def test_cartella_non_creabile(tmp_path, inventario):
    (tmp_path / "f").write_text("x")
    with pytest.raises(ErroreNote):
        apri(tmp_path / "f" / "note.db", inventario, adesso)
