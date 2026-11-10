import pytest

from assistente.config import (
    CARTELLA_PROGETTO,
    NOTE_DB_PREDEFINITO,
    Config,
    ErroreConfigurazione,
    carica_config,
)

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


@pytest.mark.parametrize(
    "valore, atteso",
    [("Pordenone", "Pordenone"), (" Udine ", "Udine"), ("", None), (None, None)],
)
def test_citta_patrono(valore, atteso):
    env = dict(BASE)
    if valore is not None:
        env["CITTA_PATRONO"] = valore
    assert carica_config(env).citta_patrono == atteso


def scrivi_env(tmp_path, testo):
    percorso = tmp_path / ".env"
    percorso.write_text(testo, encoding="utf-8")
    return percorso


def test_legge_il_file_env(tmp_path, monkeypatch):
    for nome in ("LMSTUDIO_BASE_URL", "LMSTUDIO_MODEL", "MAX_PASSAGGI", "FUSO_PREDEFINITO"):
        monkeypatch.delenv(nome, raising=False)
    percorso = scrivi_env(
        tmp_path,
        "# commento\n\nLMSTUDIO_BASE_URL=http://h:1234/v1\n"
        'LMSTUDIO_MODEL="modello-dal-file"\nMAX_PASSAGGI=3\nFUSO_PREDEFINITO=Asia/Tokyo\n',
    )
    monkeypatch.setattr("assistente.config.PERCORSO_ENV", percorso)
    cfg = carica_config()
    assert cfg.base_url == "http://h:1234/v1"
    assert cfg.model == "modello-dal-file"
    assert cfg.max_passaggi == 3
    assert cfg.fuso_predefinito == "Asia/Tokyo"


def test_l_ambiente_prevale_sul_file(tmp_path, monkeypatch):
    percorso = scrivi_env(
        tmp_path, "LMSTUDIO_BASE_URL=http://dal-file:1234/v1\nLMSTUDIO_MODEL=dal-file\n"
    )
    monkeypatch.setattr("assistente.config.PERCORSO_ENV", percorso)
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://host.docker.internal:1234/v1")
    monkeypatch.delenv("LMSTUDIO_MODEL", raising=False)
    cfg = carica_config()
    assert cfg.base_url == "http://host.docker.internal:1234/v1"
    assert cfg.model == "dal-file"


def test_variabile_senza_valore_nel_file_e_mancante(tmp_path, monkeypatch):
    monkeypatch.delenv("LMSTUDIO_MODEL", raising=False)
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://h:1234/v1")
    monkeypatch.setattr(
        "assistente.config.PERCORSO_ENV", scrivi_env(tmp_path, "LMSTUDIO_MODEL\n")
    )
    with pytest.raises(ErroreConfigurazione, match="LMSTUDIO_MODEL"):
        carica_config()


def test_file_env_assente_l_errore_suggerisce_il_file(monkeypatch):
    monkeypatch.delenv("LMSTUDIO_MODEL", raising=False)
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://h:1234/v1")
    with pytest.raises(ErroreConfigurazione, match=r"\.env") as errore:
        carica_config()
    assert "LMSTUDIO_MODEL" in str(errore.value)


def test_env_esplicito_ignora_il_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "assistente.config.PERCORSO_ENV", scrivi_env(tmp_path, "MAX_PASSAGGI=9\n")
    )
    assert carica_config(BASE).max_passaggi == 5


def test_il_file_env_e_quello_del_progetto():
    # Non dipende dalla cartella corrente: avvia.py funziona da qualunque cartella.
    import assistente.config as modulo
    from pathlib import Path

    radice = Path(__file__).resolve().parents[1]
    assert modulo.PERCORSO_ENV_PROGETTO == radice / ".env"


