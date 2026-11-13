import pytest

from frontend import config
from frontend.config import ConfigFrontend, ErroreConfigurazione, carica_config


def test_predefiniti():
    assert carica_config({}) == ConfigFrontend()
    cfg = ConfigFrontend()
    assert cfg.backend_url == "http://127.0.0.1:8001"
    assert cfg.backend_timeout == 960.0
    assert cfg.host == "127.0.0.1"
    assert cfg.porta == 8002
    assert cfg.log_level == "INFO"


def test_valori_letti():
    cfg = carica_config(
        {
            "BACKEND_URL": "http://b:9/",
            "BACKEND_TIMEOUT": "30",
            "FRONTEND_HOST": "0.0.0.0",
            "FRONTEND_PORTA": "9000",
            "LOG_LEVEL": "debug",
        }
    )
    assert cfg == ConfigFrontend("http://b:9", 30.0, "0.0.0.0", 9000, "DEBUG")


def test_vuoti_danno_i_predefiniti():
    nomi = ["BACKEND_URL", "BACKEND_TIMEOUT", "FRONTEND_HOST", "FRONTEND_PORTA", "LOG_LEVEL"]
    assert carica_config({nome: "" for nome in nomi}) == ConfigFrontend()


@pytest.mark.parametrize("grezzo", ["0", "-1", "abc", "inf", "nan"])
def test_timeout_non_valido(grezzo):
    with pytest.raises(ErroreConfigurazione) as errore:
        carica_config({"BACKEND_TIMEOUT": grezzo})
    assert str(errore.value) == (
        f"BACKEND_TIMEOUT deve essere un numero positivo di secondi, trovato {grezzo!r}."
    )


@pytest.mark.parametrize("grezzo", ["0", "65536", "x", "80.5"])
def test_porta_non_valida(grezzo):
    with pytest.raises(ErroreConfigurazione) as errore:
        carica_config({"FRONTEND_PORTA": grezzo})
    assert str(errore.value) == (
        f"FRONTEND_PORTA deve essere un intero fra 1 e 65535, trovato {grezzo!r}."
    )


def test_ambiente_prevale_sul_file(monkeypatch, tmp_path):
    file_env = tmp_path / ".env"
    file_env.write_text("FRONTEND_PORTA=9001\n", encoding="utf-8")
    monkeypatch.setattr(config, "PERCORSO_ENV", file_env)
    monkeypatch.setenv("FRONTEND_PORTA", "9002")
    assert carica_config().porta == 9002
    monkeypatch.delenv("FRONTEND_PORTA")
    assert carica_config().porta == 9001
