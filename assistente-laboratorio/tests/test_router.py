import logging

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.router import (
    MAX_TOKEN_ROUTER,
    PROMPT_ROUTER,
    Classificazione,
    crea_router,
    ultimi_messaggi,
)
from finti import LlmFinto, richiesta

FUORI = Classificazione(categoria="fuori_ambito", motivo="poesia")


def classifica(categoria="fuori_ambito", motivo="poesia"):
    """Risposta del modello: tool call verso lo strumento Classificazione."""
    return richiesta("Classificazione", {"categoria": categoria, "motivo": motivo})


def test_usa_tool_obbligatorio_con_limite_di_token():
    # Con json_schema LM Studio ignora reasoning_effort=none (gemma-4-e2b ragiona per migliaia
    # di token); con un tool obbligatorio risponde in pochi secondi senza ragionamento.
    # LM Studio accetta solo tool_choice in forma di stringa ("required").
    llm = LlmFinto([classifica()])
    crea_router(llm, "Ambito X")
    assert llm.strumenti == [Classificazione]
    assert llm.opzioni_strumenti == {"tool_choice": "required", "max_tokens": MAX_TOKEN_ROUTER}


def test_prompt_classifica_anche_le_richieste_all_imperativo():
    assert "imperativo" in PROMPT_ROUTER
    assert "Non chiederti se l'assistente conosce la data" in PROMPT_ROUTER


def test_prompt_contiene_ambito():
    llm = LlmFinto([classifica()])
    risultato = crea_router(llm, "Ambito X")([HumanMessage("Scrivi una poesia")])
    assert risultato == FUORI
    inviati = llm.chiamate[0]
    assert llm.con_strumenti == [True]
    assert isinstance(inviati[0], SystemMessage)
    assert "Ambito X" in inviati[0].content
    assert inviati[-1].content == "Scrivi una poesia"


def test_ultimi_messaggi_solo_domanda():
    domanda = HumanMessage("ciao")
    assert ultimi_messaggi([domanda]) == [domanda]


def test_ultimi_messaggi_esclude_strumenti():
    prima = HumanMessage("che ore sono a Roma?")
    chiamata = AIMessage(content="", tool_calls=[{"name": "ora", "args": {}, "id": "c1"}])
    risultato = ToolMessage(content="12:00", tool_call_id="c1")
    risposta = AIMessage("Sono le 12.")
    seguito = HumanMessage("e a Londra?")
    assert ultimi_messaggi([prima, chiamata, risultato, risposta, seguito]) == [
        prima,
        risposta,
        seguito,
    ]


def test_ultimi_messaggi_tiene_gli_ultimi_4():
    messaggi = [
        HumanMessage(f"d{i}") if i % 2 == 0 else AIMessage(f"r{i}") for i in range(6)
    ]
    assert ultimi_messaggi(messaggi) == messaggi[2:]


class LlmGuasto(LlmFinto):
    def _rispondi(self, messaggi, con_strumenti):
        raise RuntimeError("guasto")


def test_eccezione_ripiega_su_conversazione(caplog):
    with caplog.at_level(logging.WARNING, logger="assistente.router"):
        risultato = crea_router(LlmGuasto([]), "Ambito X")([HumanMessage("ciao")])
    assert risultato.categoria == "conversazione"
    assert "router non disponibile: guasto" in caplog.text


@pytest.mark.parametrize(
    "risposta",
    [
        AIMessage("conversazione"),  # testo invece della tool call
        richiesta("Classificazione", {"motivo": "manca la categoria"}),
        classifica(categoria=None),
    ],
)
def test_risultato_non_valido_ripiega(caplog, risposta):
    with caplog.at_level(logging.WARNING, logger="assistente.router"):
        risultato = crea_router(LlmFinto([risposta]), "Ambito X")([HumanMessage("ciao")])
    assert risultato.categoria == "conversazione"
    assert "router non disponibile" in caplog.text


def test_categoria_sconosciuta_conta_come_conversazione(caplog):
    # gemma-4-e2b, con domande in ambito, scrive a volte l'argomento al posto della categoria
    # ("inventario del laboratorio"); per le domande fuori ambito scrive sempre "fuori_ambito".
    llm = LlmFinto([classifica("inventario del laboratorio", "ricerca strumento")])
    with caplog.at_level(logging.WARNING, logger="assistente.router"):
        risultato = crea_router(llm, "Ambito X")([HumanMessage("Cerca un oscilloscopio")])
    assert risultato == Classificazione(categoria="conversazione", motivo="ricerca strumento")
    assert "categoria non valida 'inventario del laboratorio': considerata conversazione" in (
        caplog.text
    )
    assert "router non disponibile" not in caplog.text


@pytest.mark.parametrize(
    "scritta, attesa",
    [
        ("Fuori ambito", "fuori_ambito"),
        (" FUORI_AMBITO ", "fuori_ambito"),
        ("fuori-ambito", "fuori_ambito"),
        ("Conversazione", "conversazione"),
    ],
)
def test_varianti_di_scrittura_della_categoria(scritta, attesa):
    # Una variante di "fuori_ambito" non deve far passare la domanda all'agente.
    llm = LlmFinto([classifica(scritta, "motivo")])
    assert crea_router(llm, "Ambito X")([HumanMessage("x")]).categoria == attesa
