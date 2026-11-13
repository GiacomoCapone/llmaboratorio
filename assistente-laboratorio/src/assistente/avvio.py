"""Costruzione condivisa dell'assistente: archivio MCP, modello, strumenti e grafo."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from assistente.config import Config
from assistente.grafo import build_graph
from assistente.mcp_client import (
    URI_CATEGORIE,
    ClientArchivio,
    ErroreArchivio,
    con_categorie,
    nomi_categorie,
)
from assistente.modello import crea_llm, verifica_modello
from assistente.revisore import crea_revisore
from assistente.riassunto import crea_riassuntore
from assistente.router import crea_router
from assistente.strumenti import crea_strumenti

logger = logging.getLogger("assistente.avvio")


def leggi_contesto(archivio) -> list[str]:
    """Nomi delle categorie dalla resource dell'archivio; nessun nome se la lettura fallisce."""
    try:
        nomi = nomi_categorie(archivio.leggi_risorsa(URI_CATEGORIE))
    except ErroreArchivio as errore:
        logger.warning("contesto non disponibile: %s", errore)
        return []
    logger.info("contesto: letta la resource %s (%d categorie)", URI_CATEGORIE, len(nomi))
    return nomi


@contextmanager
def apri_assistente(config: Config) -> Iterator[tuple[object, ClientArchivio]]:
    """Avvia l'archivio e costruisce il grafo; alla chiusura ferma il server dell'archivio."""
    ambiente = {
        "NOTE_DB": str(config.note_db),
        "FUSO_PREDEFINITO": config.fuso_predefinito,
    }
    with ClientArchivio(ambiente=ambiente) as archivio:
        categorie = leggi_contesto(archivio)
        verifica_modello(config)
        strumenti = crea_strumenti(
            lambda: datetime.now(timezone.utc),
            config.fuso_predefinito,
            config.citta_patrono,
            esterni=con_categorie(archivio.strumenti(), categorie),
        )
        llm = crea_llm(config)
        grafo = build_graph(
            llm,
            strumenti,
            config.max_passaggi,
            crea_router(llm, config.ambito),
            crea_revisore(llm),
            config.max_revisioni,
            crea_riassuntore(llm),
            config.soglia_riassunto,
        )
        yield grafo, archivio
