"""Interfaccia da terminale: ciclo di conversazione con cronologia di sessione."""

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.messages import BaseMessage, HumanMessage

from assistente import servizio
from assistente.avvio import apri_assistente
from assistente.config import ErroreConfigurazione, carica_config
from assistente.mcp_client import ErroreArchivio
from assistente.modello import ErroreModello

logger = logging.getLogger("assistente.cli")

COMANDI_USCITA = {"esci", "exit", "quit"}
MESSAGGIO_RISPOSTA_VUOTA = "(il modello non ha prodotto una risposta)"
MESSAGGIO_TURNO_ANNULLATO = "(turno annullato)"


@dataclass
class EsitoTurno:
    testo: str
    cronologia: list[BaseMessage]
    interrotto: bool


def esegui_turno(grafo, cronologia: list[BaseMessage], domanda: str) -> EsitoTurno:
    """Esegue un turno; un turno interrotto non modifica la cronologia."""
    stato = grafo.invoke(
        {
            "messaggi": cronologia + [HumanMessage(domanda)],
            "passaggi": 0,
            "interrotto": False,
            "revisioni": 0,
            "scartati": [],
            "esito_revisione": "",
        }
    )
    messaggi = stato["messaggi"]
    testo = messaggi[-1].content
    if stato["interrotto"]:
        return EsitoTurno(testo, cronologia, True)
    return EsitoTurno(testo, list(messaggi), False)


def espandi_prompt(riga: str, prompt) -> tuple[str | None, str]:
    """Riga `/...` → (domanda del turno o None, testo da mostrare). `/prompt` elenca i prompt."""
    nome, _, resto = riga[1:].partition(" ")
    resto = resto.strip()
    offerti = {p.nome: p for p in prompt.prompt_disponibili()}
    if nome == "prompt" and not resto:
        if not offerti:
            return None, "Nessun prompt disponibile."
        return None, "\n".join(
            " ".join([f"/{p.nome}", *(f"<{a}>" for a in p.argomenti)]) + f" — {p.descrizione}"
            for p in offerti.values()
        )
    voce = offerti.get(nome)
    if voce is None:
        return None, f"Errore: prompt sconosciuto '/{nome}'. Scrivere /prompt per l'elenco."
    if not voce.argomenti:
        if resto:
            return None, f"Errore: /{nome} non ha argomenti."
        valori = []
    else:
        valori = resto.split(maxsplit=len(voce.argomenti) - 1)
        if len(valori) < len(voce.argomenti):
            richiesti = " ".join(f"<{a}>" for a in voce.argomenti)
            return None, f"Errore: /{nome} richiede: {richiesti}."
    argomenti = dict(zip(voce.argomenti, valori))
    try:
        testo = prompt.testo_prompt(nome, argomenti)
    except ErroreArchivio as errore:
        return None, f"Errore: {errore}"
    logger.info("prompt: /%s %s", nome, argomenti)
    return testo, f"(prompt) {testo}"


def ciclo(grafo, leggi: Callable[[], str], scrivi: Callable[[str], None], prompt=None) -> None:
    """Legge le domande ed esegue i turni; con `prompt` (l'archivio) le righe `/...` sono prompt."""
    cronologia: list[BaseMessage] = []
    while True:
        try:
            # PowerShell antepone un BOM (\ufeff) alla prima riga inviata con una pipe.
            riga = leggi().replace("\ufeff", "").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not riga:
            continue
        if riga.lower() in COMANDI_USCITA:
            break
        if prompt is not None and riga.startswith("/"):
            try:
                domanda, messaggio = espandi_prompt(riga, prompt)
            except KeyboardInterrupt:  # Ctrl-C durante l'attesa del server: come per un turno
                scrivi(MESSAGGIO_TURNO_ANNULLATO)
                continue
            scrivi(messaggio)
            if domanda is None:
                continue
            riga = domanda
        try:
            esito = esegui_turno(grafo, cronologia, riga)
        except KeyboardInterrupt:  # Ctrl-C annulla il turno, non la sessione
            scrivi(MESSAGGIO_TURNO_ANNULLATO)
            continue
        except Exception as errore:  # il turno fallito viene scartato
            logger.warning("turno fallito: %s", errore)
            scrivi(f"Errore: {errore}")
            continue
        cronologia = esito.cronologia
        scrivi(esito.testo if str(esito.testo).strip() else MESSAGGIO_RISPOSTA_VUOTA)
        if esito.interrotto:
            scrivi("(Turno interrotto: non è stato aggiunto alla cronologia.)")


def main(argv: list[str] | None = None) -> int:
    argv = [] if argv is None else argv
    if argv not in ([], ["--http"]):
        print("Uso: python avvia.py [--http]", file=sys.stderr)
        return 2
    try:
        config = carica_config()
        logging.basicConfig(
            level=getattr(logging, config.log_level, logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            stream=sys.stderr,
        )
        if argv:
            servizio.servi(config)
        else:
            with apri_assistente(config) as (grafo, archivio):
                print(
                    "Assistente del laboratorio. Scrivere 'esci' per terminare, "
                    "'/prompt' per i prompt dell'archivio."
                )
                ciclo(grafo, lambda: input("> "), print, prompt=archivio)
    except (ErroreConfigurazione, ErroreModello, ErroreArchivio) as errore:
        print(f"Errore: {errore}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrotto.", file=sys.stderr)
        return 130
    return 0
