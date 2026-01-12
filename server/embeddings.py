"""
Embedding service for generating vector embeddings.

Supports multiple providers:
- openai: OpenAI API (text-embedding-3-small, etc.)
- local: Local models via fastembed (BAAI/bge-small-en-v1.5, etc.)
"""

import os
import re
from typing import List, Optional, Literal
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

# Type alias for supported providers
EmbeddingProvider = Literal["openai", "local"]


class BaseEmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        pass

    @abstractmethod
    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """Get the embedding dimension."""
        pass


class OpenAIProvider(BaseEmbeddingProvider):
    """OpenAI API embedding provider."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self._dimension = 1536  # Default for text-embedding-3-small
        logger.info(f"Initialized OpenAI provider with model: {model}")

    def generate_embedding(self, text: str) -> List[float]:
        response = self.client.embeddings.create(model=self.model, input=text)
        return response.data[0].embedding

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [data.embedding for data in response.data]

    def get_dimension(self) -> int:
        return self._dimension


class LocalProvider(BaseEmbeddingProvider):
    """Local embedding provider using fastembed."""

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        try:
            from fastembed import TextEmbedding
        except ImportError:
            raise ImportError(
                "fastembed is required for local embeddings. "
                "Install with: pip install fastembed"
            )
        self.model_name = model
        self.model = TextEmbedding(model_name=model)
        # bge-small-en-v1.5 has 384 dimensions
        self._dimension = 384
        logger.info(f"Initialized local provider with model: {model}")

    def generate_embedding(self, text: str) -> List[float]:
        embeddings = list(self.model.embed([text]))
        return embeddings[0].tolist()

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        embeddings = list(self.model.embed(texts))
        return [emb.tolist() for emb in embeddings]

    def get_dimension(self) -> int:
        return self._dimension


class EmbeddingService:
    """Service for generating embeddings using configurable providers."""

    def __init__(
        self,
        provider: Optional[EmbeddingProvider] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        Initialize the embedding service.

        Args:
            provider: Embedding provider ("openai" or "local").
                      Defaults to EMBEDDING_PROVIDER env var or "openai".
            api_key: OpenAI API key (only needed for openai provider).
                     Defaults to OPENAI_API_KEY env var.
            model: Model to use. Defaults to EMBEDDING_MODEL env var or provider default.
        """
        provider = provider or os.getenv("EMBEDDING_PROVIDER", "openai")
        self.provider_name = provider

        if provider == "openai":
            api_key = api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "OpenAI API key not provided. Set OPENAI_API_KEY environment variable "
                    "or pass api_key parameter."
                )
            model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
            self._provider = OpenAIProvider(api_key=api_key, model=model)

        elif provider == "local":
            model = model or os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
            self._provider = LocalProvider(model=model)

        else:
            raise ValueError(f"Unknown embedding provider: {provider}")

        self.model = model
        logger.info(f"Initialized EmbeddingService with provider: {provider}, model: {model}")

    def clean_content(self, text: str) -> str:
        """
        Clean Silverbullet syntax noise from content before embedding.

        Removes:
        - Silverbullet attributes: #tag, @mention, etc.
        - Wikilinks: [[page]] or [[page|alias]]
        - Front matter delimiters
        - Excessive whitespace

        Args:
            text: Raw markdown content

        Returns:
            Cleaned text suitable for embedding
        """
        # Remove front matter delimiters
        text = re.sub(r'^---\s*$', '', text, flags=re.MULTILINE)

        # Convert wikilinks to plain text (keep the display text)
        # [[page|alias]] -> alias
        # [[page]] -> page
        text = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', text)
        text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)

        # Remove Silverbullet attributes (tags, mentions, etc.)
        # Keep the text but remove the special syntax
        text = re.sub(r'#(\w+)', r'\1', text)  # #tag -> tag
        text = re.sub(r'@(\w+)', r'\1', text)  # @mention -> mention

        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Multiple newlines -> double newline
        text = re.sub(r' +', ' ', text)  # Multiple spaces -> single space
        text = text.strip()

        return text

    def generate_embedding(self, text: str, clean: bool = True) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            clean: Whether to clean Silverbullet syntax first (default: True)

        Returns:
            Embedding vector as list of floats
        """
        if clean:
            text = self.clean_content(text)

        if not text or not text.strip():
            logger.warning("Attempted to embed empty text, returning zero vector")
            return [0.0] * self._provider.get_dimension()

        try:
            embedding = self._provider.generate_embedding(text)
            logger.debug(f"Generated embedding with dimension: {len(embedding)}")
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    def generate_embeddings_batch(
        self,
        texts: List[str],
        clean: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in a batch.

        Args:
            texts: List of texts to embed
            clean: Whether to clean Silverbullet syntax first (default: True)

        Returns:
            List of embedding vectors
        """
        if clean:
            texts = [self.clean_content(text) for text in texts]

        # Filter out empty texts but keep track of indices
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)

        dimension = self._provider.get_dimension()

        if not valid_texts:
            logger.warning("All texts were empty, returning zero vectors")
            return [[0.0] * dimension] * len(texts)

        try:
            valid_embeddings = self._provider.generate_embeddings_batch(valid_texts)

            # Create result list with zero vectors for empty texts
            embeddings = [[0.0] * dimension] * len(texts)
            for i, embedding in enumerate(valid_embeddings):
                original_index = valid_indices[i]
                embeddings[original_index] = embedding

            logger.info(f"Generated {len(valid_texts)} embeddings in batch")
            return embeddings
        except Exception as e:
            logger.error(f"Failed to generate embeddings in batch: {e}")
            raise

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings for the current model.

        Returns:
            Embedding dimension (e.g., 1536 for OpenAI, 384 for bge-small)
        """
        return self._provider.get_dimension()
