"""Rotte del back-end, con deposito in memoria e agente finto (nessun database, nessun modello)."""

import json
import threading

import httpx
import pytest
from finti_backend import DepositoMemoria
from starlette.testclient import TestClient

from backend.agente import ClientAgente
from backend import app as modulo_app
from backend.app import crea_app
from backend.deposito import ErroreDatabase

ATTESA = 10


class AgenteFinto:
    """Trasporto httpx finto: registra i corpi dei turni e risponde in modo prevedibile."""

    def __init__(self, gestore=None):
        self.turni: list[dict] = []
        self.richieste: list[httpx.Request] = []
        self._gestore = gestore

    def __call__(self, richiesta: httpx.Request) -> httpx.Response:
        self.richieste.append(richiesta)
        if self._gestore is not None:
            esito = self._gestore(richiesta)
            if esito is not None:
                return esito
        if richiesta.url.path == "/prompt":
            return httpx.Response(200, json={"prompt": [{"nome": "scheda_articolo"}], "extra": 1})
        corpo = json.loads(richiesta.content)
        self.turni.append(corpo)
        nuova = corpo["cronologia"] + [{"n": len(corpo["cronologia"])}, {"n": len(corpo["cronologia"]) + 1}]
        testo = corpo.get("domanda") or "prompt"
        return httpx.Response(200, json={"risposta": f"risposta a {testo}", "cronologia": nuova})


def _app(agente=None, deposito=None):
    agente = agente or AgenteFinto()
    deposito = deposito or DepositoMemoria()
    app = crea_app(deposito, ClientAgente("http://agente", 5, transport=httpx.MockTransport(agente)))
    return TestClient(app), agente, deposito


def _nuova(client) -> int:
    return client.post("/conversazioni").json()["id"]


def test_testo_visibile():
    assert modulo_app.testo_visibile("ciao", None) == "ciao"
    assert modulo_app.testo_visibile(None, {"nome": "a", "argomenti": {"x": "1", "y": 2}}) == "/a 1 2"
    assert modulo_app.testo_visibile(None, {"nome": "a", "argomenti": {}}) == "/a"


def test_salute():
    client, _, _ = _app()
    r = client.get("/salute")
    assert (r.status_code, r.json()) == (200, {"stato": "ok"})


def test_charset():
    client, _, _ = _app()
    cid = _nuova(client)
    risposte = [
        client.get("/salute"),
        client.get("/conversazioni"),
        client.get("/conversazioni/999"),
    ]
    with_409 = _risposta_409()
    risposte.append(with_409)
    for r in risposte:
        assert r.headers["content-type"] == "application/json; charset=utf-8"
    assert (risposte[2].status_code, risposte[3].status_code) == (404, 409)
    assert cid == 1


def _risposta_409():
    sblocca, avviato = threading.Event(), threading.Event()

    def gestore(richiesta):
        avviato.set()
        sblocca.wait(ATTESA)

    client, _, _ = _app(AgenteFinto(gestore))
    cid = _nuova(client)
    primo = threading.Thread(
        target=lambda: client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": "a"})
    )
    primo.start()
    try:
        assert avviato.wait(ATTESA)
        return client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": "b"})
    finally:
        sblocca.set()
        primo.join(ATTESA)


def test_prompt_inoltrato():
    client, agente, _ = _app()
    r = client.get("/prompt")
    assert (r.status_code, r.json()) == (200, {"prompt": [{"nome": "scheda_articolo"}], "extra": 1})
    assert agente.richieste[0].url.path == "/prompt"


def test_prompt_agente_giu():
    def rete(richiesta):
        raise httpx.ConnectError("rifiutata")

    app = crea_app(DepositoMemoria(), ClientAgente("http://agente", 5, transport=httpx.MockTransport(rete)))
    r = TestClient(app).get("/prompt")
    assert r.status_code == 502
    assert r.json()["errore"].startswith("agente non disponibile: ")


