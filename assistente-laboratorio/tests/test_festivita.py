import json
from datetime import date

import pytest

from assistente.config import ErroreConfigurazione
from assistente.strumenti.festivita import carica_festivita, pasqua


@pytest.mark.parametrize(
    "anno, mese, giorno",
    [(1583, 4, 10), (2024, 3, 31), (2025, 4, 20), (2026, 4, 5), (2038, 4, 25), (2285, 3, 22)],
)
def test_pasqua(anno, mese, giorno):
    assert pasqua(anno) == date(anno, mese, giorno)


def test_festivita_2026_pordenone():
    voci = carica_festivita("Pordenone").dell_anno(2026)
    assert len(voci) == 12
    assert voci[date(2026, 4, 6)] == "Lunedì dell'Angelo (Pasquetta)"
    assert voci[date(2026, 4, 5)] == "Pasqua"
    assert voci[date(2026, 4, 25)] == "Festa della Liberazione, San Marco (patrono di Pordenone)"
    assert voci[date(2026, 12, 8)] == "Immacolata Concezione"


def test_voce_unita_2038():
    voci = carica_festivita("Pordenone").dell_anno(2038)
    assert voci[date(2038, 4, 25)] == "Festa della Liberazione, Pasqua, San Marco (patrono di Pordenone)"


@pytest.mark.parametrize("citta", [None, ""])
def test_senza_patrono(citta):
    festivita = carica_festivita(citta)
    voci = festivita.dell_anno(2026)
    assert festivita.citta is None
    assert len(voci) == 12
    assert voci[date(2026, 4, 25)] == "Festa della Liberazione"


def test_patrono_altro_giorno():
    voci = carica_festivita("Udine").dell_anno(2026)
    assert voci[date(2026, 7, 12)] == "Santi Ermacora e Fortunato (patrono di Udine)"


def test_citta_normalizzata():
    assert carica_festivita("  pordenone ").citta == "Pordenone"


def test_citta_sconosciuta():
    with pytest.raises(ErroreConfigurazione) as errore:
        carica_festivita("Milano")
    assert str(errore.value).startswith(
        "Città del patrono sconosciuta: 'Milano'. "
        "Città disponibili: Pordenone, Roma, Trieste, Udine, Venezia (file "
    )


NAZIONALI_OK = {"01-01": "X"}


@pytest.mark.parametrize(
    "contenuto",
    [
        None,
        "{",
        "[]",
        json.dumps({"nazionali": NAZIONALI_OK}),
        json.dumps({"nazionali": {"13-01": "X"}, "patroni": {}}),
        json.dumps({"nazionali": {"02-29": "X"}, "patroni": {}}),
        json.dumps({"nazionali": {"01-01": ""}, "patroni": {}}),
        json.dumps({"nazionali": NAZIONALI_OK, "patroni": {"Roma": {"data": "06-29"}}}),
    ],
)
def test_file_non_valido(tmp_path, contenuto):
    percorso = tmp_path / "festivita.json"
    if contenuto is not None:
        percorso.write_text(contenuto, encoding="utf-8")
    with pytest.raises(ErroreConfigurazione) as errore:
        carica_festivita(None, percorso)
    assert str(errore.value).startswith("File delle festività non valido: ")


@pytest.mark.parametrize(
    "giorno, atteso",
    [
        (date(2026, 12, 1), True),
        (date(2026, 12, 5), False),
        (date(2026, 12, 6), False),
        (date(2026, 12, 8), False),
        (date(2026, 4, 6), False),
        (date(2026, 4, 25), False),
    ],
)
def test_lavorativo(giorno, atteso):
    assert carica_festivita("Pordenone").lavorativo(giorno) is atteso
