"""Client sincrono del server MCP «archivio»: l'asincronia di MCP resta in questo modulo.

La sessione MCP vive in un thread dedicato con un proprio event loop, dentro un solo compito
asincrono che la apre e la chiude (anyio richiede che i contesti si chiudano nel compito che li ha
aperti); il resto dell'assistente vede soltanto voci `Strumento` con un `esegui` sincrono.
"""

import asyncio
import concurrent.futures
import copy
import logging
import os
import sys
import tempfile
import threading
from collections.abc import Callable, Coroutine
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError
from mcp.types import CONNECTION_CLOSED

from assistente.strumenti import Strumento

logger = logging.getLogger("assistente.mcp_client")

CARTELLA_SRC = Path(__file__).resolve().parents[1]
NON_DISPONIBILE = "Errore: archivio non disponibile."
NESSUNA_RISPOSTA = "Errore: l'archivio non ha risposto."
# Margine per la chiusura del sottoprocesso da parte dell'SDK (attese limitate, alcuni secondi).
ATTESA_CHIUSURA = 10.0
# Stesso valore di `archivio.server.URI_CATEGORIE`: l'assistente non importa il pacchetto archivio.
URI_CATEGORIE = "archivio://inventario/categorie"


class ErroreArchivio(Exception):
    """Il server «archivio» non si è avviato."""


