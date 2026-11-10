import logging
from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.grafo import (
    ISTRUZIONE_RISPOSTA,
    MESSAGGIO_LIMITE,
    INDICAZIONE_REVISORE,
    MESSAGGIO_RIFIUTO,
    _esegui_strumento,
    build_graph,
    instrada_dopo_modello,
    instrada_dopo_revisore,
    instrada_dopo_router,
)
from assistente.riassunto import PREFISSO_RIASSUNTO
from assistente.strumenti import Strumento, crea_strumenti
from finti import (
    LlmFinto,
    RevisoreFinto,
    RiassuntoreFinto,
    RouterFinto,
    richiesta,
    richiesta_malformata,
    richiesta_ora,
)

ADESSO = lambda: datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)  # noqa: E731


def esegui(
    llm,
    max_passaggi=5,
    testo="Che ore sono?",
    strumenti=None,
    router=None,
    revisore=None,
    max_revisioni=2,
    riassuntore=None,
    soglia_riassunto=100000,
    cronologia=(),
):
    if strumenti is None:
        strumenti = crea_strumenti(ADESSO, "Europe/Rome")
    if router is None:
        router = RouterFinto("conversazione")
    if revisore is None:
        revisore = RevisoreFinto([True])
    if riassuntore is None:
        riassuntore = RiassuntoreFinto()
    grafo = build_graph(
        llm, strumenti, max_passaggi, router, revisore, max_revisioni, riassuntore, soglia_riassunto
    )
    return grafo.invoke(
        {
            "messaggi": [*cronologia, HumanMessage(testo)],
            "passaggi": 0,
            "interrotto": False,
            "revisioni": 0,
            "scartati": [],
            "esito_revisione": "",
        }
    )


def contenuti(stato):
    return [m.content for m in stato["messaggi"]]


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


DUE_PARTI = "Che ore sono a Tokyo e quanto fa 12 * 4?"


def test_revisore_rimanda_risposta_parziale(caplog):
    llm = LlmFinto(
        [AIMessage("A Tokyo sono le 21."), AIMessage("A Tokyo sono le 21; 12 * 4 fa 48.")]
    )
    revisore = RevisoreFinto([False, True], motivo="manca il calcolo")
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        stato = esegui(llm, testo=DUE_PARTI, revisore=revisore)
    assert len(llm.chiamate) == 2
    indicazione = INDICAZIONE_REVISORE.format(motivo="manca il calcolo")
    assert llm.chiamate[1][-1].content == indicazione
    assert "revisore coerente=no motivo=manca il calcolo → agente (revisione 1/2)" in caplog.text
    assert "revisore coerente=sì motivo=manca il calcolo → fine" in caplog.text
    assert contenuti(stato) == [DUE_PARTI, "A Tokyo sono le 21; 12 * 4 fa 48."]


def test_revisore_approva_al_primo_passaggio(caplog):
    llm = LlmFinto([AIMessage("Sono le 13.")])
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        stato = esegui(llm)
    assert len(llm.chiamate) == 1
    assert "revisore coerente=sì motivo=motivo di prova → fine" in caplog.text
    assert stato["revisioni"] == 0
    assert contenuti(stato) == ["Che ore sono?", "Sono le 13."]


def test_limite_di_revisioni(caplog):
    llm = LlmFinto([AIMessage("r1"), AIMessage("r2"), AIMessage("r3")])
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        stato = esegui(llm, revisore=RevisoreFinto([False]), max_revisioni=2)
    assert len(llm.chiamate) == 3
    assert contenuti(stato) == ["Che ore sono?", "r3"]
    assert "limite di revisioni raggiunto (2): restituita l'ultima risposta" in caplog.text
    assert any(
        r.levelno == logging.WARNING and "limite di revisioni" in r.getMessage()
        for r in caplog.records
    )
    assert stato["interrotto"] is False


def test_revisore_non_vede_bozze_scartate():
    revisore = RevisoreFinto([False, True])
    esegui(LlmFinto([AIMessage("bozza"), AIMessage("finale")]), revisore=revisore)
    secondi = [m.content for m in revisore.chiamate[1]]
    assert "bozza" not in secondi
    assert not any(str(c).startswith("Indicazione del revisore") for c in secondi)
    assert secondi[-1] == "finale"


