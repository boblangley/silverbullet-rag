"""MCP server for Silverbullet RAG."""

import asyncio
import json
from pathlib import Path
from typing import Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

from .db import GraphDB
from .parser import SpaceParser
from .search import HybridSearch


# Initialize global instances
graph_db = GraphDB("/db")
parser = SpaceParser()
hybrid_search = HybridSearch(graph_db)

# Create MCP server
app = Server("silverbullet-rag")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="cypher_query",
            description="Execute a Cypher query against the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The Cypher query to execute",
                    }
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="keyword_search",
            description="Search for pages and content by keyword",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The keyword to search for",
                    }
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="read_page",
            description="Read the contents of a Silverbullet page",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_name": {
                        "type": "string",
                        "description": "Name of the page to read (e.g., 'MyPage.md')",
                    }
                },
                "required": ["page_name"],
            },
        ),
        Tool(
            name="semantic_search",
            description="Search for semantically similar content using AI embeddings",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query to search for",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)",
                        "default": 10,
                    },
                    "filter_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of tags to filter results by",
                    },
                    "filter_pages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of page paths to filter results by",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="hybrid_search",
            description="Advanced search combining keyword (BM25) and semantic (vector) search with score fusion. Provides best results by leveraging both exact term matching and semantic similarity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query - can be keywords or natural language",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)",
                        "default": 10,
                    },
                    "filter_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of tags to filter results by",
                    },
                    "filter_pages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of page paths to filter results by",
                    },
                    "fusion_method": {
                        "type": "string",
                        "enum": ["rrf", "weighted"],
                        "description": "Fusion method: 'rrf' (Reciprocal Rank Fusion, default) or 'weighted' (custom weights)",
                        "default": "rrf",
                    },
                    "semantic_weight": {
                        "type": "number",
                        "description": "Weight for semantic search (0-1, only used with weighted fusion, default: 0.5)",
                        "default": 0.5,
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "keyword_weight": {
                        "type": "number",
                        "description": "Weight for keyword search (0-1, only used with weighted fusion, default: 0.5)",
                        "default": 0.5,
                        "minimum": 0,
                        "maximum": 1,
                    },
                },
                "required": ["query"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> CallToolResult:
    """Handle tool calls."""
    try:
        if name == "cypher_query":
            query = arguments["query"]
            results = graph_db.cypher_query(query)
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(results, indent=2))]
            )

        elif name == "keyword_search":
            keyword = arguments["query"]
            results = graph_db.keyword_search(keyword)
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(results, indent=2))]
            )

        elif name == "read_page":
            page_name = arguments["page_name"]
            space_dir = Path("/space")
            page_path = space_dir / page_name

            # Security check
            if not page_path.resolve().is_relative_to(space_dir.resolve()):
                raise ValueError("Invalid page name")

            content = page_path.read_text()
            return CallToolResult(content=[TextContent(type="text", text=content)])

        elif name == "semantic_search":
            query = arguments["query"]
            limit = arguments.get("limit", 10)
            filter_tags = arguments.get("filter_tags")
            filter_pages = arguments.get("filter_pages")

            results = graph_db.semantic_search(
                query=query,
                limit=limit,
                filter_tags=filter_tags,
                filter_pages=filter_pages,
            )

            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(results, indent=2))]
            )

        elif name == "hybrid_search":
            query = arguments["query"]
            limit = arguments.get("limit", 10)
            filter_tags = arguments.get("filter_tags")
            filter_pages = arguments.get("filter_pages")
            fusion_method = arguments.get("fusion_method", "rrf")
            semantic_weight = arguments.get("semantic_weight", 0.5)
            keyword_weight = arguments.get("keyword_weight", 0.5)

            results = hybrid_search.search(
                query=query,
                limit=limit,
                filter_tags=filter_tags,
                filter_pages=filter_pages,
                fusion_method=fusion_method,
                semantic_weight=semantic_weight,
                keyword_weight=keyword_weight,
            )

            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(results, indent=2))]
            )

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")], isError=True
        )


async def main():
    """Run the MCP server."""
    # Index the space on startup
    print("Indexing Silverbullet space...")
    chunks = parser.parse_space("/space")
    graph_db.index_chunks(chunks)
    print(f"Indexed {len(chunks)} chunks")

    # Run the server
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
