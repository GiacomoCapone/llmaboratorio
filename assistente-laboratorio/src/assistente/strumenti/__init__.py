"""Registro degli strumenti a disposizione del modello."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from assistente.strumenti.orologio import definizione_ora_corrente, esegui_ora_corrente


@dataclass(frozen=True)
class Strumento:
    definizione: dict  # schema "type": "function" per il tool calling
    esegui: Callable[[dict], str]  # argomenti (già un dict) → risultato o "Errore: ..."

    @property
    def nome(self) -> str:
        return self.definizione["function"]["name"]


def crea_strumenti(
    adesso: Callable[[], datetime], fuso_predefinito: str
) -> dict[str, Strumento]:
    """Costruisce il registro, legando a ciascuno strumento le sue dipendenze."""
    strumenti = [
        Strumento(
            definizione_ora_corrente(fuso_predefinito),
            lambda args: esegui_ora_corrente(args, adesso, fuso_predefinito),
        ),
    ]
    return {s.nome: s for s in strumenti}
