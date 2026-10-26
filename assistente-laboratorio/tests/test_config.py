import pytest

from assistente.config import Config, ErroreConfigurazione, carica_config

BASE = {"LMSTUDIO_BASE_URL": "http://localhost:1234/v1", "LMSTUDIO_MODEL": "modello"}


def test_valori_predefiniti():
    cfg = carica_config(BASE)
    assert isinstance(cfg, Config)
    assert cfg.max_passaggi == 5
    assert cfg.log_level == "INFO"


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
