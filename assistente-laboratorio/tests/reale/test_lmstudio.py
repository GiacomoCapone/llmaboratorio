"""Prova reale con LM Studio attivo: esclusa di default (marker `reale`).

Richiede LMSTUDIO_BASE_URL e LMSTUDIO_MODEL nell'ambiente. Lanciare con:
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


@pytest.mark.parametrize(
    "domanda, offset",
    [
        ("che ore sono", None),
        ("Che giorno è oggi?", None),
        ("Che ore sono a Tokyo?", "+09:00"),
    ],
)
def test_il_modello_usa_lo_strumento_orologio(caplog, domanda, offset):
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
    assert "tool_call nome=ora_corrente" in caplog.text
    validi = [
        str(m.content)
        for m in stato["messaggi"]
        if isinstance(m, ToolMessage) and not str(m.content).startswith("Errore:")
    ]
    assert validi, "nessun risultato valido dello strumento"
    if offset:
        assert any(offset in v for v in validi), f"nessun risultato con l'offset {offset}"
    assert str(stato["messaggi"][-1].content).strip()
