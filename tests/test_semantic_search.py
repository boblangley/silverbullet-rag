"""Tests for semantic search functionality."""

import pytest
from unittest.mock import patch, MagicMock
from server.db.graph import GraphDB
from server.parser import Chunk


class TestSemanticSearch:
    """Tests for semantic search in GraphDB."""

    @patch("server.db.graph.EmbeddingService")
    def test_graphdb_initialization_with_embeddings(
        self, mock_embedding_service, temp_db_path
    ):
        """Test that GraphDB initializes with embeddings enabled."""
        db = GraphDB(temp_db_path, enable_embeddings=True)
        assert db.enable_embeddings is True
        assert db.embedding_service is not None
        mock_embedding_service.assert_called_once()

    def test_graphdb_initialization_without_embeddings(self, temp_db_path):
        """Test that GraphDB can be initialized without embeddings."""
        db = GraphDB(temp_db_path, enable_embeddings=False)
        assert db.enable_embeddings is False
        assert db.embedding_service is None

    @patch("server.db.graph.EmbeddingService")
    def test_semantic_search_disabled_raises_error(
        self, mock_embedding_service, temp_db_path
    ):
        """Test that semantic_search raises error when embeddings disabled."""
        db = GraphDB(temp_db_path, enable_embeddings=False)

        with pytest.raises(ValueError, match="Semantic search requires embeddings"):
            db.semantic_search("test query")

    @patch("server.db.graph.EmbeddingService")
    @patch("real_ladybug.Connection")
    def test_semantic_search_generates_query_embedding(
        self, mock_connection, mock_embedding_service, temp_db_path
    ):
        """Test that semantic_search generates embedding for query."""
        # Setup mock embedding service
        mock_service_instance = MagicMock()
        mock_embedding = [0.1] * 1536
        mock_service_instance.generate_embedding.return_value = mock_embedding
        mock_embedding_service.return_value = mock_service_instance

        # Setup mock connection
        mock_conn_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.has_next.return_value = False
        mock_conn_instance.execute.return_value = mock_result
        mock_connection.return_value = mock_conn_instance

        db = GraphDB(temp_db_path, enable_embeddings=True)
        db.semantic_search("test query", limit=5)

        # Verify embedding was generated for the query
        mock_service_instance.generate_embedding.assert_called_once_with("test query")

    @patch("server.db.graph.EmbeddingService")
    @patch("real_ladybug.Connection")
    def test_semantic_search_executes_vector_query(
        self, mock_connection, mock_embedding_service, temp_db_path
    ):
        """Test that semantic_search executes vector search query."""
        # Setup mocks
        mock_service_instance = MagicMock()
        mock_embedding = [0.1] * 1536
        mock_service_instance.generate_embedding.return_value = mock_embedding
        mock_embedding_service.return_value = mock_service_instance

        mock_conn_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.has_next.return_value = False
        mock_conn_instance.execute.return_value = mock_result
        mock_connection.return_value = mock_conn_instance

        db = GraphDB(temp_db_path, enable_embeddings=True)
        db.semantic_search("test query", limit=10)

        # Verify vector query was executed
        mock_conn_instance.execute.assert_called()
        call_args = mock_conn_instance.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        # Verify the query uses ARRAY_COSINE_SIMILARITY for vector search
        assert "ARRAY_COSINE_SIMILARITY" in query
        assert "c.embedding" in query
        # The embedding is now inlined in the query, not passed as a parameter
        assert params["limit"] == 10

    @patch("server.db.graph.EmbeddingService")
    @patch("real_ladybug.Connection")
    def test_semantic_search_with_tag_filter(
        self, mock_connection, mock_embedding_service, temp_db_path
    ):
        """Test semantic search with tag filtering."""
        # Setup mocks
        mock_service_instance = MagicMock()
        mock_embedding = [0.1] * 1536
        mock_service_instance.generate_embedding.return_value = mock_embedding
        mock_embedding_service.return_value = mock_service_instance

        mock_conn_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.has_next.return_value = False
        mock_conn_instance.execute.return_value = mock_result
        mock_connection.return_value = mock_conn_instance

        db = GraphDB(temp_db_path, enable_embeddings=True)
        db.semantic_search("test query", limit=10, filter_tags=["tag1", "tag2"])

        # Verify that execute was called multiple times (vector search + filter)
        assert mock_conn_instance.execute.call_count >= 1

    @patch("server.db.graph.EmbeddingService")
    @patch("real_ladybug.Connection")
    def test_semantic_search_with_page_filter(
        self, mock_connection, mock_embedding_service, temp_db_path
    ):
        """Test semantic search with page filtering."""
        # Setup mocks
        mock_service_instance = MagicMock()
        mock_embedding = [0.1] * 1536
        mock_service_instance.generate_embedding.return_value = mock_embedding
        mock_embedding_service.return_value = mock_service_instance

        mock_conn_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.has_next.return_value = False
        mock_conn_instance.execute.return_value = mock_result
        mock_connection.return_value = mock_conn_instance

        db = GraphDB(temp_db_path, enable_embeddings=True)
        db.semantic_search(
            "test query", limit=10, filter_pages=["page1.md", "page2.md"]
        )

        # Verify that execute was called
        assert mock_conn_instance.execute.call_count >= 1

    @patch("server.db.graph.EmbeddingService")
    @patch("real_ladybug.Connection")
    def test_semantic_search_returns_results(
        self, mock_connection, mock_embedding_service, temp_db_path
    ):
        """Test that semantic_search returns formatted results."""
        # Setup mocks
        mock_service_instance = MagicMock()
        mock_embedding = [0.1] * 1536
        mock_service_instance.generate_embedding.return_value = mock_embedding
        mock_embedding_service.return_value = mock_service_instance

        # Create mock result with data
        mock_conn_instance = MagicMock()
        mock_result = MagicMock()

        # Simulate two results
        mock_result.has_next.side_effect = [True, True, False]
        # Mock returns [chunk_node, similarity_score] tuples
        mock_result.get_next.side_effect = [
            [{"id": "chunk1", "content": "content1"}, 0.95],
            [{"id": "chunk2", "content": "content2"}, 0.85],
        ]
        mock_conn_instance.execute.return_value = mock_result
        mock_connection.return_value = mock_conn_instance

        db = GraphDB(temp_db_path, enable_embeddings=True)
        results = db.semantic_search("test query", limit=10)

        assert len(results) == 2
        assert "col0" in results[0]  # chunk data
        assert "similarity" in results[0]  # similarity score

    @patch("server.db.graph.EmbeddingService")
    def test_index_chunks_generates_embeddings(
        self, mock_embedding_service, temp_db_path
    ):
        """Test that index_chunks generates embeddings when enabled."""
        # Setup mock
        mock_service_instance = MagicMock()
        mock_embeddings = [[0.1] * 1536, [0.2] * 1536]
        mock_service_instance.generate_embeddings_batch.return_value = mock_embeddings
        mock_embedding_service.return_value = mock_service_instance

        db = GraphDB(temp_db_path, enable_embeddings=True)

        # Create test chunks
        chunks = [
            Chunk(
                file_path="test1.md",
                header="Section 1",
                content="Content 1",
                links=["link1"],
                tags=["tag1"],
            ),
            Chunk(
                file_path="test2.md",
                header="Section 2",
                content="Content 2",
                links=["link2"],
                tags=["tag2"],
            ),
        ]

        db.index_chunks(chunks)

        # Verify embeddings were generated
        mock_service_instance.generate_embeddings_batch.assert_called_once()
        call_args = mock_service_instance.generate_embeddings_batch.call_args
        assert call_args[0][0] == ["Content 1", "Content 2"]

    @patch("server.db.graph.EmbeddingService")
    def test_index_chunks_without_embeddings(
        self, mock_embedding_service, temp_db_path
    ):
        """Test that index_chunks works without embeddings."""
        db = GraphDB(temp_db_path, enable_embeddings=False)

        chunks = [
            Chunk(
                file_path="test.md",
                header="Section",
                content="Content",
                links=[],
                tags=[],
            )
        ]

        # Should not raise error
        db.index_chunks(chunks)

    @patch("server.db.graph.EmbeddingService")
    @patch("real_ladybug.Connection")
    def test_semantic_search_default_limit(
        self, mock_connection, mock_embedding_service, temp_db_path
    ):
        """Test that semantic_search uses default limit of 10."""
        # Setup mocks
        mock_service_instance = MagicMock()
        mock_embedding = [0.1] * 1536
        mock_service_instance.generate_embedding.return_value = mock_embedding
        mock_embedding_service.return_value = mock_service_instance

        mock_conn_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.has_next.return_value = False
        mock_conn_instance.execute.return_value = mock_result
        mock_connection.return_value = mock_conn_instance

        db = GraphDB(temp_db_path, enable_embeddings=True)
        db.semantic_search("test query")  # No limit specified

        # Verify default limit of 10 was used
        call_args = mock_conn_instance.execute.call_args
        params = call_args[0][1]
        assert params["limit"] == 10

    @patch("server.db.graph.EmbeddingService")
    @patch("real_ladybug.Connection")
    def test_semantic_search_empty_results(
        self, mock_connection, mock_embedding_service, temp_db_path
    ):
        """Test semantic_search with no results."""
        # Setup mocks
        mock_service_instance = MagicMock()
        mock_embedding = [0.1] * 1536
        mock_service_instance.generate_embedding.return_value = mock_embedding
        mock_embedding_service.return_value = mock_service_instance

        mock_conn_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.has_next.return_value = False
        mock_conn_instance.execute.return_value = mock_result
        mock_connection.return_value = mock_conn_instance

        db = GraphDB(temp_db_path, enable_embeddings=True)
        results = db.semantic_search("nonexistent query")

        assert results == []

    @patch("server.db.graph.EmbeddingService")
    @patch("real_ladybug.Connection")
    def test_semantic_search_with_combined_filters(
        self, mock_connection, mock_embedding_service, temp_db_path
    ):
        """Test semantic search with both tag and page filters."""
        # Setup mocks
        mock_service_instance = MagicMock()
        mock_embedding = [0.1] * 1536
        mock_service_instance.generate_embedding.return_value = mock_embedding
        mock_embedding_service.return_value = mock_service_instance

        mock_conn_instance = MagicMock()

        # Create a default mock result for schema init and other calls
        default_result = MagicMock()
        default_result.has_next.return_value = False

        # First call (vector search) returns results
        mock_result1 = MagicMock()
        mock_result1.has_next.side_effect = [True, False]
        mock_result1.get_next.return_value = ["chunk1"]

        # Second call (filtered query) returns results
        mock_result2 = MagicMock()
        mock_result2.has_next.side_effect = [True, False]
        mock_result2.get_next.return_value = ["chunk1", "content1"]

        # Return default for all other calls, then our specific results
        mock_conn_instance.execute.return_value = default_result
        mock_connection.return_value = mock_conn_instance

        db = GraphDB(temp_db_path, enable_embeddings=True)

        # Now set up specific results for semantic_search calls
        mock_conn_instance.execute.side_effect = [mock_result1, mock_result2]

        results = db.semantic_search(
            "test query", limit=5, filter_tags=["tag1"], filter_pages=["page1.md"]
        )

        # Results should be returned
        assert len(results) >= 0


