"""Prova reale del back-end con LM Studio e PostgreSQL: esclusa di default (marker `reale` e `postgres`).

Richiede LMSTUDIO_BASE_URL e LMSTUDIO_MODEL nell'ambiente e DATABASE_URL (database in esecuzione,
per esempio `docker compose up -d postgres`). Lanciare con:
    python -m pytest -m "reale and postgres" -v -s -k backend
L'agente gira in-process (app del servizio in un TestClient); il back-end lo raggiunge con un
ClientAgente il cui transport e' quello del TestClient. I dati stanno in uno schema temporaneo e in
un database note temporaneo.
"""

import dataclasses
import time

import httpx
import pytest
from starlette.testclient import TestClient

from assistente.avvio import apri_assistente
from assistente.config import carica_config
from assistente.modello import verifica_modello
from assistente.servizio import crea_app as crea_app_agente
from backend.agente import ClientAgente
from backend.app import crea_app
from backend.deposito import DepositoPostgres

pytestmark = [pytest.mark.reale, pytest.mark.postgres]


class TransportInProcess(httpx.BaseTransport):
    """Inoltra le richieste all'app di un TestClient e rende risposte con corpo gia' letto.

    Il transport del TestClient restituisce uno stream che un altro httpx.Client rifiuta
    (non e' un SyncByteStream): qui il corpo viene letto e reimpacchettato.
    """

    def __init__(self, app_client: TestClient):
        self._transport = app_client._transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        risposta = self._transport.handle_request(request)
        risposta.read()
        return httpx.Response(
            risposta.status_code, headers=risposta.headers, content=risposta.content, request=request
        )


@pytest.fixture
def client(tmp_path, url, schema):
    config = dataclasses.replace(carica_config(), note_db=tmp_path / "note.db")
    verifica_modello(config)
    deposito = DepositoPostgres(url, schema=schema)
    deposito.prepara()
    with apri_assistente(config) as (grafo, archivio):
        app_agente = TestClient(crea_app_agente(grafo, archivio))
        agente = ClientAgente("http://testserver", 900, transport=TransportInProcess(app_agente))
        yield TestClient(crea_app(deposito, agente))


def test_backend_due_messaggi(client):
    domanda = "Annota che il multimetro MIS-001 ha la batteria scarica"
    inizio = time.perf_counter()
    id = client.post("/conversazioni").json()["id"]

    primo = client.post(f"/conversazioni/{id}/messaggi", json={"domanda": domanda})
    assert primo.status_code == 200, primo.text
    print(f"\nmessaggio 1: {primo.json()['risposta']!r} ({time.perf_counter() - inizio:.1f} s)")

    intermedio = time.perf_counter()
    secondo = client.post(f"/conversazioni/{id}/messaggi", json={"domanda": "Quali note ci sono?"})
    assert secondo.status_code == 200, secondo.text
    risposta = secondo.json()["risposta"]
    print(f"messaggio 2: {risposta!r} ({time.perf_counter() - intermedio:.1f} s)")
    assert "batteria" in risposta.lower(), risposta

    dettaglio = client.get(f"/conversazioni/{id}")
    assert dettaglio.status_code == 200, dettaglio.text
    corpo = dettaglio.json()
    print("ruoli:", [m["ruolo"] for m in corpo["messaggi"]], "titolo:", corpo["titolo"])
    assert len(corpo["messaggi"]) == 4
    assert corpo["titolo"] == domanda
