"""Collegamento al modello servito da LM Studio (API compatibile con OpenAI)."""

from collections.abc import Callable

import httpx
from langchain_openai import ChatOpenAI

from assistente.config import Config


class ErroreModello(Exception):
    """Server del modello non raggiungibile o modello non disponibile."""


def elenca_modelli(base_url: str, client: httpx.Client | None = None) -> list[str]:
    url = f"{base_url}/models"
    chiudi = client is None
    client = client or httpx.Client(timeout=5)
    try:
        risposta = client.get(url, timeout=5)
    except httpx.HTTPError as errore:
        raise ErroreModello(
            f"Server non raggiungibile all'indirizzo {url}: {errore}. "
            "Verificare che LM Studio sia avviato con il server locale attivo."
        ) from errore
    finally:
        if chiudi:
            client.close()

    if risposta.status_code != 200:
        raise ErroreModello(f"Risposta inattesa da {url}: stato HTTP {risposta.status_code}.")
    try:
        return [voce["id"] for voce in risposta.json()["data"]]
    except (ValueError, KeyError, TypeError) as errore:
        raise ErroreModello(
            f"Risposta di {url} non valida: atteso un JSON con il campo 'data'."
        ) from errore


def verifica_modello(
    config: Config, elenca: Callable[[str], list[str]] = elenca_modelli
) -> None:
    disponibili = elenca(config.base_url)
    if config.model not in disponibili:
        elenco = ", ".join(disponibili) or "(nessuno)"
        raise ErroreModello(
            f"Il modello {config.model!r} non è disponibile sul server. "
            f"Identificativi disponibili: {elenco}."
        )


def crea_llm(config: Config) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=config.base_url,
        model=config.model,
        api_key="lm-studio",
        temperature=0,
    )
