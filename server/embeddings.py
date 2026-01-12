"""
Embedding service for generating vector embeddings using OpenAI.
"""

import os
import re
from typing import List, Optional
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating embeddings using OpenAI API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        Initialize the embedding service.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Embedding model to use (defaults to EMBEDDING_MODEL env var)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

        if not self.api_key:
            raise ValueError(
                "OpenAI API key not provided. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.client = OpenAI(api_key=self.api_key)
        logger.info(f"Initialized EmbeddingService with model: {self.model}")

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
            # Return a zero vector of the expected dimension (1536 for text-embedding-3-small)
            return [0.0] * 1536

        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text
            )
            embedding = response.data[0].embedding
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

        if not valid_texts:
            logger.warning("All texts were empty, returning zero vectors")
            return [[0.0] * 1536] * len(texts)

        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=valid_texts
            )

            # Create result list with zero vectors for empty texts
            embeddings = [[0.0] * 1536] * len(texts)
            for i, data in enumerate(response.data):
                original_index = valid_indices[i]
                embeddings[original_index] = data.embedding

            logger.info(f"Generated {len(valid_texts)} embeddings in batch")
            return embeddings
        except Exception as e:
            logger.error(f"Failed to generate embeddings in batch: {e}")
            raise

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings for the current model.

        Returns:
            Embedding dimension (e.g., 1536 for text-embedding-3-small)
        """
        # text-embedding-3-small and text-embedding-3-large both use 1536 by default
        # text-embedding-ada-002 uses 1536
        return 1536
