"""Avvio del back-end: preparazione del database, uvicorn, errori di avvio."""

import logging

import pytest
from starlette.testclient import TestClient

from backend import __main__ as avvio
from backend.config import ConfigBackend
from backend.deposito import ErroreDatabase


class DepositoFinto:
    eventi: list = []
    errore: Exception | None = None

    def __init__(self, url):
        self.url = url

    def prepara(self):
        DepositoFinto.eventi.append("prepara")
        if DepositoFinto.errore:
            raise DepositoFinto.errore


@pytest.fixture(autouse=True)
def deposito_finto(monkeypatch):
    DepositoFinto.eventi = []
    DepositoFinto.errore = None
    monkeypatch.setattr(avvio, "DepositoPostgres", DepositoFinto)
    return DepositoFinto


def _config(**extra):
    return ConfigBackend(database_url="postgresql://x", host="127.0.0.9", porta=8123, **extra)


@pytest.mark.parametrize(
    ("livello", "atteso"), [("DEBUG", logging.DEBUG), ("INESISTENTE", logging.INFO)]
)
def test_servi_prepara_e_avvia(monkeypatch, livello, atteso):
    chiamate = {}

    def finto_run(app, **kwargs):
        DepositoFinto.eventi.append("run")
        chiamate.update(kwargs)
        chiamate["app"] = app

    monkeypatch.setattr(avvio.uvicorn, "run", finto_run)
    avvio.servi(_config(log_level=livello))
    assert DepositoFinto.eventi == ["prepara", "run"]
    assert chiamate["host"] == "127.0.0.9"
    assert chiamate["port"] == 8123
    assert chiamate["log_level"] == atteso
    assert TestClient(chiamate["app"]).get("/salute").json() == {"stato": "ok"}


def test_main_database_non_raggiungibile(monkeypatch, capsys):
    monkeypatch.setattr(avvio, "carica_config", lambda: _config())
    DepositoFinto.errore = ErroreDatabase("rifiutata")
    assert avvio.main([]) == 1
    assert "Errore: database non raggiungibile: rifiutata" in capsys.readouterr().err


def test_main_configurazione_non_valida(monkeypatch, capsys):
    monkeypatch.setattr(avvio.config, "PERCORSO_ENV", avvio.config.PERCORSO_ENV.parent / "assente.env")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert avvio.main([]) == 1
    assert capsys.readouterr().err.startswith("Errore: ")


def test_main_argomenti(capsys):
    assert avvio.main(["x"]) == 2
    assert capsys.readouterr().err.strip() == "Uso: python avvia.py [--http | --backend | --frontend]"


def test_main_ctrl_c(monkeypatch, capsys):
    monkeypatch.setattr(avvio, "carica_config", lambda: _config())
    DepositoFinto.errore = KeyboardInterrupt()
    assert avvio.main([]) == 130
