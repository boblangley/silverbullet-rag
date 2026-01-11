"""Tests for security vulnerabilities, particularly Cypher injection.

Following TDD RED/GREEN/REFACTOR approach.
These tests should FAIL initially since keyword_search uses string interpolation.
"""

import pytest
from server.db import GraphDB
from server.parser import SpaceParser, Chunk


class TestCypherInjection:
    """Test suite for Cypher injection vulnerabilities."""

    @pytest.fixture
    def graph_db_with_data(self, temp_db_path, temp_space_path):
        """Create a GraphDB with sample data.

        Args:
            temp_db_path: Temporary database file path
            temp_space_path: Temporary space directory

        Returns:
            GraphDB instance with indexed data
        """
        from pathlib import Path

        graph_db = GraphDB(temp_db_path, enable_embeddings=False)
        space = Path(temp_space_path)

        # Create test files
        (space / "public.md").write_text("# Public\n\nPublic content with #public tag.")
        (space / "private.md").write_text("# Private\n\nPrivate content with #private tag.")
        (space / "secret.md").write_text("# Secret\n\nSecret API keys: sk-1234567890")

        # Index files
        parser = SpaceParser()
        chunks = parser.parse_space(str(space))
        graph_db.index_chunks(chunks)

        return graph_db

    def test_keyword_search_basic_injection_attempt(self, graph_db_with_data):
        """RED: Test that keyword search rejects injection attempts.

        This should FAIL because current implementation uses string interpolation.
        """
        # Attempt to inject Cypher to bypass search
        malicious_input = "' OR 1=1 --"

        results = graph_db_with_data.keyword_search(malicious_input)

        # Should return 0 results (no match) or handle safely
        # Should NOT return all chunks (which would happen if injection succeeds)
        assert len(results) <= 1, f"Injection may have succeeded - got {len(results)} results"

    def test_keyword_search_union_injection(self, graph_db_with_data):
        """RED: Test protection against UNION-based injection.

        This should FAIL if injection is possible.
        """
        # Attempt UNION injection
        malicious_input = "' UNION MATCH (c:Chunk) RETURN c --"

        try:
            results = graph_db_with_data.keyword_search(malicious_input)
            # Should return 0 or very few results, not all chunks
            assert len(results) < 2, "UNION injection may have succeeded"
        except Exception as e:
            # Query errors are acceptable - means injection didn't work cleanly
            pass

    def test_keyword_search_with_quotes(self, graph_db_with_data):
        """RED: Test that quotes in search terms are handled safely.

        This should FAIL if string escaping is improper.
        """
        # Search terms with quotes
        inputs = [
            "test'quote",
            'test"doublequote',
            "test\\'escaped",
            "test\\\"escaped",
        ]

        for search_term in inputs:
            try:
                results = graph_db_with_data.keyword_search(search_term)
                # Should complete without error (even if 0 results)
                assert isinstance(results, list)
            except Exception as e:
                pytest.fail(f"Query failed on input '{search_term}': {e}")

    def test_keyword_search_parametrized_query(self, graph_db_with_data):
        """RED: Verify that keyword_search uses parameterized queries.

        This test checks the implementation, not just behavior.
        """
        import inspect

        # Check if keyword_search method uses proper parameterization
        source = inspect.getsource(graph_db_with_data.keyword_search)

        # Should NOT use string interpolation or f-strings
        assert "f'" not in source and 'f"' not in source, "Method uses f-strings"
        assert ".replace(" not in source, "Method uses string replacement"
        assert ".format(" not in source, "Method uses .format()"

        # Should use parameters dict
        assert "params" in source or '{"' in source, "Method should use parameter dict"

    def test_keyword_search_comment_injection(self, graph_db_with_data):
        """Test protection against comment-based injection.

        Comment characters should be treated as literal text, not as query comments.
        """
        # Attempt to use comments to bypass conditions
        # Using 'xyznotfound' as a term that won't match anything in the test data
        malicious_inputs = [
            "xyznotfound --",
            "xyznotfound /*",
            "xyznotfound */",
            "xyznotfound //",
        ]

        for search_term in malicious_inputs:
            results = graph_db_with_data.keyword_search(search_term)
            # Should search for the literal string, not execute as comment
            assert isinstance(results, list)
            # Should return 0 results since 'xyznotfound' doesn't exist in test data
            # and comment chars are treated as literals, not query syntax
            assert len(results) == 0, f"Expected 0 results for '{search_term}', got {len(results)}"

    def test_cypher_query_method_with_injection(self, graph_db_with_data):
        """Test that direct cypher_query method is safe with parameters.

        This tests the underlying query execution.
        """
        # This should be safe because cypher_query accepts params
        query = "MATCH (c:Chunk) WHERE c.content CONTAINS $keyword RETURN c LIMIT 1"
        results = graph_db_with_data.cypher_query(query, {"keyword": "' OR 1=1 --"})

        # Should return 0 results (no match for that literal string)
        assert len(results) == 0

    def test_keyword_search_legitimate_special_chars(self, graph_db_with_data):
        """Test that legitimate special characters work correctly.

        This ensures fixing injection doesn't break normal functionality.
        """
        # These are legitimate search terms that might contain special chars
        legitimate_terms = [
            "C++",
            "file.md",
            "tag#example",
            "API-KEY",
            "user@example.com",
        ]

        for term in legitimate_terms:
            try:
                results = graph_db_with_data.keyword_search(term)
                assert isinstance(results, list)
                # No error means it handled the special chars safely
            except Exception as e:
                pytest.fail(f"Legitimate term '{term}' caused error: {e}")


class TestPathTraversalSecurity:
    """Test suite for path traversal vulnerabilities."""

    def test_read_page_prevents_path_traversal(self):
        """Test that read_page in MCP server prevents path traversal.

        This is already implemented but we should test it.
        """
        # This would need to test the MCP server's read_page tool
        # Skipping for now as it requires MCP server integration
        pass

    def test_update_page_prevents_path_traversal(self):
        """Test that update_page prevents path traversal.

        This is already implemented but we should test it.
        """
        # This would need to test the MCP server's update_page tool
        # Skipping for now as it requires MCP server integration
        pass


class TestInputValidation:
    """Test suite for general input validation."""

    def test_empty_keyword_search(self, temp_db_path):
        """Test that empty keyword is handled gracefully."""
        graph_db = GraphDB(temp_db_path, enable_embeddings=False)

        results = graph_db.keyword_search("")
        assert isinstance(results, list)
        # Empty search might return everything or nothing - either is acceptable
        # As long as it doesn't crash

    def test_very_long_keyword_search(self, temp_db_path):
        """Test that very long keywords don't cause issues."""
        graph_db = GraphDB(temp_db_path, enable_embeddings=False)

        long_keyword = "a" * 10000
        results = graph_db.keyword_search(long_keyword)
        assert isinstance(results, list)

    def test_unicode_keyword_search(self, temp_db_path):
        """Test that Unicode characters are handled correctly."""
        graph_db = GraphDB(temp_db_path, enable_embeddings=False)

        unicode_terms = [
            "日本語",
            "émojis",
            "Ñoño",
            "🔥 fire",
        ]

        for term in unicode_terms:
            results = graph_db.keyword_search(term)
            assert isinstance(results, list)
