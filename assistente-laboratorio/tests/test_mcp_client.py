"""Client MCP dell'assistente con il server «archivio» vero, avviato come sottoprocesso."""

import asyncio
import logging
import signal
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from mcp.types import (
    BlobResourceContents,
    GetPromptResult,
    PromptMessage,
    ReadResourceResult,
    TextContent,
)

import archivio.__main__ as main_archivio
from assistente import mcp_client
from archivio.note import CARTELLA_PROGETTO, PERCORSO_NOTE_PREDEFINITO
from assistente.mcp_client import (
    ClientArchivio,
    ErroreArchivio,
    PromptArchivio,
    con_categorie,
    nomi_categorie,
)
from assistente.strumenti import Strumento

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
DESCRIZIONE_AGGIUNGI = (
    "Salva una nota del laboratorio (promemoria, guasto, osservazione). Chiamalo SEMPRE quando l'utente "
    "chiede di annotare, ricordare o segnare qualcosa, senza chiedere altro. Il codice di un articolo "
    "dell'inventario (per esempio MIS-003) va indicato solo se l'utente lo scrive; altrimenti la nota si "
    "salva senza codice."
)
DESCRIZIONE_ELENCA = (
    "Elenca le note del laboratorio, dalla più recente, con numero, data, codice dell'articolo e testo. "
    "Chiamalo SEMPRE quando l'utente chiede le note o i promemoria salvati, senza chiedere altro: senza "
    "codice mostra tutte le note."
)
DESCRIZIONE_ELIMINA = (
    "Elimina definitivamente una nota del laboratorio dato il suo numero, visibile con elenca_note. Usalo "
    "solo quando l'utente chiede esplicitamente di eliminare una nota."
)
DESCRIZIONE_TESTO_NOTA = "Testo della nota, per esempio display difettoso."
DESCRIZIONE_CODICE_NOTA = (
    "Facoltativo: codice dell'articolo, solo se l'utente lo indica, per esempio MIS-003."
)
DESCRIZIONE_CODICE_ELENCA = (
    "Facoltativo: codice di un articolo, solo se l'utente lo indica, per vedere solo le sue note."
)
DESCRIZIONE_NUMERO = "Numero della nota da eliminare, per esempio 3."


@pytest.fixture(scope="module")
def file_note(tmp_path_factory):
    return tmp_path_factory.mktemp("note") / "note.db"


@pytest.fixture(scope="module")
def client(file_note):
    with ClientArchivio(ambiente={"NOTE_DB": str(file_note)}) as aperto:
        yield aperto


@pytest.fixture(scope="module")
def strumenti(client):
    return {s.nome: s for s in client.strumenti()}


def test_definizioni(client):
    definizioni = [s.definizione for s in client.strumenti()]
    assert [d["function"]["name"] for d in definizioni] == [
        "cerca_inventario",
        "dettaglio_articolo",
        "aggiungi_nota",
        "elenca_note",
        "elimina_nota",
    ]
    for d in definizioni:
        assert d["type"] == "function"
        assert {"name", "description", "parameters"} <= d["function"].keys()
    cerca, dettaglio, aggiungi, elenca, elimina = (d["function"] for d in definizioni)
    assert cerca["description"] == DESCRIZIONE_CERCA
    assert dettaglio["description"] == DESCRIZIONE_DETTAGLIO
    proprieta = cerca["parameters"]["properties"]
    assert proprieta["testo"]["description"] == DESCRIZIONE_TESTO
    assert proprieta["categoria"]["description"] == DESCRIZIONE_CATEGORIA
    assert "required" not in cerca["parameters"]
    assert dettaglio["parameters"]["properties"]["codice"]["description"] == DESCRIZIONE_CODICE
    assert dettaglio["parameters"]["required"] == ["codice"]
    assert aggiungi["description"] == DESCRIZIONE_AGGIUNGI
    assert elenca["description"] == DESCRIZIONE_ELENCA
    assert elimina["description"] == DESCRIZIONE_ELIMINA
    assert aggiungi["parameters"]["properties"]["testo"]["description"] == DESCRIZIONE_TESTO_NOTA
    assert aggiungi["parameters"]["properties"]["codice"]["description"] == DESCRIZIONE_CODICE_NOTA
    assert elenca["parameters"]["properties"]["codice"]["description"] == DESCRIZIONE_CODICE_ELENCA
    assert elimina["parameters"]["properties"]["numero"]["description"] == DESCRIZIONE_NUMERO
    assert aggiungi["parameters"]["required"] == ["testo"]
    assert "required" not in elenca["parameters"]
    assert elimina["parameters"]["required"] == ["numero"]


