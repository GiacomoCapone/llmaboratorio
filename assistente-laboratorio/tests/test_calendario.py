import re
from datetime import date

import pytest

from assistente.strumenti.calendario import (
    NOME_CALENDARIO,
    aggiungi,
    definizione_calendario,
    differenza,
    esegui_calendario,
)
from assistente.strumenti.festivita import carica_festivita


@pytest.fixture(scope="module")
def fest():
    return carica_festivita("Pordenone")


DESCRIZIONE = (
    "Calcola con le date del calendario italiano, tenendo conto di weekend e festività ({elenco}). "
    "Operazione 'differenza': giorni di calendario e giorni lavorativi fra 'data' e 'data_fine'. "
    "Operazione 'aggiungi': la data che si ottiene aggiungendo 'giorni' a 'data' "
    "(negativi per andare indietro); con 'lavorativi' true conta solo i giorni lavorativi. "
    "Le date sono nel formato AAAA-MM-GG: per oggi chiama prima ora_corrente. "
    "Chiamalo SEMPRE per domande su giorni lavorativi, scadenze o quanti giorni mancano a una data."
)


def _controlla_definizione(d, descrizione):
    assert d["type"] == "function"
    f = d["function"]
    assert f["name"] == NOME_CALENDARIO == "calendario"
    assert f["description"] == descrizione
    p = f["parameters"]
    assert p["type"] == "object"
    assert p["required"] == ["operazione", "data"]
    pr = p["properties"]
    assert list(pr) == ["operazione", "data", "data_fine", "giorni", "lavorativi"]
    assert pr["operazione"] == {
        "type": "string",
        "enum": ["differenza", "aggiungi"],
        "description": "'differenza' oppure 'aggiungi'.",
    }
    assert pr["data"] == {
        "type": "string",
        "description": "Data di partenza, nel formato AAAA-MM-GG.",
    }
    assert pr["data_fine"] == {
        "type": "string",
        "description": "Solo per 'differenza': data di arrivo, nel formato AAAA-MM-GG.",
    }
    assert pr["giorni"] == {
        "type": "integer",
        "description": (
            "Solo per 'aggiungi': numero di giorni da aggiungere, negativo per andare indietro."
        ),
    }
    assert pr["lavorativi"] == {
        "type": "boolean",
        "description": (
            "Solo per 'aggiungi': true per contare solo i giorni lavorativi. "
            "Facoltativo, predefinito false."
        ),
    }


def test_definizione_con_citta():
    _controlla_definizione(
        definizione_calendario("Pordenone"),
        DESCRIZIONE.format(elenco="nazionali, Pasqua, Pasquetta e patrono di Pordenone"),
    )


def test_definizione_senza_citta():
    _controlla_definizione(
        definizione_calendario(None),
        DESCRIZIONE.format(elenco="nazionali, Pasqua e Pasquetta"),
    )


def test_differenza_dicembre(fest):
    assert differenza(date(2026, 12, 1), date(2026, 12, 31), fest) == (
        "dal 2026-12-01 (martedì) al 2026-12-31 (giovedì): 30 giorni di calendario, 20 lavorativi; "
        "festività nell'intervallo: 2026-12-08 Immacolata Concezione, 2026-12-25 Natale, "
        "2026-12-26 Santo Stefano"
    )


def test_differenza_da_fine_novembre(fest):
    r = differenza(date(2026, 11, 30), date(2026, 12, 31), fest)
    assert "31 giorni di calendario, 21 lavorativi" in r


def test_differenza_negativa(fest):
    assert differenza(date(2026, 12, 31), date(2026, 12, 1), fest) == (
        "dal 2026-12-31 (giovedì) al 2026-12-01 (martedì): -30 giorni di calendario, "
        "-20 lavorativi; festività nell'intervallo: 2026-12-08 Immacolata Concezione, "
        "2026-12-25 Natale, 2026-12-26 Santo Stefano"
    )


def test_differenza_date_uguali(fest):
    r = differenza(date(2026, 12, 1), date(2026, 12, 1), fest)
    assert r.endswith("0 giorni di calendario, 0 lavorativi; nessuna festività nell'intervallo")


