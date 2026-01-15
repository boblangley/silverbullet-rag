"""MCP tools registration."""

from mcp.server.fastmcp import FastMCP

from .search import (
    cypher_query,
    keyword_search,
    semantic_search,
    hybrid_search_tool,
    get_graph_schema,
)
from .pages import read_page, get_project_context
from .proposals import propose_change, list_proposals, withdraw_proposal


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools with the server."""
    # Search tools
    mcp.tool()(cypher_query)
    mcp.tool()(keyword_search)
    mcp.tool()(semantic_search)
    mcp.tool()(hybrid_search_tool)
    mcp.tool()(get_graph_schema)

    # Page tools
    mcp.tool()(read_page)
    mcp.tool()(get_project_context)

    # Proposal tools
    mcp.tool()(propose_change)
    mcp.tool()(list_proposals)
    mcp.tool()(withdraw_proposal)
