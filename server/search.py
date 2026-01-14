"""Hybrid search combining keyword and semantic search."""

import logging
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)


class HybridSearch:
    """Hybrid search combining keyword BM25 and semantic vector search."""

    def __init__(self, graph_db):
        """Initialize hybrid search.

        Args:
            graph_db: GraphDB instance with both keyword and semantic search capabilities
        """
        from .db.graph import GraphDB

        self.graph_db: GraphDB = graph_db

    def search(
        self,
        query: str,
        limit: int = 10,
        filter_tags: Optional[List[str]] = None,
        filter_pages: Optional[List[str]] = None,
        fusion_method: Literal["rrf", "weighted"] = "rrf",
        semantic_weight: float = 0.5,
        keyword_weight: float = 0.5,
        scope: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Perform hybrid search combining keyword and semantic results.

        Args:
            query: Search query string
            limit: Maximum number of results to return
            filter_tags: Optional list of tags to filter results
            filter_pages: Optional list of page paths to filter results
            fusion_method: Method to combine results - "rrf" (Reciprocal Rank Fusion) or "weighted"
            semantic_weight: Weight for semantic scores (used with weighted fusion)
            keyword_weight: Weight for keyword scores (used with weighted fusion)
            scope: Optional folder path to scope results to (e.g., "Projects/ProjectA")

        Returns:
            List of results with combined scores, sorted by relevance

        Raises:
            ValueError: If query is empty or weights don't sum to 1.0 for weighted fusion
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        if fusion_method == "weighted":
            total_weight = semantic_weight + keyword_weight
            if abs(total_weight - 1.0) > 0.01:  # Allow small floating point errors
                # Normalize weights if they don't sum to 1
                logger.warning(f"Weights sum to {total_weight}, normalizing to 1.0")
                semantic_weight = semantic_weight / total_weight
                keyword_weight = keyword_weight / total_weight

        # Perform keyword search with BM25
        keyword_results = self.graph_db.keyword_search(query, scope=scope)
        logger.info(f"Keyword search returned {len(keyword_results)} results")

        # Perform semantic search if embeddings are enabled
        semantic_results = []
        if self.graph_db.enable_embeddings:
            try:
                semantic_results = self.graph_db.semantic_search(
                    query=query,
                    limit=limit * 2,  # Get more candidates for better fusion
                    filter_tags=filter_tags,
                    filter_pages=filter_pages,
                    scope=scope,
                )
                logger.info(f"Semantic search returned {len(semantic_results)} results")
            except Exception as e:
                logger.warning(f"Semantic search failed, using keyword-only: {e}")
        else:
            logger.info("Embeddings disabled, using keyword-only search")

        # If only one search type has results, return those
        if not semantic_results:
            results = self._format_results(keyword_results, keyword_only=True)[:limit]
            return self._strip_embeddings(results)
        if not keyword_results:
            results = self._format_results(semantic_results, semantic_only=True)[:limit]
            return self._strip_embeddings(results)

        # Fuse results using selected method
        if fusion_method == "rrf":
            fused_results = self._reciprocal_rank_fusion(
                keyword_results, semantic_results, limit * 2  # Get more for filtering
            )
        else:  # weighted
            fused_results = self._weighted_fusion(
                keyword_results,
                semantic_results,
                semantic_weight,
                keyword_weight,
                limit * 2,  # Get more for filtering
            )

        # Apply post-fusion tag filtering if specified
        # This ensures keyword results also respect the tag filter
        if filter_tags:
            fused_results = self._filter_by_tags(fused_results, filter_tags)

        # Apply post-fusion page filtering if specified
        if filter_pages:
            fused_results = self._filter_by_pages(fused_results, filter_pages)

        # Strip embeddings from results to reduce response size
        results = fused_results[:limit]
        return self._strip_embeddings(results)

    def _reciprocal_rank_fusion(
        self,
        keyword_results: List[Dict[str, Any]],
        semantic_results: List[Dict[str, Any]],
        limit: int,
        k: int = 60,
    ) -> List[Dict[str, Any]]:
        """Combine results using Reciprocal Rank Fusion (RRF).

        RRF formula: score(d) = sum over all rankings r: 1 / (k + rank(d, r))
        where k is typically 60 (constant to prevent division by zero)

        Args:
            keyword_results: Results from keyword search
            semantic_results: Results from semantic search
            limit: Maximum number of results to return
            k: RRF constant (default: 60)

        Returns:
            Fused results sorted by RRF score
        """
        rrf_scores = {}
        chunk_data = {}

        # Process keyword results
        for rank, result in enumerate(keyword_results, start=1):
            chunk = result.get("col0", {})
            chunk_id = chunk.get("id", "")
            if not chunk_id:
                continue

            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            chunk_data[chunk_id] = {
                "chunk": chunk,
                "keyword_score": result.get("bm25_score", 0.0),
                "semantic_score": 0.0,
            }

        # Process semantic results
        for rank, result in enumerate(semantic_results, start=1):
            chunk = result.get("col0", {})
            chunk_id = chunk.get("id", "")
            if not chunk_id:
                continue

            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (k + rank)

            if chunk_id in chunk_data:
                # Update existing entry with semantic score
                chunk_data[chunk_id]["semantic_score"] = 1.0 / (k + rank)
            else:
                # New entry from semantic search only
                chunk_data[chunk_id] = {
                    "chunk": chunk,
                    "keyword_score": 0.0,
                    "semantic_score": 1.0 / (k + rank),
                }

        # Normalize RRF scores to 0-1 range
        if rrf_scores:
            max_score = max(rrf_scores.values())
            min_score = min(rrf_scores.values())
            score_range = max_score - min_score if max_score > min_score else 1.0

            for chunk_id in rrf_scores:
                rrf_scores[chunk_id] = (rrf_scores[chunk_id] - min_score) / score_range

        # Build final results
        results = []
        for chunk_id, score in rrf_scores.items():
            data = chunk_data[chunk_id]
            results.append(
                {
                    "chunk": data["chunk"],
                    "hybrid_score": round(score, 4),
                    "keyword_score": data["keyword_score"],
                    "semantic_score": data["semantic_score"],
                }
            )

        # Sort by hybrid score (descending) and limit
        results.sort(key=lambda x: x["hybrid_score"], reverse=True)
        return results[:limit]

    def _weighted_fusion(
        self,
        keyword_results: List[Dict[str, Any]],
        semantic_results: List[Dict[str, Any]],
        semantic_weight: float,
        keyword_weight: float,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Combine results using weighted score fusion.

        Args:
            keyword_results: Results from keyword search with BM25 scores
            semantic_results: Results from semantic search
            semantic_weight: Weight for semantic scores
            keyword_weight: Weight for keyword scores
            limit: Maximum number of results to return

        Returns:
            Fused results sorted by weighted score
        """
        # Normalize keyword BM25 scores to 0-1 range
        keyword_scores = {}
        if keyword_results:
            bm25_scores = [r.get("bm25_score", 0.0) for r in keyword_results]
            max_bm25 = max(bm25_scores) if bm25_scores else 1.0
            min_bm25 = min(bm25_scores) if bm25_scores else 0.0
            bm25_range = max_bm25 - min_bm25 if max_bm25 > min_bm25 else 1.0

            for result in keyword_results:
                chunk = result.get("col0", {})
                chunk_id = chunk.get("id", "")
                if chunk_id:
                    bm25 = result.get("bm25_score", 0.0)
                    keyword_scores[chunk_id] = (bm25 - min_bm25) / bm25_range

        # Normalize semantic scores to 0-1 range (using rank-based scoring)
        semantic_scores = {}
        for rank, result in enumerate(semantic_results, start=1):
            chunk = result.get("col0", {})
            chunk_id = chunk.get("id", "")
            if chunk_id:
                # Use exponential decay: score = exp(-0.1 * rank)
                import math

                semantic_scores[chunk_id] = math.exp(-0.1 * rank)

        # Combine all chunk IDs
        all_chunk_ids = set(keyword_scores.keys()) | set(semantic_scores.keys())

        # Build chunk data lookup
        chunk_data = {}
        for result in keyword_results:
            chunk = result.get("col0", {})
            chunk_id = chunk.get("id", "")
            if chunk_id:
                chunk_data[chunk_id] = chunk

        for result in semantic_results:
            chunk = result.get("col0", {})
            chunk_id = chunk.get("id", "")
            if chunk_id and chunk_id not in chunk_data:
                chunk_data[chunk_id] = chunk

        # Calculate weighted scores
        results = []
        for chunk_id in all_chunk_ids:
            kw_score = keyword_scores.get(chunk_id, 0.0)
            sem_score = semantic_scores.get(chunk_id, 0.0)
            weighted_score = keyword_weight * kw_score + semantic_weight * sem_score

            results.append(
                {
                    "chunk": chunk_data[chunk_id],
                    "hybrid_score": round(weighted_score, 4),
                    "keyword_score": kw_score,
                    "semantic_score": sem_score,
                }
            )

        # Sort by weighted score (descending) and limit
        results.sort(key=lambda x: x["hybrid_score"], reverse=True)
        return results[:limit]

    def _format_results(
        self,
        results: List[Dict[str, Any]],
        keyword_only: bool = False,
        semantic_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Format results to unified structure.

        Args:
            results: Raw results from keyword or semantic search
            keyword_only: If True, results are from keyword search only
            semantic_only: If True, results are from semantic search only

        Returns:
            Formatted results with hybrid_score, keyword_score, semantic_score
        """
        formatted = []
        for i, result in enumerate(results):
            chunk = result.get("col0", {})

            if keyword_only:
                formatted.append(
                    {
                        "chunk": chunk,
                        "hybrid_score": result.get("bm25_score", 0.0),
                        "keyword_score": result.get("bm25_score", 0.0),
                        "semantic_score": 0.0,
                    }
                )
            elif semantic_only:
                # Use rank-based scoring for semantic results
                import math

                rank_score = math.exp(-0.1 * (i + 1))
                formatted.append(
                    {
                        "chunk": chunk,
                        "hybrid_score": round(rank_score, 4),
                        "keyword_score": 0.0,
                        "semantic_score": round(rank_score, 4),
                    }
                )

        return formatted

    def _filter_by_tags(
        self, results: List[Dict[str, Any]], filter_tags: List[str]
    ) -> List[Dict[str, Any]]:
        """Filter results to only include chunks with specified tags.

        Args:
            results: List of hybrid search results
            filter_tags: List of required tag names

        Returns:
            Filtered results where each chunk has at least one of the specified tags
        """
        filtered = []
        for result in results:
            chunk = result.get("chunk", {})
            chunk_id = chunk.get("id", "")
            if not chunk_id:
                continue

            # Query the graph for this chunk's tags
            tag_query = """
            MATCH (c:Chunk {id: $chunk_id})-[:TAGGED]->(t:Tag)
            RETURN t.name as tag
            """
            tags = self.graph_db.cypher_query(tag_query, {"chunk_id": chunk_id})
            chunk_tags = {t.get("col0", "") for t in tags}

            # Check if chunk has any of the required tags
            if any(tag in chunk_tags for tag in filter_tags):
                filtered.append(result)

        return filtered

    def _filter_by_pages(
        self, results: List[Dict[str, Any]], filter_pages: List[str]
    ) -> List[Dict[str, Any]]:
        """Filter results to only include chunks from specified pages.

        Args:
            results: List of hybrid search results
            filter_pages: List of allowed page paths

        Returns:
            Filtered results where each chunk's file_path is in the allowed list
        """
        filtered = []
        for result in results:
            chunk = result.get("chunk", {})
            file_path = chunk.get("file_path", "")

            if file_path in filter_pages:
                filtered.append(result)

        return filtered

    def _strip_embeddings(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Strip embedding vectors from search results to reduce response size.

        Embeddings are typically 1536 floats (~12KB per chunk) and are not useful
        in search results for display purposes.

        Args:
            results: List of search results containing chunk data

        Returns:
            Results with embedding field removed from chunks
        """
        for result in results:
            chunk = result.get("chunk", {})
            if chunk and isinstance(chunk, dict) and "embedding" in chunk:
                del chunk["embedding"]
        return results
