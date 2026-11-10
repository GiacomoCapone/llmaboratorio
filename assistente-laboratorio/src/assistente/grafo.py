"""Grafo LangGraph dell'assistente: stato, nodi, instradamento."""

import logging
from collections.abc import Callable
from typing import Annotated, Literal, TypedDict
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from assistente.revisore import Valutazione
from assistente.router import Classificazione
from assistente.strumenti import Strumento

logger = logging.getLogger("assistente.grafo")

MESSAGGIO_LIMITE = (
    "Raggiunto il limite di passaggi con gli strumenti: "
    "la richiesta è stata interrotta senza una risposta finale."
)
ISTRUZIONE_RISPOSTA = "Rispondi all'utente riferendo il risultato degli strumenti."
MESSAGGIO_RIFIUTO = (
    "Posso rispondere solo a domande sul laboratorio e sui suoi strumenti. Motivo: {motivo}"
)
# L'utente non vede né la bozza scartata né l'indicazione: senza il divieto l'agente apriva
# con «Mi scuso per la risposta precedente».
INDICAZIONE_REVISORE = (
    "Indicazione del revisore (l'utente non la vede): la risposta precedente non è adeguata. "
    "Motivo: {motivo}. Scrivi una nuova risposta completa alla domanda dell'utente, senza "
    "citare la risposta precedente né questa indicazione."
)


class Stato(TypedDict):
    messaggi: Annotated[list[AnyMessage], add_messages]
    passaggi: int
    interrotto: bool
    categoria: str  # scritti dal nodo router
    motivo: str
    revisioni: int  # volte in cui la risposta è tornata all'agente nel turno
    scartati: list[str]  # id di bozze rifiutate e indicazioni, rimossi a fine turno
    esito_revisione: str  # "agente" | "fine", scritto dal nodo revisore


def instrada_dopo_revisore(stato: Stato) -> Literal["agente", "fine"]:
    """Segue la decisione del nodo revisore (che applica il limite di revisioni)."""
    return "agente" if stato["esito_revisione"] == "agente" else "fine"


def instrada_dopo_router(stato: Stato) -> Literal["agente", "rifiuto"]:
    """Le domande fuori ambito vanno al rifiuto, tutte le altre all'agente."""
    return "rifiuto" if stato["categoria"] == "fuori_ambito" else "agente"


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


def _vuota(risposta) -> bool:
    """Risposta senza tool call e senza testo (stringa vuota o di soli spazi, o lista vuota)."""
    if getattr(risposta, "tool_calls", None) or getattr(risposta, "invalid_tool_calls", None):
        return False
    contenuto = risposta.content
    return not contenuto.strip() if isinstance(contenuto, str) else not contenuto


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


def build_graph(
    llm,
    strumenti: dict[str, Strumento],
    max_passaggi: int,
    router: Callable[[list[AnyMessage]], Classificazione],
    revisore: Callable[[list[AnyMessage]], Valutazione],
    max_revisioni: int,
):
    """Costruisce e compila il grafo router / rifiuto / modello / strumenti / limite / revisore."""
    llm_con_strumenti = llm.bind_tools([s.definizione for s in strumenti.values()])

    def nodo_router(stato: Stato) -> dict:
        esito = router(stato["messaggi"])
        destinazione = instrada_dopo_router({"categoria": esito.categoria})
        logger.info(
            "router categoria=%s motivo=%s → %s", esito.categoria, esito.motivo, destinazione
        )
        return {"categoria": esito.categoria, "motivo": esito.motivo}

    def rifiuto(stato: Stato) -> dict:
        return {"messaggi": [AIMessage(MESSAGGIO_RIFIUTO.format(motivo=stato["motivo"]))]}

    def nodo_revisore(stato: Stato) -> dict:
        scartati = list(stato.get("scartati") or [])
        revisioni = stato.get("revisioni", 0)
        valutazione = revisore([m for m in stato["messaggi"] if m.id not in scartati])
        if not valutazione.coerente and revisioni < max_revisioni:
            revisioni += 1
            logger.info(
                "revisore coerente=no motivo=%s → agente (revisione %d/%d)",
                valutazione.motivo,
                revisioni,
                max_revisioni,
            )
            indicazione = HumanMessage(
                INDICAZIONE_REVISORE.format(motivo=valutazione.motivo), id=str(uuid4())
            )
            return {
                "messaggi": [indicazione],
                "scartati": [*scartati, stato["messaggi"][-1].id, indicazione.id],
                "revisioni": revisioni,
                "esito_revisione": "agente",
            }
        logger.info(
            "revisore coerente=%s motivo=%s → fine",
            "sì" if valutazione.coerente else "no",
            valutazione.motivo,
        )
        if not valutazione.coerente:
            logger.warning(
                "limite di revisioni raggiunto (%d): restituita l'ultima risposta", max_revisioni
            )
        # La cronologia conserva domanda, strumenti e risposta finale: bozze e indicazioni no.
        return {
            "messaggi": [RemoveMessage(id=i) for i in scartati],
            "scartati": [],
            "esito_revisione": "fine",
        }

    def modello(stato: Stato) -> dict:
        logger.info("agente: chiamata al modello")
        risposta = llm_con_strumenti.invoke(stato["messaggi"])
        # Con più strumenti collegati alcuni modelli piccoli (gemma-4-e2b) rispondono ai
        # risultati con un testo vuoto: si richiama una volta il modello senza strumenti, con in
        # testa un'istruzione di sistema che non entra nello stato né nella cronologia.
        if isinstance(stato["messaggi"][-1], ToolMessage) and _vuota(risposta):
            logger.warning(
                "risposta vuota dopo gli strumenti: nuova chiamata senza strumenti"
            )
            risposta = llm.invoke(
                [SystemMessage(ISTRUZIONE_RISPOSTA), *stato["messaggi"]]
            )
        return {"messaggi": [risposta]}

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
    grafo.add_node("router", nodo_router)
    grafo.add_node("rifiuto", rifiuto)
    grafo.add_node("modello", modello)
    grafo.add_node("strumenti", esegui_strumenti)
    grafo.add_node("limite", limite)
    grafo.add_node("revisore", nodo_revisore)
    grafo.add_edge(START, "router")
    grafo.add_conditional_edges(
        "router", instrada_dopo_router, {"agente": "modello", "rifiuto": "rifiuto"}
    )
    grafo.add_edge("rifiuto", END)
    grafo.add_conditional_edges(
        "modello",
        lambda stato: instrada_dopo_modello(stato, max_passaggi),
        {"strumenti": "strumenti", "limite": "limite", "fine": "revisore"},
    )
    grafo.add_conditional_edges(
        "revisore", instrada_dopo_revisore, {"agente": "modello", "fine": END}
    )
    grafo.add_edge("strumenti", "modello")
    grafo.add_edge("limite", END)
    return grafo.compile().with_config(
        recursion_limit=max_passaggi * 2 + 12 + 2 * (max_revisioni + 1)
    )
