"""Strumento calendario: differenza fra date e somma di giorni, anche lavorativi."""

import re
from datetime import date, timedelta

from assistente.strumenti.festivita import Festivita

NOME_CALENDARIO = "calendario"

PRIMO = date(1583, 1, 1)
ULTIMO = date(9999, 12, 31)
_GIORNI_TOTALI = (ULTIMO - PRIMO).days
_MAX_DIFFERENZA = 36525
_MAX_LAVORATIVI = 25000
_MAX_FESTIVITA_ELENCATE = 15
_SETTIMANA = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")

_ERR_LUNGO = "Errore: intervallo troppo lungo per contare i giorni lavorativi (massimo 100 anni)."
_ERR_FUORI = "Errore: la data risultante è fuori dagli anni 1583-9999."


class _ErroreArgomento(Exception):
    """Argomento non valido; il testo è il messaggio per il modello."""


def definizione_calendario(citta: str | None) -> dict:
    """Definizione dello strumento calendario; la città del patrono è citata se configurata."""
    if citta:
        elenco = f"nazionali, Pasqua, Pasquetta e patrono di {citta}"
    else:
        elenco = "nazionali, Pasqua e Pasquetta"
    return {
        "type": "function",
        "function": {
            "name": NOME_CALENDARIO,
            "description": (
                "Calcola con le date del calendario italiano, tenendo conto di weekend e "
                f"festività ({elenco}). "
                "Operazione 'differenza': giorni di calendario e giorni lavorativi fra 'data' "
                "e 'data_fine'. "
                "Operazione 'aggiungi': la data che si ottiene aggiungendo 'giorni' a 'data' "
                "(negativi per andare indietro); con 'lavorativi' true conta solo i giorni "
                "lavorativi. "
                "Le date sono nel formato AAAA-MM-GG: per oggi chiama prima ora_corrente. "
                "Chiamalo SEMPRE per domande su giorni lavorativi, scadenze o quanti giorni "
                "mancano a una data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operazione": {
                        "type": "string",
                        "enum": ["differenza", "aggiungi"],
                        "description": "'differenza' oppure 'aggiungi'.",
                    },
                    "data": {
                        "type": "string",
                        "description": "Data di partenza, nel formato AAAA-MM-GG.",
                    },
                    "data_fine": {
                        "type": "string",
                        "description": (
                            "Solo per 'differenza': data di arrivo, nel formato AAAA-MM-GG."
                        ),
                    },
                    "giorni": {
                        "type": "integer",
                        "description": (
                            "Solo per 'aggiungi': numero di giorni da aggiungere, "
                            "negativo per andare indietro."
                        ),
                    },
                    "lavorativi": {
                        "type": "boolean",
                        "description": (
                            "Solo per 'aggiungi': true per contare solo i giorni lavorativi. "
                            "Facoltativo, predefinito false."
                        ),
                    },
                },
                "required": ["operazione", "data"],
            },
        },
    }


def _con_giorno(giorno: date) -> str:
    return f"{giorno.isoformat()} ({_SETTIMANA[giorno.weekday()]})"


def differenza(inizio: date, fine: date, festivita: Festivita) -> str:
    """Giorni di calendario e lavorativi fra due date (partenza esclusa, arrivo incluso)."""
    giorni = (fine - inizio).days
    if abs(giorni) > _MAX_DIFFERENZA:
        return _ERR_LUNGO
    if giorni >= 0:
        primo, ultimo = inizio.toordinal() + 1, fine.toordinal()
    else:
        primo, ultimo = fine.toordinal(), inizio.toordinal() - 1
    lavorativi = 0
    elenco: list[tuple[date, str]] = []
    for ordinale in range(primo, ultimo + 1):
        giorno = date.fromordinal(ordinale)
        if festivita.lavorativo(giorno):
            lavorativi += 1
        if giorno in festivita.dell_anno(giorno.year):
            elenco.append((giorno, festivita.dell_anno(giorno.year)[giorno]))
    segno = -1 if giorni < 0 else 1
    if not elenco:
        coda = "nessuna festività nell'intervallo"
    elif len(elenco) > _MAX_FESTIVITA_ELENCATE:
        coda = f"{len(elenco)} festività nell'intervallo"
    else:
        voci = ", ".join(f"{g.isoformat()} {nome}" for g, nome in elenco)
        coda = f"festività nell'intervallo: {voci}"
    return (
        f"dal {_con_giorno(inizio)} al {_con_giorno(fine)}: "
        f"{giorni} giorni di calendario, {segno * lavorativi} lavorativi; {coda}"
    )


