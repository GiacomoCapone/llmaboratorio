"""Avvio del server «archivio» su stdio: `python -m archivio`."""

import signal
import sys

from archivio.inventario import PERCORSO_INVENTARIO, ErroreInventario, carica
from archivio.server import crea_server


def main() -> int:
    # Il Ctrl-C del terminale arriva anche al sottoprocesso: il server sopravvive a un turno
    # annullato e termina quando l'assistente chiude lo stdin.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        inventario = carica(PERCORSO_INVENTARIO)
    except ErroreInventario as errore:
        print(f"Errore: {errore}", file=sys.stderr)
        return 1
    except OSError as errore:
        dettaglio = errore.strerror or str(errore)
        print(f"Errore: inventario non leggibile: {PERCORSO_INVENTARIO} ({dettaglio}).", file=sys.stderr)
        return 1
    crea_server(inventario).run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
