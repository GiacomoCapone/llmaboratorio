"""Test dell'applicazione HTTP, con grafo e archivio finti (nessun modello)."""

import logging
import threading
import time

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    messages_from_dict,
    messages_to_dict,
)
from starlette.testclient import TestClient

from assistente.cli import MESSAGGIO_RISPOSTA_VUOTA
from assistente.config import carica_config
from assistente.mcp_client import ErroreArchivio, PromptArchivio
from assistente.servizio import crea_app


class GrafoFinto:
    def __init__(self, risposta="ok", interrotto=False, errore=None, attesa=0.0):
        self.risposta = risposta
        self.interrotto = interrotto
        self.errore = errore
        self.attesa = attesa
        self.ricevuti = []
        self.massimo_contemporanei = 0
        self._attivi = 0
        self._blocco = threading.Lock()

    def invoke(self, stato):
        self.ricevuti.append(stato["messaggi"])
        with self._blocco:
            self._attivi += 1
            self.massimo_contemporanei = max(self.massimo_contemporanei, self._attivi)
        try:
            time.sleep(self.attesa)
            if self.errore is not None and len(self.ricevuti) == 1:
                raise self.errore
            return {
                **stato,
                "messaggi": stato["messaggi"] + [AIMessage(self.risposta)],
                "interrotto": self.interrotto,
            }
        finally:
            with self._blocco:
                self._attivi -= 1


class PromptFinto:
    def __init__(self, prompt=None, errore=None):
        self.prompt = (
            prompt if prompt is not None else [PromptArchivio("scheda_articolo", "Scheda", ["codice"])]
        )
        self.errore = errore
        self.chiamate = []

    def prompt_disponibili(self):
        return self.prompt

    def testo_prompt(self, nome, argomenti):
        self.chiamate.append((nome, argomenti))
        if self.errore is not None:
            raise self.errore
        return f"Dettagli di {argomenti.get('codice', 'niente')}"


def crea_client(grafo=None, prompt=None):
    grafo = grafo if grafo is not None else GrafoFinto()
    prompt = prompt if prompt is not None else PromptFinto()
    return TestClient(crea_app(grafo, prompt)), grafo, prompt


def uguali(a, b):
    return [(type(x), x.content) for x in a] == [(type(x), x.content) for x in b]


def test_salute():
    client, _, _ = crea_client()
    r = client.get("/salute")
    assert r.status_code == 200
    assert r.json() == {"stato": "ok"}


def test_elenco_prompt():
    client, _, _ = crea_client()
    r = client.get("/prompt")
    assert r.status_code == 200
    assert r.json() == {
        "prompt": [{"nome": "scheda_articolo", "argomenti": ["codice"], "descrizione": "Scheda"}]
    }


def test_elenco_prompt_vuoto():
    client, _, _ = crea_client(prompt=PromptFinto(prompt=[]))
    assert client.get("/prompt").json() == {"prompt": []}


def test_turno_con_domanda():
    client, grafo, _ = crea_client()
    r = client.post("/turno", json={"domanda": "Che giorno sarà?"})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["domanda"] == "Che giorno sarà?"
    assert corpo["risposta"] == "ok"
    assert corpo["interrotto"] is False
    assert uguali(
        messages_from_dict(corpo["cronologia"]),
        [HumanMessage("Che giorno sarà?"), AIMessage("ok")],
    )
    assert grafo.ricevuti[0] == [HumanMessage("Che giorno sarà?")]


def test_cronologia_andata_e_ritorno():
    originali = [
        SystemMessage("Riassunto del passato"),
        HumanMessage("Quali note ci sono?"),
        AIMessage("", tool_calls=[{"name": "elenca_note", "args": {}, "id": "c1"}]),
        ToolMessage("Nessuna nota.", tool_call_id="c1"),
        AIMessage("Nessuna nota."),
    ]
    client, grafo, _ = crea_client()
    r = client.post(
        "/turno", json={"cronologia": messages_to_dict(originali), "domanda": "Grazie"}
    )
    assert r.status_code == 200
    assert grafo.ricevuti[0][:5] == originali


def test_turno_interrotto():
    cronologia = [HumanMessage("a"), AIMessage("b")]
    client, _, _ = crea_client(grafo=GrafoFinto(interrotto=True))
    r = client.post("/turno", json={"cronologia": messages_to_dict(cronologia), "domanda": "c"})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["interrotto"] is True
    assert corpo["cronologia"] == messages_to_dict(cronologia)