def aggiungi(inizio: date, giorni: int, lavorativi: bool, festivita: Festivita) -> str:
    """Data ottenuta aggiungendo giorni di calendario o lavorativi (negativi: indietro)."""
    if lavorativi:
        if abs(giorni) > _MAX_LAVORATIVI:
            return _ERR_LUNGO
        passo = 1 if giorni >= 0 else -1
        ordinale = inizio.toordinal()
        restanti = abs(giorni)
        while restanti:
            ordinale += passo
            if not PRIMO.toordinal() <= ordinale <= ULTIMO.toordinal():
                return _ERR_FUORI
            if festivita.lavorativo(date.fromordinal(ordinale)):
                restanti -= 1
        arrivo = date.fromordinal(ordinale)
    else:
        if abs(giorni) > _GIORNI_TOTALI:
            return _ERR_FUORI
        ordinale = inizio.toordinal() + giorni
        if not PRIMO.toordinal() <= ordinale <= ULTIMO.toordinal():
            return _ERR_FUORI
        arrivo = date.fromordinal(ordinale)
    unita = "giorno" if abs(giorni) == 1 else "giorni"
    suffisso = (" lavorativo" if abs(giorni) == 1 else " lavorativi") if lavorativi else ""
    segno = "-" if giorni < 0 else "+"
    return (
        f"{_con_giorno(inizio)} {segno} {abs(giorni)} {unita}{suffisso} = {_con_giorno(arrivo)}"
    )


def _testo(valore: object) -> str:
    return f"'{valore}'"


def _data(valore: object) -> date:
    if isinstance(valore, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valore.strip()):
        try:
            giorno = date.fromisoformat(valore.strip())
        except ValueError:
            giorno = None
        if giorno is not None and giorno >= PRIMO:
            return giorno
    raise _ErroreArgomento(
        f"Errore: data non valida: {_testo(valore)}. Usare il formato AAAA-MM-GG con un anno "
        "fra 1583 e 9999; per la data di oggi chiamare prima ora_corrente."
    )


def _giorni(valore: object) -> int:
    if not isinstance(valore, bool):
        try:
            if isinstance(valore, int):
                return valore
            if isinstance(valore, float) and valore.is_integer():
                return int(valore)
            if isinstance(valore, str) and re.fullmatch(r"[+-]?[0-9]+", valore.strip()):
                return int(valore.strip())
        except (ValueError, OverflowError):
            pass
    raise _ErroreArgomento(f"Errore: 'giorni' deve essere un numero intero: {_testo(valore)}.")


def _lavorativi(valore: object) -> bool:
    if valore is None:
        return False
    if isinstance(valore, bool):
        return valore
    if isinstance(valore, str) and valore.lower() in ("true", "false"):
        return valore.lower() == "true"
    raise _ErroreArgomento(
        f"Errore: 'lavorativi' deve essere true o false: {_testo(valore)}."
    )


def _esegui(args: dict, festivita: Festivita) -> str:
    operazione = args.get("operazione")
    nome = operazione.strip().lower() if isinstance(operazione, str) else None
    if nome not in ("differenza", "aggiungi"):
        raise _ErroreArgomento(
            f"Errore: operazione non valida: {_testo(operazione)}. "
            "Usare 'differenza' oppure 'aggiungi'."
        )
    if args.get("data") is None:
        raise _ErroreArgomento("Errore: l'argomento 'data' (AAAA-MM-GG) è obbligatorio.")
    inizio = _data(args["data"])
    if nome == "differenza":
        if args.get("data_fine") is None:
            raise _ErroreArgomento(
                "Errore: l'operazione 'differenza' richiede 'data_fine' (AAAA-MM-GG)."
            )
        return differenza(inizio, _data(args["data_fine"]), festivita)
    if args.get("giorni") is None:
        raise _ErroreArgomento(
            "Errore: l'operazione 'aggiungi' richiede 'giorni' (numero intero)."
        )
    giorni = _giorni(args["giorni"])
    return aggiungi(inizio, giorni, _lavorativi(args.get("lavorativi")), festivita)


def esegui_calendario(args: dict, festivita: Festivita) -> str:
    """Esegue la chiamata del modello; in caso di errore un testo 'Errore: ...', mai eccezioni."""
    try:
        if not isinstance(args, dict):
            raise _ErroreArgomento(
                "Errore: operazione non valida: 'None'. Usare 'differenza' oppure 'aggiungi'."
            )
        return _esegui(args, festivita)
    except _ErroreArgomento as errore:
        return str(errore)
