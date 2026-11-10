"""Prove reali con LM Studio attivo: escluse di default (marker `reale`).

Richiedono LMSTUDIO_BASE_URL e LMSTUDIO_MODEL nell'ambiente. Lanciare con:
    python -m pytest -m reale -v -s
(`-s` mostra i tempi di ogni turno.)
"""

import logging
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from assistente.config import carica_config
from archivio.inventario import PERCORSO_INVENTARIO, carica
from archivio.note import apri
from assistente.grafo import build_graph
from assistente.mcp_client import ClientArchivio
from assistente.modello import crea_llm, verifica_modello
from assistente.revisore import crea_revisore
from assistente.router import crea_router
from assistente.strumenti import crea_strumenti

pytestmark = pytest.mark.reale


def esegui_domanda(
    domanda, caplog, note_db: Path | None = None, categoria_attesa: str = "conversazione"
):
    """Esegue un turno con il grafo vero; restituisce lo stato e i risultati validi degli strumenti.

    `note_db`: file delle note (anche già popolato); se None, un file in una cartella temporanea.
    `categoria_attesa`: classificazione che il router deve dare alla domanda.
    """
    config = carica_config()
    verifica_modello(config)
    inizio = time.perf_counter()
    with tempfile.TemporaryDirectory() as cartella, ClientArchivio(
        ambiente={"NOTE_DB": str(note_db or Path(cartella) / "note.db")}
    ) as archivio:
        llm = crea_llm(config)
        grafo = build_graph(
            llm,
            crea_strumenti(
                lambda: datetime.now(timezone.utc),
                config.fuso_predefinito,
                config.citta_patrono,
                esterni=archivio.strumenti(),
            ),
            config.max_passaggi,
            crea_router(llm, config.ambito),
            crea_revisore(llm),
            config.max_revisioni,
        )
        with caplog.at_level(logging.INFO, logger="assistente"):
            stato = grafo.invoke(
                {
                    "messaggi": [HumanMessage(domanda)],
                    "passaggi": 0,
                    "interrotto": False,
                    "revisioni": 0,
                    "scartati": [],
                    "esito_revisione": "",
                }
            )
    print(
        f"\n[{domanda!r}] turno completato in {time.perf_counter() - inizio:.1f} s"
        f" (revisioni: {stato.get('revisioni', 0)})"
    )
    assert stato["categoria"] == categoria_attesa, stato["motivo"]
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


def risultati_strumenti(stato):
    return [str(m.content) for m in stato["messaggi"] if isinstance(m, ToolMessage)]


def test_il_modello_usa_il_catalogo_per_cercare(caplog):
    stato, _ = esegui_domanda("Abbiamo dei multimetri? Dove sono?", caplog)
    chiamate = chiamate_strumenti(stato)
    risultati = risultati_strumenti(stato)
    assert any(c["name"] == "cerca_inventario" for c in chiamate), (
        f"cerca_inventario non chiamato: {chiamate}"
    )
    assert any(r.startswith("Trovat") for r in risultati), (
        f"nessun ToolMessage che inizia con 'Trovat': {risultati}"
    )
    assert not any(r.startswith("Errore:") for r in risultati), risultati
    collocazione = next(
        a.collocazione for a in carica(PERCORSO_INVENTARIO).articoli if a.codice == "MIS-001"
    )
    finale = str(stato["messaggi"][-1].content)
    assert collocazione.lower() in finale.lower(), (
        f"risposta senza la collocazione {collocazione!r}: {finale!r} (chiamate: {chiamate})"
    )


def test_il_modello_usa_il_dettaglio(caplog):
    stato, _ = esegui_domanda("Dammi i dettagli dell'articolo MIS-001", caplog)
    chiamate = chiamate_strumenti(stato)
    risultati = risultati_strumenti(stato)
    assert any(
        c["name"] == "dettaglio_articolo"
        and str(c["args"].get("codice", "")).lower() == "mis-001"
        for c in chiamate
    ), f"dettaglio_articolo non chiamato con MIS-001: {chiamate}"
    assert any(r.startswith("Codice: MIS-001") for r in risultati), (
        f"nessun ToolMessage che inizia con 'Codice: MIS-001': {risultati}"
    )


def test_il_modello_cerca_per_categoria(caplog):
    stato, _ = esegui_domanda("Che cosa c'è fra gli strumenti di misura?", caplog)
    chiamate = chiamate_strumenti(stato)
    risultati = risultati_strumenti(stato)
    assert any(
        c["name"] == "cerca_inventario"
        and (
            "misura" in str(c["args"].get("categoria", "")).lower()
            or "misura" in str(c["args"].get("testo", "")).lower()
        )
        for c in chiamate
    ), f"cerca_inventario senza 'misura' in categoria o testo: {chiamate}"
    assert any(r.startswith("Trovat") for r in risultati), (
        f"nessun ToolMessage che inizia con 'Trovat': {risultati} (chiamate: {chiamate})"
    )
    print("chiamate catalogo:", [(c["name"], c["args"]) for c in chiamate])