def test_crea_elenca_leggi_elimina():
    client, _, _ = _app()
    r = client.post("/conversazioni")
    assert r.status_code == 201
    primo = r.json()
    assert primo["titolo"] == "Nuova conversazione"
    assert set(primo) == {"id", "titolo", "creata", "aggiornata"}
    for campo in ("creata", "aggiornata"):
        assert "T" in primo[campo]
    secondo = client.post("/conversazioni").json()

    elenco = client.get("/conversazioni").json()["conversazioni"]
    assert [c["id"] for c in elenco] == [secondo["id"], primo["id"]]

    dettaglio = client.get(f"/conversazioni/{primo['id']}")
    assert dettaglio.status_code == 200
    assert dettaglio.json() == {**primo, "messaggi": []}

    eliminata = client.delete(f"/conversazioni/{primo['id']}")
    assert (eliminata.status_code, eliminata.content) == (204, b"")
    assert client.get(f"/conversazioni/{primo['id']}").status_code == 404


def test_elenco_per_aggiornata():
    client, _, _ = _app()
    a, b = _nuova(client), _nuova(client)
    client.post(f"/conversazioni/{a}/messaggi", json={"domanda": "x"})
    assert [c["id"] for c in client.get("/conversazioni").json()["conversazioni"]] == [a, b]


@pytest.mark.parametrize("id", ["abc", "999"])
def test_id_non_valido_o_inesistente(id):
    client, agente, _ = _app()
    atteso = {"errore": f"conversazione {id} inesistente."}
    for r in (
        client.get(f"/conversazioni/{id}"),
        client.delete(f"/conversazioni/{id}"),
        client.post(f"/conversazioni/{id}/messaggi", json={"domanda": "x"}),
    ):
        assert (r.status_code, r.json()) == (404, atteso)
    assert agente.turni == []


def test_messaggio_con_domanda():
    client, agente, _ = _app()
    cid = _nuova(client)
    r = client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": "  Che ore sono?  "})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["risposta"] == "risposta a   Che ore sono?  "
    assert [(m["ruolo"], m["testo"]) for m in corpo["messaggi"]] == [
        ("utente", "  Che ore sono?  "),
        ("assistente", corpo["risposta"]),
    ]
    assert all(m["ora"] for m in corpo["messaggi"])
    assert agente.turni[0] == {"domanda": "  Che ore sono?  ", "cronologia": []}

    r2 = client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": "e poi?"})
    assert r2.status_code == 200
    assert agente.turni[1]["cronologia"] == [{"n": 0}, {"n": 1}]

    dettaglio = client.get(f"/conversazioni/{cid}").json()
    assert len(dettaglio["messaggi"]) == 4
    assert dettaglio["titolo"] == "Che ore sono?"


def test_messaggio_con_prompt():
    client, agente, _ = _app()
    cid = _nuova(client)
    prompt = {"nome": "scheda_articolo", "argomenti": {"codice": "MIS-001"}}
    r = client.post(f"/conversazioni/{cid}/messaggi", json={"prompt": prompt})
    assert r.status_code == 200
    assert agente.turni[0] == {"prompt": prompt, "cronologia": []}
    assert r.json()["messaggi"][0]["testo"] == "/scheda_articolo MIS-001"
    assert client.get(f"/conversazioni/{cid}").json()["titolo"] == "/scheda_articolo MIS-001"

    senza = client.post(
        f"/conversazioni/{cid}/messaggi", json={"prompt": {"nome": "elenco", "argomenti": {}}}
    )
    assert senza.json()["messaggi"][0]["testo"] == "/elenco"


CORPI_NON_VALIDI = [
    (b"[]", "corpo della richiesta non valido: atteso un oggetto JSON."),
    (b'"x"', "corpo della richiesta non valido: atteso un oggetto JSON."),
    (b"non json", "corpo della richiesta non valido: atteso un oggetto JSON."),
    (b"{}", "indicare esattamente uno fra 'domanda' e 'prompt'."),
    (
        b'{"domanda": "a", "prompt": {"nome": "a", "argomenti": {}}}',
        "indicare esattamente uno fra 'domanda' e 'prompt'.",
    ),
    (b'{"domanda": 5}', "'domanda' deve essere un testo non vuoto."),
    (b'{"prompt": "x"}', "'prompt' non valido: atteso un oggetto con 'nome' e 'argomenti'."),
    (
        b'{"prompt": {"nome": 1, "argomenti": {}}}',
        "'prompt' non valido: atteso un oggetto con 'nome' e 'argomenti'.",
    ),
    (b'{"prompt": {"nome": "a"}}', "'prompt' non valido: atteso un oggetto con 'nome' e 'argomenti'."),
]


