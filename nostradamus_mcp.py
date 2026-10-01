"""Punto de entrada estable para el servidor MCP local."""

from pathlib import Path

from dotenv import load_dotenv


# El proceso carga secretos localmente sin incluirlos en argumentos, resultados o logs.
load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)

from src.research_mcp.server import main


if __name__ == "__main__":
    main()