def test_revisione_dopo_strumenti_mantiene_le_coppie():
    llm = LlmFinto([richiesta_ora("Asia/Tokyo"), AIMessage("bozza"), AIMessage("finale")])
    stato = esegui(llm, revisore=RevisoreFinto([False, True]))
    chiamate = [m for m in stato["messaggi"] if getattr(m, "tool_calls", None)]
    assert len(chiamate) == 1 and len(tool_messages(stato)) == 1
    assert tool_messages(stato)[0].tool_call_id == chiamate[0].tool_calls[0]["id"]
    assert "bozza" not in contenuti(stato)
    assert stato["messaggi"][-1].content == "finale"


def test_risposta_vuota_passa_dal_revisore():
    revisore = RevisoreFinto([True])
    esegui(LlmFinto([AIMessage("")]), revisore=revisore)
    assert len(revisore.chiamate) == 1


def test_motivo_con_graffe():
    llm = LlmFinto([AIMessage("bozza"), AIMessage("finale")])
    esegui(llm, revisore=RevisoreFinto([False, True], motivo="manca {x}"))
    assert "manca {x}" in llm.chiamate[1][-1].content


def test_indicazione_non_cita_la_risposta_precedente():
    # L'utente non vede la bozza scartata: l'agente non deve scusarsi per essa.
    assert INDICAZIONE_REVISORE.startswith("Indicazione del revisore")
    assert "senza citare la risposta precedente" in INDICAZIONE_REVISORE


def test_revisore_non_esegue_dopo_rifiuto_del_router():
    revisore = RevisoreFinto([True])
    esegui(LlmFinto([]), router=RouterFinto("fuori_ambito"), revisore=revisore)
    assert revisore.chiamate == []


def test_revisore_non_esegue_al_limite_dei_passaggi():
    revisore = RevisoreFinto([True])
    llm = LlmFinto([richiesta_ora("UTC")], ripeti_ultima=True)
    stato = esegui(llm, max_passaggi=2, revisore=revisore)
    assert stato["interrotto"] is True
    assert revisore.chiamate == []


@pytest.mark.parametrize("esito", ["agente", "fine"])
def test_instradamento_dopo_revisore(esito):
    assert instrada_dopo_revisore({"esito_revisione": esito}) == esito


def test_risposta_vuota_rimandata_dal_revisore_vero(caplog):
    from assistente.revisore import crea_revisore

    valutatore = LlmFinto(
        [richiesta("Giudizio", {"richieste": ["Che ore sono?"], "mancanti": []})]
    )
    llm = LlmFinto([AIMessage(""), AIMessage("Sono le 12.")])
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        stato = esegui(llm, revisore=crea_revisore(valutatore))
    assert "revisore coerente=no motivo=risposta vuota → agente (revisione 1/2)" in caplog.text
    assert len(valutatore.chiamate) == 1  # solo la seconda risposta va al modello
    assert [m.content for m in stato["messaggi"]] == ["Che ore sono?", "Sono le 12."]


def conversazione(n):
    """n turni completi: D1/R1 … Dn/Rn."""
    messaggi = []
    for i in range(1, n + 1):
        messaggi += [HumanMessage(f"D{i}"), AIMessage(f"R{i}")]
    return messaggi


def sistema(messaggi):
    return [m for m in messaggi if isinstance(m, SystemMessage)]


def test_sotto_soglia_nessun_riassunto():
    riassuntore = RiassuntoreFinto()
    stato = esegui(LlmFinto([AIMessage("Sono le 12.")]), riassuntore=riassuntore)
    assert riassuntore.chiamate == []
    assert [m.content for m in stato["messaggi"]] == ["Che ore sono?", "Sono le 12."]


def test_sopra_soglia_riassume(caplog):
    riassuntore = RiassuntoreFinto()
    router = RouterFinto("conversazione")
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        stato = esegui(
            LlmFinto([AIMessage("R5")]),
            testo="D5",
            router=router,
            riassuntore=riassuntore,
            soglia_riassunto=1,
            cronologia=conversazione(4),
        )
    assert [m.content for m in riassuntore.chiamate[0]] == ["D1", "R1", "D2", "R2"]
    messaggi = stato["messaggi"]
    assert messaggi[0] == SystemMessage(PREFISSO_RIASSUNTO + "riassunto di prova", id=messaggi[0].id)
    assert len(sistema(messaggi)) == 1
    assert [m.content for m in messaggi[1:]] == ["D3", "R3", "D4", "R4", "D5", "R5"]
    assert "riassunto: 4 messaggi riassunti, stima " in caplog.text
    assert "D1" not in [m.content for m in router.chiamate[0]]


