import logging
from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from assistente.grafo import MESSAGGIO_LIMITE, build_graph, instrada_dopo_modello
from finti import LlmFinto, richiesta_malformata, richiesta_ora

ADESSO = lambda: datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)  # noqa: E731


def esegui(llm, max_passaggi=5, testo="Che ore sono?"):
    grafo = build_graph(llm, ADESSO, max_passaggi)
    return grafo.invoke(
        {"messaggi": [HumanMessage(testo)], "passaggi": 0, "interrotto": False}
    )


def tool_messages(stato):
    return [m for m in stato["messaggi"] if isinstance(m, ToolMessage)]


def test_risposta_diretta():
    llm = LlmFinto([AIMessage("Ciao!")])
    stato = esegui(llm)
    assert stato["messaggi"][-1].content == "Ciao!"
    assert stato["passaggi"] == 0
    assert stato["interrotto"] is False


def test_un_giro_con_strumento():
    llm = LlmFinto([richiesta_ora("Europe/Rome"), AIMessage("Sono le 13:00.")])
    stato = esegui(llm)
    tipi = [type(m) for m in stato["messaggi"]]
    assert tipi == [HumanMessage, AIMessage, ToolMessage, AIMessage]
    tool = stato["messaggi"][2]
    assert "2026-01-15T13:00:00+01:00" in tool.content
    assert tool.tool_call_id == "c1"
    assert any(isinstance(m, ToolMessage) for m in llm.chiamate[1])
    assert stato["messaggi"][-1].content == "Sono le 13:00."
    assert stato["passaggi"] == 1
    assert stato["interrotto"] is False


def test_piu_giri_in_sequenza():
    llm = LlmFinto(
        [richiesta_ora("Europe/Rome", "c1"), richiesta_ora("UTC", "c2"), AIMessage("Fatto.")]
    )
    stato = esegui(llm)
    assert stato["passaggi"] == 2
    assert [m.tool_call_id for m in tool_messages(stato)] == ["c1", "c2"]
    assert stato["messaggi"][-1].content == "Fatto."


def test_piu_tool_calls_in_una_risposta():
    doppia = AIMessage(
        content="",
        tool_calls=[
            {"name": "ora_corrente", "args": {"fuso": "Europe/Rome"}, "id": "c1"},
            {"name": "ora_corrente", "args": {"fuso": "UTC"}, "id": "c2"},
        ],
    )
    llm = LlmFinto([doppia, AIMessage("Ecco le due ore.")])
    stato = esegui(llm)
    tool = tool_messages(stato)
    assert [m.tool_call_id for m in tool] == ["c1", "c2"]
    assert "2026-01-15T13:00:00+01:00" in tool[0].content
    assert "2026-01-15T12:00:00+00:00" in tool[1].content
    assert stato["passaggi"] == 1


def test_strumento_sconosciuto():
    sconosciuto = AIMessage(
        content="",
        tool_calls=[{"name": "meteo", "args": {"citta": "Roma"}, "id": "c1"}],
    )
    llm = LlmFinto([sconosciuto, AIMessage("Non posso.")])
    stato = esegui(llm)
    tool = tool_messages(stato)
    assert len(tool) == 1
    assert tool[0].content.startswith("Errore:")
    assert tool[0].tool_call_id == "c1"
    assert stato["messaggi"][-1].content == "Non posso."


def test_argomento_fuso_mancante():
    senza_fuso = AIMessage(
        content="",
        tool_calls=[{"name": "ora_corrente", "args": {}, "id": "c1"}],
    )
    llm = LlmFinto([senza_fuso, AIMessage("Mi serve il fuso.")])
    stato = esegui(llm)
    tool = tool_messages(stato)
    assert tool[0].content.startswith("Errore:")
    assert stato["messaggi"][-1].content == "Mi serve il fuso."


@pytest.mark.parametrize("fuso", [None, 5, ["Europe/Rome"], {"a": 1}])
def test_argomento_fuso_non_stringa(fuso):
    llm = LlmFinto([richiesta_ora(fuso), AIMessage("Riprovo.")])
    stato = esegui(llm)
    tool = tool_messages(stato)
    assert tool[0].content.startswith("Errore:")
    assert tool[0].tool_call_id == "c1"
    assert stato["messaggi"][-1].content == "Riprovo."