def test_note_end_to_end(strumenti, file_note):
    aggiunta = strumenti["aggiungi_nota"].esegui({"testo": "batteria scarica", "codice": "mis-001"})
    assert aggiunta.startswith("Nota 1 salvata (MIS-001, ")
    assert strumenti["elenca_note"].esegui({"codice": None}).startswith("Trovata 1 nota:")
    with closing(sqlite3.connect(file_note)) as conn:
        assert conn.execute("SELECT testo FROM note").fetchall() == [("batteria scarica",)]
    assert "eliminata" in strumenti["elimina_nota"].esegui({"numero": "1"})
    assert strumenti["elimina_nota"].esegui({"numero": "tre"}).startswith("Errore:")


def test_note_db_non_valido(tmp_path):
    file = tmp_path / "note.db"
    file.write_text("non è un database", encoding="utf-8")
    with pytest.raises(ErroreArchivio, match="archivio delle note non valido"):
        with ClientArchivio(ambiente={"NOTE_DB": str(file)}):
            pass


def test_percorso_note(tmp_path):
    assert main_archivio.percorso_note(None) == PERCORSO_NOTE_PREDEFINITO
    assert main_archivio.percorso_note("") == PERCORSO_NOTE_PREDEFINITO
    assert main_archivio.percorso_note("x/n.db") == CARTELLA_PROGETTO / "x/n.db"
    assoluto = tmp_path / "n.db"
    assert main_archivio.percorso_note(str(assoluto)) == assoluto


def test_fuso_note():
    roma = ZoneInfo("Europe/Rome")
    assert main_archivio.fuso_note(None) == roma
    assert main_archivio.fuso_note("") == roma
    assert main_archivio.fuso_note("Marte/Olimpo") == roma
    assert main_archivio.fuso_note("UTC") == ZoneInfo("UTC")


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
    with ClientArchivio(ambiente={"NOTE_DB": str(tmp_path / "note.db")}) as altro:
        assert len(altro.strumenti()) == 5


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


def test_server_morto_a_meta_sessione(caplog, tmp_path):
    with caplog.at_level(logging.WARNING):
        with ClientArchivio(SERVER_CHE_MUORE, ambiente={"NOTE_DB": str(tmp_path / "note.db")}) as client:
            cerca = {s.nome: s for s in client.strumenti()}["cerca_inventario"]
            assert cerca.esegui({"testo": "multimetro"}).startswith("Trovat")
            inizio = time.monotonic()
            assert cerca.esegui({"testo": "multimetro"}) == "Errore: archivio non disponibile."
            assert time.monotonic() - inizio < 5
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_esegui_con_loop_chiuso(tmp_path):
    with ClientArchivio(ambiente={"NOTE_DB": str(tmp_path / "note.db")}) as client:
        cerca = client.strumenti()[0]
    client._chiuso = False  # il loop si chiude fra il controllo e l'invio
    assert cerca.esegui({"testo": "multimetro"}) == "Errore: archivio non disponibile."


def test_chiusura(caplog, tmp_path):
    with caplog.at_level(logging.WARNING, logger="assistente.mcp_client"):
        with ClientArchivio(ambiente={"NOTE_DB": str(tmp_path / "note.db")}) as proprio:
            cerca = proprio.strumenti()[0]
    assert proprio._thread.is_alive() is False
    assert caplog.records == []  # chiusura pulita, senza errori nel log
    assert cerca.esegui({"testo": "multimetro"}) == "Errore: archivio non disponibile."


class _ServerFinto:
    def __init__(self):
        self.gestore = None

    def run(self, trasporto):
        self.gestore = signal.getsignal(signal.SIGINT)


def test_main_ignora_sigint(tmp_path, monkeypatch):
    finto = _ServerFinto()
    monkeypatch.setenv("NOTE_DB", str(tmp_path / "note.db"))
    monkeypatch.setattr(main_archivio, "crea_server", lambda inventario, note: finto)
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
    monkeypatch.setenv("NOTE_DB", str(tmp_path / "note.db"))
    originale = signal.getsignal(signal.SIGINT)
    try:
        assert main_archivio.main() == 1
    finally:
        signal.signal(signal.SIGINT, originale)
    assert capsys.readouterr().err.startswith("Errore: inventario non valido, riga")


