"""Convertitore di unità SI: unità di base e derivate con prefisso, aree e volumi, K e °C."""

import re
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

from assistente.strumenti.numeri import contesto, formatta

NOME_CONVERTI = "converti_unita"

DEFINIZIONE_CONVERTI = {
    "type": "function",
    "function": {
        "name": NOME_CONVERTI,
        "description": (
            "Converte una misura fra unità del Sistema Internazionale (SI). Chiamalo SEMPRE "
            "quando l'utente chiede di convertire una misura, per esempio 'quanti metri sono "
            "2,5 km' o '300 K in gradi Celsius'. Accetta solo simboli SI con prefisso (km, mg, "
            "µs, kPa, MW), aree e volumi come cm² o m³, K e °C; non accetta ore, litri, km/h "
            "né unità imperiali."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "valore": {
                    "type": ["number", "string"],
                    "description": (
                        "Valore da convertire, per esempio 2.5 (punto o virgola decimale, "
                        "senza separatore delle migliaia)."
                    ),
                },
                "da": {
                    "type": "string",
                    "description": "Simbolo dell'unità di partenza, per esempio km.",
                },
                "a": {
                    "type": "string",
                    "description": "Simbolo dell'unità di arrivo, per esempio m.",
                },
            },
            "required": ["valore", "da", "a"],
        },
    },
}


class Unita(NamedTuple):
    grandezza: str
    fattore: Decimal  # verso l'unità SI coerente
    scostamento: Decimal = Decimal(0)  # solo °C: valore in K = valore × fattore + scostamento
    prefissabile: bool = True


_UNO = Decimal(1)

UNITA: dict[str, Unita] = {
    "m": Unita("lunghezza", _UNO),
    "g": Unita("massa", Decimal("0.001")),  # l'unità SI è kg; i prefissi si applicano al grammo
    "s": Unita("tempo", _UNO),
    "A": Unita("corrente elettrica", _UNO),
    "K": Unita("temperatura", _UNO),
    "°C": Unita("temperatura", _UNO, Decimal("273.15"), prefissabile=False),
    "degC": Unita("temperatura", _UNO, Decimal("273.15"), prefissabile=False),
    "mol": Unita("quantità di sostanza", _UNO),
    "cd": Unita("intensità luminosa", _UNO),
    "rad": Unita("angolo piano", _UNO),
    "sr": Unita("angolo solido", _UNO),
    "Hz": Unita("frequenza", _UNO),
    "N": Unita("forza", _UNO),
    "Pa": Unita("pressione", _UNO),
    "J": Unita("energia", _UNO),
    "W": Unita("potenza", _UNO),
    "C": Unita("carica elettrica", _UNO),
    "V": Unita("tensione elettrica", _UNO),
    "F": Unita("capacità elettrica", _UNO),
    "Ω": Unita("resistenza elettrica", _UNO),
    "ohm": Unita("resistenza elettrica", _UNO),
    "S": Unita("conduttanza elettrica", _UNO),
    "Wb": Unita("flusso magnetico", _UNO),
    "T": Unita("induzione magnetica", _UNO),
    "H": Unita("induttanza", _UNO),
    "lm": Unita("flusso luminoso", _UNO),
    "lx": Unita("illuminamento", _UNO),
    "Bq": Unita("attività (radionuclidi)", _UNO),
    "Gy": Unita("dose assorbita", _UNO),
    "Sv": Unita("dose equivalente", _UNO),
    "kat": Unita("attività catalitica", _UNO),
}

_POTENZE_PREFISSI = {
    "q": -30, "r": -27, "y": -24, "z": -21, "a": -18, "f": -15, "p": -12, "n": -9,
    "µ": -6, "m": -3, "c": -2, "d": -1, "da": 1, "h": 2, "k": 3, "M": 6, "G": 9,
    "T": 12, "P": 15, "E": 18, "Z": 21, "Y": 24, "R": 27, "Q": 30,
}
PREFISSI: dict[str, Decimal] = {p: Decimal(10) ** e for p, e in _POTENZE_PREFISSI.items()}
PREFISSI["u"] = PREFISSI["µ"]  # alias per chi non può scrivere µ
PREFISSI["μ"] = PREFISSI["µ"]  # mu greca, spesso usata al posto del segno di micro

