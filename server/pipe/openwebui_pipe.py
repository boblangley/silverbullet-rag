"""
title: Silverbullet RAG Pipe
author: Your Name
author_url: https://github.com/yourusername
version: 0.1.0
"""

from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import os

from ..db import GraphDB
from ..parser import SpaceParser


class Pipe:
    """Open WebUI Pipe for Silverbullet RAG."""

    class Valves(BaseModel):
        """Configuration valves for the pipe."""

        DB_PATH: str = "/db"
        SPACE_PATH: str = "/space"
        MAX_RESULTS: int = 5
        pass

    def __init__(self):
        self.type = "filter"
        self.name = "Silverbullet RAG"
        self.valves = self.Valves()
        self.graph_db = None
        self.parser = None

    def _ensure_initialized(self):
        """Lazy initialization of database connection."""
        if self.graph_db is None:
            self.graph_db = GraphDB(self.valves.DB_PATH)
            self.parser = SpaceParser()

    def pipes(self) -> List[dict]:
        """Return list of available pipes."""
        return [{"id": "silverbullet_rag", "name": "Silverbullet RAG"}]

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        """Process messages and inject RAG context.

        Args:
            user_message: The latest user message
            model_id: Selected model ID
            messages: Full conversation history
            body: Request body

        Returns:
            Modified messages with RAG context injected
        """
        self._ensure_initialized()

        # Extract keywords from user message
        # Simple keyword extraction - can be enhanced
        keywords = self._extract_keywords(user_message)

        if not keywords:
            # No relevant keywords, pass through
            return body

        # Search the knowledge graph
        context_chunks = []
        for keyword in keywords[:3]:  # Limit to top 3 keywords
            try:
                results = self.graph_db.keyword_search(keyword)
                context_chunks.extend(results[: self.valves.MAX_RESULTS])
            except Exception as e:
                print(f"Search error for '{keyword}': {e}")

        if not context_chunks:
            return body

        # Build context message
        context_text = self._build_context(context_chunks)

        # Inject context into messages
        system_message = {
            "role": "system",
            "content": f"""You have access to the user's Silverbullet knowledge base. Here is relevant context for the current query:

{context_text}

Use this information to provide more informed and personalized responses. Reference specific pages or notes when relevant.""",
        }

        # Insert system message before the last user message
        modified_messages = messages[:-1] + [system_message] + [messages[-1]]
        body["messages"] = modified_messages

        return body

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract potential keywords from text.

        Args:
            text: Input text

        Returns:
            List of keywords
        """
        # Simple word extraction - filter common words
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
            "are",
            "were",
            "been",
            "be",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "what",
            "when",
            "where",
            "who",
            "why",
            "how",
            "this",
            "that",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "me",
            "him",
            "her",
            "us",
            "them",
        }

        words = text.lower().split()
        keywords = [
            word.strip(".,!?;:")
            for word in words
            if len(word) > 3 and word.lower() not in stopwords
        ]

        return keywords[:10]  # Limit to top 10

    def _build_context(self, chunks: List[dict]) -> str:
        """Build context text from chunks.

        Args:
            chunks: List of chunk dictionaries

        Returns:
            Formatted context string
        """
        if not chunks:
            return ""

        context_parts = []
        seen_sources = set()

        for chunk in chunks:
            # Extract relevant fields (depends on cypher query result structure)
            content = chunk.get("content", chunk.get("col0", ""))
            if isinstance(content, dict):
                content = content.get("content", str(content))

            header = chunk.get("header", chunk.get("col1", "Unknown"))
            if isinstance(header, dict):
                header = header.get("header", str(header))

            file_path = chunk.get("file_path", chunk.get("col2", ""))
            if isinstance(file_path, dict):
                file_path = file_path.get("file_path", str(file_path))

            source = f"{file_path}#{header}"
            if source not in seen_sources:
                seen_sources.add(source)
                context_parts.append(f"## {header}\n{content}\n\nSource: {file_path}")

        return "\n\n---\n\n".join(context_parts[: self.valves.MAX_RESULTS])
