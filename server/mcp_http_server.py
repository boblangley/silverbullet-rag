"""
MCP Server with Streamable HTTP Transport for Silverbullet RAG.

This server replaces the stdio transport with production-ready HTTP transport
using FastMCP from the official MCP Python SDK.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

# Import existing components
from .db.graph import GraphDB
from .parser.space_parser import SpaceParser
from .search import HybridSearch

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP(
    name="silverbullet-rag",
    host="0.0.0.0",  # Listen on all interfaces for Docker
    port=8000,
    json_response=True,  # Recommended for production
)

# Global instances (initialized on startup)
graph_db: Optional[GraphDB] = None
space_parser: Optional[SpaceParser] = None
hybrid_search: Optional[HybridSearch] = None


# Tool 1: Cypher Query
@mcp.tool()
async def cypher_query(query: str) -> Dict[str, Any]:
    """
    Execute a Cypher query against the knowledge graph.

    Args:
        query: Cypher query string

    Returns:
        Query results as JSON with success status
    """
    try:
        results = graph_db.cypher_query(query)
        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"Cypher query failed: {e}")
        return {"success": False, "error": str(e)}


# Tool 2: Keyword Search
@mcp.tool()
async def keyword_search(query: str) -> Dict[str, Any]:
    """
    BM25-ranked keyword search across chunks, tags, and pages.

    Args:
        query: Search keyword or phrase

    Returns:
        Ranked search results with BM25 scores
    """
    try:
        results = graph_db.keyword_search(query)
        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"Keyword search failed: {e}")
        return {"success": False, "error": str(e)}


# Tool 3: Semantic Search
@mcp.tool()
async def semantic_search(
    query: str,
    limit: int = 10,
    filter_tags: Optional[List[str]] = None,
    filter_pages: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    AI-powered semantic search using vector embeddings.

    Args:
        query: Natural language search query
        limit: Maximum results to return (default: 10)
        filter_tags: Optional tag filter
        filter_pages: Optional page name filter

    Returns:
        Semantically ranked results with similarity scores
    """
    try:
        results = graph_db.semantic_search(
            query=query, limit=limit, filter_tags=filter_tags, filter_pages=filter_pages
        )
        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        return {"success": False, "error": str(e)}


