"""Search-related MCP tools."""

import logging
from typing import Any, Dict, List, Optional

from ..dependencies import get_dependencies
from ..schema import GRAPH_SCHEMA

logger = logging.getLogger(__name__)


async def cypher_query(query: str) -> Dict[str, Any]:
    """
    Execute a Cypher query against the knowledge graph.

    Args:
        query: Cypher query string

    Returns:
        Query results as JSON with success status
    """
    try:
        deps = get_dependencies()
        results = deps.graph_db.cypher_query(query)
        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"Cypher query failed: {e}")
        return {"success": False, "error": str(e)}


async def keyword_search(query: str, limit: int = 10) -> Dict[str, Any]:
    """
    BM25-ranked keyword search across chunks, tags, and pages.

    Args:
        query: Search keyword or phrase
        limit: Maximum results to return (default: 10)

    Returns:
        Ranked search results with BM25 scores
    """
    try:
        deps = get_dependencies()
        results = deps.graph_db.keyword_search(query, limit=limit)
        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"Keyword search failed: {e}")
        return {"success": False, "error": str(e)}


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
        deps = get_dependencies()
        results = deps.graph_db.semantic_search(
            query=query, limit=limit, filter_tags=filter_tags, filter_pages=filter_pages
        )
        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        return {"success": False, "error": str(e)}


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
        deps = get_dependencies()
        results = deps.hybrid_search.search(
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


async def get_graph_schema() -> Dict[str, Any]:
    """
    Get the knowledge graph schema for constructing Cypher queries.

    Returns node types, relationship types with their directions and properties.
    Use this before writing Cypher queries to understand the graph structure.

    Returns:
        Schema definition with nodes and relationships
    """
    return {"success": True, "schema": GRAPH_SCHEMA}
