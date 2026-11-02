"""Prove reali con LM Studio attivo: escluse di default (marker `reale`).

Richiedono LMSTUDIO_BASE_URL e LMSTUDIO_MODEL nell'ambiente. Lanciare con:
    python -m pytest -m reale -v -s
(`-s` mostra i tempi di ogni turno.)
"""

import logging
import time
from datetime import datetime, timezone

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from assistente.config import carica_config
from assistente.grafo import build_graph
from assistente.modello import crea_llm, verifica_modello
from assistente.strumenti import crea_strumenti

pytestmark = pytest.mark.reale


def esegui_domanda(domanda, caplog):
    """Esegue un turno con il grafo vero; restituisce lo stato e i risultati validi degli strumenti."""
    config = carica_config()
    verifica_modello(config)
    grafo = build_graph(
        crea_llm(config),
        crea_strumenti(lambda: datetime.now(timezone.utc), config.fuso_predefinito),
        config.max_passaggi,
    )
    inizio = time.perf_counter()
    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        stato = grafo.invoke(
            {"messaggi": [HumanMessage(domanda)], "passaggi": 0, "interrotto": False}
        )
    print(f"\n[{domanda!r}] turno completato in {time.perf_counter() - inizio:.1f} s")
    assert not stato["interrotto"], "limite di passaggi raggiunto"
    assert str(stato["messaggi"][-1].content).strip()
    validi = [
        str(m.content)
        for m in stato["messaggi"]
        if isinstance(m, ToolMessage) and not str(m.content).startswith("Errore:")
    ]
    return stato, validi


@pytest.mark.parametrize(
    "domanda, offset",
    [
        ("che ore sono", None),
        ("Che giorno è oggi?", None),
        ("Che ore sono a Tokyo?", "+09:00"),
    ],
)
def test_il_modello_usa_lo_strumento_orologio(caplog, domanda, offset):
    _, validi = esegui_domanda(domanda, caplog)
    assert "tool_call nome=ora_corrente" in caplog.text
    assert validi, "nessun risultato valido dello strumento"
    if offset:
        assert any(offset in v for v in validi), f"nessun risultato con l'offset {offset}"


@pytest.mark.parametrize(
    "domanda, risultato, forme",
    [
        ("Quanto fa 12,5 * 4?", "50", ("50",)),
        ("Quanto fa (3 + 7) / 4?", "2.5", ("2,5", "2.5")),
    ],
)
def test_il_modello_usa_la_calcolatrice(caplog, domanda, risultato, forme):
    stato, validi = esegui_domanda(domanda, caplog)
    assert "tool_call nome=calcola" in caplog.text
    assert risultato in validi, f"nessun ToolMessage uguale a {risultato!r}: {validi}"
    finale = str(stato["messaggi"][-1].content)
    assert any(f in finale for f in forme), f"risposta senza il risultato: {finale!r}"


@pytest.mark.parametrize(
    "domanda, risultato, forme",
    [
        ("Quanti metri sono 2,5 km?", "2500 m", ("2500", "2.500")),
        ("Quanti gradi Celsius sono 300 K?", "26.85 °C", ("26,85", "26.85")),
    ],
)
def test_il_modello_usa_il_convertitore(caplog, domanda, risultato, forme):
    stato, validi = esegui_domanda(domanda, caplog)
    assert "tool_call nome=converti_unita" in caplog.text
    assert risultato in validi, f"nessun ToolMessage uguale a {risultato!r}: {validi}"
    finale = str(stato["messaggi"][-1].content)
    assert any(f in finale for f in forme), f"risposta senza il risultato: {finale!r}"
