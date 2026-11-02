"""Calcolatrice sicura: quattro operazioni con Decimal, senza eval.

Grammatica (operatori associativi a sinistra):
    espressione := termine (("+" | "-") termine)*
    termine     := fattore (("*" | "/") fattore)*
    fattore     := ("+" | "-") fattore | numero | "(" espressione ")"
    numero      := [0-9]+ ([.,] [0-9]+)?
"""

import re
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import NamedTuple

NOME_CALCOLA = "calcola"
LUNGHEZZA_MASSIMA = 200

DEFINIZIONE_CALCOLA = {
    "type": "function",
    "function": {
        "name": NOME_CALCOLA,
        "description": (
            "Calcola il risultato esatto di un'espressione aritmetica con le quattro "
            "operazioni (+, -, *, /) e le parentesi. Chiamalo SEMPRE quando l'utente "
            "chiede un calcolo, invece di farlo a mente, per esempio 'quanto fa 12,5 * 4' "
            "o '(3 + 7) / 4'. Per le percentuali scrivi la moltiplicazione, per esempio "
            "50 * 20 / 100."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "espressione": {
                    "type": "string",
                    "description": (
                        "Espressione da calcolare, per esempio (3 + 7) / 4. Numeri con il "
                        "punto o la virgola decimale; niente unità di misura, simboli di "
                        "percentuale o funzioni."
                    ),
                }
            },
            "required": ["espressione"],
        },
    },
}

# Solo cifre ASCII: \d accetterebbe anche cifre Unicode.
_TOKEN = re.compile(r"(?P<numero>[0-9]+(?:[.,][0-9]+)?)|(?P<operatore>[-+*/()])|(?P<spazio>[ \t]+)")


class _ErroreCalcolo(Exception):
    """Errore con un messaggio già pronto per il modello (senza il prefisso 'Errore: ')."""


class _Token(NamedTuple):
    testo: str
    posizione: int  # contata da 1
    numero: bool


def _tokenizza(testo: str) -> list[_Token]:
    token: list[_Token] = []
    indice = 0
    while indice < len(testo):
        trovato = _TOKEN.match(testo, indice)
        if trovato is None:
            raise _ErroreCalcolo(
                f"carattere non ammesso '{testo[indice]}' in posizione {indice + 1}. "
                "Sono ammessi numeri, + - * / e parentesi."
            )
        if trovato.lastgroup != "spazio":
            token.append(_Token(trovato.group(), indice + 1, trovato.lastgroup == "numero"))
        indice = trovato.end()
    return token


class _Parser:
    def __init__(self, token: list[_Token], fine: int):
        self.token = token
        self.indice = 0
        self.fine = fine  # posizione dopo l'ultimo carattere

    def _corrente(self) -> _Token | None:
        return self.token[self.indice] if self.indice < len(self.token) else None

    def _posizione(self) -> int:
        corrente = self._corrente()
        return corrente.posizione if corrente else self.fine

    def _accetta(self, *operatori: str) -> str | None:
        corrente = self._corrente()
        if corrente and not corrente.numero and corrente.testo in operatori:
            self.indice += 1
            return corrente.testo
        return None

    def analizza(self) -> Decimal:
        valore = self._espressione()
        if self._corrente() is not None:
            raise _ErroreCalcolo(
                f"espressione non valida: testo inatteso in posizione {self._posizione()}."
            )
        return valore

    def _espressione(self) -> Decimal:
        valore = self._termine()
        while operatore := self._accetta("+", "-"):
            destro = self._termine()
            valore = valore + destro if operatore == "+" else valore - destro
        return valore

    def _termine(self) -> Decimal:
        valore = self._fattore()
        while operatore := self._accetta("*", "/"):
            destro = self._fattore()
            if operatore == "*":
                valore = valore * destro
            elif destro == 0:
                raise _ErroreCalcolo("divisione per zero.")
            else:
                valore = valore / destro
        return valore

    def _fattore(self) -> Decimal:
        if segno := self._accetta("+", "-"):
            valore = self._fattore()
            return -valore if segno == "-" else +valore
        corrente = self._corrente()
        if corrente and corrente.numero:
            self.indice += 1
            return Decimal(corrente.testo.replace(",", "."))
        if self._accetta("("):
            valore = self._espressione()
            if not self._accetta(")"):
                raise _ErroreCalcolo("espressione non valida: parentesi ')' mancante.")
            return valore
        raise _ErroreCalcolo(
            f"espressione non valida: atteso un numero o '(' in posizione {self._posizione()}."
        )


def _formatta(valore: Decimal) -> str:
    if valore == 0:
        return "0"
    return format(valore.normalize(), "f")


def calcola(espressione: str) -> str:
    """Risultato esatto dell'espressione oppure un testo 'Errore: ...'; non solleva eccezioni."""
    if not espressione.strip():
        return "Errore: espressione vuota."
    if len(espressione) > LUNGHEZZA_MASSIMA:
        return f"Errore: espressione troppo lunga (massimo {LUNGHEZZA_MASSIMA} caratteri)."
    try:
        with localcontext(prec=28, rounding=ROUND_HALF_EVEN):
            token = _tokenizza(espressione)
            return _formatta(_Parser(token, len(espressione) + 1).analizza())
    except _ErroreCalcolo as errore:
        return f"Errore: {errore}"


def esegui_calcola(args: dict) -> str:
    espressione = args.get("espressione")
    if not isinstance(espressione, str):
        return "Errore: argomento 'espressione' mancante o non testuale."
    return calcola(espressione)