@pytest.mark.parametrize("risposta", ["", "  "])
def test_risposta_vuota(risposta):
    client, _, _ = crea_client(grafo=GrafoFinto(risposta=risposta))
    r = client.post("/turno", json={"domanda": "ciao"})
    assert r.json()["risposta"] == MESSAGGIO_RISPOSTA_VUOTA


def test_turno_con_prompt():
    client, grafo, prompt = crea_client()
    r = client.post(
        "/turno",
        json={"prompt": {"nome": "scheda_articolo", "argomenti": {"codice": "MIS-001"}}},
    )
    assert r.status_code == 200
    assert r.json()["domanda"] == "Dettagli di MIS-001"
    assert grafo.ricevuti[0] == [HumanMessage("Dettagli di MIS-001")]
    assert prompt.chiamate == [("scheda_articolo", {"codice": "MIS-001"})]


def test_prompt_senza_argomenti():
    prompt = PromptFinto(prompt=[PromptArchivio("aiuto", "Aiuto", [])])
    client, _, _ = crea_client(prompt=prompt)
    r = client.post("/turno", json={"prompt": {"nome": "aiuto"}})
    assert r.status_code == 200
    assert prompt.chiamate == [("aiuto", {})]


def verifica_400(client, grafo, prompt, corpo, messaggio=None, inizio=None, **kwargs):
    if "content" in kwargs:
        r = client.post("/turno", content=kwargs["content"])
    else:
        r = client.post("/turno", json=corpo)
    assert r.status_code == 400
    errore = r.json()["errore"]
    if messaggio is not None:
        assert errore == messaggio
    if inizio is not None:
        assert errore.startswith(inizio)
    assert grafo.ricevuti == []
    assert prompt.chiamate == []


@pytest.mark.parametrize("contenuto", ["non json", "[1]", '"x"'])
def test_corpo_non_valido(contenuto):
    client, grafo, prompt = crea_client()
    verifica_400(
        client, grafo, prompt, None,
        "corpo della richiesta non valido: atteso un oggetto JSON.",
        content=contenuto,
    )


@pytest.mark.parametrize(
    "corpo",
    [
        {"domanda": "a", "prompt": {"nome": "scheda_articolo", "argomenti": {"codice": "A"}}},
        {"cronologia": []},
        {},
    ],
)
def test_domanda_e_prompt(corpo):
    client, grafo, prompt = crea_client()
    verifica_400(client, grafo, prompt, corpo, "indicare esattamente uno fra 'domanda' e 'prompt'.")


@pytest.mark.parametrize("domanda", ["", "   ", "\ufeff ", 5])
def test_domanda_vuota(domanda):
    client, grafo, prompt = crea_client()
    verifica_400(client, grafo, prompt, {"domanda": domanda}, "'domanda' deve essere un testo non vuoto.")


@pytest.mark.parametrize(
    "cronologia",
    [None, "x", ["ciao"], [{"type": "boh", "data": {}}], [{"type": "human"}]],
)
def test_cronologia_non_valida(cronologia):
    client, grafo, prompt = crea_client()
    verifica_400(
        client, grafo, prompt, {"cronologia": cronologia, "domanda": "ciao"},
        inizio="'cronologia' non valida:",
    )


@pytest.mark.parametrize(
    "prompt_corpo",
    ["x", {"argomenti": {}}, {"nome": "scheda_articolo", "argomenti": [1]}],
)
def test_prompt_malformato(prompt_corpo):
    client, grafo, prompt = crea_client()
    verifica_400(
        client, grafo, prompt, {"prompt": prompt_corpo},
        "'prompt' non valido: atteso un oggetto con 'nome' e 'argomenti'.",
    )


def test_prompt_sconosciuto():
    client, grafo, prompt = crea_client()
    verifica_400(
        client, grafo, prompt, {"prompt": {"nome": "boh", "argomenti": {}}}, "prompt sconosciuto 'boh'."
    )


@pytest.mark.parametrize("argomenti", [{}, {"codice": " "}])
def test_prompt_argomenti_mancanti(argomenti):
    client, grafo, prompt = crea_client()
    verifica_400(
        client, grafo, prompt, {"prompt": {"nome": "scheda_articolo", "argomenti": argomenti}},
        "scheda_articolo richiede: codice.",
    )


