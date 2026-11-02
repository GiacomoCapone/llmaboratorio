import pytest

from assistente.strumenti.calcolatrice import (
    DEFINIZIONE_CALCOLA,
    LUNGHEZZA_MASSIMA,
    NOME_CALCOLA,
    calcola,
    esegui_calcola,
)


@pytest.mark.parametrize(
    "espressione, atteso",
    [
        ("2 + 3 * 4", "14"),
        ("8 - 3 - 2", "3"),
        ("8 / 4 / 2", "1"),
        ("(2 + 3) * 4", "20"),
        ("-3 + 5", "2"),
        ("-(2 + 3)", "-5"),
        ("--2", "2"),
        ("2 * -3", "-6"),
        ("+4", "4"),
        ("0.1 + 0.2", "0.3"),
        ("12,5 * 4", "50"),
        ("10 / 4", "2.5"),
        ("2,50 * 2", "5"),
        ("1 / 3", "0.3333333333333333333333333333"),
        ("100 * 10", "1000"),
        ("-0", "0"),
        ("7 - 7", "0"),
        ("\t1 +  1 ", "2"),
        ("(" * 99 + "1" + ")" * 99, "1"),
    ],
)
def test_risultati(espressione, atteso):
    assert calcola(espressione) == atteso


def test_risultato_grande_senza_esponente():
    risultato = calcola("99999999999999999999999999999 + 1")
    assert "E" not in risultato
    assert risultato.startswith("1")


@pytest.mark.parametrize(
    "espressione, atteso",
    [
        ("", "Errore: espressione vuota."),
        ("   ", "Errore: espressione vuota."),
        ("1+" * 100 + "1", "Errore: espressione troppo lunga (massimo 200 caratteri)."),
        ("5 / 0", "Errore: divisione per zero."),
        ("5 / (2 - 2)", "Errore: divisione per zero."),
        ("0 / 0", "Errore: divisione per zero."),
        (
            "2 x 3",
            "Errore: carattere non ammesso 'x' in posizione 3. "
            "Sono ammessi numeri, + - * / e parentesi.",
        ),
    ],
)
def test_errori_esatti(espressione, atteso):
    assert calcola(espressione) == atteso


def test_limite_esatto():
    espressione = "1+" * 99 + "11"
    assert len(espressione) == LUNGHEZZA_MASSIMA == 200
    assert calcola(espressione) == "110"


@pytest.mark.parametrize(
    "espressione, dettaglio",
    [
        ("(2 + 3", "parentesi ')' mancante"),
        ("2 +", "atteso un numero o '(' in posizione 4"),
        ("2 3", "testo inatteso in posizione 3"),
        ("2 + 3)", "testo inatteso in posizione 6"),
        ("2 ** 3", "atteso un numero o '(' in posizione 4"),
    ],
)
def test_errori_di_sintassi(espressione, dettaglio):
    assert calcola(espressione) == f"Errore: espressione non valida: {dettaglio}."


@pytest.mark.parametrize(
    "espressione",
    [
        "2 ^ 3",
        "1e5",
        "0x10",
        "abs(-2)",
        "__import__('os')",
        "3.5.1",
        ".5",
        "5.",
        "50%",
        "2 =",
        "\u0661 + 1",
        "1.000,50",
    ],
)
def test_respinti(espressione):
    assert calcola(espressione).startswith("Errore:")


def test_errore_elenca_simboli_ammessi():
    assert "+ - * /" in calcola("12,5 x 4")


def test_esegui_calcola():
    assert esegui_calcola({"espressione": "2+2"}) == "4"


@pytest.mark.parametrize("args", [{}, {"espressione": 12}, {"espressione": None}])
def test_esegui_calcola_argomento_non_valido(args):
    assert (
        esegui_calcola(args)
        == "Errore: argomento 'espressione' mancante o non testuale."
    )


def test_definizione():
    funzione = DEFINIZIONE_CALCOLA["function"]
    assert DEFINIZIONE_CALCOLA["type"] == "function"
    assert funzione["name"] == NOME_CALCOLA == "calcola"
    assert funzione["parameters"]["required"] == ["espressione"]
    assert "SEMPRE" in funzione["description"]
    assert "50 * 20 / 100" in funzione["description"]
