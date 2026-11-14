"""compose.yaml: i 4 servizi dell'applicazione, profilo della CLI, porte locali e controlli di salute (senza Docker)."""

import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

COMPOSE = Path(__file__).parents[1] / "compose.yaml"

URL_SALUTE = {
    "agente": "http://127.0.0.1:8000/salute",
    "backend": "http://127.0.0.1:8001/salute",
    "frontend": "http://127.0.0.1:8002/",
}


@pytest.fixture(scope="module")
def servizi() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def test_servizi(servizi):
    assert set(servizi) == {"assistente", "agente", "backend", "postgres", "frontend"}
    senza_profilo = {nome for nome, servizio in servizi.items() if "profiles" not in servizio}
    assert senza_profilo == {"postgres", "agente", "backend", "frontend"}
    assert servizi["assistente"]["profiles"] == ["cli"]


def test_porte_solo_locali(servizi):
    for nome, servizio in servizi.items():
        for porta in servizio.get("ports", []):
            assert porta.startswith("127.0.0.1:"), (nome, porta)
    assert servizi["agente"]["ports"] == ["127.0.0.1:8000:8000"]
    assert servizi["backend"]["ports"] == ["127.0.0.1:8001:8001"]
    assert servizi["postgres"]["ports"] == ["127.0.0.1:5433:5432"]
    assert servizi["frontend"]["ports"] == ["127.0.0.1:8002:8002"]


def test_frontend(servizi):
    frontend = servizi["frontend"]
    assert frontend["build"] == "."
    assert frontend["command"] == ["python", "-m", "frontend"]
    assert frontend["env_file"] == ".env"
    # environment prevale sul valore locale dell'.env (http://127.0.0.1:8001)
    assert frontend["environment"]["BACKEND_URL"] == "http://backend:8001"
    assert frontend["environment"]["FRONTEND_HOST"] == "0.0.0.0"


def test_dipendenze(servizi):
    assert servizi["backend"]["depends_on"] == {
        "postgres": {"condition": "service_healthy"},
        "agente": {"condition": "service_healthy"},
    }
    assert servizi["frontend"]["depends_on"] == {"backend": {"condition": "service_healthy"}}


@pytest.mark.parametrize(
    ("nome", "variabile", "porta"),
    [("agente", "HTTP_PORTA", "8000"), ("backend", "BACKEND_PORTA", "8001"), ("frontend", "FRONTEND_PORTA", "8002")],
)
def test_porta_interna_fissata(servizi, nome, variabile, porta):
    """Una porta diversa nel .env non deve spostare il servizio: mappatura, URL e controllo di salute la presumono."""
    assert servizi[nome]["environment"][variabile] == porta


@pytest.mark.parametrize(("nome", "url"), URL_SALUTE.items())
def test_controlli_di_salute(servizi, nome, url):
    controllo = servizi[nome]["healthcheck"]
    assert controllo["test"][:3] == ["CMD", "python", "-c"]
    assert len(controllo["test"]) == 4
    assert f"'{url}'" in controllo["test"][3]
    assert controllo["interval"] == "5s"
    assert controllo["timeout"] == "5s"
    assert controllo["retries"] == 10
    assert controllo["start_period"] == "10s"


def _server(codice: int) -> ThreadingHTTPServer:
    class Gestore(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(codice)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Gestore)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _porta_chiusa() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize(("risposta", "riesce"), [(200, True), (500, False), (None, False)])
def test_comando_di_salute_reale(servizi, risposta, riesce):
    """Il comando di salute vero esce con 0 solo se il servizio risponde 2xx: altrimenti service_healthy non attende."""
    codice = servizi["agente"]["healthcheck"]["test"][3]
    assert "127.0.0.1:8000" in codice
    server = _server(risposta) if risposta is not None else None
    porta = server.server_address[1] if server else _porta_chiusa()
    try:
        esito = subprocess.run(
            [sys.executable, "-c", codice.replace("127.0.0.1:8000", f"127.0.0.1:{porta}")],
            capture_output=True,
            timeout=10,
        )
    finally:
        if server:
            server.shutdown()
            server.server_close()
    assert (esito.returncode == 0) is riesce, esito.stderr