def test_argomenti_extra_ignorati():
    extra = AIMessage(
        content="",
        tool_calls=[
            {"name": "ora_corrente", "args": {"fuso": "UTC", "altro": 1}, "id": "c1"}
        ],
    )
    llm = LlmFinto([extra, AIMessage("Ok.")])
    stato = esegui(llm)
    assert tool_messages(stato)[0].content == "2026-01-15T12:00:00+00:00"
    assert stato["messaggi"][-1].content == "Ok."


def test_argomenti_json_malformati():
    llm = LlmFinto([richiesta_malformata("c1"), AIMessage("Riprovo con il fuso.")])
    stato = esegui(llm)
    tool = tool_messages(stato)
    assert len(tool) == 1
    assert tool[0].tool_call_id == "c1"
    assert tool[0].content.startswith("Errore:")
    assert "JSON" in tool[0].content
    assert any(isinstance(m, ToolMessage) for m in llm.chiamate[1])
    assert stato["messaggi"][-1].content == "Riprovo con il fuso."
    assert stato["passaggi"] == 1
    assert stato["interrotto"] is False


def test_argomenti_json_malformati_senza_id():
    llm = LlmFinto([richiesta_malformata(None), AIMessage("Ok.")])
    stato = esegui(llm)
    tool = tool_messages(stato)
    assert len(tool) == 1
    assert tool[0].tool_call_id
    assert stato["messaggi"][-1].content == "Ok."


def test_argomenti_json_malformati_ripetuti_raggiungono_il_limite():
    llm = LlmFinto([richiesta_malformata()], ripeti_ultima=True)
    stato = esegui(llm, max_passaggi=2)
    assert stato["interrotto"] is True
    assert stato["passaggi"] == 2
    assert MESSAGGIO_LIMITE in stato["messaggi"][-1].content


def test_limite_raggiunto(caplog):
    llm = LlmFinto([richiesta_ora("UTC")], ripeti_ultima=True)
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        stato = esegui(llm, max_passaggi=2)
    assert stato["interrotto"] is True
    assert stato["passaggi"] == 2
    assert MESSAGGIO_LIMITE in stato["messaggi"][-1].content
    assert any(
        r.levelno == logging.WARNING and r.name == "assistente.grafo"
        for r in caplog.records
    )


def test_messaggio_limite_cita_il_limite():
    assert "limite" in MESSAGGIO_LIMITE.lower()
    assert "passaggi" in MESSAGGIO_LIMITE.lower()


def test_limite_alto_non_supera_la_ricorsione():
    llm = LlmFinto([richiesta_ora("UTC")], ripeti_ultima=True)
    stato = esegui(llm, max_passaggi=15)
    assert stato["interrotto"] is True
    assert stato["passaggi"] == 15


@pytest.mark.parametrize(
    "ultimo, passaggi, atteso",
    [
        (AIMessage("risposta"), 0, "fine"),
        (richiesta_ora("UTC"), 1, "strumenti"),
        (richiesta_ora("UTC"), 3, "limite"),
        (richiesta_malformata(), 1, "strumenti"),
        (richiesta_malformata(), 3, "limite"),
    ],
)
def test_instradamento(ultimo, passaggi, atteso):
    stato = {
        "messaggi": [HumanMessage("ciao"), ultimo],
        "passaggi": passaggi,
        "interrotto": False,
    }
    assert instrada_dopo_modello(stato, 3) == atteso


def test_log_delle_chiamate_allo_strumento(caplog):
    llm = LlmFinto([richiesta_ora("Europe/Rome"), AIMessage("Ok.")])
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        esegui(llm)
    testi = [r.getMessage() for r in caplog.records if r.name == "assistente.grafo"]
    assert any("tool_call nome=ora_corrente" in t and "Europe/Rome" in t for t in testi)
    assert any("tool_result nome=ora_corrente" in t for t in testi)
