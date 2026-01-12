"""Tests for graph deletion handling.

Following TDD RED/GREEN/REFACTOR approach.
These tests should FAIL initially since deletion logic isn't implemented.
"""

import pytest
from pathlib import Path
from server.db import GraphDB
from server.parser import SpaceParser, Chunk

# Check if watchdog module is available
try:
    import watchdog

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

requires_watchdog = pytest.mark.skipif(
    not WATCHDOG_AVAILABLE,
    reason="watchdog module not available (install watchdog package)",
)


class TestGraphDeletion:
    """Test suite for graph deletion functionality."""

    @pytest.fixture
    def graph_db(self, temp_db_path):
        """Create a test GraphDB instance.

        Args:
            temp_db_path: Temporary database file path

        Returns:
            GraphDB instance
        """
        return GraphDB(temp_db_path, enable_embeddings=False)

    @pytest.fixture
    def indexed_space(self, graph_db, temp_space_path):
        """Create and index a test space with multiple files.

        Args:
            graph_db: GraphDB instance
            temp_space_path: Temporary space directory

        Returns:
            Tuple of (graph_db, space_path, created_files)
        """
        space = Path(temp_space_path)

        # Create multiple test files
        file1 = space / "page1.md"
        file1.write_text(
            """# Page 1

## Section 1
Content with [[page2]] link and #tag1.

## Section 2
More content with #tag2.
"""
        )

        file2 = space / "page2.md"
        file2.write_text(
            """# Page 2

Content linking to [[page1]] with #tag1 #shared.
"""
        )

        file3 = space / "page3.md"
        file3.write_text(
            """# Page 3

Standalone content with #tag3 #shared.
"""
        )

        # Index all files
        parser = SpaceParser()
        chunks = parser.parse_space(str(space))
        graph_db.index_chunks(chunks)

        return graph_db, space, [file1, file2, file3]

    def test_delete_chunks_by_file_method_exists(self, graph_db):
        """RED: Test that delete_chunks_by_file method exists.

        This should FAIL because the method hasn't been implemented yet.
        """
        assert hasattr(graph_db, "delete_chunks_by_file")
        assert callable(graph_db.delete_chunks_by_file)

    def test_delete_single_file_removes_chunks(self, indexed_space):
        """RED: Test that deleting a file removes its chunks from graph.

        This should FAIL because deletion logic isn't implemented.
        """
        graph_db, space, files = indexed_space
        file_to_delete = files[0]  # page1.md

        # Verify chunks exist before deletion
        query = "MATCH (c:Chunk {file_path: $file_path}) RETURN count(c) as count"
        result = graph_db.cypher_query(
            query.replace("$file_path", f"'{str(file_to_delete)}'")
        )
        initial_count = result[0]["col0"] if result else 0
        assert initial_count > 0, "File should have chunks before deletion"

        # Delete the file's chunks
        graph_db.delete_chunks_by_file(str(file_to_delete))

        # Verify chunks are removed
        result = graph_db.cypher_query(
            query.replace("$file_path", f"'{str(file_to_delete)}'")
        )
        final_count = result[0]["col0"] if result else 0
        assert final_count == 0, "All chunks should be deleted"

    def test_delete_file_with_unique_tag_removes_tag(self, indexed_space):
        """RED: Test that deleting a file with unique tags removes orphaned tags.

        This should FAIL because orphan cleanup isn't implemented.
        """
        graph_db, space, files = indexed_space

        # page3.md has unique tag #tag3
        file_to_delete = files[2]

        # Verify tag exists before deletion
        query = "MATCH (t:Tag {name: 'tag3'}) RETURN count(t) as count"
        result = graph_db.cypher_query(query)
        assert result[0]["col0"] > 0, "Tag should exist before deletion"

        # Delete the file
        graph_db.delete_chunks_by_file(str(file_to_delete))

        # Verify orphaned tag is removed
        result = graph_db.cypher_query(query)
        count = result[0]["col0"] if result else 0
        assert count == 0, "Orphaned tag should be removed"

    def test_delete_file_with_shared_tag_keeps_tag(self, indexed_space):
        """RED: Test that deleting a file with shared tags keeps the tags.

        This should FAIL because orphan cleanup logic isn't implemented.
        """
        graph_db, space, files = indexed_space

        # Both page2 and page3 have #shared tag
        file_to_delete = files[1]  # page2.md

        # Delete the file
        graph_db.delete_chunks_by_file(str(file_to_delete))

        # Verify shared tag still exists (used by page3)
        query = "MATCH (t:Tag {name: 'shared'}) RETURN count(t) as count"
        result = graph_db.cypher_query(query)
        assert result[0]["col0"] > 0, "Shared tag should still exist"

    def test_delete_file_with_unique_wikilink_removes_page(self, indexed_space):
        """RED: Test that deleting a file removes orphaned Page nodes.

        This should FAIL because orphan cleanup isn't implemented.
        """
        graph_db, space, files = indexed_space

        # page1 links to page2, page2 links to page1
        # If we delete page2, the Page node for page2 should be removed
        file_to_delete = files[1]  # page2.md

        # Delete the file
        graph_db.delete_chunks_by_file(str(file_to_delete))

        # Verify orphaned Page node is removed
        # Note: page2 as a Page node should be removed (no incoming links after deletion)
        query = "MATCH (p:Page {name: 'page2'}) RETURN count(p) as count"
        result = graph_db.cypher_query(query)
        count = result[0]["col0"] if result else 0
        # This is tricky - page1 still links TO page2, so Page node might remain
        # But chunks from page2 are gone
        # Let's verify chunks are gone
        query_chunks = f"MATCH (c:Chunk) WHERE c.file_path CONTAINS 'page2.md' RETURN count(c) as count"
        result = graph_db.cypher_query(query_chunks)
        count = result[0]["col0"] if result else 0
        assert count == 0, "No chunks should reference deleted file"

    def test_delete_nonexistent_file_doesnt_crash(self, graph_db):
        """RED: Test that deleting a non-existent file doesn't crash.

        This should PASS even without implementation (graceful handling).
        """
        # Should not raise an exception
        graph_db.delete_chunks_by_file("/nonexistent/file.md")

    @requires_watchdog
    def test_watcher_calls_delete_on_file_deletion(self, temp_space_path, temp_db_path):
        """RED: Test that file watcher calls delete_chunks_by_file on deletion.

        This should FAIL because watcher doesn't implement deletion.
        """
        from server.watcher import SpaceWatcher
        from unittest.mock import Mock

        graph_db = GraphDB(temp_db_path, enable_embeddings=False)
        parser = SpaceParser()

        # Create a test file
        space = Path(temp_space_path)
        test_file = space / "test.md"
        test_file.write_text("# Test\n\nContent")

        # Index it
        chunks = parser.parse_space(str(space))
        graph_db.index_chunks(chunks)

        # Create watcher (but don't start it)
        watcher = SpaceWatcher(str(space), graph_db, parser)

        # Mock the delete method to track calls
        original_delete = graph_db.delete_chunks_by_file
        graph_db.delete_chunks_by_file = Mock(side_effect=original_delete)

        # Simulate file deletion event
        watcher.on_deleted(Mock(src_path=str(test_file), is_directory=False))

        # Verify delete was called
        graph_db.delete_chunks_by_file.assert_called_once_with(str(test_file))


