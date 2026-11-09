"""Prove reali con LM Studio attivo: escluse di default (marker `reale`).

Richiedono LMSTUDIO_BASE_URL e LMSTUDIO_MODEL nell'ambiente. Lanciare con:
    python -m pytest -m reale -v -s
(`-s` mostra i tempi di ogni turno.)
"""

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

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
        crea_strumenti(
            lambda: datetime.now(timezone.utc), config.fuso_predefinito, config.citta_patrono
        ),
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


@pytest.mark.parametrize(
    "domanda, risultato, forme",
    [
        (
            "Quanti giorni lavorativi ci sono dal 1° al 31 dicembre 2026?",
            "20 lavorativi",
            ("20",),
        ),
        (
            "Che data è 10 giorni lavorativi dopo il 18 dicembre 2026?",
            "2027-01-05",
            ("5 gennaio 2027", "2027-01-05"),
        ),
    ],
)
def test_il_modello_usa_il_calendario(caplog, domanda, risultato, forme):
    stato, validi = esegui_domanda(domanda, caplog)
    assert "tool_call nome=calendario" in caplog.text
    assert any(risultato in v for v in validi), f"nessun ToolMessage con {risultato!r}: {validi}"
    finale = str(stato["messaggi"][-1].content)
    assert any(f in finale for f in forme), f"risposta senza il risultato: {finale!r}"


def verifica_catena(caplog, domanda):
    config = carica_config()
    _, validi = esegui_domanda(domanda, caplog)
    orologio = caplog.text.find("tool_call nome=ora_corrente")
    calendario = caplog.text.find("tool_call nome=calendario")
    assert orologio != -1, "ora_corrente non chiamato"
    assert calendario != -1, "calendario non chiamato"
    assert orologio < calendario, "calendario chiamato prima di ora_corrente"
    atteso = (
        datetime.now(ZoneInfo(config.fuso_predefinito)).date() + timedelta(days=30)
    ).isoformat()
    assert any(" = " in v and v.split(" = ", 1)[1].startswith(atteso) for v in validi), (
        f"nessun ToolMessage con arrivo {atteso}: {validi}"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "gemma-4-e2b, contesto nuovo: non chiama ora_corrente e chiede la data "
        "(limite noto del modello, vedi README)"
    ),
)
def test_catena_orologio_calendario(caplog):
    verifica_catena(caplog, "Che giorno sarà fra 30 giorni?")


def test_catena_orologio_calendario_con_oggi(caplog):
    verifica_catena(caplog, "Che giorno sarà tra 30 giorni a partire da oggi?")


def chiamate_strumenti(stato):
    return [c for m in stato["messaggi"] if isinstance(m, AIMessage) for c in m.tool_calls]


def test_il_modello_usa_il_meteo(caplog):
    stato, validi = esegui_domanda("Che tempo fa a Trieste?", caplog)
    chiamate = [
        c
        for c in chiamate_strumenti(stato)
        if c["name"] == "meteo_attuale" and "trieste" in str(c["args"].get("localita", "")).lower()
    ]
    assert chiamate, f"meteo_attuale non chiamato per Trieste: {chiamate_strumenti(stato)}"
    risultati = [
        str(m.content) for m in stato["messaggi"] if isinstance(m, ToolMessage)
    ]
    assert not any(r.startswith("Errore:") for r in risultati), risultati
    meteo = [v for v in validi if v.startswith("Luogo:")]
    assert meteo, f"nessun ToolMessage valido con 'Luogo:': {validi}"
    trovato = re.search(r"Temperatura: (-?\d+(?:,\d+)?) °C", meteo[0])
    assert trovato, f"riga Temperatura assente: {meteo[0]!r}"
    t = float(trovato.group(1).replace(",", "."))
    finale = str(stato["messaggi"][-1].content)
    candidati = {str(abs(int(t))), str(abs(round(t))), f"{abs(t):.1f}".replace(".", ",")}
    candidati.add(f"{abs(t):.1f}")
    modello = "|".join(re.escape(c) for c in sorted(candidati, key=len, reverse=True))
    assert re.search(rf"(?<![\d.,])(?:{modello})(?!\d)", finale), (
        f"risposta senza la temperatura {t} (cercati {sorted(candidati)} a confini di cifra): "
        f"{finale!r}"
    )


def test_osserva_domanda_di_previsione(caplog):
    stato, _ = esegui_domanda("Che tempo farà domani a Trieste?", caplog)
    print("strumenti chiamati:", [(c["name"], c["args"]) for c in chiamate_strumenti(stato)])
    print("risposta finale:", stato["messaggi"][-1].content)
