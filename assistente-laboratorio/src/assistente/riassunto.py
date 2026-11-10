"""Riassunto della cronologia: i messaggi più vecchi diventano un riassunto prodotto dal modello."""

from collections.abc import Callable

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

CARATTERI_PER_TOKEN = 4  # stima grossolana, senza tokenizzatore
TURNI_RECENTI = 2  # turni completi tenuti intatti, oltre alla domanda corrente
# Margine per il ragionamento nascosto di gemma-4-e2b osservato nel revisore.
MAX_TOKEN_RIASSUNTO = 1024
PREFISSO_RIASSUNTO = "Riassunto della conversazione precedente: "

PROMPT_RIASSUNTO = """Riassumi in italiano la conversazione fra l'utente e l'assistente del \
laboratorio. Il riassunto serve all'assistente per continuare la conversazione.
- Conserva le richieste dell'utente e i dati ottenuti dagli strumenti: valori, orari, risultati, \
codici degli articoli, numeri delle note.
- Scrivi solo fatti presenti nella conversazione: non inventare nulla.
- Al massimo 10 frasi. Rispondi solo con il riassunto."""


def _testo(messaggio: AnyMessage) -> str:
    return str(messaggio.content)


def stima_token(messaggi: list[AnyMessage]) -> int:
    """Token stimati (caratteri / 4, per eccesso), tool call comprese."""
    caratteri = 0
    for m in messaggi:
        caratteri += len(_testo(m))
        if isinstance(m, AIMessage) and m.tool_calls:
            caratteri += len(str(m.tool_calls))
    return -(-caratteri // CARATTERI_PER_TOKEN)


def unisci(precedente: str, nuovo: str, limite_token: int) -> tuple[str, int]:
    """Riassunto precedente (alla lettera) seguito dal nuovo; oltre il limite toglie le righe più
    vecchie, mai l'ultima. Restituisce il testo e le righe tolte.

    La fusione è del codice: chiamato a integrare il riassunto precedente, gemma-4-e2b lo perdeva.
    """
    righe = [r for r in (*precedente.splitlines(), *nuovo.splitlines()) if r.strip()]
    tolte = 0
    while len(righe) > 1 and -(-len("\n".join(righe)) // CARATTERI_PER_TOKEN) > limite_token:
        righe.pop(0)
        tolte += 1
    return "\n".join(righe), tolte


def e_riassunto(messaggio: AnyMessage) -> bool:
    """Vero per il SystemMessage del riassunto in testa alla cronologia."""
    return isinstance(messaggio, SystemMessage) and _testo(messaggio).startswith(
        PREFISSO_RIASSUNTO
    )


def dividi(messaggi: list[AnyMessage]) -> tuple[list[AnyMessage], list[AnyMessage]]:
    """(vecchi, recenti): i recenti sono gli ultimi TURNI_RECENTI turni e la domanda corrente.

    Un turno comincia da una domanda dell'utente: il taglio cade su un HumanMessage, quindi
    ogni tool call resta col suo risultato.
    """
    domande = [i for i, m in enumerate(messaggi) if isinstance(m, HumanMessage)]
    if len(domande) < TURNI_RECENTI + 1:
        return [], list(messaggi)
    taglio = domande[-(TURNI_RECENTI + 1)]
    return list(messaggi[:taglio]), list(messaggi[taglio:])


def trascrivi(nuovi: list[AnyMessage]) -> str:
    """Messaggi da riassumere come testo, risultati degli strumenti compresi."""
    righe = []
    for m in nuovi:
        if isinstance(m, HumanMessage):
            righe.append(f"Utente: {_testo(m)}")
        elif isinstance(m, ToolMessage):
            righe.append(f"Strumento {m.name}: {_testo(m)}")
        elif isinstance(m, AIMessage) and _testo(m).strip():
            righe.append(f"Assistente: {_testo(m)}")
    return "\n".join(righe)


def crea_riassuntore(llm) -> Callable[[list[AnyMessage]], str]:
    """Riassuntore senza strumenti; le eccezioni passano al chiamante."""
    modello = llm.bind(max_tokens=MAX_TOKEN_RIASSUNTO)
    prompt = SystemMessage(PROMPT_RIASSUNTO)

    def riassuntore(nuovi: list[AnyMessage]) -> str:
        risposta = modello.invoke([prompt, HumanMessage(trascrivi(nuovi))])
        return str(risposta.content)

    return riassuntore
