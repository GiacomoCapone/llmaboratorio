import uuid

import psycopg
import pytest

from backend.config import ErroreConfigurazione, carica_config
from backend.deposito import (
    ConversazioneInesistente,
    DepositoPostgres,
    ErroreDatabase,
    titolo_da,
)

pytestmark = pytest.mark.postgres

CRONOLOGIA = [
    {"type": "system", "content": "Riassunto: l'utente ha chiesto l'ora."},
    {"type": "human", "content": "Che ore sono a Tōkyō? «subito» 🔧"},
    {
        "type": "ai",
        "content": "",
        "tool_calls": [
            {"name": "ora_corrente", "args": {"fuso": "Asia/Tokyo"}, "id": "c1", "type": "tool_call"}
        ],
    },
    {"type": "tool", "content": "12:00", "tool_call_id": "c1", "name": "ora_corrente"},
    {"type": "ai", "content": "Sono le 12:00."},
]
TESTO_DIFFICILE = 'Perché è così? «ok» 🔧 "x"'


@pytest.fixture
def deposito(url, schema):
    dep = DepositoPostgres(url, schema=schema)
    dep.prepara()
    dep.prepara()  # idempotente
    return dep


def _conta_messaggi(url, schema, id):
    with psycopg.connect(url, options=f"-c search_path={schema}") as conn:
        return conn.execute(
            "SELECT count(*) FROM messaggi WHERE conversazione_id = %s", (id,)
        ).fetchone()[0]


def test_crea_elenca_leggi(deposito):
    prima = deposito.crea()
    seconda = deposito.crea()
    assert [c.id for c in deposito.elenca()] == [seconda.id, prima.id]
    conv, messaggi = deposito.leggi(prima.id)
    assert conv.titolo == "Nuova conversazione"
    assert messaggi == []


def test_registra_turno(deposito):
    conv = deposito.crea()
    salvati = deposito.registra_turno(conv.id, "  Ciao  ", "Salve", CRONOLOGIA)
    assert [m.ruolo for m in salvati] == ["utente", "assistente"]
    letto, messaggi = deposito.leggi(conv.id)
    assert [(m.ruolo, m.testo) for m in messaggi] == [("utente", "  Ciao  "), ("assistente", "Salve")]
    assert letto.titolo == titolo_da("  Ciao  ") == "Ciao"
    assert deposito.cronologia(conv.id) == CRONOLOGIA
    assert letto.aggiornata > conv.aggiornata

    deposito.registra_turno(conv.id, "Altro", "Risposta", CRONOLOGIA)
    letto, messaggi = deposito.leggi(conv.id)
    assert letto.titolo == "Ciao"
    assert [m.testo for m in messaggi] == ["  Ciao  ", "Salve", "Altro", "Risposta"]


def test_testi_e_cronologia_intatti(deposito):
    conv = deposito.crea()
    deposito.registra_turno(conv.id, TESTO_DIFFICILE, TESTO_DIFFICILE, CRONOLOGIA)
    _, messaggi = deposito.leggi(conv.id)
    assert [m.testo for m in messaggi] == [TESTO_DIFFICILE, TESTO_DIFFICILE]
    assert deposito.cronologia(conv.id) == CRONOLOGIA


def test_registra_turno_su_conversazione_eliminata(deposito, url, schema):
    conv = deposito.crea()
    deposito.elimina(conv.id)
    with pytest.raises(ConversazioneInesistente):
        deposito.registra_turno(conv.id, "a", "b", [])
    assert _conta_messaggi(url, schema, conv.id) == 0


def test_elimina_a_cascata(deposito, url, schema):
    conv = deposito.crea()
    deposito.registra_turno(conv.id, "a", "b", [])
    assert _conta_messaggi(url, schema, conv.id) == 2
    deposito.elimina(conv.id)
    assert _conta_messaggi(url, schema, conv.id) == 0
    assert deposito.elenca() == []


def test_inesistente(deposito):
    for operazione in (deposito.leggi, deposito.cronologia, deposito.elimina):
        with pytest.raises(ConversazioneInesistente) as errore:
            operazione(999999)
        assert errore.value.id == 999999


def test_cronologia_rifiutata(deposito, url, schema):
    conv = deposito.crea()
    with pytest.raises(ErroreDatabase):
        deposito.registra_turno(conv.id, "a", "b", [{"type": "human", "content": "x\u0000y"}])
    assert _conta_messaggi(url, schema, conv.id) == 0
    assert deposito.cronologia(conv.id) == []


def test_errore_di_connessione():
    with pytest.raises(ErroreDatabase):
        DepositoPostgres("postgresql://x:y@127.0.0.1:1/z").prepara()
