"""Grafo LangGraph dell'assistente: stato, nodi, instradamento."""

import logging
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from assistente.strumenti import Strumento

logger = logging.getLogger("assistente.grafo")

MESSAGGIO_LIMITE = (
    "Raggiunto il limite di passaggi con gli strumenti: "
    "la richiesta è stata interrotta senza una risposta finale."
)


class Stato(TypedDict):
    messaggi: Annotated[list[AnyMessage], add_messages]
    passaggi: int
    interrotto: bool


def instrada_dopo_modello(
    stato: Stato, max_passaggi: int
) -> Literal["strumenti", "limite", "fine"]:
    """Decide il nodo successivo in base all'ultimo messaggio del modello."""
    ultimo = stato["messaggi"][-1]
    if not (
        getattr(ultimo, "tool_calls", None) or getattr(ultimo, "invalid_tool_calls", None)
    ):
        return "fine"
    if stato["passaggi"] < max_passaggi:
        return "strumenti"
    return "limite"


def _esegui_strumento(strumenti: dict[str, Strumento], nome, args) -> str:
    """Esegue uno strumento del registro; ogni problema diventa un testo 'Errore: ...'."""
    strumento = strumenti.get(nome)
    if strumento is None:
        return f"Errore: strumento sconosciuto: '{nome}'."
    if not isinstance(args, dict):
        return "Errore: argomenti non validi, atteso un oggetto JSON."
    try:
        return strumento.esegui(args)
    except Exception:  # un guasto dello strumento non deve interrompere il turno
        logger.exception("strumento %s fallito", nome)
        return f"Errore: errore interno dello strumento '{nome}'."


def build_graph(llm, strumenti: dict[str, Strumento], max_passaggi: int):
    """Costruisce e compila il grafo modello / strumenti / limite."""
    llm_con_strumenti = llm.bind_tools([s.definizione for s in strumenti.values()])

    def modello(stato: Stato) -> dict:
        return {"messaggi": [llm_con_strumenti.invoke(stato["messaggi"])]}

    def esegui_strumenti(stato: Stato) -> dict:
        ultimo = stato["messaggi"][-1]
        risultati = []
        for chiamata in ultimo.tool_calls:
            nome, args = chiamata.get("name"), chiamata.get("args")
            logger.info("tool_call nome=%s args=%s", nome, args)
            testo = _esegui_strumento(strumenti, nome, args)
            logger.info("tool_result nome=%s risultato=%s", nome, testo)
            risultati.append(
                ToolMessage(content=testo, tool_call_id=chiamata["id"], name=nome)
            )
        # Argomenti non JSON: langchain li mette in invalid_tool_calls; si risponde
        # comunque, così il modello può correggersi e la cronologia resta coerente.
        for indice, chiamata in enumerate(getattr(ultimo, "invalid_tool_calls", None) or []):
            nome = chiamata.get("name")
            id_chiamata = chiamata.get("id") or f"non_valida_{stato['passaggi']}_{indice}"
            logger.warning(
                "tool_call non valida nome=%s args=%r", nome, chiamata.get("args")
            )
            risultati.append(
                ToolMessage(
                    content=(
                        "Errore: argomenti non in formato JSON valido. "
                        "Riprovare con un oggetto JSON."
                    ),
                    tool_call_id=id_chiamata,
                    name=nome or "sconosciuto",
                )
            )
        return {"messaggi": risultati, "passaggi": stato["passaggi"] + 1}

    def limite(stato: Stato) -> dict:
        logger.warning("limite di passaggi raggiunto: max_passaggi=%s", max_passaggi)
        return {"messaggi": [AIMessage(MESSAGGIO_LIMITE)], "interrotto": True}

    grafo = StateGraph(Stato)
    grafo.add_node("modello", modello)
    grafo.add_node("strumenti", esegui_strumenti)
    grafo.add_node("limite", limite)
    grafo.add_edge(START, "modello")
    grafo.add_conditional_edges(
        "modello",
        lambda stato: instrada_dopo_modello(stato, max_passaggi),
        {"strumenti": "strumenti", "limite": "limite", "fine": END},
    )
    grafo.add_edge("strumenti", "modello")
    grafo.add_edge("limite", END)
    return grafo.compile().with_config(recursion_limit=max_passaggi * 2 + 10)