def prepara_nota(note_db, testo, codice):
    """Crea una nota prima del turno; restituisce il suo numero."""
    risposta = apri(
        note_db, carica(PERCORSO_INVENTARIO), lambda: datetime.now(ZoneInfo("Europe/Rome"))
    ).aggiungi(testo, codice)
    return int(re.match(r"Nota (\d+) ", risposta).group(1))


def test_il_modello_aggiunge_una_nota(caplog, tmp_path):
    stato, _ = esegui_domanda(
        "Annota che il multimetro MIS-001 ha la batteria scarica", caplog, tmp_path / "note.db"
    )
    chiamate = chiamate_strumenti(stato)
    risultati = risultati_strumenti(stato)
    print("chiamate note:", [(c["name"], c["args"]) for c in chiamate])
    assert any(
        c["name"] == "aggiungi_nota" and str(c["args"].get("codice", "")).lower() == "mis-001"
        for c in chiamate
    ), f"aggiungi_nota non chiamato con MIS-001: {chiamate}"
    assert any(r.startswith("Nota ") and "salvata" in r for r in risultati), (
        f"nessun ToolMessage 'Nota ... salvata': {risultati} (chiamate: {chiamate})"
    )


def test_il_modello_aggiunge_una_nota_senza_codice(caplog, tmp_path):
    stato, _ = esegui_domanda("Annota che il saldatore va pulito", caplog, tmp_path / "note.db")
    chiamate = chiamate_strumenti(stato)
    risultati = risultati_strumenti(stato)
    print("chiamate note:", [(c["name"], c["args"]) for c in chiamate])
    assert any(
        c["name"] == "aggiungi_nota" and not c["args"].get("codice") for c in chiamate
    ), f"aggiungi_nota non chiamato senza codice: {chiamate}"
    assert any(r.startswith("Nota ") and "salvata" in r for r in risultati), (
        f"nessun ToolMessage 'Nota ... salvata': {risultati} (chiamate: {chiamate})"
    )


def test_il_modello_elenca_le_note(caplog, tmp_path):
    note_db = tmp_path / "note.db"
    prepara_nota(note_db, "Batteria scarica", "MIS-001")
    stato, _ = esegui_domanda("Quali note ci sono?", caplog, note_db)
    chiamate = chiamate_strumenti(stato)
    risultati = risultati_strumenti(stato)
    print("chiamate note:", [(c["name"], c["args"]) for c in chiamate])
    assert any(c["name"] == "elenca_note" for c in chiamate), f"elenca_note non chiamato: {chiamate}"
    assert any(r.startswith("Trovat") for r in risultati), (
        f"nessun ToolMessage che inizia con 'Trovat': {risultati} (chiamate: {chiamate})"
    )


def test_il_modello_elimina_una_nota(caplog, tmp_path):
    note_db = tmp_path / "note.db"
    numero = prepara_nota(note_db, "Batteria scarica", "MIS-001")
    stato, _ = esegui_domanda(f"Elimina la nota {numero}", caplog, note_db)
    chiamate = chiamate_strumenti(stato)
    risultati = risultati_strumenti(stato)
    print("chiamate note:", [(c["name"], c["args"]) for c in chiamate])
    assert any(
        c["name"] == "elimina_nota" and int(c["args"].get("numero", -1)) == numero
        for c in chiamate
    ), f"elimina_nota non chiamato con numero {numero}: {chiamate}"
    assert any("eliminata" in r for r in risultati), (
        f"nessun ToolMessage con 'eliminata': {risultati} (chiamate: {chiamate})"
    )


def test_mostrare_le_note_non_elimina(caplog, tmp_path):
    note_db = tmp_path / "note.db"
    prepara_nota(note_db, "Batteria scarica", "MIS-001")
    stato, _ = esegui_domanda("Mostrami le note", caplog, note_db)
    chiamate = chiamate_strumenti(stato)
    print("chiamate note:", [(c["name"], c["args"]) for c in chiamate])
    assert not any(c["name"] == "elimina_nota" for c in chiamate), (
        f"elimina_nota chiamato per una semplice richiesta di lettura: {chiamate}"
    )


def test_osserva_domanda_di_previsione(caplog):
    stato, _ = esegui_domanda("Che tempo farà domani a Trieste?", caplog)
    print("strumenti chiamati:", [(c["name"], c["args"]) for c in chiamate_strumenti(stato)])
    print("risposta finale:", stato["messaggi"][-1].content)


def test_router_rifiuta_fuori_ambito(caplog):
    stato, _ = esegui_domanda(
        "Scrivimi una poesia sul calcio", caplog, categoria_attesa="fuori_ambito"
    )
    assert str(stato["messaggi"][-1].content).startswith("Posso rispondere solo")
    assert "router categoria=fuori_ambito" in caplog.text
    assert "agente:" not in caplog.text


