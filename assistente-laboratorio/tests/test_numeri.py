from decimal import ROUND_HALF_EVEN, Decimal, getcontext

import pytest

from assistente.strumenti.numeri import contesto, formatta


@pytest.mark.parametrize(
    "valore, atteso",
    [
        (Decimal("2.50"), "2.5"),
        (Decimal("1E+3"), "1000"),
        (Decimal("-0"), "0"),
        (Decimal("0.000"), "0"),
        (Decimal("1E+60"), "1" + "0" * 60),
        (Decimal("1E-30"), "0." + "0" * 29 + "1"),
    ],
)
def test_formatta(valore, atteso):
    assert formatta(valore) == atteso


def test_contesto():
    with contesto():
        terzo = Decimal(1) / Decimal(3)
        assert getcontext().rounding == ROUND_HALF_EVEN
    assert len(terzo.as_tuple().digits) == 28