_ESPONENTE = re.compile(r"(?P<base>.+?)(?:\^?(?P<cifra>[23])|(?P<apice>[²³]))")
_GRANDEZZE_POTENZA = {2: "area", 3: "volume"}
_VALORE = re.compile(r"[+-]?[0-9]+(?:[.,][0-9]+)?")


def _leggi_base(simbolo: str) -> Unita | None:
    """Unità senza prefisso, oppure un solo prefisso seguito da un'unità che lo ammette."""
    if simbolo in UNITA:
        return UNITA[simbolo]
    for prefisso, fattore in PREFISSI.items():
        resto = simbolo[len(prefisso):]
        if simbolo.startswith(prefisso) and resto in UNITA and UNITA[resto].prefissabile:
            unita = UNITA[resto]
            return unita._replace(fattore=fattore * unita.fattore)
    return None


def leggi_unita(simbolo: str) -> Unita | None:
    """Legge un simbolo come `km`, `µs`, `°C`, `cm²`; None se non è un'unità ammessa."""
    simbolo = simbolo.strip()
    potenza = _ESPONENTE.fullmatch(simbolo)
    if potenza is None:
        return _leggi_base(simbolo)
    esponente = int(potenza["cifra"] or {"²": 2, "³": 3}[potenza["apice"]])
    base = _leggi_base(potenza["base"])
    if base is None or base.grandezza != "lunghezza":
        return None
    with contesto():
        fattore = base.fattore**esponente
    return Unita(_GRANDEZZE_POTENZA[esponente], fattore)


def _leggi_valore(valore) -> Decimal | None:
    if isinstance(valore, bool):
        return None
    if isinstance(valore, (int, float)):
        numero = Decimal(str(valore))
    elif isinstance(valore, str) and _VALORE.fullmatch(valore.strip()):
        numero = Decimal(valore.strip().replace(",", "."))
    else:
        return None
    return numero if numero.is_finite() else None


def _messaggio_unita(simbolo: str) -> str:
    return (
        f"Errore: unità non riconosciuta: '{simbolo}'. Sono ammessi solo simboli SI con "
        "prefisso, per esempio m, km, kg, mg, s, ms, A, K, °C, mol, cd, N, Pa, kPa, J, W, MW, "
        "Hz, V, Ω, e aree o volumi come cm² e m³."
    )


def converti(valore, da: str, a: str) -> str:
    """Valore convertito con il simbolo di arrivo, oppure 'Errore: ...'; non solleva eccezioni."""
    da, a = da.strip(), a.strip()
    numero = _leggi_valore(valore)
    if numero is None:
        return f"Errore: valore non numerico: '{valore}'."
    partenza, arrivo = leggi_unita(da), leggi_unita(a)
    if partenza is None:
        return _messaggio_unita(da)
    if arrivo is None:
        return _messaggio_unita(a)
    if partenza.grandezza != arrivo.grandezza:
        return (
            f"Errore: non si può convertire '{da}' ({partenza.grandezza}) in '{a}' "
            f"({arrivo.grandezza}): grandezze diverse."
        )
    try:
        with contesto():
            coerente = numero * partenza.fattore + partenza.scostamento
            risultato = (coerente - arrivo.scostamento) / arrivo.fattore
            return f"{formatta(risultato)} {a}"
    except (InvalidOperation, ArithmeticError):
        return f"Errore: valore non numerico: '{valore}'."


def esegui_converti(args: dict) -> str:
    valore, da, a = args.get("valore"), args.get("da"), args.get("a")
    if (
        valore is None
        or isinstance(valore, bool)
        or not isinstance(valore, (int, float, str))
        or not isinstance(da, str)
        or not isinstance(a, str)
    ):
        return (
            "Errore: argomenti 'valore' (numero), 'da' e 'a' (simboli di unità) obbligatori."
        )
    return converti(valore, da, a)
