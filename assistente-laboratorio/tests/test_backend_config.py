import pytest

from backend.config import ConfigBackend, ErroreConfigurazione, carica_config
from backend.deposito import titolo_da


def test_predefiniti():
    assert carica_config({"DATABASE_URL": "postgresql://x"}) == ConfigBackend("postgresql://x")
    cfg = ConfigBackend("postgresql://x")
    assert cfg.agente_url == "http://127.0.0.1:8000"
    assert cfg.agente_timeout == 900.0
    assert cfg.host == "127.0.0.1"
    assert cfg.porta == 8001
    assert cfg.log_level == "INFO"


def test_impostati():
    cfg = carica_config(
        {
            "DATABASE_URL": "postgresql://x",
            "AGENTE_URL": "http://agente:8000/",
            "AGENTE_TIMEOUT": "30",
            "BACKEND_HOST": " 0.0.0.0 ",
            "BACKEND_PORTA": "9001",
            "LOG_LEVEL": "debug",
        }
    )
    assert cfg.agente_url == "http://agente:8000"
    assert cfg.agente_timeout == 30.0
    assert cfg.host == "0.0.0.0"
    assert cfg.porta == 9001
    assert cfg.log_level == "DEBUG"


@pytest.mark.parametrize("valore", [None, "", "  "])
def test_database_url_mancante(valore):
    env = {} if valore is None else {"DATABASE_URL": valore}
    with pytest.raises(ErroreConfigurazione, match="DATABASE_URL"):
        carica_config(env)


@pytest.mark.parametrize("grezzo", ["0", "65536", "abc"])
def test_porta_non_valida(grezzo):
    with pytest.raises(ErroreConfigurazione) as errore:
        carica_config({"DATABASE_URL": "postgresql://x", "BACKEND_PORTA": grezzo})
    assert str(errore.value) == (
        f"BACKEND_PORTA deve essere un intero fra 1 e 65535, trovato {grezzo!r}."
    )


@pytest.mark.parametrize("grezzo", ["0", "-5", "x"])
def test_timeout_non_valido(grezzo):
    with pytest.raises(ErroreConfigurazione) as errore:
        carica_config({"DATABASE_URL": "postgresql://x", "AGENTE_TIMEOUT": grezzo})
    assert str(errore.value) == (
        f"AGENTE_TIMEOUT deve essere un numero positivo di secondi, trovato {grezzo!r}."
    )


def test_titolo_da():
    assert titolo_da("  Ciao  ") == "Ciao"
    assert titolo_da("a" * 60) == "a" * 60
    lungo = titolo_da("a" * 61)
    assert lungo == "a" * 59 + "…"
    assert len(lungo) == 60
