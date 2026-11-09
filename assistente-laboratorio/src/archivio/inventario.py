"""Inventario del laboratorio: caricamento e validazione del CSV, ricerca e dettaglio."""

import csv
import unicodedata
from dataclasses import dataclass
from pathlib import Path

PERCORSO_INVENTARIO = Path(__file__).with_name("inventario.csv")

COLONNE = ["codice", "nome", "categoria", "quantita", "collocazione", "descrizione"]
OBBLIGATORI = ("codice", "nome", "categoria", "collocazione")
LUNGHEZZA_MASSIMA = 100
RISULTATI_MASSIMI = 10
RADICE_DA = 4  # le parole di almeno 4 caratteri perdono l'ultimo (singolare/plurale)


class ErroreInventario(Exception):
    """Il file dell'inventario non è valido; il messaggio indica la riga."""


@dataclass(frozen=True)
class Articolo:
    codice: str
    nome: str
    categoria: str
    quantita: int
    collocazione: str
    descrizione: str


def normalizza(testo: str) -> str:
    """Minuscolo senza accenti, per confrontare i testi."""
    scomposto = unicodedata.normalize("NFD", testo)
    senza_segni = "".join(c for c in scomposto if not unicodedata.combining(c))
    return senza_segni.casefold()


def _errore(riga: int, motivo: str) -> ErroreInventario:
    return ErroreInventario(f"inventario non valido, riga {riga}: {motivo}.")


def _articolo_da_campi(riga: int, campi: list[str]) -> Articolo:
    if len(campi) != len(COLONNE):
        raise _errore(riga, f"attesi {len(COLONNE)} campi, trovati {len(campi)}")
    valori = dict(zip(COLONNE, (c.strip() for c in campi)))
    for nome in OBBLIGATORI:
        if not valori[nome]:
            raise _errore(riga, f"campo '{nome}' vuoto")
    quantita = valori["quantita"]
    if not (quantita.isascii() and quantita.isdigit()):
        raise _errore(riga, f"quantità non valida '{quantita}'")
    return Articolo(**{**valori, "quantita": int(quantita)})


def carica(percorso: Path) -> "Inventario":
    """Legge e valida il CSV (UTF-8, separatore ';', BOM tollerato).

    Le righe vuote sono ignorate; la prima riga non vuota è l'intestazione.
    """
    articoli: list[Articolo] = []
    codici: set[str] = set()
    intestazione_letta = False
    with open(percorso, encoding="utf-8-sig", newline="") as file:
        for numero, campi in enumerate(csv.reader(file, delimiter=";"), start=1):
            if not any(c.strip() for c in campi):
                continue
            if not intestazione_letta:
                if [c.strip() for c in campi] != COLONNE:
                    raise _errore(numero, "intestazione non valida")
                intestazione_letta = True
                continue
            articolo = _articolo_da_campi(numero, campi)
            chiave = normalizza(articolo.codice)
            if chiave in codici:
                raise _errore(numero, f"codice ripetuto '{articolo.codice}'")
            codici.add(chiave)
            articoli.append(articolo)
    if not intestazione_letta:
        raise _errore(1, "intestazione non valida")
    return Inventario(articoli)


def _pezzi(quantita: int) -> str:
    return "1 pezzo" if quantita == 1 else f"{quantita} pezzi"


def _termini(testo: str) -> list[str]:
    """Parole normalizzate; quelle di almeno 4 caratteri sono ridotte alla radice."""
    return [p[:-1] if len(p) >= RADICE_DA else p for p in normalizza(testo).split()]


class Inventario:
    """Articoli del laboratorio, in sola lettura, in ordine di codice."""

    def __init__(self, articoli: list[Articolo]):
        ordinati = sorted(articoli, key=lambda a: normalizza(a.codice))
        self.articoli: tuple[Articolo, ...] = tuple(ordinati)
        self._campi = {
            a.codice: [normalizza(c) for c in (a.nome, a.categoria, a.descrizione, a.collocazione)]
            for a in self.articoli
        }
        self._per_codice = {normalizza(a.codice): a for a in self.articoli}
        self._categorie = {normalizza(a.categoria): a.categoria for a in self.articoli}

    def cerca(self, testo: str | None, categoria: str | None) -> str:
        """Testo del risultato della ricerca, o di un errore che inizia con «Errore:»."""
        testo = (testo or "").strip()
        categoria = (categoria or "").strip()
        if len(testo) > LUNGHEZZA_MASSIMA or len(categoria) > LUNGHEZZA_MASSIMA:
            return f"Errore: testo troppo lungo (massimo {LUNGHEZZA_MASSIMA} caratteri)."
        if not testo and not categoria:
            return "Errore: indicare un testo da cercare o una categoria."
        chiave_categoria = normalizza(categoria)
        if categoria and chiave_categoria not in self._categorie:
            elenco = ", ".join(sorted(self._categorie.values(), key=normalizza))
            return f"Errore: categoria sconosciuta '{categoria}'. Categorie: {elenco}."
        termini = _termini(testo)
        trovati = [
            a
            for a in self.articoli
            if (not categoria or normalizza(a.categoria) == chiave_categoria)
            and all(any(t in campo for campo in self._campi[a.codice]) for t in termini)
        ]
        if not trovati:
            return self._nessuno(testo, categoria)
        intestazione = (
            "Trovato 1 articolo:" if len(trovati) == 1 else f"Trovati {len(trovati)} articoli:"
        )
        righe = [
            f"- {a.codice} — {a.nome} — {_pezzi(a.quantita)} — {a.collocazione}"
            for a in trovati[:RISULTATI_MASSIMI]
        ]
        if len(trovati) > RISULTATI_MASSIMI:
            altri = len(trovati) - RISULTATI_MASSIMI
            righe.append(f"(altri {altri} risultati: restringere la ricerca)")
        return "\n".join([intestazione, *righe])

    @staticmethod
    def _nessuno(testo: str, categoria: str) -> str:
        if testo and categoria:
            return f"Nessun articolo trovato per «{testo}» nella categoria «{categoria}»."
        if categoria:
            return f"Nessun articolo trovato nella categoria «{categoria}»."
        return f"Nessun articolo trovato per «{testo}»."

    def dettaglio(self, codice: str | None) -> str:
        """Le sei righe dell'articolo, o un testo di errore che inizia con «Errore:»."""
        codice = (codice or "").strip()
        if not codice:
            return "Errore: indicare il codice dell'articolo, per esempio MIS-001."
        if len(codice) > LUNGHEZZA_MASSIMA:
            return f"Errore: testo troppo lungo (massimo {LUNGHEZZA_MASSIMA} caratteri)."
        a = self._per_codice.get(normalizza(codice))
        if a is None:
            return f"Errore: nessun articolo con codice '{codice}'."
        return "\n".join(
            [
                f"Codice: {a.codice}",
                f"Nome: {a.nome}",
                f"Categoria: {a.categoria}",
                f"Quantità: {a.quantita}",
                f"Collocazione: {a.collocazione}",
                f"Descrizione: {a.descrizione or '(nessuna)'}",
            ]
        )
