r"""Avvio dell'assistente senza impostare PYTHONPATH né variabili d'ambiente.

Da qualunque cartella:  python avvia.py   (oppure .venv\Scripts\python.exe avvia.py)
La configurazione è letta dal file .env della cartella del progetto. Se avviato con un Python
diverso da quello del .venv del progetto, lo script si rilancia con quello del .venv, dove sono
installate le dipendenze.
"""

import os
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent
VENV = RADICE / ".venv"
PYTHON_VENV = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _nel_venv() -> bool:
    return Path(sys.prefix).resolve() == VENV.resolve()


def _rilancia_nel_venv() -> int:
    processo = subprocess.Popen([str(PYTHON_VENV), str(RADICE / "avvia.py"), *sys.argv[1:]])
    while True:
        try:
            return processo.wait()
        except KeyboardInterrupt:
            continue  # Ctrl-C arriva anche al processo figlio, che lo gestisce


if not _nel_venv() and PYTHON_VENV.is_file():
    raise SystemExit(_rilancia_nel_venv())

sys.path.insert(0, str(RADICE / "src"))

try:
    if sys.argv[1:] == ["--backend"]:
        from backend.__main__ import main

        argomenti = []
    elif sys.argv[1:] == ["--frontend"]:
        from frontend.__main__ import main

        argomenti = []
    else:
        from assistente.cli import main

        argomenti = sys.argv[1:]
except ModuleNotFoundError as errore:
    print(
        f"Errore: dipendenza mancante ({errore.name}). Creare l'ambiente del progetto con\n"
        "  python -m venv .venv\n"
        r"  .venv\Scripts\python.exe -m pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1) from None

raise SystemExit(main(argomenti))
