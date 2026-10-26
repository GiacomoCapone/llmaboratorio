import httpx
import pytest

from assistente.config import Config
from assistente.modello import ErroreModello, crea_llm, elenca_modelli, verifica_modello

URL = "http://localhost:1234/v1"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _config(model="a"):
    return Config(URL, model, 5, "INFO")


def test_elenca_modelli():
    def handler(request):
        assert str(request.url) == f"{URL}/models"
        return httpx.Response(200, json={"data": [{"id": "a"}, {"id": "b"}]})

    assert elenca_modelli(URL, _client(handler)) == ["a", "b"]


def test_server_non_raggiungibile():
    def handler(request):
        raise httpx.ConnectError("rifiutata", request=request)

    with pytest.raises(ErroreModello) as exc:
        elenca_modelli(URL, _client(handler))
    assert URL in str(exc.value)


def test_risposta_non_valida():
    with pytest.raises(ErroreModello):
        elenca_modelli(URL, _client(lambda r: httpx.Response(500)))
    with pytest.raises(ErroreModello):
        elenca_modelli(URL, _client(lambda r: httpx.Response(200, text="non json")))
    with pytest.raises(ErroreModello):
        elenca_modelli(URL, _client(lambda r: httpx.Response(200, json={"x": 1})))


def test_verifica_modello_presente():
    verifica_modello(_config("a"), lambda url: ["a", "b"])


def test_verifica_modello_assente():
    with pytest.raises(ErroreModello) as exc:
        verifica_modello(_config("z"), lambda url: ["a", "b"])
    assert "a" in str(exc.value) and "b" in str(exc.value)


def test_crea_llm_usa_configurazione():
    llm = crea_llm(_config("a"))
    assert llm.model_name == "a"
    assert str(llm.openai_api_base).rstrip("/") == URL