def test_differenza_molte_festivita(fest):
    r = differenza(date(2026, 1, 1), date(2027, 12, 31), fest)
    assert r.endswith("; 23 festività nell'intervallo")
    r = differenza(date(2026, 12, 31), date(2027, 12, 31), fest)
    voci = r.split("festività nell'intervallo: ")[1].split(", 2")
    assert len(voci) == 12


@pytest.mark.parametrize(
    "inizio, giorni, lav, atteso",
    [
        (date(2026, 12, 18), 10, True,
         "2026-12-18 (venerdì) + 10 giorni lavorativi = 2027-01-05 (martedì)"),
        (date(2026, 12, 18), -1, False, "2026-12-18 (venerdì) - 1 giorno = 2026-12-17 (giovedì)"),
        (date(2026, 12, 18), 0, False, "2026-12-18 (venerdì) + 0 giorni = 2026-12-18 (venerdì)"),
        (date(2026, 12, 18), 1, True,
         "2026-12-18 (venerdì) + 1 giorno lavorativo = 2026-12-21 (lunedì)"),
        (date(2027, 1, 5), -10, True,
         "2027-01-05 (martedì) - 10 giorni lavorativi = 2026-12-18 (venerdì)"),
    ],
)
def test_aggiungi(fest, inizio, giorni, lav, atteso):
    assert aggiungi(inizio, giorni, lav, fest) == atteso


@pytest.mark.parametrize(
    "inizio", [date(2026, 1, 1), date(2026, 4, 3), date(2026, 12, 24), date(2027, 2, 27)]
)
@pytest.mark.parametrize("n", [-40, -7, -1, 1, 7, 40])
def test_coerenza(fest, inizio, n):
    r = aggiungi(inizio, n, True, fest)
    arrivo = date.fromisoformat(re.search(r"= (\d{4}-\d{2}-\d{2})", r).group(1))
    assert f", {n} lavorativi;" in differenza(inizio, arrivo, fest)


def test_limiti(fest):
    lungo = "Errore: intervallo troppo lungo per contare i giorni lavorativi (massimo 100 anni)."
    fuori = "Errore: la data risultante è fuori dagli anni 1583-9999."
    assert differenza(date(1900, 1, 1), date(2000, 1, 3), fest) == lungo
    assert aggiungi(date(2026, 1, 1), 25001, True, fest) == lungo
    assert aggiungi(date(9999, 12, 31), 1, False, fest) == fuori
    assert aggiungi(date(1583, 1, 1), -1, False, fest) == fuori
    assert aggiungi(date(9999, 12, 31), 1, True, fest) == fuori
    assert aggiungi(date(1583, 1, 3), -10, True, fest) == fuori


ERR_OP = "Errore: operazione non valida: '{}'. Usare 'differenza' oppure 'aggiungi'."
ERR_DATA = "Errore: l'argomento 'data' (AAAA-MM-GG) è obbligatorio."
ERR_FINE = "Errore: l'operazione 'differenza' richiede 'data_fine' (AAAA-MM-GG)."
ERR_GIORNI = "Errore: l'operazione 'aggiungi' richiede 'giorni' (numero intero)."
ERR_INT = "Errore: 'giorni' deve essere un numero intero: '{}'."
ERR_LAV = "Errore: 'lavorativi' deve essere true o false: '{}'."


def _agg(**extra):
    return {"operazione": "aggiungi", "data": "2026-01-01", **extra}


@pytest.mark.parametrize(
    "args, atteso",
    [
        ({}, ERR_OP.format("None")),
        ({"operazione": "somma", "data": "2026-01-01"}, ERR_OP.format("somma")),
        ({"operazione": "aggiungi", "giorni": 1}, ERR_DATA),
        ({"operazione": "aggiungi", "giorni": 1, "data": None}, ERR_DATA),
        ({"operazione": "differenza", "data": "2026-01-01"}, ERR_FINE),
        (_agg(), ERR_GIORNI),
        (_agg(giorni=10.5), ERR_INT.format("10.5")),
        (_agg(giorni="dieci"), ERR_INT.format("dieci")),
        (_agg(giorni="10.0"), ERR_INT.format("10.0")),
        (_agg(giorni=True), ERR_INT.format("True")),
        (_agg(giorni="١٠"), ERR_INT.format("١٠")),
        (_agg(giorni=1, lavorativi="si"), ERR_LAV.format("si")),
        (_agg(giorni=1, lavorativi=1), ERR_LAV.format("1")),
        (_agg(giorni=1, lavorativi="vero"), ERR_LAV.format("vero")),
    ],
)
def test_esegui_errori(fest, args, atteso):
    assert esegui_calendario(args, fest) == atteso


