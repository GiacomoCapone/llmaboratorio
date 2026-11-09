"""Test del modulo di rete: nessuna connessione reale, urlopen è sostituito."""

import http.client
import logging
import urllib.error

import pytest

from assistente.strumenti import rete
from assistente.strumenti.rete import ErroreRete, scarica_json

URL = "https://x.test/v1/search"
MSG_TIMEOUT = "il servizio meteo non ha risposto entro 5 secondi."
MSG_NON_VALIDA = "risposta del servizio meteo non valida."


class RispostaFinta:
    """Risposta HTTP minima: context manager con read()."""

    def __init__(self, corpo=b"{}", errore_lettura=None):
        self._corpo = corpo
        self._errore_lettura = errore_lettura

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        if self._errore_lettura is not None:
            raise self._errore_lettura
        return self._corpo


@pytest.fixture
def urlopen_finto(monkeypatch):
    """Installa un urlopen finto; restituisce la lista delle chiamate (richiesta, timeout)."""
    chiamate = []

    def installa(risposta=None, eccezione=None):
        def finto(richiesta, timeout=None):
            chiamate.append((richiesta, timeout))
            if eccezione is not None:
                raise eccezione
            return risposta

        monkeypatch.setattr(rete.urllib.request, "urlopen", finto)
        return chiamate

    return installa


def test_url_parametri_e_intestazioni(urlopen_finto):
    chiamate = urlopen_finto(RispostaFinta())
    scarica_json(URL, {"name": "Forlì", "count": 1})
    richiesta, timeout = chiamate[0]
    assert richiesta.full_url == "https://x.test/v1/search?name=Forl%C3%AC&count=1"
    assert richiesta.get_header("User-agent") == "assistente-laboratorio"
    assert timeout == 5
    assert richiesta.get_method() == "GET"


def test_restituisce_il_json(urlopen_finto):
    urlopen_finto(RispostaFinta(b'{"a": 1}'))
    assert scarica_json(URL, {}) == {"a": 1}


def test_stato_http(urlopen_finto):
    urlopen_finto(eccezione=urllib.error.HTTPError(URL, 503, "x", {}, None))
    with pytest.raises(ErroreRete) as info:
        scarica_json(URL, {})
    assert str(info.value) == "il servizio meteo ha risposto con stato 503."


def test_timeout_in_apertura(urlopen_finto):
    urlopen_finto(eccezione=TimeoutError())
    with pytest.raises(ErroreRete) as info:
        scarica_json(URL, {})
    assert str(info.value) == MSG_TIMEOUT


def test_timeout_come_motivo(urlopen_finto):
    urlopen_finto(eccezione=urllib.error.URLError(TimeoutError()))
    with pytest.raises(ErroreRete) as info:
        scarica_json(URL, {})
    assert str(info.value) == MSG_TIMEOUT


def test_timeout_in_lettura(urlopen_finto):
    urlopen_finto(RispostaFinta(errore_lettura=TimeoutError()))
    with pytest.raises(ErroreRete) as info:
        scarica_json(URL, {})
    assert str(info.value) == MSG_TIMEOUT


def test_non_raggiungibile(urlopen_finto):
    urlopen_finto(eccezione=urllib.error.URLError("getaddrinfo failed"))
    with pytest.raises(ErroreRete) as info:
        scarica_json(URL, {})
    assert str(info.value) == "servizio meteo non raggiungibile (getaddrinfo failed)."


@pytest.mark.parametrize("corpo", [b"non json", b"", b"[1]", b"\xff"])
def test_risposta_non_valida(urlopen_finto, corpo):
    urlopen_finto(RispostaFinta(corpo))
    with pytest.raises(ErroreRete) as info:
        scarica_json(URL, {})
    assert str(info.value) == MSG_NON_VALIDA


def test_guasto_registrato(urlopen_finto, caplog):
    urlopen_finto(eccezione=urllib.error.HTTPError(URL, 503, "x", {}, None))
    with caplog.at_level(logging.WARNING, logger="assistente.strumenti.rete"):
        with pytest.raises(ErroreRete):
            scarica_json(URL, {"name": "Forlì"})
    record = [r for r in caplog.records if r.name == "assistente.strumenti.rete"]
    assert len(record) == 1 and record[0].levelno == logging.WARNING
    testo = record[0].getMessage()
    assert URL in testo
    assert "Forl" not in testo


def test_lettura_troncata(urlopen_finto):
    urlopen_finto(RispostaFinta(errore_lettura=http.client.IncompleteRead(b"")))
    with pytest.raises(ErroreRete) as info:
        scarica_json(URL, {})
    assert str(info.value) == MSG_NON_VALIDA


def test_riga_di_stato_malformata(urlopen_finto, caplog):
    urlopen_finto(eccezione=http.client.BadStatusLine("x"))
    with caplog.at_level(logging.WARNING, logger="assistente.strumenti.rete"):
        with pytest.raises(ErroreRete) as info:
            scarica_json(URL, {})
    assert str(info.value) == MSG_NON_VALIDA
    assert any(r.levelno == logging.WARNING for r in caplog.records)
