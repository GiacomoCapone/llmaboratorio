r"""Avvio dell'assistente senza impostare PYTHONPATH.

Dalla cartella del progetto:  .venv\Scripts\python.exe avvia.py
La configurazione è letta dal file .env di questa cartella.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from assistente.cli import main  # noqa: E402

raise SystemExit(main())
