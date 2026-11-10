"""Server «archivio» in-process: resource delle categorie e strumenti registrati."""

import asyncio
from datetime import datetime, timezone

import pytest
from mcp.shared.exceptions import MCPError

from archivio.inventario import Articolo, Inventario
from archivio.note import apri
from archivio.server import (
    DESCRIZIONE_SCHEDA,
    INTESTAZIONE_CATEGORIE,
    URI_CATEGORIE,
    crea_server,
)
from archivio.server import testo_categorie as genera_testo  # alias: pytest raccoglierebbe test*


def articolo(codice: str, categoria: str) -> Articolo:
    return Articolo(codice, f"Articolo {codice}", categoria, 1, "Cassetto", "")


def server_con(tmp_path, inventario):
    note = apri(tmp_path / "note.db", inventario, lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    return crea_server(inventario, note)


def leggi(server) -> list:
    return list(asyncio.run(server.read_resource(URI_CATEGORIE)))


PROVA = Inventario(
    [articolo("ATT-001", "attrezzi"), articolo("ATT-002", "attrezzi"), articolo("ALI-001", "alimentatori")]
)


def test_resource_elencata(tmp_path):
    risorse = asyncio.run(server_con(tmp_path, PROVA).list_resources())
    assert len(risorse) == 1
    assert str(risorse[0].uri) == URI_CATEGORIE == "archivio://inventario/categorie"
    assert risorse[0].name == "categorie"
    assert risorse[0].mime_type == "text/plain"


def test_resource_testo(tmp_path):
    contenuti = leggi(server_con(tmp_path, PROVA))
    assert len(contenuti) == 1
    assert contenuti[0].content == (
        INTESTAZIONE_CATEGORIE + "\n- alimentatori (1 articolo)\n- attrezzi (2 articoli)"
    )
    assert INTESTAZIONE_CATEGORIE == (
        "Categorie dell'inventario (nomi esatti per il filtro categoria di cerca_inventario):"
    )


def test_resource_inventario_vuoto():
    assert genera_testo(Inventario([])) == INTESTAZIONE_CATEGORIE


class InventarioCheCambia(Inventario):
    """Inventario le cui categorie cambiano a ogni chiamata, per vedere quando è letto."""

    def __init__(self):
        super().__init__([])
        self.letture = 0

    def categorie(self):
        self.letture += 1
        return [("attrezzi", self.letture)]


def test_resource_generata_a_ogni_lettura(tmp_path):
    inventario = InventarioCheCambia()
    server = server_con(tmp_path, inventario)
    assert leggi(server)[0].content.endswith("- attrezzi (1 articolo)")
    assert leggi(server)[0].content.endswith("- attrezzi (2 articoli)")


def test_strumenti_invariati(tmp_path):
    nomi = [t.name for t in asyncio.run(server_con(tmp_path, PROVA).list_tools())]
    assert nomi == [
        "cerca_inventario",
        "dettaglio_articolo",
        "aggiungi_nota",
        "elenca_note",
        "elimina_nota",
    ]


CON_MIS = Inventario([articolo("MIS-001", "strumenti di misura"), articolo("ATT-001", "attrezzi")])


def test_prompt_elencato(tmp_path):
    prompt = asyncio.run(server_con(tmp_path, CON_MIS).list_prompts())
    assert len(prompt) == 1
    assert prompt[0].name == "scheda_articolo"
    assert prompt[0].description == DESCRIZIONE_SCHEDA
    assert DESCRIZIONE_SCHEDA == "Scheda di un articolo dell'inventario con le sue note."
    assert [(a.name, a.required) for a in prompt[0].arguments] == [("codice", True)]


@pytest.mark.parametrize("codice", ["mis-001", " MIS-001 "])
def test_prompt_testo(tmp_path, codice):
    risultato = asyncio.run(
        server_con(tmp_path, CON_MIS).get_prompt("scheda_articolo", {"codice": codice})
    )
    assert len(risultato.messages) == 1
    assert risultato.messages[0].role == "user"
    assert risultato.messages[0].content.text == (
        "Dammi i dettagli dell'articolo MIS-001 e le note che lo riguardano."
    )


@pytest.mark.parametrize("codice, atteso", [("XYZ", "'XYZ'"), (" xyz ", "'xyz'"), ("", "''")])
def test_prompt_codice_sconosciuto(tmp_path, codice, atteso):
    server = server_con(tmp_path, CON_MIS)
    with pytest.raises(MCPError, match="nessun articolo con codice " + atteso + r"\."):
        asyncio.run(server.get_prompt("scheda_articolo", {"codice": codice}))
