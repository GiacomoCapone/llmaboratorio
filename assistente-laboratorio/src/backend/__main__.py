"""Avvio del back-end delle conversazioni: python -m backend (o python avvia.py --backend)."""

import logging
import sys

import uvicorn

from backend import config
from backend.agente import ClientAgente
from backend.app import crea_app
from backend.config import ConfigBackend, ErroreConfigurazione, carica_config
from backend.deposito import DepositoPostgres, ErroreDatabase

logger = logging.getLogger("backend")


def servi(config: ConfigBackend) -> None:
    """Prepara il database e avvia il servizio; ritorna dopo Ctrl-C o SIGTERM."""
    deposito = DepositoPostgres(config.database_url)
    deposito.prepara()
    agente = ClientAgente(config.agente_url, config.agente_timeout)
    logger.info("backend in ascolto su http://%s:%d", config.host, config.porta)
    uvicorn.run(
        crea_app(deposito, agente),
        host=config.host,
        port=config.porta,
        log_level=getattr(logging, config.log_level, logging.INFO),
    )


def main(argv: list[str] | None = None) -> int:
    argv = [] if argv is None else argv
    if argv:
        print("Uso: python avvia.py [--http | --backend]", file=sys.stderr)
        return 2
    try:
        impostazioni = carica_config()
        logging.basicConfig(
            level=getattr(logging, impostazioni.log_level, logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            stream=sys.stderr,
        )
        servi(impostazioni)
    except ErroreConfigurazione as errore:
        print(f"Errore: {errore}", file=sys.stderr)
        return 1
    except ErroreDatabase as errore:
        print(f"Errore: database non raggiungibile: {errore}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrotto.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