def test_main_inventario_non_leggibile(tmp_path, monkeypatch, capsys):
    csv = tmp_path / "manca.csv"
    monkeypatch.setattr(main_archivio, "PERCORSO_INVENTARIO", csv)
    monkeypatch.setenv("NOTE_DB", str(tmp_path / "note.db"))
    originale = signal.getsignal(signal.SIGINT)
    try:
        assert main_archivio.main() == 1
    finally:
        signal.signal(signal.SIGINT, originale)
    errore = capsys.readouterr().err
    assert errore.startswith(f"Errore: inventario non leggibile: {csv} (")
    assert errore.endswith(").\n") and "Traceback" not in errore


def test_main_note_non_valide(tmp_path, monkeypatch, capsys):
    file = tmp_path / "note.db"
    file.write_text("non è un database", encoding="utf-8")
    monkeypatch.setenv("NOTE_DB", str(file))
    originale = signal.getsignal(signal.SIGINT)
    try:
        assert main_archivio.main() == 1
    finally:
        signal.signal(signal.SIGINT, originale)
    assert capsys.readouterr().err.startswith("Errore: archivio delle note non valido")


def test_leggi_risorsa_categorie(client):
    testo = client.leggi_risorsa(mcp_client.URI_CATEGORIE)
    assert testo.startswith(
        "Categorie dell'inventario (nomi esatti per il filtro categoria di cerca_inventario):"
    )
    assert "- strumenti di misura (4 articoli)" in testo
    assert "- alimentatori (3 articoli)" in testo


def test_leggi_risorsa_uri_sconosciuto(client):
    with pytest.raises(ErroreArchivio, match="archivio://altro"):
        client.leggi_risorsa("archivio://altro")
    assert "alimentatori" in client.leggi_risorsa(mcp_client.URI_CATEGORIE)


def test_leggi_risorsa_client_chiuso(tmp_path):
    with ClientArchivio(ambiente={"NOTE_DB": str(tmp_path / "note.db")}) as proprio:
        pass
    with pytest.raises(ErroreArchivio, match="archivio non disponibile"):
        proprio.leggi_risorsa(mcp_client.URI_CATEGORIE)


def test_leggi_risorsa_server_morto(tmp_path):
    with ClientArchivio(SERVER_CHE_MUORE, ambiente={"NOTE_DB": str(tmp_path / "note.db")}) as proprio:
        cerca = {s.nome: s for s in proprio.strumenti()}["cerca_inventario"]
        cerca.esegui({"testo": "multimetro"})
        cerca.esegui({"testo": "multimetro"})  # il server muore qui
        inizio = time.monotonic()
        with pytest.raises(ErroreArchivio):
            proprio.leggi_risorsa(mcp_client.URI_CATEGORIE)
        assert time.monotonic() - inizio < 5


@pytest.mark.parametrize(
    "contenuti",
    [
        [],
        [BlobResourceContents(uri="archivio://x", blob="AA==", mime_type="application/octet-stream")],
    ],
)
def test_leggi_risorsa_contenuto_non_testuale(monkeypatch, client, contenuti):
    async def finta(uri, **opzioni):
        return ReadResourceResult(contents=contenuti)

    monkeypatch.setattr(client._sessione, "read_resource", finta)
    with pytest.raises(ErroreArchivio, match="non ha contenuto testuale"):
        client.leggi_risorsa(mcp_client.URI_CATEGORIE)


def test_nomi_categorie(client):
    assert nomi_categorie(client.leggi_risorsa(mcp_client.URI_CATEGORIE)) == [
        "alimentatori",
        "attrezzi",
        "cavi e connettori",
        "componenti passivi",
        "schede e microcontrollori",
        "sicurezza",
        "strumenti di misura",
    ]


def test_nomi_categorie_senza_righe():
    intestazione = "Categorie dell'inventario (nomi esatti per il filtro categoria di cerca_inventario):"
    assert nomi_categorie(intestazione) == []
    assert nomi_categorie("\n".join([intestazione, "testo", "-senza spazio", "- attrezzi (1 articolo)"])) == [
        "attrezzi"
    ]


