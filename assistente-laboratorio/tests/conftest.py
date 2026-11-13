import uuid

import psycopg
import pytest

from backend.config import ErroreConfigurazione, carica_config


@pytest.fixture(autouse=True)
def file_env_isolato(request, tmp_path, monkeypatch):
    """I test automatici non leggono il .env reale del progetto; le prove reali sì."""
    if request.node.get_closest_marker("reale"):
        return
    monkeypatch.setattr("assistente.config.PERCORSO_ENV", tmp_path / "assente.env")


@pytest.fixture
def url():
    try:
        valore = carica_config().database_url
    except ErroreConfigurazione:
        pytest.skip("DATABASE_URL non impostata: prova PostgreSQL saltata.")
    try:
        psycopg.connect(valore, connect_timeout=3).close()
    except psycopg.Error as errore:
        pytest.skip(f"PostgreSQL non raggiungibile: {errore}")
    return valore


@pytest.fixture
def schema(url):
    nome = f"prova_{uuid.uuid4().hex}"
    yield nome
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {nome} CASCADE")
