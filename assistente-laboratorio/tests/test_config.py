import pytest

from assistente.config import Config, ErroreConfigurazione, carica_config

BASE = {"LMSTUDIO_BASE_URL": "http://localhost:1234/v1", "LMSTUDIO_MODEL": "modello"}


def test_valori_predefiniti():
    cfg = carica_config(BASE)
    assert isinstance(cfg, Config)
    assert cfg.max_passaggi == 5
    assert cfg.log_level == "INFO"
    assert cfg.reasoning_effort == "none"
    assert cfg.fuso_predefinito == "Europe/Rome"


def test_valori_espliciti():
    cfg = carica_config({**BASE, "MAX_PASSAGGI": "3", "LOG_LEVEL": "DEBUG"})
    assert cfg.max_passaggi == 3
    assert cfg.log_level == "DEBUG"


def test_base_url_senza_barra_finale():
    cfg = carica_config({**BASE, "LMSTUDIO_BASE_URL": "http://h:1234/v1/"})
    assert cfg.base_url == "http://h:1234/v1"


@pytest.mark.parametrize("nome", ["LMSTUDIO_MODEL", "LMSTUDIO_BASE_URL"])
@pytest.mark.parametrize("valore", [None, "", "   "])
def test_variabile_mancante(nome, valore):
    env = dict(BASE)
    if valore is None:
        del env[nome]
    else:
        env[nome] = valore
    with pytest.raises(ErroreConfigurazione, match=nome):
        carica_config(env)


@pytest.mark.parametrize("valore", ["0", "-1", "abc", ""])
def test_max_passaggi_non_valido(valore):
    with pytest.raises(ErroreConfigurazione, match="MAX_PASSAGGI"):
        carica_config({**BASE, "MAX_PASSAGGI": valore})


@pytest.mark.parametrize(
    "valore, atteso", [("low", "low"), (" Low ", "low"), ("HIGH", "high"), ("", "none")]
)
def test_reasoning_effort_valido(valore, atteso):
    cfg = carica_config({**BASE, "LMSTUDIO_REASONING_EFFORT": valore})
    assert cfg.reasoning_effort == atteso


@pytest.mark.parametrize("valore", ["massimo", "0"])
def test_reasoning_effort_non_valido(valore):
    with pytest.raises(ErroreConfigurazione, match="LMSTUDIO_REASONING_EFFORT"):
        carica_config({**BASE, "LMSTUDIO_REASONING_EFFORT": valore})


@pytest.mark.parametrize(
    "valore, atteso", [(" Asia/Tokyo ", "Asia/Tokyo"), ("", "Europe/Rome")]
)
def test_fuso_predefinito_valido(valore, atteso):
    cfg = carica_config({**BASE, "FUSO_PREDEFINITO": valore})
    assert cfg.fuso_predefinito == atteso


@pytest.mark.parametrize("valore", ["Europe/Roma", "Mars/Base", "../etc/passwd"])
def test_fuso_predefinito_non_valido(valore):
    with pytest.raises(ErroreConfigurazione, match="FUSO_PREDEFINITO"):
        carica_config({**BASE, "FUSO_PREDEFINITO": valore})