ERR_DATA_NV = (
    "Errore: data non valida: '{}'. Usare il formato AAAA-MM-GG con un anno fra 1583 e 9999; "
    "per la data di oggi chiamare prima ora_corrente."
)
DATE_NV = [
    "2026-2-5", "05/02/2026", "2026-02-30", "oggi", "1582-12-31", "2027-02-29",
    "2026-12-18T00:00:00", "2026-12-18 10:00", "20261218", "２０２６-12-01", "٢٠٢٦-12-01", 5,
]


@pytest.mark.parametrize("valore", DATE_NV)
def test_date_non_valide(fest, valore):
    atteso = ERR_DATA_NV.format(valore)
    assert esegui_calendario(
        {"operazione": "aggiungi", "data": valore, "giorni": 1}, fest
    ) == atteso
    assert esegui_calendario(
        {"operazione": "differenza", "data": "2026-01-01", "data_fine": valore}, fest
    ) == atteso


def test_argomenti_tolleranti(fest):
    base = esegui_calendario(
        {"operazione": "differenza", "data": "2026-12-01", "data_fine": "2026-12-31"}, fest
    )
    assert base.startswith("dal 2026-12-01")
    assert esegui_calendario(
        {"operazione": " Differenza ", "data": " 2026-12-01 ", "data_fine": "2026-12-31"}, fest
    ) == base
    attesa = "2026-12-18 (venerdì) + 10 giorni = 2026-12-28 (lunedì)"
    for g in (10, 10.0, "10"):
        r = esegui_calendario({"operazione": "aggiungi", "data": "2026-12-18", "giorni": g}, fest)
        assert r == attesa
    r = esegui_calendario({"operazione": "aggiungi", "data": "2026-12-18", "giorni": "-5"}, fest)
    assert r == "2026-12-18 (venerdì) - 5 giorni = 2026-12-13 (domenica)"
    r = esegui_calendario({"operazione": "aggiungi", "data": "2026-12-18", "giorni": "+3"}, fest)
    assert r == "2026-12-18 (venerdì) + 3 giorni = 2026-12-21 (lunedì)"
    for lav, lavorativi in (("TRUE", True), ("false", False), (None, False)):
        r = esegui_calendario(
            {"operazione": "aggiungi", "data": "2026-12-18", "giorni": 2, "lavorativi": lav}, fest
        )
        assert (" lavorativi = " in r) == lavorativi
    r = esegui_calendario({"operazione": "aggiungi", "data": "2028-02-28", "giorni": 1}, fest)
    assert r == "2028-02-28 (lunedì) + 1 giorno = 2028-02-29 (martedì)"


def test_argomenti_estranei_ignorati(fest):
    normale = esegui_calendario(
        {"operazione": "differenza", "data": "2026-12-01", "data_fine": "2026-12-31"}, fest
    )
    assert esegui_calendario(
        {"operazione": "differenza", "data": "2026-12-01", "data_fine": "2026-12-31",
         "giorni": "x", "lavorativi": "x"}, fest
    ) == normale
    normale = esegui_calendario({"operazione": "aggiungi", "data": "2026-12-18", "giorni": 3}, fest)
    assert esegui_calendario(
        {"operazione": "aggiungi", "data": "2026-12-18", "giorni": 3, "data_fine": "x"}, fest
    ) == normale


def test_giorni_enormi(fest):
    fuori = "Errore: la data risultante è fuori dagli anni 1583-9999."
    for g in ("999999999999", 10**20):
        assert esegui_calendario(_agg(giorni=g), fest) == fuori
    r = esegui_calendario(_agg(giorni="9" * 5000), fest)
    assert "deve essere un numero intero" in r or "fuori" in r
