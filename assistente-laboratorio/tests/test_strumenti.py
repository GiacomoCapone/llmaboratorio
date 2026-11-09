from datetime import datetime, timezone

import pytest

from assistente.config import ErroreConfigurazione
from assistente.strumenti import Strumento, crea_strumenti, registro
from assistente.strumenti.calcolatrice import DEFINIZIONE_CALCOLA, esegui_calcola
from assistente.strumenti.rete import ErroreRete

ADESSO = lambda: datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)  # noqa: E731


def test_registro_contiene_gli_strumenti():
    assert list(crea_strumenti(ADESSO, "Europe/Rome")) == [
        "ora_corrente",
        "calcola",
        "converti_unita",
        "calendario",
        "meteo_attuale",
    ]


def test_nome_coincide_con_definizione():
    for chiave, strumento in crea_strumenti(ADESSO, "Europe/Rome").items():
        assert chiave == strumento.nome == strumento.definizione["function"]["name"]


def test_registro_usa_il_fuso_predefinito():
    registro = crea_strumenti(ADESSO, "Asia/Tokyo")
    assert registro["ora_corrente"].esegui({}) == "2026-01-15T21:00:00+09:00"


def test_nomi_duplicati():
    doppio = [Strumento(DEFINIZIONE_CALCOLA, esegui_calcola)] * 2
    with pytest.raises(ValueError, match="nome duplicato nel registro: 'calcola'"):
        registro(doppio)


def test_registro_citta_sconosciuta():
    with pytest.raises(ErroreConfigurazione):
        crea_strumenti(ADESSO, "Europe/Rome", "Milano")


def test_registro_cita_il_patrono():
    descrizione = crea_strumenti(ADESSO, "Europe/Rome", "pordenone")["calendario"].definizione[
        "function"
    ]["description"]
    assert "patrono di Pordenone" in descrizione


def test_registro_usa_scarica_iniettata():
    chiamate = []

    def finta(url, parametri):
        chiamate.append((url, parametri))
        raise ErroreRete("prova.")

    meteo = crea_strumenti(ADESSO, "Europe/Rome", scarica=finta)["meteo_attuale"]
    assert meteo.esegui({"localita": "Pordenone"}) == "Errore: prova."
    assert len(chiamate) == 1
