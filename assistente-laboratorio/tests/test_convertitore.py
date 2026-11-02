from decimal import Decimal

import pytest

from assistente.strumenti.convertitore import (
    DEFINIZIONE_CONVERTI,
    NOME_CONVERTI,
    PREFISSI,
    UNITA,
    converti,
    esegui_converti,
    leggi_unita,
)

MESSAGGIO_UNITA = (
    "Errore: unità non riconosciuta: '{}'. Sono ammessi solo simboli SI con prefisso, "
    "per esempio m, km, kg, mg, s, ms, A, K, °C, mol, cd, N, Pa, kPa, J, W, MW, Hz, V, Ω, "
    "e aree o volumi come cm² e m³."
)
MESSAGGIO_ARGOMENTI = (
    "Errore: argomenti 'valore' (numero), 'da' e 'a' (simboli di unità) obbligatori."
)


@pytest.mark.parametrize(
    "valore, da, a, atteso",
    [
        (2.5, "km", "m", "2500 m"),
        (1500, "m", "km", "1.5 km"),
        (1, "kg", "g", "1000 g"),
        (300, "K", "°C", "26.85 °C"),
        (0, "°C", "K", "273.15 K"),
        (1, "m²", "cm²", "10000 cm²"),
        (1, "m³", "mm³", "1000000000 mm³"),
        (1, "kPa", "Pa", "1000 Pa"),
        (1, "µs", "ns", "1000 ns"),
        (1, "MW", "mW", "1000000000 mW"),
        (1000, "mK", "°C", "-272.15 °C"),
        (1, "m2", "cm^2", "10000 cm^2"),
        (1, "km3", "m³", "1000000000 m³"),
        (1, "kA", "A", "1000 A"),
        (1, "mmol", "mol", "0.001 mol"),
        (1, "kcd", "cd", "1000 cd"),
        (1, "mrad", "rad", "0.001 rad"),
        (1, "msr", "sr", "0.001 sr"),
        (1, "GHz", "Hz", "1000000000 Hz"),
        (1, "kN", "N", "1000 N"),
        (1, "kJ", "J", "1000 J"),
        (1, "nC", "C", "0.000000001 C"),
        (1, "mV", "V", "0.001 V"),
        (1, "µF", "nF", "1000 nF"),
        (1, "kΩ", "Ω", "1000 Ω"),
        (1, "mS", "S", "0.001 S"),
        (1, "mWb", "Wb", "0.001 Wb"),
        (1, "mT", "T", "0.001 T"),
        (1, "mH", "H", "0.001 H"),
        (1, "klm", "lm", "1000 lm"),
        (1, "klx", "lx", "1000 lx"),
        (1, "kBq", "Bq", "1000 Bq"),
        (1, "mGy", "Gy", "0.001 Gy"),
        (1, "mSv", "Sv", "0.001 Sv"),
        (1, "mkat", "kat", "0.001 kat"),
    ],
)
def test_conversioni(valore, da, a, atteso):
    assert converti(valore, da, a) == atteso


@pytest.mark.parametrize(
    "valore, da, a, atteso",
    [
        (1, "kohm", "Ω", "1000 Ω"),
        (1, "us", "ns", "1000 ns"),
        (1, "\u03bcs", "ns", "1000 ns"),
        (0, "degC", "K", "273.15 K"),
    ],
)
def test_alias(valore, da, a, atteso):
    assert converti(valore, da, a) == atteso


@pytest.mark.parametrize(
    "valore, da, a, atteso",
    [
        ("2,5", "km", "m", "2500 m"),
        ("2.5", "km", "m", "2500 m"),
        (-1.5, "km", "m", "-1500 m"),
        (1e-06, "km", "m", "0.001 m"),
        (2, " km ", " m ", "2000 m"),
    ],
)
def test_valori(valore, da, a, atteso):
    assert converti(valore, da, a) == atteso


def test_prefissi_estremi():
    assert converti(1, "Qm", "qm") == "1" + "0" * 60 + " qm"
    piccolo = converti(1, "qm", "Qm")
    assert piccolo.startswith("0.") and "E" not in piccolo


@pytest.mark.parametrize(
    "simbolo",
    [
        "h", "min", "L", "l", "t", "ha", "km/h", "°F", "mi", "kkm", "mkg", "k°C", "°C²",
        "s²", "KM", "Km", "°c", "celsius", "metri", "",
    ],
)
def test_unita_non_riconosciute(simbolo):
    assert leggi_unita(simbolo) is None
    assert converti(1, simbolo, "m") == MESSAGGIO_UNITA.format(simbolo)


def test_unita_di_arrivo_non_riconosciuta():
    assert converti(1, "m", "mi") == MESSAGGIO_UNITA.format("mi")


def test_grandezze_diverse():
    assert converti(1, "kg", "m") == (
        "Errore: non si può convertire 'kg' (massa) in 'm' (lunghezza): grandezze diverse."
    )


@pytest.mark.parametrize("da, a", [("Hz", "Bq"), ("Gy", "Sv"), ("m²", "m³"), ("m", "m²")])
def test_grandezze_diverse_con_stessa_dimensione(da, a):
    assert converti(1, da, a).startswith("Errore: non si può convertire")


@pytest.mark.parametrize("valore", ["abc", "1.000,5", "nan", "inf", "1e3", "\u0661", ""])
def test_valori_non_numerici(valore):
    assert converti(valore, "m", "km") == f"Errore: valore non numerico: '{valore}'."


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"valore": 1, "da": "m"},
        {"valore": True, "da": "m", "a": "km"},
        {"valore": 1, "da": 5, "a": "m"},
        {"valore": None, "da": "m", "a": "km"},
        {"valore": [1], "da": "m", "a": "km"},
    ],
)
def test_esegui_argomenti_mancanti(args):
    assert esegui_converti(args) == MESSAGGIO_ARGOMENTI


def test_esegui_converti():
    assert esegui_converti({"valore": 2.5, "da": "km", "a": "m"}) == "2500 m"


def test_lettura_univoca():
    letture = {}
    for unita, dati in UNITA.items():
        letture.setdefault(unita, set()).add((dati.grandezza, dati.fattore))
        if not dati.prefissabile:
            continue
        for prefisso, fattore in PREFISSI.items():
            simbolo = prefisso + unita
            lettura = leggi_unita(simbolo)
            assert lettura is not None, simbolo
            assert lettura.grandezza == dati.grandezza, simbolo
            assert lettura.fattore == fattore * dati.fattore, simbolo
            letture.setdefault(simbolo, set()).add((dati.grandezza, fattore * dati.fattore))
    ambigui = {s: v for s, v in letture.items() if len(v) > 1}
    assert ambigui == {}


def test_tabelle():
    assert len([p for p in PREFISSI if p not in ("u", "\u03bc")]) == 24
    assert PREFISSI["da"] == Decimal(10)
    assert PREFISSI["\u00b5"] == PREFISSI["u"] == PREFISSI["\u03bc"] == Decimal("1e-6")


def test_definizione():
    funzione = DEFINIZIONE_CONVERTI["function"]
    assert funzione["name"] == NOME_CONVERTI == "converti_unita"
    assert funzione["parameters"]["required"] == ["valore", "da", "a"]
    assert "SEMPRE" in funzione["description"]
    assert "300 K in gradi Celsius" in funzione["description"]
