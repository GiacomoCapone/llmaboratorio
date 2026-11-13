"""Servizio del front-end: file statici e proxy verso un back-end finto (httpx.MockTransport)."""

import asyncio
import json

import httpx
import pytest
from starlette.testclient import TestClient

from frontend.app import STATICO, crea_app

JSON_UTF8 = "application/json; charset=utf-8"


class BackendFinto:
    """Registra le richieste ricevute e risponde con `risposta` (o solleva `errore`)."""

    def __init__(self, risposta: httpx.Response | None = None, errore: Exception | None = None):
        self.richieste: list[httpx.Request] = []
        self.risposta = risposta or httpx.Response(200, json={})
        self.errore = errore

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.richieste.append(request)
        if self.errore is not None:
            raise self.errore
        return self.risposta


def _client(backend: BackendFinto, timeout: float = 960.0) -> TestClient:
    app = crea_app("http://backend:8001", timeout, transport=httpx.MockTransport(backend))
    return TestClient(app)


def _risposta_json(codice: int, corpo) -> httpx.Response:
    return httpx.Response(
        codice,
        content=json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
        headers={"content-type": JSON_UTF8},
    )


@pytest.mark.parametrize(
    ("percorso", "file", "tipo"),
    [
        ("/", "index.html", "text/html; charset=utf-8"),
        ("/app.js", "app.js", "text/javascript; charset=utf-8"),
        ("/stile.css", "stile.css", "text/css; charset=utf-8"),
    ],
)
def test_pagina(percorso, file, tipo):
    with _client(BackendFinto()) as client:
        risposta = client.get(percorso)
    assert risposta.status_code == 200
    assert risposta.headers["content-type"] == tipo
    assert risposta.content == (STATICO / file).read_bytes()
    # Dopo un aggiornamento della pagina il browser deve riconvalidare, non usare la copia vecchia.
    assert risposta.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize(
    "percorso",
    ["/config.py", "/app.py", "/statico/index.html", "/index.html.bak", "/..%2fconfig.py", "/favicon.ico"],
)
def test_altri_percorsi_404(percorso):
    backend = BackendFinto()
    with _client(backend) as client:
        assert client.get(percorso).status_code == 404
    assert backend.richieste == []


def test_inoltro_get_con_query():
    backend = BackendFinto(_risposta_json(200, {"conversazioni": []}))
    with _client(backend) as client:
        risposta = client.get("/api/conversazioni?a=1&b=%C3%A8")
    (richiesta,) = backend.richieste
    assert richiesta.method == "GET"
    assert richiesta.url.path == "/conversazioni"
    assert richiesta.url.query == b"a=1&b=%C3%A8"
    assert risposta.status_code == 200
    assert risposta.headers["content-type"] == JSON_UTF8
    assert risposta.json() == {"conversazioni": []}


def test_inoltro_post_con_corpo():
    corpo = json.dumps({"domanda": "perché costa 5 € 🙂?"}, ensure_ascii=False).encode("utf-8")
    uscita = {"risposta": "è così 🙂", "messaggi": []}
    backend = BackendFinto(_risposta_json(200, uscita))
    with _client(backend) as client:
        risposta = client.post(
            "/api/conversazioni/7/messaggi", content=corpo, headers={"content-type": "application/json"}
        )
    (richiesta,) = backend.richieste
    assert richiesta.method == "POST"
    assert richiesta.url.path == "/conversazioni/7/messaggi"
    assert richiesta.content == corpo
    assert richiesta.headers["content-type"] == "application/json"
    assert risposta.content == json.dumps(uscita, ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize(
    ("codice", "corpo"),
    [
        (201, {"id": 1, "titolo": "Nuova conversazione"}),
        (400, {"errore": "corpo della richiesta non valido: atteso un oggetto JSON."}),
        (404, {"errore": "conversazione 9 inesistente."}),
        (409, {"errore": "turno in corso per la conversazione 9."}),
        (422, {"errore": "domanda fuori ambito"}),
        (500, {"errore": "errore del database: rifiutata"}),
        (502, {"errore": "agente non disponibile: rifiutata"}),
    ],
)
def test_codici_invariati(codice, corpo):
    backend = BackendFinto(_risposta_json(codice, corpo))
    with _client(backend) as client:
        risposta = client.post("/api/conversazioni")
    assert risposta.status_code == codice
    assert risposta.headers["content-type"] == JSON_UTF8
    assert risposta.json() == corpo


def test_204_senza_corpo():
    backend = BackendFinto(httpx.Response(204))
    with _client(backend) as client:
        risposta = client.delete("/api/conversazioni/3")
    assert backend.richieste[0].method == "DELETE"
    assert risposta.status_code == 204
    assert risposta.content == b""


def test_risposta_non_json():
    backend = BackendFinto(
        httpx.Response(500, content=b"Internal Server Error", headers={"content-type": "text/plain; charset=utf-8"})
    )
    with _client(backend) as client:
        risposta = client.get("/api/conversazioni")
    assert risposta.status_code == 500
    assert risposta.headers["content-type"] == "text/plain; charset=utf-8"
    assert risposta.content == b"Internal Server Error"


def test_metodo_non_ammesso():
    backend = BackendFinto()
    with _client(backend) as client:
        assert client.put("/api/conversazioni/1").status_code == 405
    assert backend.richieste == []


def test_backend_irraggiungibile():
    backend = BackendFinto(errore=httpx.ConnectError("connessione rifiutata"))
    with _client(backend) as client:
        risposta = client.get("/api/conversazioni")
    assert risposta.status_code == 502
    assert risposta.headers["content-type"] == JSON_UTF8
    assert risposta.json() == {"errore": "back-end non disponibile: connessione rifiutata"}


def test_backend_irraggiungibile_senza_messaggio():
    backend = BackendFinto(errore=httpx.ConnectError(""))
    with _client(backend) as client:
        risposta = client.get("/api/conversazioni")
    assert risposta.json() == {"errore": "back-end non disponibile: ConnectError"}


def test_tempo_scaduto():
    backend = BackendFinto(errore=httpx.ReadTimeout("x"))
    with _client(backend, timeout=960) as client:
        risposta = client.post("/api/conversazioni/1/messaggi", json={"domanda": "ciao"})
    assert risposta.status_code == 502
    assert risposta.json() == {"errore": "back-end non disponibile: tempo scaduto dopo 960 s"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_turno_lungo_non_blocca():
    sblocca = asyncio.Event()

    async def gestore(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            await sblocca.wait()
            return httpx.Response(200, json={"risposta": "ok", "messaggi": []})
        return httpx.Response(200, json={"conversazioni": []})

    app = crea_app("http://backend:8001", 960, transport=httpx.MockTransport(gestore))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://frontend"
        ) as client:
            turno = asyncio.create_task(
                client.post("/api/conversazioni/1/messaggi", json={"domanda": "lunga"})
            )
            await asyncio.sleep(0.05)
            elenco = await asyncio.wait_for(client.get("/api/conversazioni"), timeout=2)
            assert elenco.status_code == 200
            assert not turno.done()
            sblocca.set()
            assert (await asyncio.wait_for(turno, timeout=2)).status_code == 200
