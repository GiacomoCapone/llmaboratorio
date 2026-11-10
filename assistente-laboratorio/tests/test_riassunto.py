from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.riassunto import (
    MAX_TOKEN_RIASSUNTO,
    PREFISSO_RIASSUNTO,
    PROMPT_RIASSUNTO,
    crea_riassuntore,
    dividi,
    stima_token,
    trascrivi,
    unisci,
)
from finti import LlmFinto, richiesta_ora


def conversazione(n):
    """n turni completi: D1/R1 … Dn/Rn."""
    messaggi = []
    for i in range(1, n + 1):
        messaggi += [HumanMessage(f"D{i}"), AIMessage(f"R{i}")]
    return messaggi


def contenuti(messaggi):
    return [m.content for m in messaggi]


def test_stima_token():
    assert stima_token([HumanMessage("abcde")]) == 2  # 5 / 4 per eccesso
    assert stima_token([HumanMessage("abcd")]) == 1
    assert stima_token([]) == 0
    # una tool call conta anche senza testo
    assert stima_token([richiesta_ora("Asia/Tokyo")]) > stima_token([AIMessage("")])


def test_stima_contenuto_non_stringa():
    messaggio = ToolMessage(content=[{"type": "text", "text": "x"}], tool_call_id="c1")
    assert stima_token([messaggio]) > 0


def test_dividi_pochi_turni():
    messaggi = conversazione(2) + [HumanMessage("D3")]
    vecchi, recenti = dividi(messaggi)
    assert vecchi == []
    assert recenti == messaggi


def test_dividi_confine():
    vecchi, recenti = dividi(conversazione(4) + [HumanMessage("D5")])
    assert contenuti(vecchi) == ["D1", "R1", "D2", "R2"]
    assert contenuti(recenti) == ["D3", "R3", "D4", "R4", "D5"]


def test_dividi_tiene_le_coppie():
    chiamata = richiesta_ora("Asia/Tokyo")
    risultato = ToolMessage("21:00", tool_call_id="c1", name="ora_corrente")
    messaggi = (
        conversazione(2)
        + [HumanMessage("D3"), chiamata, risultato, AIMessage("R3")]
        + conversazione(1)
        + [HumanMessage("D5")]
    )
    vecchi, recenti = dividi(messaggi)
    assert chiamata in recenti and risultato in recenti
    assert contenuti(vecchi) == ["D1", "R1", "D2", "R2"]


def test_dividi_riassunto_precedente_fra_i_vecchi():
    riassunto = SystemMessage(PREFISSO_RIASSUNTO + "x")
    vecchi, recenti = dividi([riassunto] + conversazione(3) + [HumanMessage("D4")])
    assert vecchi[0] is riassunto
    assert contenuti(vecchi) == [riassunto.content, "D1", "R1"]
    assert contenuti(recenti)[0] == "D2"


def test_dividi_conta_il_turno_rifiutato():
    messaggi = (
        conversazione(2)
        + [HumanMessage("Scrivimi una poesia"), AIMessage("Posso rispondere solo ...")]
        + conversazione(1)
        + [HumanMessage("D5")]
    )
    vecchi, recenti = dividi(messaggi)
    assert contenuti(vecchi) == ["D1", "R1", "D2", "R2"]
    assert contenuti(recenti)[0] == "Scrivimi una poesia"


def test_unisci_concatena():
    assert unisci("a", "b", 100) == ("a\nb", 0)
    assert unisci("", "b", 100) == ("b", 0)


def test_unisci_toglie_le_righe_piu_vecchie():
    righe = ["x" * 40, "y" * 40, "z" * 40]
    # 40 caratteri = 10 token per riga: con limite 20 restano le ultime due
    assert unisci("\n".join(righe[:2]), righe[2], 21) == (righe[1] + "\n" + righe[2], 1)


def test_unisci_ignora_le_righe_vuote():
    # gemma-4-e2b separa i paragrafi con righe vuote: dopo un taglio non devono restare in testa.
    assert unisci("a\n\nb", "\nc\n", 100) == ("a\nb\nc", 0)


def test_unisci_tiene_l_ultima_riga():
    riga = "x" * 400
    assert unisci("", riga, 1) == (riga, 0)


def test_trascrivi():
    messaggi = [
        HumanMessage("Che ore sono?"),
        richiesta_ora("Asia/Tokyo"),
        ToolMessage("21:00", tool_call_id="c1", name="ora_corrente"),
        AIMessage("Sono le 21."),
    ]
    assert trascrivi(messaggi) == (
        "Utente: Che ore sono?\n"
        "Strumento ora_corrente: 21:00\n"
        "Assistente: Sono le 21."
    )


def test_crea_riassuntore():
    llm = LlmFinto([AIMessage("sintesi")])
    vecchi = conversazione(2)
    assert crea_riassuntore(llm)(vecchi) == "sintesi"
    assert llm.strumenti == []
    assert llm.opzioni_bind == {"max_tokens": MAX_TOKEN_RIASSUNTO}
    assert llm.con_strumenti == [False]
    assert llm.chiamate[0] == [SystemMessage(PROMPT_RIASSUNTO), HumanMessage(trascrivi(vecchi))]


def test_prompt_regole():
    for frammento in ("numeri delle note", "codici", "non inventare"):
        assert frammento in PROMPT_RIASSUNTO, frammento
    # Il modello non fonde i riassunti: chiamato a integrarli perdeva i fatti precedenti
    # (specifica, «Revisione del 2026-11-10»); la concatenazione è del codice.
    assert "riassunto precedente" not in PROMPT_RIASSUNTO.lower()