# Tool 4: Hybrid Search
@mcp.tool()
async def hybrid_search_tool(
    query: str,
    limit: int = 10,
    filter_tags: Optional[List[str]] = None,
    filter_pages: Optional[List[str]] = None,
    fusion_method: str = "rrf",
    semantic_weight: float = 0.5,
    keyword_weight: float = 0.5,
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Combined keyword + semantic search with result fusion.

    Args:
        query: Search query
        limit: Maximum results
        filter_tags: Optional tag filter
        filter_pages: Optional page filter
        fusion_method: "rrf" (Reciprocal Rank Fusion) or "weighted"
        semantic_weight: Weight for semantic results (0-1)
        keyword_weight: Weight for keyword results (0-1)
        scope: Optional folder path to scope results to (e.g., "Projects/ProjectA")

    Returns:
        Fused search results sorted by combined score
    """
    try:
        results = hybrid_search.search(
            query=query,
            limit=limit,
            filter_tags=filter_tags,
            filter_pages=filter_pages,
            fusion_method=fusion_method,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
            scope=scope,
        )
        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        return {"success": False, "error": str(e)}


# Tool 5: Get Project Context
@mcp.tool()
async def get_project_context(
    github_remote: Optional[str] = None, folder_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get project context from Silverbullet space by GitHub remote or folder path.

    This tool finds and returns the project index page and related metadata.
    Use this to inject relevant context when working on a project.

    Args:
        github_remote: GitHub repository in "org/repo" format (e.g., "anthropics/claude-code")
        folder_path: Folder path in Silverbullet space (e.g., "Projects/MyProject")

    Returns:
        Project context including index page content, frontmatter, and related pages
    """
    try:
        space_path = Path(os.getenv("SPACE_PATH", "/space"))

        if not github_remote and not folder_path:
            return {
                "success": False,
                "error": "Must provide either github_remote or folder_path",
            }

        project_file = None
        frontmatter = {}

        # Search by GitHub remote
        if github_remote:
            # Search all markdown files for matching github frontmatter
            for md_file in space_path.glob("**/*.md"):
                fm = space_parser.get_frontmatter(str(md_file))
                if fm.get("github") == github_remote:
                    project_file = md_file
                    frontmatter = fm
                    break

        # Search by folder path
        elif folder_path:
            # In Silverbullet, folder index is Folder.md (sibling), not Folder/index.md
            # First try the sibling index file
            parts = folder_path.split("/")
            if len(parts) > 1:
                parent = "/".join(parts[:-1])
                index_file = space_path / parent / f"{parts[-1]}.md"
            else:
                index_file = space_path / f"{folder_path}.md"

            if index_file.exists():
                project_file = index_file
                frontmatter = space_parser.get_frontmatter(str(index_file))
            else:
                # Try looking for any .md file in the folder with project metadata
                folder_dir = space_path / folder_path
                if folder_dir.exists() and folder_dir.is_dir():
                    for md_file in folder_dir.glob("*.md"):
                        fm = space_parser.get_frontmatter(str(md_file))
                        if fm:  # Has some frontmatter
                            project_file = md_file
                            frontmatter = fm
                            break

        if not project_file:
            return {
                "success": False,
                "error": f"No project found for github_remote={github_remote}, folder_path={folder_path}",
            }

        # Read the project file content
        content = project_file.read_text(encoding="utf-8")

        # Strip frontmatter from content for display
        clean_content = space_parser._strip_frontmatter(content)

        # Get related pages from the same folder
        relative_path = project_file.relative_to(space_path)
        folder = relative_path.parent

        related_pages = []
        if folder != Path("."):
            folder_dir = space_path / folder
            for md_file in folder_dir.glob("*.md"):
                if md_file != project_file:
                    related_pages.append(
                        {
                            "name": md_file.stem,
                            "path": str(md_file.relative_to(space_path)),
                        }
                    )

        # Also check for subdirectory matching the project file name
        # e.g., for Projects/Project.md, check Projects/Project/ directory
        project_subdir = project_file.parent / project_file.stem
        if project_subdir.exists() and project_subdir.is_dir():
            for md_file in project_subdir.glob("**/*.md"):
                related_pages.append(
                    {"name": md_file.stem, "path": str(md_file.relative_to(space_path))}
                )

        return {
            "success": True,
            "project": {
                "file": str(relative_path),
                "github": frontmatter.get("github"),
                "tags": frontmatter.get("tags", []),
                "concerns": frontmatter.get("concerns", []),
                "content": clean_content,
            },
            "related_pages": related_pages[:20],  # Limit to 20 related pages
        }

    except Exception as e:
        logger.error(f"Failed to get project context: {e}")
        return {"success": False, "error": str(e)}


# Tool 6: Read Page
@mcp.tool()
async def read_page(page_name: str) -> Dict[str, Any]:
    """
    Read the contents of a Silverbullet page.

    Args:
        page_name: Name of the page (e.g., 'MyPage.md')

    Returns:
        Page content as string
    """
    try:
        space_path = Path(os.getenv("SPACE_PATH", "/space"))
        file_path = space_path / page_name

        # Security check - prevent path traversal
        if not file_path.resolve().is_relative_to(space_path.resolve()):
            return {"success": False, "error": f"Invalid page name: {page_name}"}

        if not file_path.exists():
            return {"success": False, "error": f"Page '{page_name}' not found"}

        content = file_path.read_text(encoding="utf-8")
        return {"success": True, "content": content}
    except Exception as e:
        logger.error(f"Failed to read page '{page_name}': {e}")
        return {"success": False, "error": str(e)}


# Tool 7: Update Page
@mcp.tool()
async def update_page(page_name: str, content: str) -> Dict[str, Any]:
    """
    Update or create a Silverbullet page.

    Args:
        page_name: Name of the page (e.g., 'MyPage.md')
        content: New page content

    Returns:
        Success confirmation
    """
    try:
        space_path = Path(os.getenv("SPACE_PATH", "/space"))
        file_path = space_path / page_name

        # Security check - prevent path traversal
        if not file_path.resolve().is_relative_to(space_path.resolve()):
            return {"success": False, "error": f"Invalid page name: {page_name}"}

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        file_path.write_text(content, encoding="utf-8")

        # File watcher will trigger reindexing automatically
        logger.info(f"Updated page: {page_name}")

        return {"success": True, "message": f"Page '{page_name}' updated successfully"}
    except Exception as e:
        logger.error(f"Failed to update page '{page_name}': {e}")
        return {"success": False, "error": str(e)}


async def initialize_server():
    """Initialize database and parser before serving requests."""
    global graph_db, space_parser, hybrid_search

    logger.info("Initializing Silverbullet RAG server...")

    # Get paths from environment variables
    db_path = os.getenv("DB_PATH", "/data/ladybug")
    space_path = os.getenv("SPACE_PATH", "/space")

    # Initialize graph database
    logger.info(f"Initializing GraphDB at {db_path}...")
    graph_db = GraphDB(db_path)

    # Initialize space parser
    logger.info(f"Initializing SpaceParser for {space_path}...")
    space_parser = SpaceParser(space_path)

    # Parse and index entire space on startup
    logger.info("Indexing Silverbullet space...")
    chunks = space_parser.parse_space(space_path)
    graph_db.index_chunks(chunks)
    logger.info(f"Indexed {len(chunks)} chunks")

    # Initialize hybrid search
    hybrid_search = HybridSearch(graph_db)

    logger.info("Server initialization complete!")


def main():
    """Main entry point for the MCP HTTP server."""
    # Initialize before starting server
    logger.info("Starting MCP server initialization...")
    asyncio.run(initialize_server())

    # Run FastMCP with streamable HTTP transport
    logger.info("Starting MCP server on http://0.0.0.0:8000/mcp")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
