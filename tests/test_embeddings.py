"""Tests for the embedding service."""

import os
import pytest
from server.embeddings import EmbeddingService


# Skip OpenAI tests unless RUN_OPENAI_TESTS=true or a real API key is present
def has_openai_access():
    """Check if we should run OpenAI integration tests."""
    if os.getenv("RUN_OPENAI_TESTS", "").lower() == "true":
        return True
    # Check if API key looks real (not a test key)
    api_key = os.getenv("OPENAI_API_KEY", "")
    return api_key.startswith("sk-") and len(api_key) > 20


requires_openai = pytest.mark.skipif(
    not has_openai_access(),
    reason="OpenAI tests skipped. Set RUN_OPENAI_TESTS=true to run.",
)


class TestEmbeddingServiceLocal:
    """Tests for EmbeddingService with local fastembed provider."""

    def test_initialization_with_local_provider(self):
        """Test that EmbeddingService initializes with local provider."""
        service = EmbeddingService()
        assert service.provider_name == "local"
        assert service.model == "BAAI/bge-small-en-v1.5"

    def test_get_embedding_dimension_local(self):
        """Test that local provider returns correct dimension."""
        service = EmbeddingService()
        assert service.get_embedding_dimension() == 384

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

    def test_generate_embedding_success(self):
        """Test successful embedding generation with local provider."""
        service = EmbeddingService()
        result = service.generate_embedding("test content")

        assert len(result) == 384  # bge-small dimension
        assert all(isinstance(x, float) for x in result)

    def test_generate_embedding_with_cleaning(self):
        """Test that generate_embedding cleans content by default."""
        service = EmbeddingService()
        text = "Content with [[wikilink]] and #tag"
        result = service.generate_embedding(text, clean=True)

        assert len(result) == 384
        # Can't easily verify cleaning happened, but embedding should work

    def test_generate_embedding_empty_text(self):
        """Test that empty text returns zero vector."""
        service = EmbeddingService()
        result = service.generate_embedding("")

        assert len(result) == 384
        assert all(x == 0.0 for x in result)

    def test_generate_embeddings_batch_success(self):
        """Test batch embedding generation."""
        service = EmbeddingService()
        texts = ["text 1", "text 2", "text 3"]
        results = service.generate_embeddings_batch(texts)

        assert len(results) == 3
        for result in results:
            assert len(result) == 384

    def test_generate_embeddings_batch_with_empty_texts(self):
        """Test batch generation with some empty texts."""
        service = EmbeddingService()
        texts = ["", "text 2", ""]
        results = service.generate_embeddings_batch(texts)

        assert len(results) == 3
        # First and third should be zero vectors
        assert all(x == 0.0 for x in results[0])
        assert all(x == 0.0 for x in results[2])
        # Second should have real embedding
        assert len(results[1]) == 384
        assert not all(x == 0.0 for x in results[1])

    def test_generate_embeddings_batch_all_empty(self):
        """Test batch generation with all empty texts."""
        service = EmbeddingService()
        texts = ["", "", ""]
        results = service.generate_embeddings_batch(texts)

        assert len(results) == 3
        for result in results:
            assert len(result) == 384
            assert all(x == 0.0 for x in result)

    def test_silverbullet_syntax_cleaning_comprehensive(self):
        """Test comprehensive Silverbullet syntax cleaning."""
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
        cleaned = service.clean_content(text)

        assert "[[" not in cleaned
        assert "]]" not in cleaned
        assert "---" not in cleaned
        assert "@mentions" not in cleaned
        # But content words should remain
        assert "Main Header" in cleaned
        assert "content" in cleaned


@requires_openai
class TestEmbeddingServiceOpenAI:
    """Tests for EmbeddingService with OpenAI provider.

    These tests only run when RUN_OPENAI_TESTS=true is set (e.g., in CI).
    """

    def test_initialization_with_openai_provider(self, monkeypatch):
        """Test that EmbeddingService initializes with OpenAI provider."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        service = EmbeddingService()
        assert service.provider_name == "openai"
        assert service.model == "text-embedding-3-small"

    def test_get_embedding_dimension_openai(self, monkeypatch):
        """Test that OpenAI provider returns correct dimension."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        service = EmbeddingService()
        assert service.get_embedding_dimension() == 1536

    def test_generate_embedding_openai(self, monkeypatch):
        """Test embedding generation with real OpenAI API."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        service = EmbeddingService()
        result = service.generate_embedding("test content")

        assert len(result) == 1536
        assert all(isinstance(x, float) for x in result)

    def test_generate_embeddings_batch_openai(self, monkeypatch):
        """Test batch embedding with real OpenAI API."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        service = EmbeddingService()
        texts = ["text 1", "text 2"]
        results = service.generate_embeddings_batch(texts)

        assert len(results) == 2
        for result in results:
            assert len(result) == 1536


class TestEmbeddingServiceErrors:
    """Test error handling in EmbeddingService."""

    def test_initialization_without_api_key_for_openai(self, monkeypatch):
        """Test that initialization fails without API key when using OpenAI."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="OpenAI API key not provided"):
            EmbeddingService()

    def test_invalid_provider(self, monkeypatch):
        """Test that invalid provider raises error."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "invalid_provider")
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            EmbeddingService()