def test_sopra_soglia_senza_vecchi(caplog):
    riassuntore = RiassuntoreFinto()
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        stato = esegui(
            LlmFinto([AIMessage("R2")]),
            testo="D2",
            riassuntore=riassuntore,
            soglia_riassunto=1,
            cronologia=conversazione(1),
        )
    assert riassuntore.chiamate == []
    assert "niente da riassumere" in caplog.text
    assert [m.content for m in stato["messaggi"]] == ["D1", "R1", "D2", "R2"]


def test_secondo_riassunto_cumulativo():
    vecchio = SystemMessage(PREFISSO_RIASSUNTO + "vecchio")
    riassuntore = RiassuntoreFinto(testo="nuovo")
    stato = esegui(
        LlmFinto([AIMessage("R4")]),
        testo="D4",
        riassuntore=riassuntore,
        soglia_riassunto=10,  # superata dalla cronologia; metà (5 token) contiene "vecchio\nnuovo"
        cronologia=[vecchio, *conversazione(3)],
    )
    # Il precedente non va al modello (lo perdeva): il codice lo conserva alla lettera.
    assert [m.content for m in riassuntore.chiamate[0]] == ["D1", "R1"]
    riassunti = sistema(stato["messaggi"])
    assert [m.content for m in riassunti] == [PREFISSO_RIASSUNTO + "vecchio\nnuovo"]


def test_solo_riassunto_fra_i_vecchi(caplog):
    riassuntore = RiassuntoreFinto()
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        esegui(
            LlmFinto([AIMessage("R3")]),
            testo="D3",
            riassuntore=riassuntore,
            soglia_riassunto=1,
            cronologia=[SystemMessage(PREFISSO_RIASSUNTO + "vecchio"), *conversazione(2)],
        )
    assert riassuntore.chiamate == []
    assert "niente da riassumere" in caplog.text


def test_riassunto_troppo_lungo(caplog):
    righe = ["a" * 400, "b" * 400, "c" * 400]
    precedente = SystemMessage(PREFISSO_RIASSUNTO + "\n".join(righe))
    with caplog.at_level(logging.WARNING, logger="assistente.grafo"):
        stato = esegui(
            LlmFinto([AIMessage("R4")]),
            testo="D4",
            riassuntore=RiassuntoreFinto(testo="nuovo"),
            soglia_riassunto=10,  # metà soglia: 5 token, restano solo le righe necessarie
            cronologia=[precedente, *conversazione(3)],
        )
    assert "righe più vecchie" in caplog.text
    assert sistema(stato["messaggi"])[0].content == PREFISSO_RIASSUNTO + "nuovo"


@pytest.mark.parametrize(
    "riassuntore",
    [
        RiassuntoreFinto(errore=RuntimeError("guasto")),
        RiassuntoreFinto(testo=""),
        RiassuntoreFinto(testo="   "),
    ],
)
def test_guasto_lascia_la_cronologia(caplog, riassuntore):
    with caplog.at_level(logging.WARNING, logger="assistente.grafo"):
        stato = esegui(
            LlmFinto([AIMessage("R4")]),
            testo="D4",
            riassuntore=riassuntore,
            soglia_riassunto=1,
            cronologia=conversazione(3),
        )
    assert sistema(stato["messaggi"]) == []
    assert stato["messaggi"][0].content == "D1"
    assert "riassunto non disponibile" in caplog.text


def test_riassunto_e_revisione_nello_stesso_turno():
    stato = esegui(
        LlmFinto([AIMessage("bozza"), AIMessage("finale")]),
        testo="D4",
        revisore=RevisoreFinto([False, True]),
        soglia_riassunto=1,
        cronologia=conversazione(3),
    )
    contenuti = [m.content for m in stato["messaggi"]]
    assert len(sistema(stato["messaggi"])) == 1
    assert "bozza" not in contenuti
    assert contenuti[-1] == "finale"
