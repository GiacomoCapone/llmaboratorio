"""Revisore delle risposte: giudica se la risposta proposta dall'agente è completa e pertinente.

Il modello elenca le richieste della domanda e quelle rimaste senza risposta; la coerenza la decide
il codice. Un giudizio diretto «coerente sì/no» faceva rifiutare a gemma-4-e2b risposte corrette
(formato, dettagli non chiesti): vedi la specifica, «Revisione del 2026-11-10».
"""

import logging
from collections.abc import Callable

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from assistente.router import ultimi_messaggi

logger = logging.getLogger("assistente.revisore")

# Il giudizio occupa poche decine di token, ma gemma-4-e2b a volte ragiona fino a ~300 token
# nonostante reasoning_effort=none: con 256 la tool call veniva troncata (finish_reason=length).
MAX_TOKEN_REVISORE = 1024

PROMPT_REVISORE = """Sei il revisore dell'assistente del laboratorio. Non rispondi all'utente. \
Rispondi chiamando lo strumento Giudizio.
1. In "richieste" elenca le cose che l'utente chiede nell'ULTIMA domanda (di solito una sola).
2. In "mancanti" elenca le richieste a cui l'ULTIMA risposta dell'assistente non risponde affatto \
o risponde parlando d'altro.
Una richiesta ha risposta anche se la risposta è breve, contiene un dato grezzo, dice che non ci \
sono risultati o riferisce un errore. Non verificare l'esattezza dei dati e non chiedere \
spiegazioni, fonti o dettagli in più."""


class Giudizio(BaseModel):
    """Strumento chiesto al modello."""

    richieste: list[str] = Field(
        description="le cose che l'utente chiede nell'ultima domanda, una per elemento"
    )
    mancanti: list[str] = Field(
        description=(
            "le richieste a cui la risposta non dà alcuna risposta; vuota se le tratta tutte"
        )
    )


class Valutazione(BaseModel):
    """Esito restituito al grafo."""

    coerente: bool
    motivo: str


def valuta(giudizio: Giudizio) -> Valutazione:
    """Coerente se nessuna richiesta è rimasta senza risposta (voci vuote ignorate)."""
    mancanti = [m.strip() for m in giudizio.mancanti if m.strip()]
    if mancanti:
        return Valutazione(coerente=False, motivo="manca la risposta a: " + "; ".join(mancanti))
    return Valutazione(coerente=True, motivo="richieste trattate: " + "; ".join(giudizio.richieste))


def trascrivi(messaggi: list[AnyMessage]) -> str:
    """Domanda e risposta da valutare (con i messaggi precedenti) come testo per il revisore."""
    *precedenti, domanda, risposta = messaggi if len(messaggi) >= 2 else [None, *messaggi]
    righe = []
    if precedenti:
        righe.append("Conversazione precedente:")
        for m in precedenti:
            chi = "Utente" if isinstance(m, HumanMessage) else "Assistente"
            righe.append(f"{chi}: {m.content}")
        righe.append("")
    if domanda is not None:
        righe.append(f"Domanda dell'utente: {domanda.content}")
    righe.append(f"Risposta proposta dall'assistente: {risposta.content}")
    return "\n".join(righe)


def crea_revisore(llm) -> Callable[[list[AnyMessage]], Valutazione]:
    """Revisore con output strutturato; un guasto approva la risposta."""
    # Strumento obbligatorio, come il router: con response_format json_schema LM Studio ignora
    # reasoning_effort=none e accetta tool_choice solo come stringa.
    valutatore = llm.bind_tools(
        [Giudizio], tool_choice="required", max_tokens=MAX_TOKEN_REVISORE
    )
    prompt = SystemMessage(PROMPT_REVISORE)

    def revisore(messaggi: list[AnyMessage]) -> Valutazione:
        # Risposta vuota: torna all'agente senza chiamare il modello (ultimi_messaggi la
        # scarterebbe e la domanda verrebbe trascritta come risposta proposta).
        if not messaggi or not isinstance(messaggi[-1], AIMessage) or not str(
            messaggi[-1].content
        ).strip():
            return Valutazione(coerente=False, motivo="risposta vuota")
        try:
            # Un solo messaggio utente: con l'ultimo messaggio dell'assistente e la tool call
            # obbligatoria LM Studio risponde HTTP 400 ("empty grammar stack").
            testo = trascrivi(ultimi_messaggi(messaggi))
            risposta = valutatore.invoke([prompt, HumanMessage(testo)])
            if not risposta.tool_calls:
                raise ValueError(f"nessuna valutazione: {risposta.content!r}")
            return valuta(Giudizio.model_validate(risposta.tool_calls[0]["args"]))
        except Exception as errore:  # il revisore non deve bloccare l'assistente
            logger.warning("revisore non disponibile: %s", errore)
            return Valutazione(coerente=True, motivo="revisore non disponibile")

    return revisore
