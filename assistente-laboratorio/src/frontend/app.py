"""Servizio del front-end: tre file statici e un proxy asincrono di /api/... verso il back-end."""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Route

logger = logging.getLogger("frontend")

STATICO = Path(__file__).resolve().parent / "statico"

_FILE = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/stile.css": ("stile.css", "text/css; charset=utf-8"),
}


def _errore_502(messaggio: str) -> Response:
    logger.warning("%s", messaggio)
    return Response(
        json.dumps({"errore": messaggio}, ensure_ascii=False).encode("utf-8"),
        status_code=502,
        media_type="application/json; charset=utf-8",
    )


def crea_app(
    backend_url: str, timeout: float, transport: httpx.AsyncBaseTransport | None = None
) -> Starlette:
    """Applicazione con la pagina (/, /app.js, /stile.css) e il proxy /api/{percorso}."""

    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with httpx.AsyncClient(
            base_url=backend_url, timeout=timeout, transport=transport
        ) as client:
            app.state.client = client
            yield

    def statico(nome: str, tipo: str):
        async def rotta(request: Request) -> Response:
            # no-cache: il browser riconvalida (ETag) e non usa una pagina vecchia dopo un aggiornamento.
            return FileResponse(STATICO / nome, media_type=tipo, headers={"Cache-Control": "no-cache"})

        return rotta

    async def proxy(request: Request) -> Response:
        client: httpx.AsyncClient = request.app.state.client
        intestazioni = {}
        if "content-type" in request.headers:
            intestazioni["content-type"] = request.headers["content-type"]
        url = httpx.URL(
            path="/" + request.path_params["percorso"], query=request.url.query.encode("ascii")
        )
        try:
            risposta = await client.request(
                request.method, url, content=await request.body(), headers=intestazioni
            )
        except httpx.TimeoutException:
            return _errore_502(f"back-end non disponibile: tempo scaduto dopo {timeout:g} s")
        except httpx.HTTPError as errore:
            return _errore_502(f"back-end non disponibile: {str(errore) or type(errore).__name__}")
        if risposta.status_code == 204:
            return Response(status_code=204)
        return Response(
            risposta.content,
            status_code=risposta.status_code,
            media_type=risposta.headers.get("content-type"),
        )

    rotte = [Route(percorso, statico(nome, tipo)) for percorso, (nome, tipo) in _FILE.items()]
    rotte.append(Route("/api/{percorso:path}", proxy, methods=["GET", "POST", "DELETE"]))
    return Starlette(routes=rotte, lifespan=lifespan)
