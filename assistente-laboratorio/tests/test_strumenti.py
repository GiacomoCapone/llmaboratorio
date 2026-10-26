from datetime import datetime, timezone

import pytest

from assistente.strumenti import (
    DEFINIZIONE_ORA_CORRENTE,
    NOME_ORA_CORRENTE,
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


def test_definizione_dichiara_fuso_obbligatorio():
    funzione = DEFINIZIONE_ORA_CORRENTE["function"]
    assert DEFINIZIONE_ORA_CORRENTE["type"] == "function"
    assert funzione["name"] == NOME_ORA_CORRENTE == "ora_corrente"
    assert funzione["parameters"]["required"] == ["fuso"]
