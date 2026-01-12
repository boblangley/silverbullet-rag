"""Tests for the embedding service."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from server.embeddings import EmbeddingService


class TestEmbeddingService:
    """Tests for EmbeddingService class."""

    def test_initialization_with_env_vars(self):
        """Test that EmbeddingService initializes with environment variables."""
        service = EmbeddingService()
        assert service.api_key == "test-key-12345"
        assert service.model == "text-embedding-3-small"
        assert service.client is not None

    def test_initialization_with_params(self, monkeypatch):
        """Test that EmbeddingService can be initialized with parameters."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        service = EmbeddingService(api_key="custom-key", model="custom-model")
        assert service.api_key == "custom-key"
        assert service.model == "custom-model"

    def test_initialization_without_api_key(self, monkeypatch):
        """Test that initialization fails without API key."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="OpenAI API key not provided"):
            EmbeddingService()

    def test_clean_content_removes_wikilinks(self):
        """Test that clean_content removes wikilinks correctly."""
        service = EmbeddingService()
        text = "This has [[wikilink]] and [[page|alias]] references."
        cleaned = service.clean_content(text)
        assert "[[" not in cleaned
        assert "]]" not in cleaned
        assert "wikilink" in cleaned
        assert "alias" in cleaned
        assert "page|alias" not in cleaned

    def test_clean_content_removes_tags(self):
        """Test that clean_content handles tags."""
        service = EmbeddingService()
        text = "This has #tag and #another-tag references."
        cleaned = service.clean_content(text)
        assert "#tag" not in cleaned
        assert "tag" in cleaned
        assert "another-tag" in cleaned

    def test_clean_content_removes_mentions(self):
        """Test that clean_content handles mentions."""
        service = EmbeddingService()
        text = "Hello @user and @another."
        cleaned = service.clean_content(text)
        assert "@user" not in cleaned
        assert "user" in cleaned
        assert "another" in cleaned

    def test_clean_content_removes_front_matter(self):
        """Test that clean_content removes front matter delimiters."""
        service = EmbeddingService()
        text = """---
