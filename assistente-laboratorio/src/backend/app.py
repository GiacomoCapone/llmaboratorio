"""Applicazione HTTP del back-end: le rotte delle conversazioni, senza SQL e senza httpx."""

import json
import logging
import threading
import time

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from backend.agente import ClientAgente, ErroreAgente
from backend.deposito import (
    Conversazione,
    ConversazioneInesistente,
    Deposito,
    ErroreDatabase,
    Messaggio,
)

logger = logging.getLogger("backend")

_ID_MASSIMO = 2**63 - 1  # bigint di PostgreSQL


class _RichiestaNonValida(Exception):
    """Richiesta da rifiutare con 400 e questo messaggio."""


class _RispostaJSON(JSONResponse):
    # PowerShell 5.1 senza charset nel Content-Type legge il corpo UTF-8 come Latin-1.
    media_type = "application/json; charset=utf-8"


def _errore(codice: int, messaggio: str) -> _RispostaJSON:
    return _RispostaJSON({"errore": messaggio}, status_code=codice)


def testo_visibile(domanda: str | None, prompt: dict | None) -> str:
    """Il testo che la persona ha scritto: la domanda, o `/nome valori` per un prompt."""
    if prompt is None:
        return domanda
    valori = [str(valore) for valore in prompt["argomenti"].values()]
    return " ".join(["/" + prompt["nome"], *valori])


def _conversazione(c: Conversazione) -> dict:
    return {
        "id": c.id,
        "titolo": c.titolo,
        "creata": c.creata.isoformat(),
        "aggiornata": c.aggiornata.isoformat(),
    }


def _messaggio(m: Messaggio) -> dict:
    return {"ruolo": m.ruolo, "testo": m.testo, "ora": m.ora.isoformat()}


def _leggi_corpo(corpo) -> tuple[str | None, dict | None]:
    if not isinstance(corpo, dict):
        raise _RichiestaNonValida("corpo della richiesta non valido: atteso un oggetto JSON.")
    if ("domanda" in corpo) == ("prompt" in corpo):
        raise _RichiestaNonValida("indicare esattamente uno fra 'domanda' e 'prompt'.")
    if "domanda" in corpo:
        if not isinstance(corpo["domanda"], str):
            raise _RichiestaNonValida("'domanda' deve essere un testo non vuoto.")
        return corpo["domanda"], None
    voce = corpo["prompt"]
    if (
        not isinstance(voce, dict)
        or not isinstance(voce.get("nome"), str)
        or not isinstance(voce.get("argomenti"), dict)
    ):
        raise _RichiestaNonValida("'prompt' non valido: atteso un oggetto con 'nome' e 'argomenti'.")
    return None, voce


def crea_app(deposito: Deposito, agente: ClientAgente) -> Starlette:
    """Applicazione con /salute, /prompt e le rotte delle conversazioni."""
    occupate: set[int] = set()
    lock = threading.Lock()

    def _id_valido(testo: str) -> int | None:
        if testo.isascii() and testo.isdigit() and int(testo) <= _ID_MASSIMO:
            return int(testo)
        return None

    def _inesistente(testo: str) -> _RispostaJSON:
        return _errore(404, f"conversazione {testo} inesistente.")

    def _errore_database(e: ErroreDatabase) -> _RispostaJSON:
        logger.warning("errore del database: %s", e)
        return _errore(500, f"errore del database: {e}")

    async def esegui(testo_id: str, funzione, *args):
        """Id valido ed esistenza come prima cosa; poi `funzione(id, *args)` nel thread pool."""
        id = _id_valido(testo_id)
        if id is None:
            return _inesistente(testo_id)
        try:
            return await run_in_threadpool(funzione, id, *args)
        except ConversazioneInesistente:
            return _inesistente(testo_id)
        except ErroreDatabase as e:
            return _errore_database(e)

    async def salute(request: Request) -> _RispostaJSON:
        return _RispostaJSON({"stato": "ok"})

    async def elenco_prompt(request: Request) -> _RispostaJSON:
        try:
            return _RispostaJSON(await run_in_threadpool(agente.prompt))
        except ErroreAgente as e:
            if e.codice == 502:
                logger.warning("%s", e.messaggio)
            return _errore(e.codice, e.messaggio)

    async def elenca(request: Request) -> _RispostaJSON:
        try:
            conversazioni = await run_in_threadpool(deposito.elenca)
        except ErroreDatabase as e:
            return _errore_database(e)
        return _RispostaJSON({"conversazioni": [_conversazione(c) for c in conversazioni]})

    async def crea(request: Request) -> _RispostaJSON:
        try:
            conversazione = await run_in_threadpool(deposito.crea)
        except ErroreDatabase as e:
            return _errore_database(e)
        return _RispostaJSON(_conversazione(conversazione), status_code=201)

    def _leggi(id: int):
        conversazione, messaggi = deposito.leggi(id)
        return _RispostaJSON({**_conversazione(conversazione), "messaggi": [_messaggio(m) for m in messaggi]})

    async def leggi(request: Request):
        return await esegui(request.path_params["id"], _leggi)

    def _elimina(id: int):
        deposito.elimina(id)
        return Response(status_code=204)

    async def elimina(request: Request):
        return await esegui(request.path_params["id"], _elimina)

    def _turno(id: int, domanda: str | None, voce: dict | None):
        inizio = time.monotonic()
        testo_utente = testo_visibile(domanda, voce)
        try:
            cronologia = deposito.cronologia(id)
            risposta, nuova = agente.turno(cronologia, domanda=domanda, prompt=voce)
        except ErroreAgente as e:
            if e.codice == 502:
                logger.warning("%s", e.messaggio)
            return _errore(e.codice, e.messaggio)
        messaggi = deposito.registra_turno(id, testo_utente, risposta, nuova)
        logger.info("messaggio: conversazione %d, %.1f s", id, time.monotonic() - inizio)
        return _RispostaJSON({"risposta": risposta, "messaggi": [_messaggio(m) for m in messaggi]})

    async def messaggio(request: Request):
        testo_id = request.path_params["id"]
        try:
            corpo = json.loads(await request.body())
        except ValueError:
            corpo = None
        id = _id_valido(testo_id)
        if id is None:
            return _inesistente(testo_id)
        # Ordine: esistenza (404) -> corpo (400) -> turno in corso (409) -> agente -> salvataggio.
        esito = await esegui(testo_id, deposito.cronologia)
        if isinstance(esito, Response):
            return esito
        try:
            domanda, voce = _leggi_corpo(corpo)
        except _RichiestaNonValida as e:
            return _errore(400, str(e))
        with lock:
            if id in occupate:
                return _errore(409, f"turno in corso per la conversazione {testo_id}.")
            occupate.add(id)
        try:
            return await esegui(testo_id, _turno, domanda, voce)
        finally:
            with lock:
                occupate.discard(id)

    async def errore_interno(request: Request, e: Exception) -> _RispostaJSON:
        logger.exception("errore interno: %s", e)
        return _errore(500, f"errore interno: {e}")

    return Starlette(
        exception_handlers={Exception: errore_interno},
        routes=[
            Route("/salute", salute, methods=["GET"]),
            Route("/prompt", elenco_prompt, methods=["GET"]),
            Route("/conversazioni", elenca, methods=["GET"]),
            Route("/conversazioni", crea, methods=["POST"]),
            Route("/conversazioni/{id}", leggi, methods=["GET"]),
            Route("/conversazioni/{id}", elimina, methods=["DELETE"]),
            Route("/conversazioni/{id}/messaggi", messaggio, methods=["POST"]),
        ]
    )
