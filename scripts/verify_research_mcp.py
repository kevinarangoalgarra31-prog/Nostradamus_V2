"""Verificación manual del transporte stdio del MCP de investigación."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def verify() -> dict[str, object]:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(PROJECT_ROOT / "nostradamus_mcp.py"), "stdio"],
        cwd=PROJECT_ROOT,
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            initialized = await session.initialize()
            listed = await session.list_tools()
            response = await session.call_tool("sources_describe", {})
            return {
                "server": initialized.serverInfo.name,
                "version": initialized.serverInfo.version,
                "tools": [tool.name for tool in listed.tools],
                "sources_describe_ok": not bool(response.isError),
            }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(verify()), ensure_ascii=False, indent=2))
