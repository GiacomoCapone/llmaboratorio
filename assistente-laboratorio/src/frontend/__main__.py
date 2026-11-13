"""Avvio del front-end: python -m frontend (o python avvia.py --frontend)."""

import logging
import sys

import uvicorn

from frontend.app import crea_app
from frontend.config import ConfigFrontend, ErroreConfigurazione, carica_config

logger = logging.getLogger("frontend")


def servi(config: ConfigFrontend) -> None:
    """Avvia il servizio della pagina; ritorna dopo Ctrl-C o SIGTERM."""
    logger.info("frontend in ascolto su http://%s:%d", config.host, config.porta)
    uvicorn.run(
        crea_app(config.backend_url, config.backend_timeout),
        host=config.host,
        port=config.porta,
        log_level=getattr(logging, config.log_level, logging.INFO),
    )


def main(argv: list[str] | None = None) -> int:
    argv = [] if argv is None else argv
    if argv:
        print("Uso: python avvia.py [--http | --backend | --frontend]", file=sys.stderr)
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
    except KeyboardInterrupt:
        print("Interrotto.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
