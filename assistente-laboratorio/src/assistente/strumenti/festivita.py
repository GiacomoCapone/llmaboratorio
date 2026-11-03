"""Festività italiane: file JSON, Pasqua calcolata e santo patrono di una città."""

import json
import re
from datetime import date, timedelta
from pathlib import Path

from assistente.config import ErroreConfigurazione

PERCORSO_FESTIVITA = Path(__file__).with_name("festivita.json")


def pasqua(anno: int) -> date:
    """Domenica di Pasqua (calendario gregoriano, algoritmo di Meeus/Jones/Butcher)."""
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese, giorno = divmod(h + l - 7 * m + 114, 31)
    return date(anno, mese, giorno + 1)


class Festivita:
    """Festività di un anno qualsiasi: nazionali, Pasqua, Pasquetta e patrono."""

    def __init__(
        self,
        nazionali: dict[tuple[int, int], str],
        patrono: tuple[tuple[int, int], str] | None,
        citta: str | None,
    ):
        self.citta = citta
        self._nazionali = nazionali
        self._patrono = patrono
        self._cache: dict[int, dict[date, str]] = {}

    def dell_anno(self, anno: int) -> dict[date, str]:
        """Festività dell'anno; più ricorrenze nello stesso giorno formano una sola voce."""
        if anno not in self._cache:
            voci: dict[date, list[str]] = {}
            for (mese, giorno), nome in self._nazionali.items():
                voci.setdefault(date(anno, mese, giorno), []).append(nome)
            domenica = pasqua(anno)
            voci.setdefault(domenica, []).append("Pasqua")
            voci.setdefault(domenica + timedelta(days=1), []).append(
                "Lunedì dell'Angelo (Pasquetta)"
            )
            if self._patrono is not None:
                (mese, giorno), santo = self._patrono
                voci.setdefault(date(anno, mese, giorno), []).append(
                    f"{santo} (patrono di {self.citta})"
                )
            self._cache[anno] = {giorno: ", ".join(nomi) for giorno, nomi in voci.items()}
        return self._cache[anno]

    def lavorativo(self, giorno: date) -> bool:
        """Da lunedì a venerdì e non festivo."""
        return giorno.weekday() < 5 and giorno not in self.dell_anno(giorno.year)


def _mese_giorno(chiave: object) -> tuple[int, int]:
    if not isinstance(chiave, str) or not re.fullmatch(r"[0-9]{2}-[0-9]{2}", chiave):
        raise ValueError(f"data non valida: {chiave!r}")
    mese, giorno = int(chiave[:2]), int(chiave[3:])
    date(2001, mese, giorno)  # anno non bisestile: 02-29 è respinto
    return mese, giorno


def _nome(valore: object, contesto: str) -> str:
    if not isinstance(valore, str) or not valore.strip():
        raise ValueError(f"nome mancante o vuoto in {contesto}")
    return valore


def _leggi(percorso: Path):
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
        if not isinstance(dati, dict):
            raise ValueError("il file deve contenere un oggetto")
        for chiave in ("nazionali", "patroni"):
            if not isinstance(dati.get(chiave), dict):
                raise ValueError(f"chiave '{chiave}' mancante o non valida")
        nazionali = {
            _mese_giorno(k): _nome(v, f"'nazionali' ({k})") for k, v in dati["nazionali"].items()
        }
        patroni = {}
        for citta, voce in dati["patroni"].items():
            if not isinstance(voce, dict):
                raise ValueError(f"patrono di {citta!r} non valido")
            patroni[_nome(citta, "'patroni'")] = (
                _mese_giorno(voce.get("data")),
                _nome(voce.get("santo"), f"patrono di {citta!r}"),
            )
    except (OSError, ValueError) as errore:  # JSONDecodeError è un ValueError
        raise ErroreConfigurazione(
            f"File delle festività non valido: {percorso}: {errore}."
        ) from errore
    return nazionali, patroni


def carica_festivita(citta: str | None, percorso: Path = PERCORSO_FESTIVITA) -> Festivita:
    """Legge il file delle festività e sceglie il patrono della città (se indicata)."""
    nazionali, patroni = _leggi(percorso)
    richiesta = (citta or "").strip()
    if not richiesta:
        return Festivita(nazionali, None, None)
    for nome, patrono in patroni.items():
        if nome.casefold() == richiesta.casefold():
            return Festivita(nazionali, patrono, nome)
    elenco = ", ".join(sorted(patroni))
    raise ErroreConfigurazione(
        f"Città del patrono sconosciuta: {citta!r}. "
        f"Città disponibili: {elenco} (file {percorso})."
    )
