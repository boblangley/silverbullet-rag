"""Tests for BM25 ranking in keyword search."""

import pytest
from pathlib import Path
from server.db.graph import GraphDB
from server.parser.space_parser import SpaceParser


@pytest.fixture
def sample_docs_for_bm25(temp_space_path: str) -> Path:
    """Create sample documents with varying term frequencies for BM25 testing.

    Args:
        temp_space_path: Temporary space directory

    Returns:
        Path to the temporary space directory
    """
    space = Path(temp_space_path)

    # Document 1: High frequency of "database" keyword
    doc1 = space / "database_tutorial.md"
    doc1.write_text(
        """# Database Tutorial
tags: #database #sql

## Introduction to Databases

A database is a structured collection of data. Databases are used everywhere.
The database management system helps you work with databases. Modern databases
provide many features. This tutorial covers database fundamentals.

## Types of Databases

Relational databases, NoSQL databases, graph databases - all are databases.
"""
    )

    # Document 2: Single mention of "database" but with relevant tag
    doc2 = space / "graph_systems.md"
    doc2.write_text(
        """# Graph Systems
tags: #database #graph #networking

## Overview

Graph-based systems use nodes and edges. A database can store graph data efficiently.
"""
    )

    # Document 3: Multiple mentions but in different context (noise)
    doc3 = space / "software_architecture.md"
    doc3.write_text(
        """# Software Architecture
tags: #architecture #design

## System Design

When designing systems, consider the architecture patterns. The architecture should
be scalable. Good architecture principles lead to maintainable systems.
"""
    )

    # Document 4: Technical terms related to search query
    doc4 = space / "database_optimization.md"
    doc4.write_text(
        """# Database Optimization
tags: #database #performance #optimization

## Performance Tuning

Optimizing database queries is critical. Use indexes, query optimization,
and proper database schema design for best performance.
"""
    )

    return space


def test_bm25_ranking_basic(temp_db_path: str, sample_docs_for_bm25: Path):
    """Test that BM25 ranking is applied to keyword search results.

    This test verifies that:
    1. Results are returned with BM25 scores
    2. Results are sorted by relevance (highest score first)
    3. Documents with higher term frequency get higher scores
    """
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=False)
    parser = SpaceParser()
    chunks = parser.parse_space(str(sample_docs_for_bm25))
    graph_db.index_chunks(chunks)

    # Act
    results = graph_db.keyword_search("database")

    # Assert
    assert len(results) > 0, "Should return results for 'database' query"

    # Check that results have BM25 scores
    for result in results:
        assert "bm25_score" in result, "Each result should have a BM25 score"
        assert isinstance(
            result["bm25_score"], (int, float)
        ), "BM25 score should be numeric"

    # Check that results are sorted by score (descending)
    scores = [r["bm25_score"] for r in results]
    assert scores == sorted(
        scores, reverse=True
    ), "Results should be sorted by BM25 score (highest first)"

    # Document with highest frequency should rank higher than single mention
    top_result = results[0]
    assert "database_tutorial" in top_result.get("col0", {}).get(
        "file_path", ""
    ), "Document with highest term frequency should rank first"


def test_bm25_tag_weighting(temp_db_path: str, sample_docs_for_bm25: Path):
    """Test that documents with matching tags get boosted in ranking.

    According to spec: "Tags are good keywords" - they should be weighted higher.
    """
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=False)
    parser = SpaceParser()
    chunks = parser.parse_space(str(sample_docs_for_bm25))
    graph_db.index_chunks(chunks)

    # Act - search for a term that appears in tags
    results = graph_db.keyword_search("optimization")

    # Assert
    assert len(results) > 0, "Should return results for 'optimization' query"

    # Document with "optimization" in tags should rank highly
    top_results_content = [r.get("col0", {}).get("file_path", "") for r in results[:2]]
    assert any(
        "database_optimization" in path for path in top_results_content
    ), "Document with matching tag should be in top results"


def test_bm25_technical_term_weighting(temp_db_path: str, sample_docs_for_bm25: Path):
    """Test that technical terms are weighted appropriately.

    According to spec: "Also technical terms" should have higher weight.
    Technical terms include: SQL, NoSQL, indexes, queries, schema, etc.
    """
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=False)
    parser = SpaceParser()
    chunks = parser.parse_space(str(sample_docs_for_bm25))
    graph_db.index_chunks(chunks)

    # Act - search for technical term
    results = graph_db.keyword_search("indexes")

    # Assert
    assert len(results) > 0, "Should return results for technical term 'indexes'"

    # Document mentioning the technical term should rank appropriately
    assert "bm25_score" in results[0], "Results should include BM25 scores"


def test_bm25_empty_results(temp_db_path: str, sample_docs_for_bm25: Path):
    """Test that BM25 search handles empty results gracefully."""
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=False)
    parser = SpaceParser()
    chunks = parser.parse_space(str(sample_docs_for_bm25))
    graph_db.index_chunks(chunks)

    # Act
    results = graph_db.keyword_search("nonexistent_term_xyz")

    # Assert
    assert len(results) == 0, "Should return empty list for non-matching query"


def test_bm25_multi_term_query(temp_db_path: str, sample_docs_for_bm25: Path):
    """Test BM25 ranking with multi-word queries."""
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=False)
    parser = SpaceParser()
    chunks = parser.parse_space(str(sample_docs_for_bm25))
    graph_db.index_chunks(chunks)

    # Act
    results = graph_db.keyword_search("database optimization")

    # Assert
    assert len(results) > 0, "Should return results for multi-word query"

    # Document matching both terms should rank highest
    top_result = results[0]
    top_path = top_result.get("col0", {}).get("file_path", "")
    assert (
        "database_optimization" in top_path
    ), "Document matching both query terms should rank first"


def test_bm25_scoring_consistency(temp_db_path: str, sample_docs_for_bm25: Path):
    """Test that BM25 scores are consistent across multiple searches."""
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=False)
    parser = SpaceParser()
    chunks = parser.parse_space(str(sample_docs_for_bm25))
    graph_db.index_chunks(chunks)

    # Act - perform same search twice
    results1 = graph_db.keyword_search("database")
    results2 = graph_db.keyword_search("database")

    # Assert
    assert len(results1) == len(
        results2
    ), "Same query should return same number of results"

    for r1, r2 in zip(results1, results2):
        assert (
            r1["bm25_score"] == r2["bm25_score"]
        ), "BM25 scores should be consistent across identical searches"


def test_bm25_score_normalization(temp_db_path: str, sample_docs_for_bm25: Path):
    """Test that BM25 scores are properly normalized and reasonable."""
    # Arrange
    graph_db = GraphDB(temp_db_path, enable_embeddings=False)
    parser = SpaceParser()
    chunks = parser.parse_space(str(sample_docs_for_bm25))
    graph_db.index_chunks(chunks)

    # Act
    results = graph_db.keyword_search("database")

    # Assert
    for result in results:
        score = result["bm25_score"]
        assert score >= 0, "BM25 scores should be non-negative"
        assert (
            score < 1000
        ), "BM25 scores should be reasonable (< 1000 for typical documents)"