@pytest.mark.parametrize(
    "valore, atteso",
    [
        (None, NOTE_DB_PREDEFINITO),
        ("  ", NOTE_DB_PREDEFINITO),
        ("altro/n.db", CARTELLA_PROGETTO / "altro" / "n.db"),
        ("__ASSOLUTO__", "__ASSOLUTO__"),
    ],
)
def test_note_db(tmp_path, valore, atteso):
    env = dict(BASE)
    if valore == "__ASSOLUTO__":
        valore = atteso = str(tmp_path / "n.db")
    if valore is not None:
        env["NOTE_DB"] = valore
    cfg = carica_config(env)
    assert cfg.note_db.is_absolute()
    assert cfg.note_db == type(cfg.note_db)(atteso)


def test_ambito_predefinito():
    from assistente.config import AMBITO_PREDEFINITO

    atteso = AMBITO_PREDEFINITO.read_text(encoding="utf-8-sig").strip()
    assert atteso
    assert carica_config(BASE).ambito == atteso


def test_ambito_file_relativo(tmp_path, monkeypatch):
    monkeypatch.setattr("assistente.config.CARTELLA_PROGETTO", tmp_path)
    (tmp_path / "a.txt").write_text("Solo chimica.\n", encoding="utf-8")
    assert carica_config({**BASE, "AMBITO_FILE": "a.txt"}).ambito == "Solo chimica."


def test_ambito_file_assoluto(tmp_path):
    percorso = tmp_path / "ambito.txt"
    percorso.write_text("Solo fisica.", encoding="utf-8")
    assert carica_config({**BASE, "AMBITO_FILE": str(percorso)}).ambito == "Solo fisica."


def test_ambito_file_mancante(tmp_path):
    percorso = tmp_path / "manca.txt"
    with pytest.raises(ErroreConfigurazione) as errore:
        carica_config({**BASE, "AMBITO_FILE": str(percorso)})
    assert str(percorso) in str(errore.value)


def test_ambito_file_vuoto(tmp_path):
    percorso = tmp_path / "vuoto.txt"
    percorso.write_text("  \n", encoding="utf-8")
    with pytest.raises(ErroreConfigurazione):
        carica_config({**BASE, "AMBITO_FILE": str(percorso)})


def test_ambito_con_bom(tmp_path):
    percorso = tmp_path / "bom.txt"
    percorso.write_text("Ambito\n\n", encoding="utf-8-sig")
    assert carica_config({**BASE, "AMBITO_FILE": str(percorso)}).ambito == "Ambito"


def test_max_revisioni_predefinito():
    assert carica_config(BASE).max_revisioni == 2


@pytest.mark.parametrize("valore, atteso", [("3", 3), (" 3 ", 3), ("1", 1)])
def test_max_revisioni_esplicito(valore, atteso):
    assert carica_config({**BASE, "MAX_REVISIONI": valore}).max_revisioni == atteso


@pytest.mark.parametrize("valore", ["0", "-1", "abc", "1.5"])
def test_max_revisioni_non_valido(valore):
    with pytest.raises(ErroreConfigurazione) as errore:
        carica_config({**BASE, "MAX_REVISIONI": valore})
    assert "MAX_REVISIONI" in str(errore.value)


def test_soglia_riassunto_predefinita():
    assert carica_config(BASE).soglia_riassunto == 3000


@pytest.mark.parametrize("valore, atteso", [("500", 500), (" 500 ", 500), ("1", 1)])
def test_soglia_riassunto_esplicita(valore, atteso):
    assert carica_config({**BASE, "RIASSUNTO_SOGLIA_TOKEN": valore}).soglia_riassunto == atteso


@pytest.mark.parametrize("valore", ["0", "-1", "abc", "1.5"])
def test_soglia_riassunto_non_valida(valore):
    with pytest.raises(ErroreConfigurazione) as errore:
        carica_config({**BASE, "RIASSUNTO_SOGLIA_TOKEN": valore})
    assert "RIASSUNTO_SOGLIA_TOKEN" in str(errore.value)
