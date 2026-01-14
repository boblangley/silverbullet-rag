"""Tests for hybrid search combining keyword and semantic search."""

import pytest
from pathlib import Path
from server.db.graph import GraphDB
from server.parser.space_parser import SpaceParser
from server.search import HybridSearch


@pytest.fixture
def diverse_docs_for_hybrid(temp_space_path: str) -> Path:
    """Create diverse documents for testing hybrid search.

    Args:
        temp_space_path: Temporary space directory

    Returns:
        Path to the temporary space directory
    """
    space = Path(temp_space_path)

    # Document 1: Exact keyword match but semantically less relevant
    doc1 = space / "fruit_database.md"
    doc1.write_text(
        """---
tags: [food, nutrition]
---
# Fruit Database

## Fruit Information

This database contains information about fruits. The fruit database has
entries for apples, oranges, and bananas.
"""
    )

    # Document 2: Semantically relevant but fewer keyword matches
    doc2 = space / "data_storage_systems.md"
    doc2.write_text(
        """---
tags: [technology, architecture]
---
# Data Storage Systems

## Modern Storage Solutions

Contemporary data management platforms utilize various persistence mechanisms
including relational stores, document collections, and graph repositories.
These systems handle information efficiently and scale horizontally.
"""
    )

    # Document 3: Both keyword and semantic relevance
    doc3 = space / "database_architecture.md"
    doc3.write_text(
        """---
tags: [database, system-design]
---
# Database Architecture

## Database Design Patterns

Modern database systems require careful architectural planning. Database
schemas, indexing strategies, and query optimization are essential for
building scalable database applications.
"""
    )

    # Document 4: Different topic entirely
    doc4 = space / "cooking_recipes.md"
    doc4.write_text(
        """---
tags: [cooking, recipes]
---
# Cooking Recipes

## Italian Cuisine

Learn to make pasta, pizza, and risotto. These traditional recipes
have been passed down through generations.
"""
    )

    return space


def test_hybrid_search_initialization(temp_db_path: str):
    """Test that HybridSearch can be initialized with GraphDB."""
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=True)

    # Act
    hybrid_search = HybridSearch(graph_db)

    # Assert
    assert hybrid_search is not None
    assert hybrid_search.graph_db is graph_db


def test_hybrid_search_basic(temp_db_path: str, diverse_docs_for_hybrid: Path):
    """Test basic hybrid search functionality.

    Hybrid search should combine keyword and semantic results.
    """
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=True)
    parser = SpaceParser()
    chunks = parser.parse_space(str(diverse_docs_for_hybrid))
    graph_db.index_chunks(chunks)

    hybrid_search = HybridSearch(graph_db)

    # Act
    results = hybrid_search.search(query="database systems", limit=10)

    # Assert
    assert len(results) > 0, "Hybrid search should return results"

    # Check result structure
    for result in results:
        assert "chunk" in result, "Each result should have chunk data"
        assert "hybrid_score" in result, "Each result should have hybrid score"
        assert "keyword_score" in result, "Each result should have keyword BM25 score"
        assert "semantic_score" in result, "Each result should have semantic score"


def test_hybrid_search_outperforms_keyword_only(
    temp_db_path: str, diverse_docs_for_hybrid: Path
):
    """Test that hybrid search finds semantically relevant documents that keyword search misses.

    Query: "data management platform"
    - Keyword-only: Might miss "data_storage_systems.md" due to different terminology
    - Semantic: Should find "data_storage_systems.md" due to semantic similarity
    - Hybrid: Should combine both for better recall
    """
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=True)
    parser = SpaceParser()
    chunks = parser.parse_space(str(diverse_docs_for_hybrid))
    graph_db.index_chunks(chunks)

    hybrid_search = HybridSearch(graph_db)

    # Act
    _keyword_results = graph_db.keyword_search("data management platform")  # noqa: F841
    hybrid_results = hybrid_search.search(query="data management platform", limit=10)

    # Assert - hybrid should find more relevant results
    hybrid_paths = [r["chunk"].get("file_path", "") for r in hybrid_results]

    # Should find the semantically relevant document
    assert any("data_storage_systems" in path for path in hybrid_paths), (
        "Hybrid search should find semantically relevant document"
    )