def _ambiente(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Variabili da aggiungere all'ambiente del sottoprocesso: `src/` in testa a PYTHONPATH.

    `extra` (per esempio NOTE_DB) si aggiunge, ma non può sovrascrivere PYTHONPATH.
    """
    percorsi = [str(CARTELLA_SRC)]
    if os.environ.get("PYTHONPATH"):
        percorsi.append(os.environ["PYTHONPATH"])
    return {
        **(extra or {}),
        "PYTHONPATH": os.pathsep.join(percorsi),
        "PYTHONIOENCODING": "utf-8",
    }


@dataclass(frozen=True)
class PromptArchivio:
    """Un prompt offerto dal server: nome, descrizione e nomi degli argomenti nell'ordine dichiarato."""

    nome: str
    descrizione: str
    argomenti: list[str]


def _causa_prompt(errore: Exception) -> str:
    """Causa leggibile di un errore di `get_prompt`: il messaggio del server, salvo la connessione
    chiusa (server terminato), detta come per gli strumenti."""
    if isinstance(errore, MCPError) and errore.error.code == CONNECTION_CLOSED:
        return "archivio non disponibile."
    return str(errore)


def nomi_categorie(testo: str) -> list[str]:
    """Nomi delle categorie dal testo della resource: righe «- <nome> (<n> articoli)»."""
    return [
        riga[2 : riga.rindex(" (")]
        for riga in testo.splitlines()
        if riga.startswith("- ") and " (" in riga
    ]


def con_categorie(strumenti: list[Strumento], nomi: list[str]) -> list[Strumento]:
    """Strumenti con i nomi delle categorie aggiunti alla descrizione del parametro `categoria` di
    `cerca_inventario`, su una copia della definizione; il resto è restituito così com'è."""
    risultato = []
    for strumento in strumenti:
        proprieta = strumento.definizione["function"].get("parameters", {}).get("properties", {})
        if nomi and strumento.nome == "cerca_inventario" and "categoria" in proprieta:
            definizione = copy.deepcopy(strumento.definizione)
            categoria = definizione["function"]["parameters"]["properties"]["categoria"]
            categoria["description"] = (
                categoria.get("description", "") + " Categorie esistenti: " + ", ".join(nomi) + "."
            )
            strumento = Strumento(definizione, strumento.esegui)
        risultato.append(strumento)
    return risultato


def _descrivi(errore: BaseException, timeout: float) -> str:
    """Testo dell'errore, cercato dentro i gruppi di eccezioni di anyio con un solo elemento."""
    while isinstance(errore, BaseExceptionGroup) and len(errore.exceptions) == 1:
        errore = errore.exceptions[0]
    if isinstance(errore, TimeoutError):
        return f"il server non ha risposto entro {timeout:g} secondi."
    return str(errore) or type(errore).__name__


class ClientArchivio:
    """Context manager: avvia il server come sottoprocesso e ne espone gli strumenti."""

    def __init__(
        self,
        comando: list[str] | None = None,
        timeout: float = 10.0,
        ambiente: dict[str, str] | None = None,
    ):
        self._ambiente = ambiente
        self._comando = comando or [sys.executable, "-m", "archivio"]
        self._timeout = timeout
        self._chiuso = True
        self._strumenti_mcp: list = []
        self._prompt_mcp: list = []

    def __enter__(self) -> "ClientArchivio":
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._gira, name="archivio-mcp", daemon=True)
        self._thread.start()
        self._errlog = tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace")
        self._pronto: concurrent.futures.Future = concurrent.futures.Future()
        self._fine = asyncio.Event()  # legato al loop solo al primo uso, nel thread del loop
        self._vita = asyncio.run_coroutine_threadsafe(self._vivi(), self._loop)
        try:
            self._strumenti_mcp, self._prompt_mcp = self._pronto.result(
                self._timeout + ATTESA_CHIUSURA
            )
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
                    command=self._comando[0], args=self._comando[1:], env=_ambiente(self._ambiente)
                )
                lettura, scrittura = await stack.enter_async_context(
                    stdio_client(parametri, errlog=self._errlog)
                )
                sessione = await stack.enter_async_context(ClientSession(lettura, scrittura))
                with anyio.fail_after(self._timeout):
                    await sessione.initialize()
                    strumenti = (await sessione.list_tools()).tools
                    prompt = (await sessione.list_prompts()).prompts
                self._sessione = sessione
                self._pronto.set_result((strumenti, prompt))
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

    def _attendi(self, crea: Callable[[], Coroutine], descrivi: Callable[[Exception], str]):
        """Esegue sulla sessione la richiesta creata da `crea` e ne attende il risultato.

        Chi la usa è l'applicazione, non il modello: per questo un guasto è un `ErroreArchivio` (non
        un testo `Errore: ...` come in `_chiama`); `descrivi` dà la causa per un errore del server.
        """
        if self._chiuso:
            raise ErroreArchivio("archivio non disponibile.")
        richiesta = crea()
        futuro = None
        try:
            futuro = asyncio.run_coroutine_threadsafe(richiesta, self._loop)
            return futuro.result(self._timeout)
        except TimeoutError:
            futuro.cancel()
            raise ErroreArchivio(
                f"l'archivio non ha risposto entro {self._timeout:g} secondi."
            ) from None
        except Exception as errore:
            if futuro is None:
                richiesta.close()  # mai inviata al loop: evita «coroutine was never awaited»
            raise ErroreArchivio(descrivi(errore)) from errore

    def leggi_risorsa(self, uri: str) -> str:
        """Testo del primo contenuto della resource `uri`; solleva `ErroreArchivio` se non riesce."""
        risultato = self._attendi(
            lambda: self._sessione.read_resource(uri),
            lambda errore: f"lettura di {uri} fallita: {errore}",
        )
        contenuti = getattr(risultato, "contents", None) or []
        testo = getattr(contenuti[0], "text", None) if contenuti else None
        if not isinstance(testo, str):
            raise ErroreArchivio(f"la resource {uri} non ha contenuto testuale.")
        return testo

    def prompt_disponibili(self) -> list[PromptArchivio]:
        """I prompt offerti dal server, letti all'avvio."""
        return [
            PromptArchivio(p.name, p.description or "", [a.name for a in p.arguments or []])
            for p in self._prompt_mcp
        ]

    def testo_prompt(self, nome: str, argomenti: dict[str, str]) -> str:
        """Testo del messaggio utente generato dal prompt `nome`; solleva `ErroreArchivio`."""
        risultato = self._attendi(
            lambda: self._sessione.get_prompt(nome, argomenti), _causa_prompt
        )
        for messaggio in getattr(risultato, "messages", None) or []:
            testo = getattr(messaggio.content, "text", None)
            if messaggio.role == "user" and isinstance(testo, str):
                return testo
        raise ErroreArchivio(f"il prompt {nome} non ha prodotto una domanda.")

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
