import logging
from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.grafo import (
    ISTRUZIONE_RISPOSTA,
    MESSAGGIO_LIMITE,
    MESSAGGIO_RIFIUTO,
    _esegui_strumento,
    build_graph,
    instrada_dopo_modello,
    instrada_dopo_router,
)
from assistente.strumenti import Strumento, crea_strumenti
from finti import LlmFinto, RouterFinto, richiesta, richiesta_malformata, richiesta_ora

ADESSO = lambda: datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)  # noqa: E731


def esegui(llm, max_passaggi=5, testo="Che ore sono?", strumenti=None, router=None):
    if strumenti is None:
        strumenti = crea_strumenti(ADESSO, "Europe/Rome")
    if router is None:
        router = RouterFinto("conversazione")
    grafo = build_graph(llm, strumenti, max_passaggi, router)
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
    assert tool[0].content == "Errore: strumento sconosciuto: 'meteo'."
    assert tool[0].tool_call_id == "c1"
    assert stato["messaggi"][-1].content == "Non posso."


def test_definizioni_nell_ordine_del_registro():
    registro = crea_strumenti(ADESSO, "Asia/Tokyo")
    llm = LlmFinto([AIMessage("Ciao!")])
    esegui(llm, strumenti=registro)
    assert llm.strumenti == [s.definizione for s in registro.values()]
    fuso = llm.strumenti[0]["function"]["parameters"]["properties"]["fuso"]
    assert "Asia/Tokyo" in fuso["description"]


def test_log_mostra_argomenti_ricevuti(caplog):
    llm = LlmFinto([richiesta("ora_corrente", {}), AIMessage("Ok.")])
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        esegui(llm)
    assert "tool_call nome=ora_corrente args={}" in caplog.text


def test_argomenti_non_oggetto():
    # AIMessage non accetta args non dict: si prova direttamente l'esecuzione.
    registro = crea_strumenti(ADESSO, "Europe/Rome")
    risultato = _esegui_strumento(registro, "ora_corrente", ["x"])
    assert risultato == "Errore: argomenti non validi, atteso un oggetto JSON."


def _solleva(args):
    raise RuntimeError("guasto")


