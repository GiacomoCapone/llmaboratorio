"""Server MCP «archivio»: espone inventario e note del laboratorio come strumenti e le categorie
dell'inventario come resource."""

from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

from archivio.inventario import Inventario
from archivio.note import Note

DESCRIZIONE_CERCA = (
    "Cerca nell'inventario del laboratorio (strumenti, componenti, attrezzi) per parole e/o categoria e "
    "restituisce codice, nome, quantità e collocazione degli articoli trovati. Chiamalo SEMPRE quando "
    "l'utente chiede se in laboratorio c'è qualcosa, quanti pezzi ci sono o dove si trova."
)
DESCRIZIONE_DETTAGLIO = (
    "Restituisce tutti i dati di un articolo dell'inventario del laboratorio dato il suo codice, per "
    "esempio MIS-001. Usalo dopo cerca_inventario o quando l'utente indica un codice."
)
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


URI_CATEGORIE = "archivio://inventario/categorie"
DESCRIZIONE_CATEGORIE = "Categorie dell'inventario del laboratorio con il numero di articoli."
INTESTAZIONE_CATEGORIE = (
    "Categorie dell'inventario (nomi esatti per il filtro categoria di cerca_inventario):"
)


def testo_categorie(inventario: Inventario) -> str:
    """Testo della resource delle categorie: intestazione e una riga per categoria."""
    righe = [
        f"- {nome} ({numero} {'articolo' if numero == 1 else 'articoli'})"
        for nome, numero in inventario.categorie()
    ]
    return "\n".join([INTESTAZIONE_CATEGORIE, *righe])


def crea_server(inventario: Inventario, note: Note) -> MCPServer:
    """Server chiamato «archivio» con gli strumenti e la resource delle categorie legati
    all'inventario e alle note dati; il testo della resource è generato a ogni lettura."""
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

    @server.tool(description=DESCRIZIONE_AGGIUNGI)
    def aggiungi_nota(
        testo: Annotated[str, Field(description="Testo della nota, per esempio display difettoso.")],
        codice: Annotated[
            str | None,
            Field(
                description="Facoltativo: codice dell'articolo, solo se l'utente lo indica, "
                "per esempio MIS-003."
            ),
        ] = None,
    ) -> str:
        return note.aggiungi(testo, codice)

    @server.tool(description=DESCRIZIONE_ELENCA)
    def elenca_note(
        codice: Annotated[
            str | None,
            Field(
                description="Facoltativo: codice di un articolo, solo se l'utente lo indica, "
                "per vedere solo le sue note."
            ),
        ] = None,
    ) -> str:
        return note.elenca(codice)

    @server.tool(description=DESCRIZIONE_ELIMINA)
    def elimina_nota(
        numero: Annotated[int, Field(description="Numero della nota da eliminare, per esempio 3.")],
    ) -> str:
        return note.elimina(numero)

    @server.resource(
        URI_CATEGORIE,
        name="categorie",
        mime_type="text/plain",
        description=DESCRIZIONE_CATEGORIE,
    )
    def categorie() -> str:
        return testo_categorie(inventario)

    return server
