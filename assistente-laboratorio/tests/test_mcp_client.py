"""Client MCP dell'assistente con il server «archivio» vero, avviato come sottoprocesso."""

import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

import pytest

import archivio.__main__ as main_archivio
from assistente import mcp_client
from assistente.mcp_client import ClientArchivio, ErroreArchivio

DESCRIZIONE_CERCA = (
    "Cerca nell'inventario del laboratorio (strumenti, componenti, attrezzi) per parole e/o categoria e "
    "restituisce codice, nome, quantità e collocazione degli articoli trovati. Chiamalo SEMPRE quando "
    "l'utente chiede se in laboratorio c'è qualcosa, quanti pezzi ci sono o dove si trova."
)
DESCRIZIONE_DETTAGLIO = (
    "Restituisce tutti i dati di un articolo dell'inventario del laboratorio dato il suo codice, per "
    "esempio MIS-001. Usalo dopo cerca_inventario o quando l'utente indica un codice."
)
DESCRIZIONE_TESTO = (
    "Parole da cercare nel nome, nella categoria, nella descrizione o nella collocazione, "
    "per esempio multimetro."
)
DESCRIZIONE_CATEGORIA = "Nome esatto di una categoria, per esempio strumenti di misura."
DESCRIZIONE_CODICE = "Codice dell'articolo, per esempio MIS-001."


@pytest.fixture(scope="module")
def client():
    with ClientArchivio() as aperto:
        yield aperto


@pytest.fixture(scope="module")
def strumenti(client):
    return {s.nome: s for s in client.strumenti()}


def test_definizioni(client):
    definizioni = [s.definizione for s in client.strumenti()]
    assert [d["function"]["name"] for d in definizioni] == ["cerca_inventario", "dettaglio_articolo"]
    for d in definizioni:
        assert d["type"] == "function"
        assert {"name", "description", "parameters"} <= d["function"].keys()
    cerca, dettaglio = (d["function"] for d in definizioni)
    assert cerca["description"] == DESCRIZIONE_CERCA
    assert dettaglio["description"] == DESCRIZIONE_DETTAGLIO
    proprieta = cerca["parameters"]["properties"]
    assert proprieta["testo"]["description"] == DESCRIZIONE_TESTO
    assert proprieta["categoria"]["description"] == DESCRIZIONE_CATEGORIA
    assert "required" not in cerca["parameters"]
    assert dettaglio["parameters"]["properties"]["codice"]["description"] == DESCRIZIONE_CODICE
    assert dettaglio["parameters"]["required"] == ["codice"]


def test_cerca_e_dettaglio(strumenti):
    trovati = strumenti["cerca_inventario"].esegui({"testo": "multimetro"})
    assert trovati.startswith("Trovat")
    assert "MIS-001" in trovati
    assert strumenti["dettaglio_articolo"].esegui({"codice": "MIS-001"}).startswith("Codice: MIS-001")


def test_cerca_con_null(strumenti):
    risultato = strumenti["cerca_inventario"].esegui({"testo": "multimetro", "categoria": None})
    assert risultato.startswith("Trovat")


def test_caratteri_non_ascii(strumenti):
    assert "Quantità: " in strumenti["dettaglio_articolo"].esegui({"codice": "MIS-001"})
    nessuno = strumenti["cerca_inventario"].esegui({"testo": "zzzinesistente"})
    assert "«" in nessuno and "»" in nessuno


def test_argomento_di_tipo_sbagliato(strumenti):
    dettaglio = strumenti["dettaglio_articolo"]
    assert dettaglio.esegui({"codice": 5}).startswith("Errore:")
    assert dettaglio.esegui({}).startswith("Errore:")


def test_avvio_da_altra_cartella(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with ClientArchivio() as altro:
        assert len(altro.strumenti()) == 2


def test_avvio_fallito_comando_inesistente():
    with pytest.raises(ErroreArchivio, match="archivio non avviato"):
        with ClientArchivio(["comando-inesistente-xyz"]):
            pass


def test_avvio_fallito_con_messaggio():
    comando = [
        sys.executable,
        "-c",
        "import sys; print('Errore: inventario non valido, riga 3: prova.', file=sys.stderr); sys.exit(1)",
    ]
    with pytest.raises(ErroreArchivio) as info:
        with ClientArchivio(comando):
            pass
    assert "archivio non avviato" in str(info.value)
    assert "riga 3: prova" in str(info.value)
    assert str(info.value) == "archivio non avviato: inventario non valido, riga 3: prova."


SERVER_MUTO = [sys.executable, "-c", "import time; time.sleep(60)"]
SERVER_CHE_MUORE = [sys.executable, str(Path(__file__).parent / "server_finti" / "muore_dopo_una_chiamata.py")]


def test_avvio_fallito_per_timeout(caplog):
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ErroreArchivio) as info:
            with ClientArchivio(SERVER_MUTO, timeout=2.0):
                pass
    assert str(info.value) == "archivio non avviato: il server non ha risposto entro 2 secondi."
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


