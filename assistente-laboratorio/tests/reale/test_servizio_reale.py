"""Prove reali del servizio HTTP con LM Studio attivo: escluse di default (marker `reale`).

Richiedono LMSTUDIO_BASE_URL e LMSTUDIO_MODEL nell'ambiente. Lanciare con:
    python -m pytest -m reale -v -s -k servizio
(`-s` mostra le chiamate agli strumenti di ogni turno.)
"""

import dataclasses
import time

import pytest
from starlette.testclient import TestClient

from assistente.avvio import apri_assistente
from assistente.config import carica_config
from assistente.modello import verifica_modello
from assistente.servizio import crea_app

pytestmark = pytest.mark.reale


@pytest.fixture
def client(tmp_path):
    """Client di prova sull'app vera: modello, strumenti e archivio MCP con un database temporaneo."""
    config = dataclasses.replace(carica_config(), note_db=tmp_path / "note.db")
    verifica_modello(config)
    with apri_assistente(config) as (grafo, archivio):
        yield TestClient(crea_app(grafo, archivio))


def chiamate_della_cronologia(cronologia):
    """Chiamate agli strumenti degli AIMessage di una cronologia serializzata."""
    return [
        (c["name"], c["args"])
        for m in cronologia
        if m["type"] == "ai"
        for c in m["data"].get("tool_calls", [])
    ]


def test_servizio_turni_concatenati(client):
    inizio = time.perf_counter()
    primo = client.post(
        "/turno", json={"domanda": "Annota che il multimetro MIS-001 ha la batteria scarica"}
    )
    assert primo.status_code == 200, primo.text
    print("\nchiamate turno 1:", chiamate_della_cronologia(primo.json()["cronologia"]))
    secondo = client.post(
        "/turno",
        json={"domanda": "Quali note ci sono?", "cronologia": primo.json()["cronologia"]},
    )
    assert secondo.status_code == 200, secondo.text
    corpo = secondo.json()
    chiamate = chiamate_della_cronologia(corpo["cronologia"])
    print("chiamate turno 2 (cronologia completa):", chiamate)
    print(f"risposta: {corpo['risposta']!r} ({time.perf_counter() - inizio:.1f} s)")
    assert any(nome == "elenca_note" for nome, _ in chiamate), f"elenca_note non chiamato: {chiamate}"
    assert "batteria" in corpo["risposta"].lower(), corpo["risposta"]


def test_servizio_prompt_scheda_articolo(client):
    inizio = time.perf_counter()
    risposta = client.post(
        "/turno",
        json={"prompt": {"nome": "scheda_articolo", "argomenti": {"codice": "MIS-001"}}},
    )
    assert risposta.status_code == 200, risposta.text
    corpo = risposta.json()
    chiamate = chiamate_della_cronologia(corpo["cronologia"])
    print("\nchiamate:", chiamate)
    print(f"risposta: {corpo['risposta']!r} ({time.perf_counter() - inizio:.1f} s)")
    assert any(
        nome == "dettaglio_articolo" and "MIS-001" in str(args.get("codice", "")).upper()
        for nome, args in chiamate
    ), f"dettaglio_articolo non chiamato con MIS-001: {chiamate}"
