"""
Nostradamus V1.1 -- Punto de Entrada Principal (Web Server)
===========================================================
Carga .env, inicia el servidor FastAPI con Uvicorn y abre el navegador.
Uso: python -m src.nostradamus.main
"""
import io
import logging
import sys
import webbrowser
import uvicorn
from threading import Timer

from dotenv import load_dotenv

# Cargar variables de entorno antes de cualquier import de servicios
load_dotenv()

# -- Configurar logging ------------------------------------------------
LOG_FORMAT = "%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s"
DATE_FORMAT = "%H:%M:%S"


def setup_logging():
    """Configura logging estandar de Python."""
    root_logger = logging.getLogger("nostradamus")
    root_logger.setLevel(logging.DEBUG)

    # Console handler -- force UTF-8 on Windows
    utf8_stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )
    console = logging.StreamHandler(utf8_stdout)
    console.setLevel(logging.DEBUG)
    console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root_logger.addHandler(console)

    # Silenciar loggers ruidosos
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def open_browser():
    """Abre el navegador tras un breve retraso."""
    webbrowser.open("http://127.0.0.1:8000")


def main():
    """Punto de entrada principal para el Backend."""
    setup_logging()
    logger = logging.getLogger("nostradamus.main")
    logger.info("Iniciando Nostradamus V1.1 (Servidor Web)...")

    # Abrir navegador en 1.5 segundos
    Timer(1.5, open_browser).start()

    # Lanzar servidor uvicorn
    uvicorn.run("src.nostradamus.server:app", host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