class _ClientSpia(ClientArchivio):
    """Ricorda il compito asincrono della sessione, per controllare che non resti pendente."""

    async def _vivi(self):
        self.compito = asyncio.current_task()
        await super()._vivi()


def test_avvio_con_chiusura_lenta(monkeypatch, caplog):
    # L'SDK impiega alcuni secondi a chiudere un server che ignora lo stdin: con un margine minimo
    # il client non attende, ma il loop si ferma solo a compito finito e il thread lo chiude.
    monkeypatch.setattr(mcp_client, "ATTESA_CHIUSURA", 0.1)
    client = _ClientSpia(SERVER_MUTO, timeout=1.0)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ErroreArchivio, match="il server non ha risposto entro 1 secondi"):
            with client:
                pass
        client._thread.join(15)
    assert not client._thread.is_alive()
    assert client.compito.done() and client._loop.is_closed()
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_server_morto_a_meta_sessione(caplog):
    with caplog.at_level(logging.WARNING):
        with ClientArchivio(SERVER_CHE_MUORE) as client:
            cerca = {s.nome: s for s in client.strumenti()}["cerca_inventario"]
            assert cerca.esegui({"testo": "multimetro"}).startswith("Trovat")
            inizio = time.monotonic()
            assert cerca.esegui({"testo": "multimetro"}) == "Errore: archivio non disponibile."
            assert time.monotonic() - inizio < 5
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_esegui_con_loop_chiuso():
    with ClientArchivio() as client:
        cerca = client.strumenti()[0]
    client._chiuso = False  # il loop si chiude fra il controllo e l'invio
    assert cerca.esegui({"testo": "multimetro"}) == "Errore: archivio non disponibile."


def test_chiusura(caplog):
    with caplog.at_level(logging.WARNING, logger="assistente.mcp_client"):
        with ClientArchivio() as proprio:
            cerca = proprio.strumenti()[0]
    assert proprio._thread.is_alive() is False
    assert caplog.records == []  # chiusura pulita, senza errori nel log
    assert cerca.esegui({"testo": "multimetro"}) == "Errore: archivio non disponibile."


class _ServerFinto:
    def __init__(self):
        self.gestore = None

    def run(self, trasporto):
        self.gestore = signal.getsignal(signal.SIGINT)


def test_main_ignora_sigint(monkeypatch):
    finto = _ServerFinto()
    monkeypatch.setattr(main_archivio, "crea_server", lambda inventario: finto)
    originale = signal.getsignal(signal.SIGINT)
    try:
        assert main_archivio.main() == 0
    finally:
        signal.signal(signal.SIGINT, originale)
    assert finto.gestore == signal.SIG_IGN


def test_main_inventario_non_valido(tmp_path, monkeypatch, capsys):
    csv = tmp_path / "inventario.csv"
    csv.write_text("codice;nome\n", encoding="utf-8")
    monkeypatch.setattr(main_archivio, "PERCORSO_INVENTARIO", csv)
    originale = signal.getsignal(signal.SIGINT)
    try:
        assert main_archivio.main() == 1
    finally:
        signal.signal(signal.SIGINT, originale)
    assert capsys.readouterr().err.startswith("Errore: inventario non valido, riga")


def test_main_inventario_non_leggibile(tmp_path, monkeypatch, capsys):
    csv = tmp_path / "manca.csv"
    monkeypatch.setattr(main_archivio, "PERCORSO_INVENTARIO", csv)
    originale = signal.getsignal(signal.SIGINT)
    try:
        assert main_archivio.main() == 1
    finally:
        signal.signal(signal.SIGINT, originale)
    errore = capsys.readouterr().err
    assert errore.startswith(f"Errore: inventario non leggibile: {csv} (")
    assert errore.endswith(").\n") and "Traceback" not in errore
