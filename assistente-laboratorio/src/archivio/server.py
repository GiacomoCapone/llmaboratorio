"""Server MCP «archivio»: espone ricerca e dettaglio dell'inventario come strumenti."""

from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

from archivio.inventario import Inventario

DESCRIZIONE_CERCA = (
    "Cerca nell'inventario del laboratorio (strumenti, componenti, attrezzi) per parole e/o categoria e "
    "restituisce codice, nome, quantità e collocazione degli articoli trovati. Chiamalo SEMPRE quando "
    "l'utente chiede se in laboratorio c'è qualcosa, quanti pezzi ci sono o dove si trova."
)
DESCRIZIONE_DETTAGLIO = (
    "Restituisce tutti i dati di un articolo dell'inventario del laboratorio dato il suo codice, per "
    "esempio MIS-001. Usalo dopo cerca_inventario o quando l'utente indica un codice."
)


def crea_server(inventario: Inventario) -> MCPServer:
    """Server chiamato «archivio» con i due strumenti legati all'inventario dato."""
    server = MCPServer("archivio", log_level="WARNING")

    @server.tool(description=DESCRIZIONE_CERCA)
    def cerca_inventario(
        testo: Annotated[
            str | None,
            Field(
                description="Parole da cercare nel nome, nella categoria, nella descrizione o nella "
                "collocazione, per esempio multimetro."
            ),
        ] = None,
        categoria: Annotated[
            str | None,
            Field(description="Nome esatto di una categoria, per esempio strumenti di misura."),
        ] = None,
    ) -> str:
        return inventario.cerca(testo, categoria)

    @server.tool(description=DESCRIZIONE_DETTAGLIO)
    def dettaglio_articolo(
        codice: Annotated[str, Field(description="Codice dell'articolo, per esempio MIS-001.")],
    ) -> str:
        return inventario.dettaglio(codice)

    return server
