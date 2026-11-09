"""Client sincrono del server MCP «archivio»: l'asincronia di MCP resta in questo modulo.

La sessione MCP vive in un thread dedicato con un proprio event loop, dentro un solo compito
asincrono che la apre e la chiude (anyio richiede che i contesti si chiudano nel compito che li ha
aperti); il resto dell'assistente vede soltanto voci `Strumento` con un `esegui` sincrono.
"""

import asyncio
import concurrent.futures
import logging
import os
import sys
import tempfile
import threading
from contextlib import AsyncExitStack
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from assistente.strumenti import Strumento

logger = logging.getLogger("assistente.mcp_client")

CARTELLA_SRC = Path(__file__).resolve().parents[1]
NON_DISPONIBILE = "Errore: archivio non disponibile."
NESSUNA_RISPOSTA = "Errore: l'archivio non ha risposto."
# Margine per la chiusura del sottoprocesso da parte dell'SDK (attese limitate, alcuni secondi).
ATTESA_CHIUSURA = 10.0


class ErroreArchivio(Exception):
    """Il server «archivio» non si è avviato."""


def _ambiente() -> dict[str, str]:
    """Variabili da aggiungere all'ambiente del sottoprocesso: `src/` in testa a PYTHONPATH."""
    percorsi = [str(CARTELLA_SRC)]
    if os.environ.get("PYTHONPATH"):
        percorsi.append(os.environ["PYTHONPATH"])
    return {"PYTHONPATH": os.pathsep.join(percorsi), "PYTHONIOENCODING": "utf-8"}


def _descrivi(errore: BaseException, timeout: float) -> str:
    """Testo dell'errore, cercato dentro i gruppi di eccezioni di anyio con un solo elemento."""
    while isinstance(errore, BaseExceptionGroup) and len(errore.exceptions) == 1:
        errore = errore.exceptions[0]
    if isinstance(errore, TimeoutError):
        return f"il server non ha risposto entro {timeout:g} secondi."
    return str(errore) or type(errore).__name__


class ClientArchivio:
    """Context manager: avvia il server come sottoprocesso e ne espone gli strumenti."""

    def __init__(self, comando: list[str] | None = None, timeout: float = 10.0):
        self._comando = comando or [sys.executable, "-m", "archivio"]
        self._timeout = timeout
        self._chiuso = True
        self._strumenti_mcp: list = []

    def __enter__(self) -> "ClientArchivio":
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._gira, name="archivio-mcp", daemon=True)
        self._thread.start()
        self._errlog = tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace")
        self._pronto: concurrent.futures.Future = concurrent.futures.Future()
        self._fine = asyncio.Event()  # legato al loop solo al primo uso, nel thread del loop
        self._vita = asyncio.run_coroutine_threadsafe(self._vivi(), self._loop)
        try:
            self._strumenti_mcp = self._pronto.result(self._timeout + ATTESA_CHIUSURA)
        except BaseException as errore:
            self._ferma(attesa=ATTESA_CHIUSURA)
            motivo = self._stderr_del_server() or _descrivi(errore, self._timeout)
            self._errlog.close()
            if not isinstance(errore, Exception):
                raise
            raise ErroreArchivio(f"archivio non avviato: {motivo}") from errore
        self._chiuso = False
        return self

    def _gira(self) -> None:
        """Corpo del thread: il loop gira finché `_ferma` non lo ferma, poi si chiude qui."""
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    async def _vivi(self) -> None:
        """Apre sessione e sottoprocesso, attende la richiesta di chiusura e li chiude."""
        try:
            async with AsyncExitStack() as stack:
                parametri = StdioServerParameters(
                    command=self._comando[0], args=self._comando[1:], env=_ambiente()
                )
                lettura, scrittura = await stack.enter_async_context(
                    stdio_client(parametri, errlog=self._errlog)
                )
                sessione = await stack.enter_async_context(ClientSession(lettura, scrittura))
                with anyio.fail_after(self._timeout):
                    await sessione.initialize()
                    strumenti = (await sessione.list_tools()).tools
                self._sessione = sessione
                self._pronto.set_result(strumenti)
                await self._fine.wait()
        except Exception as errore:
            if not self._pronto.done():
                self._pronto.set_exception(errore)
            else:
                logger.warning("archivio: chiusura non riuscita: %r", errore)

    def strumenti(self) -> list[Strumento]:
        """Gli strumenti del server nella forma del registro dell'assistente."""
        return [
            Strumento(
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                },
                lambda args, nome=t.name: self._chiama(nome, args),
            )
            for t in self._strumenti_mcp
        ]

    def _chiama(self, nome: str, args: dict) -> str:
        if self._chiuso:
            return NON_DISPONIBILE
        chiamata = self._sessione.call_tool(nome, args)
        futuro = None
        try:
            # Dentro il try: il loop può chiudersi fra il controllo di `_chiuso` e l'invio.
            futuro = asyncio.run_coroutine_threadsafe(chiamata, self._loop)
            risultato = futuro.result(self._timeout)
        except TimeoutError:
            futuro.cancel()
            logger.warning("archivio: %s senza risposta entro %s s", nome, self._timeout)
            return NESSUNA_RISPOSTA
        except Exception as errore:
            if futuro is None:
                chiamata.close()  # mai inviata al loop: evita «coroutine was never awaited»
            logger.warning("archivio: %s fallito: %r", nome, errore)
            return NON_DISPONIBILE
        testo = "\n".join(b.text for b in risultato.content if hasattr(b, "text"))
        if risultato.is_error:
            logger.warning("archivio: %s ha restituito un errore: %s", nome, testo)
            if not testo.startswith("Errore:"):
                testo = f"Errore: {testo}"
        return testo

    def __exit__(self, *eccezione) -> bool:
        self._chiuso = True
        self._ferma(attesa=self._timeout)
        self._errlog.close()
        return False

    def _ferma(self, attesa: float) -> None:
        """Chiede la chiusura della sessione e ferma il loop quando il compito è davvero finito."""
        self._loop.call_soon_threadsafe(self._fine.set)
        try:
            self._vita.result(attesa)
        except concurrent.futures.TimeoutError:
            # Nessun annullamento: la chiusura dell'SDK è protetta e ha attese limitate (alcuni
            # secondi), e il sottoprocesso termina comunque con lo stdin chiuso (POSIX) o con il Job
            # Object (Windows). Il thread daemon finisce da solo e chiude il proprio loop.
            logger.warning("archivio: chiusura non conclusa entro %s s", attesa)
        # Fermare il loop prima della fine del compito lo lascerebbe pendente.
        self._vita.add_done_callback(lambda _: self._loop.call_soon_threadsafe(self._loop.stop))
        self._thread.join(attesa)

    def _stderr_del_server(self) -> str:
        self._errlog.seek(0)
        testo = self._errlog.read().strip()
        return testo.removeprefix("Errore: ")  # la CLI aggiunge già «Errore:»
