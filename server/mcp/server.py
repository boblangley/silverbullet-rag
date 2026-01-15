"""
MCP Server with Streamable HTTP Transport for Silverbullet RAG.

This module provides the FastMCP server setup and entry point.
"""

import asyncio
import logging
import os

from mcp.server.fastmcp import FastMCP

from .dependencies import initialize
from .tools import register_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_mcp_server(port: int = 8000) -> FastMCP:
    """Create and configure an MCP server instance.

    Args:
        port: Port to run the server on (default: 8000)

    Returns:
        Configured FastMCP server instance
    """
    server = FastMCP(
        name="silverbullet-rag",
        host="0.0.0.0",
        port=port,
        json_response=True,
    )
    register_tools(server)
    return server


# Default server instance for standalone mode
# Tools are registered lazily when main() is called
mcp: FastMCP = None  # type: ignore


def main() -> None:
    """Main entry point for the MCP HTTP server (standalone mode)."""
    global mcp

    logger.info("Starting MCP server initialization...")
    asyncio.run(initialize())

    port = int(os.getenv("MCP_PORT", "8000"))
    mcp = create_mcp_server(port)

    logger.info(f"Starting MCP server on http://0.0.0.0:{port}/mcp")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
