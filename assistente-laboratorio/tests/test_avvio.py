"""Lo script avvia.py trova il pacchetto senza PYTHONPATH."""

import os
import subprocess
import sys
from pathlib import Path

AVVIA = Path(__file__).resolve().parents[1] / "avvia.py"


def test_avvia_senza_pythonpath_ne_configurazione(tmp_path):
    ambiente = {
        k: v
        for k, v in os.environ.items()
        if k != "PYTHONPATH" and not k.startswith(("LMSTUDIO_", "MAX_PASSAGGI", "FUSO_"))
    }
    esito = subprocess.run(
        [sys.executable, str(AVVIA)],
        cwd=tmp_path,  # nessun .env in questa cartella
        env=ambiente,
        input="",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert esito.returncode == 1
    assert "LMSTUDIO_" in esito.stderr
    assert "ModuleNotFoundError" not in esito.stderr
