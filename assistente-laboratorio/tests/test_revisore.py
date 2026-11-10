import logging

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.revisore import (
    MAX_TOKEN_REVISORE,
    PROMPT_REVISORE,
    Giudizio,
    Valutazione,
    crea_revisore,
)
from finti import LlmFinto, richiesta

DOMANDA = HumanMessage("Che ore sono a Tokyo e quanto fa 12 * 4?")
PARZIALE = AIMessage("A Tokyo sono le 21.")


def giudica(richieste=("ora a Tokyo", "12 * 4"), mancanti=("12 * 4",)):
    """Risposta del modello: tool call verso lo strumento Giudizio."""
    return richiesta("Giudizio", {"richieste": list(richieste), "mancanti": list(mancanti)})


def test_usa_tool_obbligatorio_con_limite_di_token():
    llm = LlmFinto([giudica()])
    crea_revisore(llm)
    assert llm.strumenti == [Giudizio]
    # gemma-4-e2b a volte ragiona ~300 token prima della tool call
    assert MAX_TOKEN_REVISORE == 1024
    assert llm.opzioni_strumenti == {"tool_choice": "required", "max_tokens": MAX_TOKEN_REVISORE}


def test_prompt_e_messaggi():
    # LM Studio rifiuta (HTTP 400, "empty grammar stack") una tool call obbligatoria quando
    # l'ultimo messaggio è dell'assistente: domanda e risposta vanno in un solo messaggio utente.
    llm = LlmFinto([giudica()])
    risultato = crea_revisore(llm)([DOMANDA, PARZIALE])
    assert risultato == Valutazione(coerente=False, motivo="manca la risposta a: 12 * 4")
    inviati = llm.chiamate[0]
    assert inviati[0] == SystemMessage(PROMPT_REVISORE)
    assert len(inviati) == 2 and isinstance(inviati[1], HumanMessage)
    assert inviati[1].content == (
        f"Domanda dell'utente: {DOMANDA.content}\n"
        f"Risposta proposta dall'assistente: {PARZIALE.content}"
    )


def test_trascrive_i_messaggi_precedenti():
    llm = LlmFinto([giudica(mancanti=())])
    crea_revisore(llm)(
        [HumanMessage("Che ore sono a Roma?"), AIMessage("Le 13."), HumanMessage("e a Londra?"),
         AIMessage("A Londra sono le 12.")]
    )
    assert llm.chiamate[0][1].content == (
        "Conversazione precedente:\n"
        "Utente: Che ore sono a Roma?\n"
        "Assistente: Le 13.\n\n"
        "Domanda dell'utente: e a Londra?\n"
        "Risposta proposta dall'assistente: A Londra sono le 12."
    )


def test_esclude_messaggi_degli_strumenti():
    chiamata = AIMessage(content="", tool_calls=[{"name": "ora", "args": {}, "id": "c1"}])
    risultato = ToolMessage(content="21:00", tool_call_id="c1")
    llm = LlmFinto([giudica(mancanti=())])
    crea_revisore(llm)([DOMANDA, chiamata, risultato, PARZIALE])
    assert "21:00" not in llm.chiamate[0][1].content  # il risultato dello strumento
    assert llm.chiamate[0][1].content.startswith("Domanda dell'utente:")


def test_nessuna_mancante_coerente():
    risultato = crea_revisore(LlmFinto([giudica(mancanti=())]))([DOMANDA, PARZIALE])
    assert risultato == Valutazione(coerente=True, motivo="richieste trattate: ora a Tokyo; 12 * 4")


def test_mancanti_vuote_ignorate():
    risultato = crea_revisore(LlmFinto([giudica(mancanti=("", "  "))]))([DOMANDA, PARZIALE])
    assert risultato.coerente is True


def test_prompt_regole():
    for frammento in ("richieste", "mancanti", "Non verificare"):
        assert frammento in PROMPT_REVISORE, frammento
    # Regole misurate con gemma-4-e2b e scartate (specifica, «Revisione del 2026-11-10»): sulle
    # domande di seguito fa approvare le risposte parziali; su «dice di non poterlo fare» fa
    # rifiutare le risposte complete.
    assert "di seguito" not in PROMPT_REVISORE
    assert "non poterlo fare" not in PROMPT_REVISORE


class LlmGuasto(LlmFinto):
    def _rispondi(self, messaggi, con_strumenti):
        raise RuntimeError("guasto")


@pytest.mark.parametrize(
    "llm",
    [
        LlmGuasto([]),
        LlmFinto([AIMessage("sì")]),  # testo invece della tool call
        LlmFinto([richiesta("Giudizio", {"richieste": ["x"]})]),  # manca mancanti
    ],
)
def test_guasto_approva(caplog, llm):
    with caplog.at_level(logging.WARNING, logger="assistente.revisore"):
        risultato = crea_revisore(llm)([DOMANDA, PARZIALE])
    assert risultato.coerente is True
    assert "revisore non disponibile" in caplog.text


@pytest.mark.parametrize(
    "messaggi",
    [
        [DOMANDA, AIMessage("")],
        [HumanMessage("Roma?"), AIMessage("Le 13."), DOMANDA, AIMessage("  ")],
        [DOMANDA],
        [],
    ],
)
def test_risposta_vuota_rimandata_senza_modello(messaggi):
    # ultimi_messaggi scarta le risposte vuote: senza il controllo la domanda finirebbe
    # trascritta come «risposta proposta».
    llm = LlmFinto([giudica(mancanti=())])
    risultato = crea_revisore(llm)(messaggi)
    assert risultato == Valutazione(coerente=False, motivo="risposta vuota")
    assert llm.chiamate == []