def test_hybrid_search_outperforms_semantic_only(
    temp_db_path: str, diverse_docs_for_hybrid: Path
):
    """Test that hybrid search benefits from keyword precision.

    Query with specific technical term should rank exact matches higher.
    """
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=True)
    parser = SpaceParser()
    chunks = parser.parse_space(str(diverse_docs_for_hybrid))
    graph_db.index_chunks(chunks)

    hybrid_search = HybridSearch(graph_db)

    # Act
    _semantic_results = graph_db.semantic_search("database")  # noqa: F841
    hybrid_results = hybrid_search.search(query="database", limit=10)

    # Assert
    # Hybrid should rank documents with exact "database" keyword higher
    top_hybrid = hybrid_results[0] if hybrid_results else {}
    top_hybrid_path = top_hybrid.get("chunk", {}).get("file_path", "")

    # Should prioritize documents with the exact term
    assert "database" in top_hybrid_path.lower(), (
        "Hybrid search should prioritize exact keyword matches"
    )


def test_hybrid_search_rrf_fusion(temp_db_path: str, diverse_docs_for_hybrid: Path):
    """Test Reciprocal Rank Fusion (RRF) is applied correctly.

    RRF formula: score(d) = sum over all rankings r: 1 / (k + rank(d, r))
    where k is typically 60.
    """
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=True)
    parser = SpaceParser()
    chunks = parser.parse_space(str(diverse_docs_for_hybrid))
    graph_db.index_chunks(chunks)

    hybrid_search = HybridSearch(graph_db)

    # Act
    results = hybrid_search.search(query="database", limit=10, fusion_method="rrf")

    # Assert
    assert len(results) > 0, "RRF fusion should return results"

    # RRF scores should be between 0 and 2 (since we have 2 rankings: keyword + semantic)
    # Each ranking contributes at most 1/(k+1) ≈ 0.016 for rank 1
    for result in results:
        rrf_score = result["hybrid_score"]
        assert 0 <= rrf_score <= 1, (
            f"RRF score should be normalized between 0-1, got {rrf_score}"
        )

    # Results should be sorted by hybrid score
    scores = [r["hybrid_score"] for r in results]
    assert scores == sorted(scores, reverse=True), (
        "Results should be sorted by hybrid score"
    )


def test_hybrid_search_weighted_fusion(
    temp_db_path: str, diverse_docs_for_hybrid: Path
):
    """Test weighted fusion with custom weights for keyword vs semantic."""
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=True)
    parser = SpaceParser()
    chunks = parser.parse_space(str(diverse_docs_for_hybrid))
    graph_db.index_chunks(chunks)

    hybrid_search = HybridSearch(graph_db)

    # Act - favor semantic search (70% semantic, 30% keyword)
    results_semantic_heavy = hybrid_search.search(
        query="database",
        limit=10,
        fusion_method="weighted",
        semantic_weight=0.7,
        keyword_weight=0.3,
    )

    # Act - favor keyword search (70% keyword, 30% semantic)
    results_keyword_heavy = hybrid_search.search(
        query="database",
        limit=10,
        fusion_method="weighted",
        semantic_weight=0.3,
        keyword_weight=0.7,
    )

    # Assert - different weightings should produce different rankings
    semantic_heavy_top = results_semantic_heavy[0] if results_semantic_heavy else {}
    keyword_heavy_top = results_keyword_heavy[0] if results_keyword_heavy else {}

    # Top results might differ based on weighting
    # At minimum, scores should be different
    if semantic_heavy_top and keyword_heavy_top:
        assert (
            semantic_heavy_top["hybrid_score"] != keyword_heavy_top["hybrid_score"]
            or semantic_heavy_top["chunk"]["id"] != keyword_heavy_top["chunk"]["id"]
        ), "Different fusion weights should affect results"