def test_prompt_argomenti_in_piu():
    client, grafo, prompt = crea_client()
    verifica_400(
        client, grafo, prompt,
        {"prompt": {"nome": "scheda_articolo", "argomenti": {"codice": "A", "x": "1"}}},
        "argomenti non previsti per scheda_articolo: x.",
    )


def test_prompt_argomenti_non_validi():
    client, grafo, prompt = crea_client()
    verifica_400(
        client, grafo, prompt,
        {"prompt": {"nome": "scheda_articolo", "argomenti": {"codice": 1}}},
        "gli argomenti di scheda_articolo devono essere testi.",
    )


def test_errore_archivio_sul_prompt():
    prompt = PromptFinto(errore=ErroreArchivio("nessun articolo con codice 'XYZ'."))
    client, grafo, _ = crea_client(prompt=prompt)
    r = client.post(
        "/turno", json={"prompt": {"nome": "scheda_articolo", "argomenti": {"codice": "XYZ"}}}
    )
    assert r.status_code == 422
    assert r.json()["errore"] == "nessun articolo con codice 'XYZ'."
    assert grafo.ricevuti == []


def test_turno_fallito_libera_il_lock(caplog):
    client, _, _ = crea_client(grafo=GrafoFinto(errore=RuntimeError("LM Studio spento")))
    with caplog.at_level(logging.INFO, logger="assistente.servizio"):
        r = client.post("/turno", json={"domanda": "ciao"})
    assert r.status_code == 500
    assert r.json()["errore"] == "turno fallito: LM Studio spento"
    assert any(
        rec.levelno == logging.WARNING and rec.name == "assistente.servizio" for rec in caplog.records
    )
    assert client.post("/turno", json={"domanda": "ciao"}).status_code == 200


def test_un_turno_alla_volta():
    grafo = GrafoFinto(attesa=0.3)
    client, _, _ = crea_client(grafo=grafo)
    codici = []

    def chiama():
        codici.append(client.post("/turno", json={"domanda": "ciao"}).status_code)

    fili = [threading.Thread(target=chiama) for _ in range(2)]
    for f in fili:
        f.start()
    for f in fili:
        f.join()
    assert codici == [200, 200]
    assert grafo.massimo_contemporanei == 1


@pytest.mark.parametrize(
    "livello, atteso", [("DEBUG", logging.DEBUG), ("WARN", logging.WARNING), ("INESISTENTE", logging.INFO)]
)
def test_servi_avvia_uvicorn(monkeypatch, livello, atteso):
    from contextlib import contextmanager

    from assistente import servizio

    grafo, prompt = GrafoFinto(), PromptFinto()
    eventi = []
    chiamate = {}

    @contextmanager
    def apri_finto(config):
        eventi.append("aperto")
        try:
            yield grafo, prompt
        finally:
            eventi.append("chiuso")

    def run_finto(app, **kwargs):
        chiamate["app"] = app
        chiamate.update(kwargs)
        eventi.append("run")
        assert TestClient(app).get("/salute").json() == {"stato": "ok"}

    monkeypatch.setattr("assistente.servizio.apri_assistente", apri_finto)
    monkeypatch.setattr("assistente.servizio.uvicorn.run", run_finto)
    config = carica_config(
        {
            "LMSTUDIO_BASE_URL": "http://localhost:1234/v1",
            "LMSTUDIO_MODEL": "m",
            "HTTP_HOST": "0.0.0.0",
            "HTTP_PORTA": "9000",
            "LOG_LEVEL": livello,
        }
    )
    servizio.servi(config)
    assert chiamate["host"] == config.http_host == "0.0.0.0"
    assert chiamate["port"] == config.http_porta == 9000
    assert chiamate["log_level"] == atteso
    assert eventi == ["aperto", "run", "chiuso"]


def test_risposte_dichiarano_utf8():
    client, _, _ = crea_client()
    risposte = [
        client.get("/salute"),
        client.get("/prompt"),
        client.post("/turno", json={"domanda": "Perché è così?"}),
        client.post("/turno", json={}),
    ]
    assert [r.status_code for r in risposte] == [200, 200, 200, 400]
    for r in risposte:
        assert r.headers["content-type"] == "application/json; charset=utf-8"
