"""Router di ambito: classifica la domanda dell'utente prima che raggiunga l'agente."""

import logging
from collections.abc import Callable
from typing import Literal, get_args

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

logger = logging.getLogger("assistente.router")

MAX_MESSAGGI_ROUTER = 4
# La classificazione occupa poche decine di token: il tetto interrompe in pochi secondi un modello
# che si dilunga, e il router ripiega su "conversazione".
MAX_TOKEN_ROUTER = 256

PROMPT_ROUTER = """Sei il router dell'assistente del laboratorio. Non rispondi alle domande: classifichi soltanto l'ULTIMO messaggio dell'utente (domanda o richiesta, anche all'imperativo) in base all'ARGOMENTO, confrontandolo con l'ambito descritto qui sotto.

Ambito dell'assistente:
{ambito}

Rispondi chiamando lo strumento Classificazione. Il campo "categoria" vale ESATTAMENTE "conversazione" oppure "fuori_ambito", nient'altro; l'argomento della richiesta va nel campo "motivo".

Regole:
- "conversazione": l'argomento rientra nell'ambito; anche saluti, ringraziamenti e domande su chi è l'assistente e su che cosa sa fare.
- "fuori_ambito": l'argomento non rientra nell'ambito.
- Giudica solo l'argomento. Non chiederti se l'assistente conosce la data, l'ora o altri dati, né se ha gli strumenti per rispondere: l'assistente ha i suoi strumenti e lo decide lui.
- I messaggi precedenti servono solo a capire le domande di seguito (per esempio "e a Londra?").
- "motivo": una frase breve in italiano, con parole separate da spazi."""


Categoria = Literal["conversazione", "fuori_ambito"]
CATEGORIE = get_args(Categoria)


class Classificazione(BaseModel):
    categoria: Categoria = Field(
        description=(
            '"conversazione" se rientra nell\'ambito, "fuori_ambito" se non rientra; '
            "mai l'argomento"
        )
    )
    motivo: str = Field(description="motivo breve della classificazione, in italiano")


def ultimi_messaggi(
    messaggi: list[AnyMessage], n: int = MAX_MESSAGGI_ROUTER
) -> list[AnyMessage]:
    """Ultimi `n` messaggi fra utente e assistente, senza i passaggi con gli strumenti."""
    scelti = [
        m
        for m in messaggi
        if isinstance(m, HumanMessage)
        or (isinstance(m, AIMessage) and not m.tool_calls and str(m.content).strip())
    ]
    return scelti[-n:]


def crea_router(llm, ambito: str) -> Callable[[list[AnyMessage]], Classificazione]:
    """Router con output strutturato; un guasto lascia passare la domanda all'agente."""
    # Tool obbligatorio e non json_schema: con lo schema in response_format LM Studio ignora
    # reasoning_effort=none e gemma-4-e2b ragiona per migliaia di token (minuti per domanda).
    # tool_choice è la stringa "required": LM Studio non accetta la forma a oggetto che
    # with_structured_output(method="function_calling") invierebbe.
    classificatore = llm.bind_tools(
        [Classificazione], tool_choice="required", max_tokens=MAX_TOKEN_ROUTER
    )
    prompt = SystemMessage(PROMPT_ROUTER.format(ambito=ambito))

    def router(messaggi: list[AnyMessage]) -> Classificazione:
        try:
            risposta = classificatore.invoke([prompt, *ultimi_messaggi(messaggi)])
            if not risposta.tool_calls:
                raise ValueError(f"nessuna classificazione: {risposta.content!r}")
            args = risposta.tool_calls[0]["args"]
            categoria = args.get("categoria")
            if isinstance(categoria, str):
                # Varianti di scrittura ("Fuori ambito", "fuori-ambito") valgono il valore giusto.
                normale = categoria.strip().lower().replace(" ", "_").replace("-", "_")
                # Un modello piccolo scrive a volte l'argomento al posto della categoria, ma solo
                # per le domande in ambito: un testo diverso dai due valori vale "conversazione".
                if normale not in CATEGORIE:
                    logger.warning(
                        "categoria non valida %r: considerata conversazione", categoria
                    )
                    normale = "conversazione"
                args = {**args, "categoria": normale}
            return Classificazione.model_validate(args)
        except Exception as errore:  # il router non deve bloccare l'assistente
            logger.warning("router non disponibile: %s", errore)
            return Classificazione(categoria="conversazione", motivo="router non disponibile")

    return router
