import httpx
import pytest

from backend.agente import ClientAgente, ErroreAgente

CRONOLOGIA = [{"type": "human", "data": {"content": "ciao"}}]


def _client(gestore, timeout=900, richieste=None):
    def trasporto(richiesta):
        if richieste is not None:
            richieste.append(richiesta)
        return gestore(richiesta)

    return ClientAgente("http://agente", timeout, transport=httpx.MockTransport(trasporto))


def _ok(richiesta):
    return httpx.Response(200, json={"risposta": "ok", "cronologia": CRONOLOGIA})


def test_turno_con_domanda():
    richieste = []
    esito = _client(_ok, richieste=richieste).turno(CRONOLOGIA, domanda="Che ore sono?")
    assert esito == ("ok", CRONOLOGIA)
    (r,) = richieste
    assert (r.method, r.url.path) == ("POST", "/turno")
    import json

    assert json.loads(r.content) == {"domanda": "Che ore sono?", "cronologia": CRONOLOGIA}


def test_turno_con_prompt():
    import json

    richieste = []
    voce = {"nome": "scheda_articolo", "argomenti": {"codice": "A1"}}
    _client(_ok, richieste=richieste).turno([], prompt=voce)
    assert json.loads(richieste[0].content) == {"prompt": voce, "cronologia": []}


def test_prompt():
    corpo = {"prompt": [{"nome": "x", "argomenti": ["a"], "descrizione": "d"}]}
    richieste = []
    client = _client(lambda r: httpx.Response(200, json=corpo), richieste=richieste)
    assert client.prompt() == corpo
    assert (richieste[0].method, richieste[0].url.path) == ("GET", "/prompt")


@pytest.mark.parametrize("codice", [400, 422])
def test_errori_inoltrati(codice):
    client = _client(lambda r: httpx.Response(codice, json={"errore": "motivo è così"}))
    with pytest.raises(ErroreAgente) as e:
        client.turno([], domanda="x")
    assert e.value.codice == codice
    assert e.value.messaggio == "motivo è così" == str(e.value)


def _solleva(eccezione):
    def gestore(richiesta):
        raise eccezione

    return gestore


@pytest.mark.parametrize(
    "gestore, messaggio",
    [
        (
            lambda r: httpx.Response(500, json={"errore": "turno fallito: x"}),
            "agente non disponibile: turno fallito: x",
        ),
        (
            lambda r: httpx.Response(200, content=b"non json"),
            "agente non disponibile: risposta non valida",
        ),
        (
            lambda r: httpx.Response(400, json={"altro": 1}),
            "agente non disponibile: risposta non valida",
        ),
        (
            _solleva(httpx.ConnectError("connessione rifiutata")),
            "agente non disponibile: connessione rifiutata",
        ),
        (
            _solleva(httpx.InvalidURL("url malformato")),
            "agente non disponibile: url malformato",
        ),
        (
            _solleva(httpx.ReadTimeout("lento")),
            "agente non disponibile: tempo scaduto dopo 900 s",
        ),
    ],
)
def test_errori_502(gestore, messaggio):
    with pytest.raises(ErroreAgente) as e:
        _client(gestore).turno([], domanda="x")
    assert e.value.codice == 502
    assert e.value.messaggio == messaggio


def test_timeout_usato():
    richieste = []
    _client(_ok, timeout=30, richieste=richieste).turno([], domanda="x")
    assert richieste[0].extensions["timeout"] == {"connect": 30, "read": 30, "write": 30, "pool": 30}