title: Test
---
Content here"""
        cleaned = service.clean_content(text)
        assert "---" not in cleaned
        assert "Content here" in cleaned

    def test_clean_content_normalizes_whitespace(self):
        """Test that clean_content normalizes excessive whitespace."""
        service = EmbeddingService()
        text = "This  has    multiple   spaces\n\n\n\nand newlines"
        cleaned = service.clean_content(text)
        assert "  " not in cleaned  # No double spaces
        assert "\n\n\n" not in cleaned  # No triple newlines

    @patch("server.embeddings.OpenAI")
    def test_generate_embedding_success(self, mock_openai_class):
        """Test successful embedding generation."""
        # Setup mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_embedding = [0.1] * 1536
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        mock_client.embeddings.create.return_value = mock_response

        service = EmbeddingService()
        result = service.generate_embedding("test content")

        assert len(result) == 1536
        assert result == mock_embedding
        mock_client.embeddings.create.assert_called_once()

    @patch("server.embeddings.OpenAI")
    def test_generate_embedding_with_cleaning(self, mock_openai_class):
        """Test that generate_embedding cleans content by default."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_embedding = [0.1] * 1536
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        mock_client.embeddings.create.return_value = mock_response

        service = EmbeddingService()
        text = "Content with [[wikilink]] and #tag"
        result = service.generate_embedding(text, clean=True)

        # Verify the API was called with cleaned text
        call_args = mock_client.embeddings.create.call_args
        assert "[[" not in call_args.kwargs["input"]
        assert "#tag" not in call_args.kwargs["input"]

    @patch("server.embeddings.OpenAI")
    def test_generate_embedding_without_cleaning(self, mock_openai_class):
        """Test that generate_embedding can skip cleaning."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_embedding = [0.1] * 1536
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        mock_client.embeddings.create.return_value = mock_response

        service = EmbeddingService()
        text = "Content with [[wikilink]]"
        result = service.generate_embedding(text, clean=False)

        # Verify the API was called with original text
        call_args = mock_client.embeddings.create.call_args
        assert "[[" in call_args.kwargs["input"]

    @patch("server.embeddings.OpenAI")
    def test_generate_embedding_empty_text(self, mock_openai_class):
        """Test that empty text returns zero vector."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        service = EmbeddingService()
        result = service.generate_embedding("")

        assert len(result) == 1536
        assert all(x == 0.0 for x in result)
        mock_client.embeddings.create.assert_not_called()

    @patch("server.embeddings.OpenAI")
    def test_generate_embeddings_batch_success(self, mock_openai_class):
        """Test batch embedding generation."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_embeddings = [[0.1] * 1536, [0.2] * 1536, [0.3] * 1536]
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=mock_embeddings[0]),
            MagicMock(embedding=mock_embeddings[1]),
            MagicMock(embedding=mock_embeddings[2])
        ]
        mock_client.embeddings.create.return_value = mock_response

        service = EmbeddingService()
        texts = ["text 1", "text 2", "text 3"]
        results = service.generate_embeddings_batch(texts)

        assert len(results) == 3
        assert results[0] == mock_embeddings[0]
        assert results[1] == mock_embeddings[1]
        assert results[2] == mock_embeddings[2]
        mock_client.embeddings.create.assert_called_once()

    @patch("server.embeddings.OpenAI")
    def test_generate_embeddings_batch_with_empty_texts(self, mock_openai_class):
        """Test batch generation with some empty texts."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_embedding = [0.1] * 1536
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        mock_client.embeddings.create.return_value = mock_response

        service = EmbeddingService()
        texts = ["", "text 2", ""]
        results = service.generate_embeddings_batch(texts)

        assert len(results) == 3
        # First and third should be zero vectors
        assert all(x == 0.0 for x in results[0])
        assert all(x == 0.0 for x in results[2])
        # Second should be the actual embedding
        assert results[1] == mock_embedding

    @patch("server.embeddings.OpenAI")
    def test_generate_embeddings_batch_all_empty(self, mock_openai_class):
        """Test batch generation with all empty texts."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        service = EmbeddingService()
        texts = ["", "", ""]
        results = service.generate_embeddings_batch(texts)

        assert len(results) == 3
        for result in results:
            assert len(result) == 1536
            assert all(x == 0.0 for x in result)
        mock_client.embeddings.create.assert_not_called()

    @patch("server.embeddings.OpenAI")
    def test_generate_embedding_api_error(self, mock_openai_class):
        """Test that API errors are propagated."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.embeddings.create.side_effect = Exception("API Error")

        service = EmbeddingService()
        with pytest.raises(Exception, match="API Error"):
            service.generate_embedding("test content")

    def test_get_embedding_dimension(self):
        """Test that get_embedding_dimension returns correct dimension."""
        service = EmbeddingService()
        assert service.get_embedding_dimension() == 1536

    @patch("server.embeddings.OpenAI")
    def test_silverbullet_syntax_cleaning_comprehensive(self, mock_openai_class):
        """Test comprehensive Silverbullet syntax cleaning."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_embedding = [0.1] * 1536
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        mock_client.embeddings.create.return_value = mock_response

        service = EmbeddingService()

        # Complex Silverbullet content
        text = """---
title: Test Page
tags: #tag1, #tag2
---

# Main Header

This is content with [[wikilink]] and [[page|alias]].

It has @mentions and #tags everywhere.

## Section

More [[links]] and #more-tags here.
"""
        result = service.generate_embedding(text)

        # Verify API was called with cleaned text
        call_args = mock_client.embeddings.create.call_args
        cleaned_input = call_args.kwargs["input"]

        assert "[[" not in cleaned_input
        assert "]]" not in cleaned_input
        assert "---" not in cleaned_input
        assert "@mentions" not in cleaned_input
        # But content words should remain
        assert "Main Header" in cleaned_input
        assert "content" in cleaned_input
