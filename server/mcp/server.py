"""
MCP Server with Streamable HTTP Transport for Silverbullet RAG.

This module provides the FastMCP server setup and entry point.
"""

import asyncio
import logging

from mcp.server.fastmcp import FastMCP

from .dependencies import initialize
from .tools import register_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP(
    name="silverbullet-rag",
    host="0.0.0.0",
    port=8000,
    json_response=True,
)

# Register all tools
register_tools(mcp)


def main() -> None:
    """Main entry point for the MCP HTTP server."""
    logger.info("Starting MCP server initialization...")
    asyncio.run(initialize())

    logger.info("Starting MCP server on http://0.0.0.0:8000/mcp")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