@pytest.mark.parametrize("corpo, messaggio", CORPI_NON_VALIDI)
def test_400_propri(corpo, messaggio):
    client, agente, _ = _app()
    cid = _nuova(client)
    r = client.post(f"/conversazioni/{cid}/messaggi", content=corpo)
    assert (r.status_code, r.json()) == (400, {"errore": messaggio})
    assert agente.turni == []


def test_domanda_vuota_va_all_agente():
    client, agente, _ = _app()
    cid = _nuova(client)
    assert client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": ""}).status_code == 200
    assert agente.turni[0]["domanda"] == ""


def _agente_con_errore(stato, corpo=None):
    return AgenteFinto(lambda richiesta: httpx.Response(stato, json=corpo or {"errore": "boom"}))


@pytest.mark.parametrize("stato", [400, 422])
def test_errori_agente_inoltrati(stato):
    client, agente, deposito = _app(_agente_con_errore(stato, {"errore": "motivo preciso"}))
    cid = _nuova(client)
    r = client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": "x"})
    assert (r.status_code, r.json()) == (stato, {"errore": "motivo preciso"})
    assert client.get(f"/conversazioni/{cid}").json()["messaggi"] == []
    assert deposito.cronologia(cid) == []


@pytest.mark.parametrize("modo", ["500", "rete"])
def test_errori_agente_502(modo):
    if modo == "500":
        agente = _agente_con_errore(500)
    else:

        def rete(richiesta):
            raise httpx.ConnectError("rifiutata")

        agente = AgenteFinto(rete)
    client, _, deposito = _app(agente)
    cid = _nuova(client)
    r = client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": "x"})
    assert r.status_code == 502
    assert r.json()["errore"].startswith("agente non disponibile: ")
    assert client.get(f"/conversazioni/{cid}").json()["messaggi"] == []
    assert deposito.cronologia(cid) == []


def test_timeout_agente_non_salva_e_libera():
    scaduto = [True]

    def gestore(richiesta):
        if scaduto[0]:
            raise httpx.ReadTimeout("troppo lento")

    client, agente, deposito = _app(AgenteFinto(gestore))
    cid = _nuova(client)
    r = client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": "x"})
    assert r.status_code == 502
    assert r.json()["errore"].startswith("agente non disponibile: ")
    assert client.get(f"/conversazioni/{cid}").json()["messaggi"] == []
    assert deposito.cronologia(cid) == []

    scaduto[0] = False
    assert client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": "x"}).status_code == 200


def test_turno_in_corso_409():
    sblocca, avviato = threading.Event(), threading.Event()
    bloccate = []

    def gestore(richiesta):
        corpo = json.loads(richiesta.content)
        if corpo.get("domanda") == "lenta":
            bloccate.append(1)
            avviato.set()
            sblocca.wait(ATTESA)

    client, agente, _ = _app(AgenteFinto(gestore))
    a, b = _nuova(client), _nuova(client)
    esito = {}

    def primo():
        esito["r"] = client.post(f"/conversazioni/{a}/messaggi", json={"domanda": "lenta"})

    thread = threading.Thread(target=primo)
    thread.start()
    try:
        assert avviato.wait(ATTESA)
        r = client.post(f"/conversazioni/{a}/messaggi", json={"domanda": "veloce"})
        assert (r.status_code, r.json()) == (409, {"errore": f"turno in corso per la conversazione {a}."})
        altra = client.post(f"/conversazioni/{b}/messaggi", json={"domanda": "veloce"})
        assert altra.status_code == 200
    finally:
        sblocca.set()
        thread.join(ATTESA)
    assert not thread.is_alive()
    assert esito["r"].status_code == 200
    assert client.post(f"/conversazioni/{a}/messaggi", json={"domanda": "terzo"}).status_code == 200
    assert len(client.get(f"/conversazioni/{a}").json()["messaggi"]) == 4