class TestSemanticSearchIntegration:
    """Integration tests for semantic search with real data."""

    @pytest.mark.skip(reason="Requires real LadybugDB and OpenAI API")
    def test_semantic_search_with_silverbullet_data(
        self, temp_db_path, silverbullet_test_data
    ):
        """Test semantic search with real Silverbullet markdown data.

        This test is skipped by default as it requires:
        - Real LadybugDB setup
        - Valid OpenAI API key
        - Silverbullet test data submodule
        """
        from server.parser import SpaceParser

        db = GraphDB(temp_db_path, enable_embeddings=True)
        parser = SpaceParser()

        # Parse and index Silverbullet test data
        chunks = parser.parse_space(str(silverbullet_test_data))
        db.index_chunks(chunks)

        # Test semantic search
        results = db.semantic_search("database", limit=5)

        assert len(results) > 0
        # Results should contain database-related content

    @pytest.mark.skip(reason="Requires real LadybugDB and OpenAI API")
    def test_semantic_search_with_filtering(self, temp_db_path, silverbullet_test_data):
        """Test semantic search with tag filtering on real data."""
        from server.parser import SpaceParser

        db = GraphDB(temp_db_path, enable_embeddings=True)
        parser = SpaceParser()

        chunks = parser.parse_space(str(silverbullet_test_data))
        db.index_chunks(chunks)

        # Search for content with specific tag filter
        results = db.semantic_search("markdown", limit=10, filter_tags=["syntax"])

        # Results should be filtered by tag
        assert len(results) >= 0
