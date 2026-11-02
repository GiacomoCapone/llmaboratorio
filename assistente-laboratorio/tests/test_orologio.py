from datetime import datetime, timezone

import pytest

from assistente.strumenti.orologio import (
    NOME_ORA_CORRENTE,
    definizione_ora_corrente,
    esegui_ora_corrente,
    ora_corrente,
)

ADESSO = lambda: datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)  # noqa: E731


def test_europe_rome():
    assert ora_corrente("Europe/Rome", ADESSO) == "2026-01-15T13:00:00+01:00"


def test_utc():
    assert ora_corrente("UTC", ADESSO) == "2026-01-15T12:00:00+00:00"


def test_estate_ora_legale():
    luglio = lambda: datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)  # noqa: E731
    assert ora_corrente("Europe/Rome", luglio) == "2026-07-15T14:00:00+02:00"


@pytest.mark.parametrize(
    "fuso", ["", "   ", "../etc/passwd", "Mars/Base", "Europe/Roma"]
)
def test_fuso_non_valido(fuso):
    risultato = ora_corrente(fuso, ADESSO)
    assert risultato.startswith("Errore:")
    assert fuso in risultato


def test_definizione_fuso_facoltativo():
    definizione = definizione_ora_corrente("Asia/Tokyo")
    funzione = definizione["function"]
    assert definizione["type"] == "function"
    assert funzione["name"] == NOME_ORA_CORRENTE == "ora_corrente"
    assert funzione["parameters"]["required"] == []
    assert "Asia/Tokyo" in funzione["parameters"]["properties"]["fuso"]["description"]
    assert "SEMPRE" in funzione["description"]
    assert "Non chiedere mai il fuso" in funzione["description"]


def esegui(args, fuso_predefinito="Europe/Rome"):
    return esegui_ora_corrente(args, ADESSO, fuso_predefinito)


@pytest.mark.parametrize("args", [{}, {"fuso": None}, {"fuso": ""}, {"fuso": "  "}])
def test_fuso_assente_usa_predefinito(args):
    assert esegui(args) == "2026-01-15T13:00:00+01:00"


def test_predefinito_diverso_da_roma():
    assert esegui({}, "Asia/Tokyo") == "2026-01-15T21:00:00+09:00"


def test_fuso_esplicito_ha_precedenza():
    assert esegui({"fuso": "UTC"}, "Asia/Tokyo") == "2026-01-15T12:00:00+00:00"


def test_fuso_esplicito_non_valido_non_ripiega():
    assert esegui({"fuso": "Europe/Roma"}).startswith("Errore:")


@pytest.mark.parametrize("fuso", [5, ["Europe/Rome"], {"a": 1}])
def test_argomento_fuso_non_stringa(fuso):
    assert esegui({"fuso": fuso}).startswith("Errore:")


def test_argomenti_extra_ignorati():
    assert esegui({"fuso": "UTC", "altro": 1}) == "2026-01-15T12:00:00+00:00"