def test_eliminata_durante_il_turno():
    sblocca, avviato = threading.Event(), threading.Event()

    def gestore(richiesta):
        avviato.set()
        sblocca.wait(ATTESA)

    client, _, deposito = _app(AgenteFinto(gestore))
    cid = _nuova(client)
    esito = {}

    def primo():
        esito["r"] = client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": "x"})

    thread = threading.Thread(target=primo)
    thread.start()
    try:
        assert avviato.wait(ATTESA)
        assert client.delete(f"/conversazioni/{cid}").status_code == 204
    finally:
        sblocca.set()
        thread.join(ATTESA)
    assert not thread.is_alive()
    assert (esito["r"].status_code, esito["r"].json()) == (404, {"errore": f"conversazione {cid} inesistente."})
    assert deposito.elenca() == []


def _agente_rete_giu():
    def rete(richiesta):
        raise httpx.ConnectError("rifiutata")

    return AgenteFinto(rete)


def test_log_502_senza_prefisso_doppio(caplog):
    client, _, _ = _app(_agente_rete_giu())
    cid = _nuova(client)
    with caplog.at_level("WARNING", logger="backend"):
        assert client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": "x"}).status_code == 502
    assert [r.getMessage() for r in caplog.records] == ["agente non disponibile: rifiutata"]


def test_log_502_prompt_senza_prefisso_doppio(caplog):
    client, _, _ = _app(_agente_rete_giu())
    with caplog.at_level("WARNING", logger="backend"):
        assert client.get("/prompt").status_code == 502
    assert [r.getMessage() for r in caplog.records] == ["agente non disponibile: rifiutata"]


def test_prompt_422_non_registra_warning(caplog):
    client, _, _ = _app(_agente_con_errore(422, {"errore": "motivo"}))
    with caplog.at_level("WARNING", logger="backend"):
        assert client.get("/prompt").status_code == 422
    assert caplog.records == []


@pytest.mark.parametrize("dove", ["agente", "deposito"])
def test_eccezione_inattesa_500_json(dove):
    class DepositoRotto(DepositoMemoria):
        def cronologia(self, id):
            if dove == "deposito" and self.rotto:
                raise RuntimeError("boom")
            return super().cronologia(id)

    deposito = DepositoRotto()
    deposito.rotto = True
    if dove == "agente":
        guasto = [True]

        def gestore(richiesta):
            if guasto[0]:
                raise RuntimeError("boom")

        agente = AgenteFinto(gestore)
    else:
        agente = AgenteFinto()
    app = crea_app(deposito, ClientAgente("http://agente", 5, transport=httpx.MockTransport(agente)))
    client = TestClient(app, raise_server_exceptions=False)
    cid = _nuova(client)
    if dove == "deposito":
        deposito.rotto = False
        deposito.cronologia = lambda id: (_ for _ in ()).throw(RuntimeError("boom"))
    r = client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": "x"})
    assert r.status_code == 500
    assert r.json() == {"errore": "errore interno: boom"}
    assert r.headers["content-type"] == "application/json; charset=utf-8"
    if dove == "agente":
        guasto[0] = False
    else:
        del deposito.cronologia
    assert client.post(f"/conversazioni/{cid}/messaggi", json={"domanda": "y"}).status_code == 200


def test_errore_database():
    client, _, _ = _app(deposito=DepositoMemoria(errore=ErroreDatabase("giù")))
    r = client.post("/conversazioni/1/messaggi", json={"domanda": "x"})
    assert (r.status_code, r.json()) == (500, {"errore": "errore del database: giù"})
    assert client.get("/conversazioni").json() == {"errore": "errore del database: giù"}
