"""Logica pura delle note: apertura, aggiunta, elenco, eliminazione."""

import logging
import sqlite3
from datetime import datetime, timedelta
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


def orologio_che_avanza():
    """Un istante diverso (un minuto in più) a ogni chiamata."""
    istanti = iter(adesso() + timedelta(minutes=n) for n in range(100))
    return lambda: next(istanti)


@pytest.fixture
def note_datate(tmp_path, inventario):
    return apri(tmp_path / "note.db", inventario, orologio_che_avanza())


def test_elenco_dalla_piu_recente(note_datate):
    note_datate.aggiungi("primo", "MIS-001")
    note_datate.aggiungi("secondo", None)
    note_datate.aggiungi("terzo", "SAL-002")
    assert note_datate.elenca(None) == (
        "Trovate 3 note:\n"
        "- 3 — 2026-11-09 14:34 — SAL-002 — terzo\n"
        "- 2 — 2026-11-09 14:33 — secondo\n"
        "- 1 — 2026-11-09 14:32 — MIS-001 — primo"
    )


def test_elenco_una_nota(note):
    note.aggiungi("unica", None)
    assert note.elenca(None).splitlines()[0] == "Trovata 1 nota:"


def test_elenco_vuoto(note):
    assert note.elenca(None) == "Nessuna nota."
    assert note.elenca("mis-001") == "Nessuna nota per l'articolo MIS-001."


@pytest.mark.parametrize("codice", ["MIS-001", " mis-001 "])
def test_elenco_filtrato(note, codice):
    note.aggiungi("del multimetro", "MIS-001")
    note.aggiungi("del saldatore", "SAL-002")
    note.aggiungi("generica", None)
    risultato = note.elenca(codice)
    assert risultato.startswith("Trovata 1 nota:")
    assert "del multimetro" in risultato
    assert "del saldatore" not in risultato
    assert "generica" not in risultato


def test_elenco_codice_sconosciuto(note):
    assert note.elenca("XYZ-9") == "Errore: nessun articolo con codice 'XYZ-9'."
    assert (
        note.elenca("a" * 101) == "Errore: testo troppo lungo (massimo 100 caratteri)."
    )


def test_elenco_limite(note):
    for n in range(23):
        note.aggiungi(f"nota {n + 1}", None)
    righe = note.elenca(None).splitlines()
    assert righe[0] == "Trovate 23 note:"
    assert len(righe) == 1 + 20 + 1
    assert righe[1].startswith("- 23 — ")
    assert righe[20].startswith("- 4 — ")
    assert righe[-1] == "(altre 3 note più vecchie non mostrate)"


def test_elimina(note):
    note.aggiungi("display difettoso", "MIS-001")
    assert (
        note.elimina(1)
        == "Nota 1 eliminata: «display difettoso» (MIS-001, 2026-11-09 14:32)."
    )
    assert note.elenca(None) == "Nessuna nota."
    note.aggiungi("senza codice", None)
    assert note.elimina(2) == "Nota 2 eliminata: «senza codice» (2026-11-09 14:32)."


def test_elimina_inesistente(note):
    assert note.elimina(12) == "Errore: nessuna nota con numero 12."
    note.aggiungi("prova", None)
    note.elimina(1)
    assert note.elimina(1) == "Errore: nessuna nota con numero 1."


@pytest.mark.parametrize("numero", [0, -1])
def test_elimina_numero_non_positivo(note, numero):
    assert note.elimina(numero) == "Errore: il numero della nota deve essere un intero positivo."


def test_numero_non_riusato(note):
    note.aggiungi("uno", None)
    note.aggiungi("due", None)
    note.elimina(2)
    assert note.aggiungi("tre", None).startswith("Nota 3 salvata")


@pytest.mark.parametrize(
    "operazione",
    [
        lambda n: n.aggiungi("prova", None),
        lambda n: n.elenca(None),
        lambda n: n.elimina(1),
    ],
    ids=["aggiungi", "elenca", "elimina"],
)
def test_errore_sqlite_in_esercizio(tmp_path, note, operazione, caplog):
    (tmp_path / "note.db").write_bytes(b"non sono un database" * 100)
    with caplog.at_level(logging.WARNING, logger="archivio.note"):
        assert operazione(note) == "Errore: archivio delle note non disponibile."
    assert any(
        r.name == "archivio.note" and r.levelno == logging.WARNING for r in caplog.records
    )


def test_elimina_numero_oltre_il_limite_di_sqlite(note):
    assert note.elimina(10**30) == f"Errore: nessuna nota con numero {10**30}."
