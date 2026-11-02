"""Aritmetica decimale condivisa dagli strumenti: precisione e formato dei risultati."""

from decimal import ROUND_HALF_EVEN, Decimal, localcontext


def contesto():
    """Contesto decimale degli strumenti: 28 cifre significative, arrotondamento al pari."""
    return localcontext(prec=28, rounding=ROUND_HALF_EVEN)


def formatta(valore: Decimal) -> str:
    """Notazione decimale semplice: niente esponente né zeri finali; lo zero (anche -0) è "0"."""
    if valore == 0:
        return "0"
    return format(valore.normalize(), "f")