DUE_PARTI = "Che ore sono a Tokyo e quanto fa 12 * 4?"


def valuta_risposta(risposta, caplog, domanda=DUE_PARTI):
    config = carica_config()
    verifica_modello(config)
    with caplog.at_level(logging.WARNING, logger="assistente.revisore"):
        valutazione = crea_revisore(crea_llm(config))(
            [HumanMessage(domanda), AIMessage(risposta)]
        )
    print(f"\n[{risposta!r}] coerente={valutazione.coerente} motivo={valutazione.motivo!r}")
    assert "revisore non disponibile" not in caplog.text
    return valutazione


def test_revisore_rifiuta_risposta_parziale(caplog):
    # Risposta parziale costruita a mano: il modello vero non si può costringere a rispondere a metà.
    valutazione = valuta_risposta("A Tokyo sono le 21:00.", caplog)
    assert valutazione.coerente is False
    assert valutazione.motivo.strip()


def test_revisore_approva_risposta_completa(caplog):
    valutazione = valuta_risposta("A Tokyo sono le 21:00 e 12 * 4 fa 48.", caplog)
    assert valutazione.coerente is True


# Risposte corrette a una sola richiesta che il primo revisore (giudizio diretto coerente sì/no)
# rifiutava sempre: vedi la specifica del revisore, «Revisione del 2026-11-10».
RISPOSTE_A_UNA_RICHIESTA = [
    ("Che ore sono a Tokyo?",
     "La data e l'ora attuali a Tokyo sono 2026-11-10T17:28:39.936095+09:00."),
    ("Quanti giorni lavorativi ci sono dal 1° al 31 dicembre 2026?",
     "I giorni lavorativi dal 1° al 31 dicembre 2026 sono **20**."),
    ("Che cosa c'è fra gli strumenti di misura?",
     "La categoria \"strumenti di misura\" contiene i seguenti articoli:\n"
     "* **MIS-001**: Multimetro digitale (4 pezzi) - Collocazione: Armadio A, ripiano 2\n"
     "* **MIS-002**: Oscilloscopio digitale (2 pezzi) - Collocazione: Bancone 3\n"
     "* **MIS-003**: Pinza amperometrica (1 pezzo) - Collocazione: Armadio A, ripiano 2\n"
     "* **MIS-004**: Analizzatore logico (0 pezzi) - Collocazione: Armadio A, ripiano 3"),
    ("Quali note ci sono?", "Il risultato dell'azione è che **non ci sono note**."),
    ("Che tempo farà domani a Trieste?",
     "Mi dispiace, ma non ho accesso alle previsioni meteorologiche future. Posso solo fornirti"
     " le condizioni meteo attuali di Trieste."),
    ("Che giorno sarà fra 30 giorni?",
     "Per calcolarlo mi serve la data di partenza: da quale giorno vuoi contare?"),
]


# Osservazioni, non vincoli: con gemma-4-e2b il verdetto su queste risposte cambia da una
# sessione all'altra (ragionamento nascosto di 200-300 token); i rifiuti restano vincolanti.
# xfail imperativo dopo valuta_risposta: un «revisore non disponibile» resta un fallimento vero.
INSTABILE = (
    "limite noto: verdetto instabile fra sessioni su risposte corrette a una richiesta"
    " (specifica del revisore, «Revisione del 2026-11-10»)"
)
SEGUITO = (
    "limite noto: gemma-4-e2b non ricollega una domanda di seguito ai messaggi precedenti"
    " e la giudica senza risposta (specifica del revisore, «Revisione del 2026-11-10»)"
)


@pytest.mark.parametrize("domanda, risposta", RISPOSTE_A_UNA_RICHIESTA)
def test_revisore_approva_risposta_a_una_richiesta(caplog, domanda, risposta):
    if not valuta_risposta(risposta, caplog, domanda).coerente:
        pytest.xfail(INSTABILE)


def test_revisore_approva_risposta_di_seguito(caplog):
    config = carica_config()
    verifica_modello(config)
    with caplog.at_level(logging.WARNING, logger="assistente.revisore"):
        valutazione = crea_revisore(crea_llm(config))(
            [HumanMessage("Che ore sono a Roma?"), AIMessage("A Roma sono le 13:00."),
             HumanMessage("e a Londra?"), AIMessage("A Londra sono le 12:00.")]
        )
    print(f"\n[seguito] coerente={valutazione.coerente} motivo={valutazione.motivo!r}")
    assert "revisore non disponibile" not in caplog.text
    if not valutazione.coerente:
        pytest.xfail(SEGUITO)


def test_revisore_rifiuta_risposta_fuori_tema(caplog):
    valutazione = valuta_risposta(
        "Il calcio è uno sport molto popolare in Italia.", caplog, "Dove si trova il multimetro?"
    )
    assert valutazione.coerente is False
