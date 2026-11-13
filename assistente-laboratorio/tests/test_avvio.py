"""Lo script avvia.py trova il pacchetto senza PYTHONPATH, da qualunque cartella."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

AVVIA = Path(__file__).resolve().parents[1] / "avvia.py"


def ambiente_senza_configurazione():
    """Ambiente senza PYTHONPATH; LMSTUDIO_BASE_URL vuota prevale sul .env reale."""
    ambiente = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    ambiente["LMSTUDIO_BASE_URL"] = ""
    return ambiente


def avvia(interprete, cartella):
    return subprocess.run(
        [interprete, str(AVVIA)],
        cwd=cartella,
        env=ambiente_senza_configurazione(),
        input="",
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_avvia_senza_pythonpath_da_un_altra_cartella(tmp_path):
    esito = avvia(sys.executable, tmp_path)
    assert esito.returncode == 1
    assert "LMSTUDIO_BASE_URL" in esito.stderr
    assert "ModuleNotFoundError" not in esito.stderr


def test_avvia_frontend_configurazione_non_valida(tmp_path):
    ambiente = ambiente_senza_configurazione()
    ambiente["FRONTEND_PORTA"] = "abc"
    esito = subprocess.run(
        [sys.executable, str(AVVIA), "--frontend"],
        cwd=tmp_path,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert esito.returncode == 1
    assert "FRONTEND_PORTA" in esito.stderr
    assert "ModuleNotFoundError" not in esito.stderr


BASE = getattr(sys, "_base_executable", sys.executable)


@pytest.mark.skipif(
    Path(BASE).resolve() == Path(sys.executable).resolve(),
    reason="serve un interprete diverso da quello del .venv",
)
def test_avvia_con_il_python_di_sistema_usa_il_venv(tmp_path):
    # Il Python di sistema non ha le dipendenze: avvia.py deve rilanciarsi con quello del .venv.
    esito = avvia(BASE, tmp_path)
    assert "ModuleNotFoundError" not in esito.stderr
    assert esito.returncode == 1
    assert "LMSTUDIO_BASE_URL" in esito.stderr
