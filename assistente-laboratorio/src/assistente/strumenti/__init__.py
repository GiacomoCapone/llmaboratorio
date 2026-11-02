"""Registro degli strumenti a disposizione del modello."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from assistente.strumenti.calcolatrice import DEFINIZIONE_CALCOLA, esegui_calcola
from assistente.strumenti.convertitore import DEFINIZIONE_CONVERTI, esegui_converti
from assistente.strumenti.orologio import definizione_ora_corrente, esegui_ora_corrente


@dataclass(frozen=True)
class Strumento:
    definizione: dict  # schema "type": "function" per il tool calling
    esegui: Callable[[dict], str]  # argomenti (già un dict) → risultato o "Errore: ..."

    @property
    def nome(self) -> str:
        return self.definizione["function"]["name"]


def registro(strumenti: list[Strumento]) -> dict[str, Strumento]:
    """Registro per nome, nell'ordine dato; un nome ripetuto è un errore di programmazione."""
    per_nome: dict[str, Strumento] = {}
    for strumento in strumenti:
        if strumento.nome in per_nome:
            raise ValueError(f"nome duplicato nel registro: '{strumento.nome}'")
        per_nome[strumento.nome] = strumento
    return per_nome


def crea_strumenti(
    adesso: Callable[[], datetime], fuso_predefinito: str
) -> dict[str, Strumento]:
    """Costruisce il registro, legando a ciascuno strumento le sue dipendenze."""
    strumenti = [
        Strumento(
            definizione_ora_corrente(fuso_predefinito),
            lambda args: esegui_ora_corrente(args, adesso, fuso_predefinito),
        ),
        Strumento(DEFINIZIONE_CALCOLA, esegui_calcola),
        Strumento(DEFINIZIONE_CONVERTI, esegui_converti),
    ]
    return registro(strumenti)