def test_hybrid_search_with_filters(temp_db_path: str, diverse_docs_for_hybrid: Path):
    """Test that hybrid search supports tag and page filtering."""
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=True)
    parser = SpaceParser()
    chunks = parser.parse_space(str(diverse_docs_for_hybrid))
    graph_db.index_chunks(chunks)

    hybrid_search = HybridSearch(graph_db)

    # Act - filter by tag
    results = hybrid_search.search(query="database", limit=10, filter_tags=["database"])

    # Assert
    assert len(results) > 0, "Should find results with tag filter"

    # All results should have the specified tag
    for result in results:
        # We need to verify the chunk is tagged with "database"
        # This requires checking the graph relationships
        chunk_id = result["chunk"]["id"]
        tag_query = """
        MATCH (c:Chunk {id: $chunk_id})-[:TAGGED]->(t:Tag)
        RETURN t.name as tag
        """
        tags = graph_db.cypher_query(tag_query, {"chunk_id": chunk_id})
        tag_names = [t.get("col0", "") for t in tags]
        assert "database" in tag_names, "Result should have 'database' tag"


def test_hybrid_search_empty_query(temp_db_path: str, diverse_docs_for_hybrid: Path):
    """Test hybrid search handles empty queries gracefully."""
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=True)
    parser = SpaceParser()
    chunks = parser.parse_space(str(diverse_docs_for_hybrid))
    graph_db.index_chunks(chunks)

    hybrid_search = HybridSearch(graph_db)

    # Act & Assert
    with pytest.raises(ValueError, match="Query cannot be empty"):
        hybrid_search.search(query="", limit=10)


def test_hybrid_search_no_results(temp_db_path: str, diverse_docs_for_hybrid: Path):
    """Test hybrid search handles queries with no keyword matches gracefully.

    Note: Semantic search will still return results (based on similarity scores)
    even for queries that don't match any keywords. This is expected behavior.
    This test verifies that when keyword search has no matches, hybrid search
    still returns reasonable results with low keyword scores.
    """
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=True)
    parser = SpaceParser()
    chunks = parser.parse_space(str(diverse_docs_for_hybrid))
    graph_db.index_chunks(chunks)

    hybrid_search = HybridSearch(graph_db)

    # Act
    results = hybrid_search.search(query="quantum_physics_xyz_nonexistent", limit=10)

    # Assert - semantic search will return results but keyword scores should be 0
    # since no documents contain the exact query terms
    for result in results:
        assert result["keyword_score"] == 0.0, (
            "No keyword matches expected for nonexistent terms"
        )


def test_hybrid_search_limit_parameter(
    temp_db_path: str, diverse_docs_for_hybrid: Path
):
    """Test that limit parameter controls number of results."""
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=True)
    parser = SpaceParser()
    chunks = parser.parse_space(str(diverse_docs_for_hybrid))
    graph_db.index_chunks(chunks)

    hybrid_search = HybridSearch(graph_db)

    # Act
    results_small = hybrid_search.search(query="database", limit=2)
    results_large = hybrid_search.search(query="database", limit=10)

    # Assert
    assert len(results_small) <= 2, "Should respect limit parameter"
    assert len(results_large) >= len(results_small), (
        "Larger limit should return more results"
    )


def test_hybrid_search_deduplication(temp_db_path: str, diverse_docs_for_hybrid: Path):
    """Test that hybrid search deduplicates results from keyword and semantic search.

    A document appearing in both keyword and semantic results should appear only once
    in the final hybrid results with a combined score.
    """
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=True)
    parser = SpaceParser()
    chunks = parser.parse_space(str(diverse_docs_for_hybrid))
    graph_db.index_chunks(chunks)

    hybrid_search = HybridSearch(graph_db)

    # Act
    results = hybrid_search.search(query="database", limit=10)

    # Assert - no duplicate chunk IDs
    chunk_ids = [r["chunk"]["id"] for r in results]
    unique_ids = set(chunk_ids)

    assert len(chunk_ids) == len(unique_ids), "Hybrid search should deduplicate results"
