"""Avvio del front-end: uvicorn, argomenti, errori di configurazione, Ctrl-C."""

import logging

import pytest
from starlette.testclient import TestClient

from frontend import __main__ as avvio
from frontend.config import ConfigFrontend


@pytest.mark.parametrize(
    ("livello", "atteso"), [("DEBUG", logging.DEBUG), ("INESISTENTE", logging.INFO)]
)
def test_servi_avvia_uvicorn(monkeypatch, livello, atteso):
    chiamate = {}

    def finto_run(app, **kwargs):
        chiamate.update(kwargs)
        chiamate["app"] = app

    monkeypatch.setattr(avvio.uvicorn, "run", finto_run)
    avvio.servi(ConfigFrontend(host="127.0.0.9", porta=8123, log_level=livello))
    assert chiamate["host"] == "127.0.0.9"
    assert chiamate["port"] == 8123
    assert chiamate["log_level"] == atteso
    with TestClient(chiamate["app"]) as client:
        assert client.get("/").status_code == 200


def test_main_argomenti(capsys):
    assert avvio.main(["x"]) == 2
    assert capsys.readouterr().err.strip() == "Uso: python avvia.py [--http | --backend | --frontend]"


def test_main_configurazione_non_valida(monkeypatch, capsys):
    monkeypatch.setenv("FRONTEND_PORTA", "abc")
    assert avvio.main([]) == 1
    assert capsys.readouterr().err.startswith("Errore: FRONTEND_PORTA")


def test_main_ctrl_c(monkeypatch, capsys):
    monkeypatch.setattr(avvio, "carica_config", lambda: ConfigFrontend())

    def interrompi(config):
        raise KeyboardInterrupt

    monkeypatch.setattr(avvio, "servi", interrompi)
    assert avvio.main([]) == 130
    assert "Interrotto." in capsys.readouterr().err