def test_strumento_che_solleva(caplog):
    rotto = Strumento(
        definizione={
            "type": "function",
            "function": {
                "name": "rotto",
                "description": "Strumento di prova che fallisce.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        esegui=_solleva,
    )
    llm = LlmFinto([richiesta("rotto", {}), AIMessage("Mi dispiace.")])
    with caplog.at_level(logging.ERROR, logger="assistente.grafo"):
        stato = esegui(llm, strumenti={"rotto": rotto})
    tool = tool_messages(stato)
    assert tool[0].content == "Errore: errore interno dello strumento 'rotto'."
    assert stato["interrotto"] is False
    assert stato["messaggi"][-1].content == "Mi dispiace."
    assert "guasto" in caplog.text


def test_argomenti_json_malformati():
    llm = LlmFinto([richiesta_malformata("c1"), AIMessage("Riprovo con il fuso.")])
    stato = esegui(llm)
    tool = tool_messages(stato)
    assert len(tool) == 1
    assert tool[0].tool_call_id == "c1"
    assert tool[0].content == (
        "Errore: argomenti non in formato JSON valido. Riprovare con un oggetto JSON."
    )
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


def test_tool_call_calcola():
    llm = LlmFinto(
        [richiesta("calcola", {"espressione": "2 + 3 * 4"}), AIMessage("Fa 14.")]
    )
    stato = esegui(llm, testo="Quanto fa 2 + 3 * 4?")
    assert tool_messages(stato)[0].content == "14"
    assert stato["messaggi"][-1].content == "Fa 14."


def test_due_strumenti_nella_stessa_risposta():
    doppia = AIMessage(
        content="",
        tool_calls=[
            {"name": "ora_corrente", "args": {}, "id": "c1"},
            {"name": "calcola", "args": {"espressione": "1 / 4"}, "id": "c2"},
        ],
    )
    llm = LlmFinto([doppia, AIMessage("Ecco.")])
    stato = esegui(llm)
    tool = tool_messages(stato)
    assert [m.tool_call_id for m in tool] == ["c1", "c2"]
    assert [m.content for m in tool] == ["2026-01-15T13:00:00+01:00", "0.25"]


def test_risposta_vuota_dopo_strumenti_ripete_senza_strumenti(caplog):
    llm = LlmFinto(
        [richiesta("calcola", {"espressione": "2+2"}), AIMessage(""), AIMessage("Fa 4.")]
    )
    with caplog.at_level(logging.WARNING, logger="assistente.grafo"):
        stato = esegui(llm)
    assert stato["messaggi"][-1].content == "Fa 4."
    assert llm.con_strumenti == [True, True, False]
    vuote = [
        m
        for m in stato["messaggi"]
        if isinstance(m, AIMessage) and not m.tool_calls and not m.content
    ]
    assert vuote == []
    assert stato["passaggi"] == 1
    assert "risposta vuota dopo gli strumenti" in caplog.text


def test_ripetizione_dopo_risposta_vuota_riceve_istruzione_di_sistema():
    llm = LlmFinto(
        [richiesta("calcola", {"espressione": "2+2"}), AIMessage(""), AIMessage("Fa 4.")]
    )
    stato = esegui(llm)
    prima, ripetizione = llm.chiamate[1], llm.chiamate[2]
    assert ISTRUZIONE_RISPOSTA == "Rispondi all'utente riferendo il risultato degli strumenti."
    assert isinstance(ripetizione[0], SystemMessage)
    assert ripetizione[0].content == ISTRUZIONE_RISPOSTA
    assert ripetizione[1:] == prima  # il resto dei messaggi è quello dello stato
    assert not any(isinstance(m, SystemMessage) for m in llm.chiamate[0] + prima)
    assert not any(isinstance(m, SystemMessage) for m in stato["messaggi"])


def test_risposta_vuota_ripetuta_una_sola_volta():
    llm = LlmFinto(
        [richiesta("calcola", {"espressione": "2+2"}), AIMessage(""), AIMessage("  ")]
    )
    stato = esegui(llm)
    assert llm.con_strumenti == [True, True, False]
    assert stato["messaggi"][-1].content == "  "


def test_risposta_vuota_senza_strumenti_non_ripete():
    llm = LlmFinto([AIMessage("")])
    stato = esegui(llm)
    assert llm.con_strumenti == [True]
    assert stato["messaggi"][-1].content == ""


def test_tool_call_calendario():
    llm = LlmFinto(
        [
            richiesta(
                "calendario",
                {"operazione": "aggiungi", "data": "2026-12-18", "giorni": 10, "lavorativi": True},
            ),
            AIMessage("Il 5 gennaio."),
        ]
    )
    stato = esegui(llm, testo="Tra 10 giorni lavorativi dal 18 dicembre?")
    assert (
        tool_messages(stato)[0].content
        == "2026-12-18 (venerdì) + 10 giorni lavorativi = 2027-01-05 (martedì)"
    )


def test_tool_call_converti_unita():
    llm = LlmFinto(
        [
            richiesta("converti_unita", {"valore": 2.5, "da": "km", "a": "m"}),
            AIMessage("Sono 2500 m."),
        ]
    )
    stato = esegui(llm, testo="Quanti metri sono 2,5 km?")
    assert tool_messages(stato)[0].content == "2500 m"


def test_router_in_ambito_passa_all_agente(caplog):
    llm = LlmFinto([AIMessage("Sono le 13.")])
    router = RouterFinto("conversazione", "domanda sull'ora")
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        stato = esegui(llm, router=router)
    assert stato["messaggi"][-1].content == "Sono le 13."
    assert len(llm.chiamate) == 1
    assert stato["categoria"] == "conversazione"
    assert "router categoria=conversazione motivo=domanda sull'ora → agente" in caplog.text
    assert "agente: chiamata al modello" in caplog.text


def test_router_fuori_ambito_rifiuta_senza_agente(caplog):
    llm = LlmFinto([])
    router = RouterFinto("fuori_ambito", "poesia")
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        stato = esegui(llm, testo="Scrivi una poesia", router=router)
    assert llm.chiamate == []
    ultimo = stato["messaggi"][-1]
    assert isinstance(ultimo, AIMessage)
    assert ultimo.content == MESSAGGIO_RIFIUTO.format(motivo="poesia")
    assert stato["categoria"] == "fuori_ambito"
    assert stato["interrotto"] is False
    assert "router categoria=fuori_ambito motivo=poesia → rifiuto" in caplog.text
    assert "agente:" not in caplog.text


def test_router_riceve_la_cronologia():
    router = RouterFinto("conversazione")
    esegui(LlmFinto([AIMessage("ok")]), testo="Che giorno è?", router=router)
    assert router.chiamate[0][-1].content == "Che giorno è?"


@pytest.mark.parametrize(
    "categoria, atteso", [("conversazione", "agente"), ("fuori_ambito", "rifiuto")]
)
def test_instradamento_dopo_router(categoria, atteso):
    assert instrada_dopo_router({"categoria": categoria}) == atteso
