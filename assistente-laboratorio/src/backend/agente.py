"""Client HTTP del servizio dell'agente (step 6)."""

import httpx

_NON_VALIDA = "agente non disponibile: risposta non valida"


class ErroreAgente(Exception):
    """Errore da restituire al chiamante con questo codice (400, 422 o 502)."""

    def __init__(self, codice: int, messaggio: str):
        super().__init__(messaggio)
        self.codice = codice
        self.messaggio = messaggio


def _corpo_json(risposta: httpx.Response):
    try:
        return risposta.json()
    except ValueError:
        return None


def _errore_del_corpo(corpo) -> str | None:
    if isinstance(corpo, dict) and isinstance(corpo.get("errore"), str):
        return corpo["errore"]
    return None


class ClientAgente:
    def __init__(self, url: str, timeout: float, transport: httpx.BaseTransport | None = None):
        self._url = url
        self._timeout = timeout
        self._transport = transport

    def _chiama(self, metodo: str, percorso: str, **kwargs) -> dict:
        try:
            with httpx.Client(
                base_url=self._url, timeout=self._timeout, transport=self._transport
            ) as client:
                risposta = client.request(metodo, percorso, **kwargs)
        except httpx.TimeoutException as e:
            raise ErroreAgente(502, f"agente non disponibile: tempo scaduto dopo {self._timeout:g} s") from e
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            raise ErroreAgente(502, f"agente non disponibile: {e}") from e

        corpo = _corpo_json(risposta)
        errore = _errore_del_corpo(corpo)
        if risposta.status_code == 200:
            if not isinstance(corpo, dict):
                raise ErroreAgente(502, _NON_VALIDA)
            return corpo
        if risposta.status_code in (400, 422) and errore is not None:
            raise ErroreAgente(risposta.status_code, errore)
        if risposta.status_code not in (400, 422) and errore is not None:
            raise ErroreAgente(502, f"agente non disponibile: {errore}")
        raise ErroreAgente(502, _NON_VALIDA)

    def prompt(self) -> dict:
        return self._chiama("GET", "/prompt")

    def turno(
        self, cronologia: list[dict], domanda: str | None = None, prompt: dict | None = None
    ) -> tuple[str, list[dict]]:
        corpo: dict = {"domanda": domanda} if prompt is None else {"prompt": prompt}
        corpo["cronologia"] = cronologia
        risultato = self._chiama("POST", "/turno", json=corpo)
        risposta, nuova = risultato.get("risposta"), risultato.get("cronologia")
        if not isinstance(risposta, str) or not isinstance(nuova, list):
            raise ErroreAgente(502, _NON_VALIDA)
        return risposta, nuova
