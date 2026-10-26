"""Prova reale con LM Studio attivo: esclusa di default (marker `reale`).

Richiede LMSTUDIO_BASE_URL e LMSTUDIO_MODEL nell'ambiente. Lanciare con:
    python -m pytest -m reale -v
"""

import logging
from datetime import datetime, timezone

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from assistente.config import carica_config
from assistente.grafo import build_graph
from assistente.modello import crea_llm, verifica_modello

pytestmark = pytest.mark.reale


def test_il_modello_usa_lo_strumento_orologio(caplog):
    config = carica_config()
    verifica_modello(config)
    grafo = build_graph(
        crea_llm(config), lambda: datetime.now(timezone.utc), config.max_passaggi
    )

    with caplog.at_level(logging.INFO, logger="assistente.grafo"):
        stato = grafo.invoke(
            {
                "messaggi": [
                    HumanMessage("Che ore sono a Tokyo? Usa lo strumento orologio.")
                ],
                "passaggi": 0,
                "interrotto": False,
            }
        )

    assert "tool_call nome=ora_corrente" in caplog.text
    risultati = [m for m in stato["messaggi"] if isinstance(m, ToolMessage)]
    assert risultati, "nessun ToolMessage nello stato"
    assert any(not str(m.content).startswith("Errore:") for m in risultati)
    assert str(stato["messaggi"][-1].content).strip()
