"""Servizio HTTP: l'agente senza stato, un turno alla volta."""

import json
import logging
import threading
import time

import uvicorn
from langchain_core.messages import messages_from_dict, messages_to_dict
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from assistente import cli
from assistente.avvio import apri_assistente
from assistente.config import Config
from assistente.mcp_client import ErroreArchivio

logger = logging.getLogger("assistente.servizio")


class _RichiestaNonValida(Exception):
    """Richiesta da rifiutare con 400 e questo messaggio."""


class _RispostaJSON(JSONResponse):
    # PowerShell 5.1 senza charset nel Content-Type legge il corpo UTF-8 come Latin-1.
    media_type = "application/json; charset=utf-8"


def _errore(codice: int, messaggio: str) -> _RispostaJSON:
    return _RispostaJSON({"errore": messaggio}, status_code=codice)


def _leggi_domanda(corpo: dict) -> str:
    domanda = corpo["domanda"]
    if not isinstance(domanda, str):
        raise _RichiestaNonValida("'domanda' deve essere un testo non vuoto.")
    domanda = domanda.replace("\ufeff", "").strip()
    if not domanda:
        raise _RichiestaNonValida("'domanda' deve essere un testo non vuoto.")
    return domanda


def _leggi_prompt(corpo: dict, disponibili) -> tuple[str, dict[str, str]]:
    voce = corpo["prompt"]
    argomenti = voce.get("argomenti", {}) if isinstance(voce, dict) else None
    if (
        not isinstance(voce, dict)
        or not isinstance(voce.get("nome"), str)
        or not isinstance(argomenti, dict)
    ):
        raise _RichiestaNonValida("'prompt' non valido: atteso un oggetto con 'nome' e 'argomenti'.")
    nome = voce["nome"]
    offerto = {p.nome: p for p in disponibili}.get(nome)
    if offerto is None:
        raise _RichiestaNonValida(f"prompt sconosciuto '{nome}'.")
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in argomenti.items()):
        raise _RichiestaNonValida(f"gli argomenti di {nome} devono essere testi.")
    mancanti = [a for a in offerto.argomenti if not argomenti.get(a, "").strip()]
    if mancanti:
        raise _RichiestaNonValida(f"{nome} richiede: {', '.join(mancanti)}.")
    in_piu = sorted(set(argomenti) - set(offerto.argomenti))
    if in_piu:
        raise _RichiestaNonValida(f"argomenti non previsti per {nome}: {', '.join(in_piu)}.")
    return nome, {a: argomenti[a] for a in offerto.argomenti}


def _leggi_cronologia(corpo: dict) -> list:
    grezza = corpo.get("cronologia", [])
    if not isinstance(grezza, list):
        raise _RichiestaNonValida("'cronologia' non valida: atteso un elenco di messaggi.")
    try:
        return messages_from_dict(grezza)
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise _RichiestaNonValida(f"'cronologia' non valida: {type(e).__name__}: {e}") from e


def crea_app(grafo, prompt) -> Starlette:
    """Applicazione con /salute, /prompt e /turno; `prompt` offre prompt_disponibili() e testo_prompt()."""
    lock = threading.Lock()

    def salute(request: Request) -> _RispostaJSON:
        return _RispostaJSON({"stato": "ok"})

    def elenco_prompt(request: Request) -> _RispostaJSON:
        return _RispostaJSON(
            {
                "prompt": [
                    {"nome": p.nome, "argomenti": list(p.argomenti), "descrizione": p.descrizione}
                    for p in prompt.prompt_disponibili()
                ]
            }
        )

    def turno_sul_grafo(cronologia, domanda):
        with lock:
            inizio = time.monotonic()
            esito = cli.esegui_turno(grafo, cronologia, domanda)
            durata = time.monotonic() - inizio
        logger.info("turno: %d messaggi in ingresso, %.1f s", len(cronologia), durata)
        return esito

    def esegui_prompt(nome, argomenti):
        logger.info("prompt: %s %s", nome, argomenti)
        return prompt.testo_prompt(nome, argomenti)

    async def turno(request: Request) -> _RispostaJSON:
        try:
            corpo = json.loads(await request.body())
        except ValueError:
            corpo = None
        if not isinstance(corpo, dict):
            return _errore(400, "corpo della richiesta non valido: atteso un oggetto JSON.")
        try:
            if ("domanda" in corpo) == ("prompt" in corpo):
                raise _RichiestaNonValida("indicare esattamente uno fra 'domanda' e 'prompt'.")
            if "domanda" in corpo:
                domanda, voce = _leggi_domanda(corpo), None
            else:
                domanda, voce = None, _leggi_prompt(corpo, prompt.prompt_disponibili())
            cronologia = _leggi_cronologia(corpo)
        except _RichiestaNonValida as e:
            return _errore(400, str(e))

        if voce is not None:
            try:
                domanda = await run_in_threadpool(esegui_prompt, *voce)
            except ErroreArchivio as e:
                return _errore(422, str(e))
        try:
            esito = await run_in_threadpool(turno_sul_grafo, cronologia, domanda)
        except Exception as e:
            logger.warning("turno fallito: %s", e)
            return _errore(500, f"turno fallito: {e}")
        return _RispostaJSON(
            {
                "domanda": domanda,
                "risposta": esito.testo if str(esito.testo).strip() else cli.MESSAGGIO_RISPOSTA_VUOTA,
                "cronologia": messages_to_dict(esito.cronologia),
                "interrotto": esito.interrotto,
            }
        )

    return Starlette(
        routes=[
            Route("/salute", salute, methods=["GET"]),
            Route("/prompt", elenco_prompt, methods=["GET"]),
            Route("/turno", turno, methods=["POST"]),
        ]
    )


def servi(config: Config) -> None:
    """Avvia il servizio HTTP; ritorna dopo Ctrl-C o SIGTERM, chiudendo l'archivio."""
    with apri_assistente(config) as (grafo, archivio):
        logger.info("servizio in ascolto su http://%s:%d", config.http_host, config.http_porta)
        uvicorn.run(
            crea_app(grafo, archivio),
            host=config.http_host,
            port=config.http_porta,
            log_level=getattr(logging, config.log_level, logging.INFO),
        )