def test_nomi_categorie_con_parentesi():
    assert nomi_categorie("- cavi (rame) (2 articoli)") == ["cavi (rame)"]


def strumento_finto(nome, proprieta=None):
    parametri = {"type": "object", "properties": proprieta if proprieta is not None else {}}
    definizione = {"type": "function", "function": {"name": nome, "parameters": parametri}}
    return Strumento(definizione, lambda args, nome=nome: f"eseguito {nome}")


def cerca_finto():
    return strumento_finto("cerca_inventario", {"categoria": {"type": "string", "description": "Nome esatto."}})


def descrizione_categoria(strumento):
    return strumento.definizione["function"]["parameters"]["properties"]["categoria"]["description"]


def test_con_categorie():
    cerca, altro = cerca_finto(), strumento_finto("altro")
    risultato = con_categorie([cerca, altro], ["a", "b"])
    assert [s.nome for s in risultato] == ["cerca_inventario", "altro"]
    assert descrizione_categoria(risultato[0]) == "Nome esatto. Categorie esistenti: a, b."
    assert risultato[0].esegui({}) == "eseguito cerca_inventario"
    assert risultato[1] is altro


def test_con_categorie_non_modifica_l_originale():
    cerca = cerca_finto()
    con_categorie([cerca], ["a"])
    assert descrizione_categoria(cerca) == "Nome esatto."


@pytest.mark.parametrize(
    "strumenti, nomi",
    [
        ([cerca_finto()], []),
        ([strumento_finto("altro")], ["a"]),
        ([strumento_finto("cerca_inventario")], ["a"]),
    ],
)
def test_con_categorie_invariata(strumenti, nomi):
    risultato = con_categorie(strumenti, nomi)
    assert len(risultato) == len(strumenti)
    assert all(r is s for r, s in zip(risultato, strumenti))


def test_prompt_disponibili(client):
    assert client.prompt_disponibili() == [
        PromptArchivio(
            "scheda_articolo", "Scheda di un articolo dell'inventario con le sue note.", ["codice"]
        )
    ]


def test_testo_prompt(client):
    assert client.testo_prompt("scheda_articolo", {"codice": "mis-001"}) == (
        "Dammi i dettagli dell'articolo MIS-001 e le note che lo riguardano."
    )


def test_testo_prompt_codice_sconosciuto(client):
    with pytest.raises(ErroreArchivio, match="nessun articolo con codice 'XYZ'"):
        client.testo_prompt("scheda_articolo", {"codice": "XYZ"})
    assert "MIS-001" in client.testo_prompt("scheda_articolo", {"codice": "MIS-001"})


def test_testo_prompt_sconosciuto(client):
    with pytest.raises(ErroreArchivio):
        client.testo_prompt("altro", {})


def test_testo_prompt_client_chiuso(tmp_path):
    with ClientArchivio(ambiente={"NOTE_DB": str(tmp_path / "note.db")}) as proprio:
        pass
    with pytest.raises(ErroreArchivio, match="archivio non disponibile"):
        proprio.testo_prompt("scheda_articolo", {"codice": "MIS-001"})


def test_testo_prompt_server_morto(tmp_path):
    with ClientArchivio(SERVER_CHE_MUORE, ambiente={"NOTE_DB": str(tmp_path / "note.db")}) as proprio:
        cerca = {s.nome: s for s in proprio.strumenti()}["cerca_inventario"]
        cerca.esegui({"testo": "multimetro"})
        cerca.esegui({"testo": "multimetro"})  # il server muore qui
        inizio = time.monotonic()
        with pytest.raises(ErroreArchivio, match=r"^archivio non disponibile\.$"):
            proprio.testo_prompt("scheda_articolo", {"codice": "MIS-001"})
        assert time.monotonic() - inizio < 5


@pytest.mark.parametrize(
    "messaggi",
    [[], [PromptMessage(role="assistant", content=TextContent(type="text", text="x"))]],
)
def test_testo_prompt_senza_domanda(monkeypatch, client, messaggi):
    async def finta(nome, argomenti=None, **opzioni):
        return GetPromptResult(messages=messaggi)

    monkeypatch.setattr(client._sessione, "get_prompt", finta)
    with pytest.raises(ErroreArchivio, match="non ha prodotto una domanda"):
        client.testo_prompt("scheda_articolo", {"codice": "MIS-001"})
