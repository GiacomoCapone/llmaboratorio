from datetime import datetime, timezone

from assistente.strumenti import crea_strumenti

ADESSO = lambda: datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)  # noqa: E731


def test_registro_contiene_orologio():
    assert list(crea_strumenti(ADESSO, "Europe/Rome")) == ["ora_corrente"]


def test_nome_coincide_con_definizione():
    for chiave, strumento in crea_strumenti(ADESSO, "Europe/Rome").items():
        assert chiave == strumento.nome == strumento.definizione["function"]["name"]


def test_registro_usa_il_fuso_predefinito():
    registro = crea_strumenti(ADESSO, "Asia/Tokyo")
    assert registro["ora_corrente"].esegui({}) == "2026-01-15T21:00:00+09:00"
