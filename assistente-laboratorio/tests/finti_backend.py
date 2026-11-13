"""Finti del back-end: deposito in memoria con la stessa semantica di quello PostgreSQL."""

import threading
from datetime import datetime, timedelta, timezone

from backend.deposito import (
    TITOLO_INIZIALE,
    Conversazione,
    ConversazioneInesistente,
    ErroreDatabase,
    Messaggio,
    titolo_da,
)

_INIZIO = datetime(2026, 11, 13, 9, 0, 0, tzinfo=timezone.utc)


class DepositoMemoria:
    """Thread-safe; `errore` simula il database rotto (ogni operazione lo solleva)."""

    def __init__(self, errore: ErroreDatabase | None = None):
        self._errore = errore
        self._lock = threading.Lock()
        self._tick = 0
        self._prossimo_id = 1
        self._conversazioni: dict[int, dict] = {}

    def _ora(self) -> datetime:
        # Strettamente crescente: gli ordinamenti dei test sono deterministici.
        self._tick += 1
        return _INIZIO + timedelta(seconds=self._tick)

    def _controlla(self) -> None:
        if self._errore is not None:
            raise self._errore

    def _esistente(self, id: int) -> dict:
        voce = self._conversazioni.get(id)
        if voce is None:
            raise ConversazioneInesistente(id)
        return voce

    @staticmethod
    def _vista(voce: dict) -> Conversazione:
        return Conversazione(voce["id"], voce["titolo"], voce["creata"], voce["aggiornata"])

    def prepara(self) -> None:
        self._controlla()

    def crea(self) -> Conversazione:
        with self._lock:
            self._controlla()
            ora = self._ora()
            voce = {
                "id": self._prossimo_id,
                "titolo": TITOLO_INIZIALE,
                "creata": ora,
                "aggiornata": ora,
                "cronologia": [],
                "messaggi": [],
            }
            self._conversazioni[voce["id"]] = voce
            self._prossimo_id += 1
            return self._vista(voce)

    def elenca(self) -> list[Conversazione]:
        with self._lock:
            self._controlla()
            voci = sorted(
                self._conversazioni.values(), key=lambda v: (v["aggiornata"], v["id"]), reverse=True
            )
            return [self._vista(v) for v in voci]

    def leggi(self, id: int) -> tuple[Conversazione, list[Messaggio]]:
        with self._lock:
            self._controlla()
            voce = self._esistente(id)
            return self._vista(voce), list(voce["messaggi"])

    def cronologia(self, id: int) -> list[dict]:
        with self._lock:
            self._controlla()
            return list(self._esistente(id)["cronologia"])

    def registra_turno(
        self, id: int, testo_utente: str, testo_risposta: str, cronologia: list[dict]
    ) -> list[Messaggio]:
        with self._lock:
            self._controlla()
            voce = self._esistente(id)
            primo = not voce["messaggi"]
            ora = self._ora()
            salvati = [Messaggio("utente", testo_utente, ora), Messaggio("assistente", testo_risposta, ora)]
            voce["messaggi"].extend(salvati)
            voce["cronologia"] = list(cronologia)
            voce["aggiornata"] = ora
            if primo:
                voce["titolo"] = titolo_da(testo_utente)
            return salvati

    def elimina(self, id: int) -> None:
        with self._lock:
            self._controlla()
            self._esistente(id)
            del self._conversazioni[id]
