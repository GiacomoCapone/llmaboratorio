"""Deposito delle conversazioni: interfaccia e implementazione PostgreSQL con SQL esplicito."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import psycopg
from psycopg.types.json import Jsonb

TITOLO_INIZIALE = "Nuova conversazione"
LUNGHEZZA_TITOLO = 60

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversazioni (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titolo      text        NOT NULL,
    creata      timestamptz NOT NULL DEFAULT now(),
    aggiornata  timestamptz NOT NULL DEFAULT now(),
    cronologia  jsonb       NOT NULL DEFAULT '[]'::jsonb
);
CREATE TABLE IF NOT EXISTS messaggi (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversazione_id bigint      NOT NULL REFERENCES conversazioni(id) ON DELETE CASCADE,
    ruolo            text        NOT NULL CHECK (ruolo IN ('utente', 'assistente')),
    testo            text        NOT NULL,
    ora              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messaggi_per_conversazione ON messaggi (conversazione_id, id);
"""


def titolo_da(testo: str) -> str:
    """Titolo dal testo visibile del primo messaggio: senza spazi ai lati, al massimo 60 caratteri."""
    testo = testo.strip()
    if len(testo) > LUNGHEZZA_TITOLO:
        return testo[: LUNGHEZZA_TITOLO - 1] + "…"
    return testo


@dataclass(frozen=True)
class Conversazione:
    id: int
    titolo: str
    creata: datetime
    aggiornata: datetime


@dataclass(frozen=True)
class Messaggio:
    ruolo: str
    testo: str
    ora: datetime


class ConversazioneInesistente(Exception):
    """La conversazione non esiste (mai creata o eliminata)."""

    def __init__(self, id: int):
        super().__init__(f"conversazione {id} inesistente.")
        self.id = id


class ErroreDatabase(Exception):
    """Errore del database, con il messaggio originale."""


class Deposito(Protocol):
    def prepara(self) -> None: ...

    def crea(self) -> Conversazione: ...

    def elenca(self) -> list[Conversazione]: ...

    def leggi(self, id: int) -> tuple[Conversazione, list[Messaggio]]: ...

    def cronologia(self, id: int) -> list[dict]: ...

    def registra_turno(
        self, id: int, testo_utente: str, testo_risposta: str, cronologia: list[dict]
    ) -> list[Messaggio]: ...

    def elimina(self, id: int) -> None: ...


_COLONNE = "id, titolo, creata, aggiornata"


class DepositoPostgres:
    """Una connessione per operazione; `schema` isola le prove (search_path di ogni connessione)."""

    def __init__(self, conninfo: str, schema: str | None = None):
        self._conninfo = conninfo
        self._schema = schema

    def _connetti(self) -> psycopg.Connection:
        opzioni = {"options": f"-c search_path={self._schema}"} if self._schema else {}
        return psycopg.connect(self._conninfo, connect_timeout=10, **opzioni)

    def prepara(self) -> None:
        try:
            with self._connetti() as conn:
                if self._schema:
                    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self._schema}")
                conn.execute(SCHEMA_SQL)
        except psycopg.Error as errore:
            raise ErroreDatabase(str(errore)) from errore

    def crea(self) -> Conversazione:
        try:
            with self._connetti() as conn:
                riga = conn.execute(
                    f"INSERT INTO conversazioni (titolo) VALUES (%s) RETURNING {_COLONNE}",
                    (TITOLO_INIZIALE,),
                ).fetchone()
        except psycopg.Error as errore:
            raise ErroreDatabase(str(errore)) from errore
        return Conversazione(*riga)

    def elenca(self) -> list[Conversazione]:
        try:
            with self._connetti() as conn:
                righe = conn.execute(
                    f"SELECT {_COLONNE} FROM conversazioni ORDER BY aggiornata DESC, id DESC"
                ).fetchall()
        except psycopg.Error as errore:
            raise ErroreDatabase(str(errore)) from errore
        return [Conversazione(*riga) for riga in righe]

    def leggi(self, id: int) -> tuple[Conversazione, list[Messaggio]]:
        try:
            with self._connetti() as conn:
                riga = conn.execute(
                    f"SELECT {_COLONNE} FROM conversazioni WHERE id = %s", (id,)
                ).fetchone()
                if riga is None:
                    raise ConversazioneInesistente(id)
                messaggi = conn.execute(
                    "SELECT ruolo, testo, ora FROM messaggi WHERE conversazione_id = %s ORDER BY id",
                    (id,),
                ).fetchall()
        except psycopg.Error as errore:
            raise ErroreDatabase(str(errore)) from errore
        return Conversazione(*riga), [Messaggio(*m) for m in messaggi]

    def cronologia(self, id: int) -> list[dict]:
        try:
            with self._connetti() as conn:
                riga = conn.execute(
                    "SELECT cronologia FROM conversazioni WHERE id = %s", (id,)
                ).fetchone()
        except psycopg.Error as errore:
            raise ErroreDatabase(str(errore)) from errore
        if riga is None:
            raise ConversazioneInesistente(id)
        return riga[0]

    def registra_turno(
        self, id: int, testo_utente: str, testo_risposta: str, cronologia: list[dict]
    ) -> list[Messaggio]:
        try:
            with self._connetti() as conn, conn.transaction():
                riga = conn.execute(
                    "SELECT id FROM conversazioni WHERE id = %s FOR UPDATE", (id,)
                ).fetchone()
                if riga is None:
                    raise ConversazioneInesistente(id)
                primo = (
                    conn.execute(
                        "SELECT count(*) FROM messaggi WHERE conversazione_id = %s", (id,)
                    ).fetchone()[0]
                    == 0
                )
                salvati = []
                for ruolo, testo in (("utente", testo_utente), ("assistente", testo_risposta)):
                    salvati.append(
                        Messaggio(
                            *conn.execute(
                                "INSERT INTO messaggi (conversazione_id, ruolo, testo) "
                                "VALUES (%s, %s, %s) RETURNING ruolo, testo, ora",
                                (id, ruolo, testo),
                            ).fetchone()
                        )
                    )
                if primo:
                    conn.execute(
                        "UPDATE conversazioni SET cronologia = %s, aggiornata = now(), titolo = %s "
                        "WHERE id = %s",
                        (Jsonb(cronologia), titolo_da(testo_utente), id),
                    )
                else:
                    conn.execute(
                        "UPDATE conversazioni SET cronologia = %s, aggiornata = now() WHERE id = %s",
                        (Jsonb(cronologia), id),
                    )
        except psycopg.Error as errore:
            raise ErroreDatabase(str(errore)) from errore
        return salvati

    def elimina(self, id: int) -> None:
        try:
            with self._connetti() as conn:
                eliminate = conn.execute(
                    "DELETE FROM conversazioni WHERE id = %s", (id,)
                ).rowcount
        except psycopg.Error as errore:
            raise ErroreDatabase(str(errore)) from errore
        if eliminate == 0:
            raise ConversazioneInesistente(id)