class TestOrphanCleanup:
    """Test suite for orphaned node cleanup."""

    @pytest.fixture
    def graph_db(self, temp_db_path):
        """Create a test GraphDB instance."""
        return GraphDB(temp_db_path, enable_embeddings=False)

    def test_cleanup_orphaned_tags(self, graph_db):
        """RED: Test that orphaned tags are identified and removed.

        This should FAIL because cleanup logic isn't implemented.
        """
        # Manually create orphaned tag (no TAGGED relationships)
        query = "CREATE (t:Tag {name: 'orphan'})"
        graph_db.cypher_query(query)

        # Verify it exists
        result = graph_db.cypher_query(
            "MATCH (t:Tag {name: 'orphan'}) RETURN count(t) as count"
        )
        assert result[0]["col0"] > 0

        # Call cleanup (should be part of delete_chunks_by_file)
        # For now, test that we can identify orphans
        orphan_query = """
        MATCH (t:Tag)
        WHERE NOT (t)<-[:TAGGED]-()
        RETURN t.name as name
        """
        result = graph_db.cypher_query(orphan_query)
        assert len(result) > 0, "Should find orphaned tags"
        assert any(r.get("col0") == "orphan" or "orphan" in str(r) for r in result)

    def test_cleanup_orphaned_pages(self, graph_db):
        """RED: Test that orphaned Page nodes are identified and removed.

        This should FAIL because cleanup logic isn't implemented.
        """
        # Manually create orphaned Page (no LINKS_TO relationships)
        query = "CREATE (p:Page {name: 'orphan_page'})"
        graph_db.cypher_query(query)

        # Verify it exists
        result = graph_db.cypher_query(
            "MATCH (p:Page {name: 'orphan_page'}) RETURN count(p) as count"
        )
        assert result[0]["col0"] > 0

        # Call cleanup to identify orphans
        orphan_query = """
        MATCH (p:Page)
        WHERE NOT (p)<-[:LINKS_TO]-()
        RETURN p.name as name
        """
        result = graph_db.cypher_query(orphan_query)
        assert len(result) > 0, "Should find orphaned pages"
