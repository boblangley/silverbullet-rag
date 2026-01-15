"""Tests for Page node relationships (HAS_CHUNK and PAGE_LINKS_TO).

These tests verify the enhanced graph structure where:
- Page nodes represent source files (not just link targets)
- HAS_CHUNK edges connect Pages to their Chunks (ordered)
- PAGE_LINKS_TO edges connect Pages to Pages (for easy traversal)
"""

import pytest
from pathlib import Path
from server.db import GraphDB
from server.parser import SpaceParser


class TestPageHasChunkRelationship:
    """Test suite for Page -[HAS_CHUNK]-> Chunk relationships."""

    @pytest.fixture
    def graph_db(self, temp_db_path):
        """Create a test GraphDB instance."""
        return GraphDB(temp_db_path, enable_embeddings=False)

    @pytest.fixture
    def indexed_space(self, graph_db, temp_space_path):
        """Create and index a test space with files."""
        space = Path(temp_space_path)

        # Create a file with multiple sections (multiple chunks)
        file1 = space / "multi_section.md"
        file1.write_text(
            """# Multi Section Page

## Section 1
First section content.

## Section 2
Second section content.

## Section 3
Third section content.
"""
        )

        # Create a simple single-section file
        file2 = space / "single_section.md"
        file2.write_text(
            """# Single Section
Just one section here.
"""
        )

        # Index all files
        parser = SpaceParser()
        chunks = parser.parse_space(str(space))
        graph_db.index_chunks(chunks)

        return graph_db, space, [file1, file2]

    def test_page_node_created_for_source_file(self, indexed_space):
        """Test that Page nodes are created for source files."""
        graph_db, space, files = indexed_space

        # Check that Page node exists for multi_section (without .md extension)
        query = "MATCH (p:Page {name: 'multi_section'}) RETURN p.name as name"
        result = graph_db.cypher_query(query)
        assert len(result) == 1
        assert result[0]["col0"] == "multi_section"

    def test_has_chunk_relationship_exists(self, indexed_space):
        """Test that HAS_CHUNK relationships are created."""
        graph_db, space, files = indexed_space

        # Check that HAS_CHUNK edges exist from page to chunks
        query = """
        MATCH (p:Page {name: 'multi_section'})-[r:HAS_CHUNK]->(c:Chunk)
        RETURN count(r) as count
        """
        result = graph_db.cypher_query(query)
        assert result[0]["col0"] > 0, "Should have HAS_CHUNK relationships"

    def test_has_chunk_preserves_order(self, indexed_space):
        """Test that HAS_CHUNK relationships preserve chunk order."""
        graph_db, space, files = indexed_space

        # Get chunks in order (use chunk_idx to avoid 'order' reserved keyword)
        query = """
        MATCH (p:Page {name: 'multi_section'})-[r:HAS_CHUNK]->(c:Chunk)
        RETURN c.header as header, r.chunk_order as chunk_idx
        ORDER BY r.chunk_order
        """
        result = graph_db.cypher_query(query)

        # Verify we have multiple chunks
        assert len(result) >= 3, "Should have at least 3 chunks for multi-section page"

        # Verify order is sequential starting from 0
        orders = [r["col1"] for r in result]
        assert orders == list(range(len(orders))), "Chunk order should be sequential"

    def test_single_section_page_has_one_chunk(self, indexed_space):
        """Test that a single-section page has one chunk."""
        graph_db, space, files = indexed_space

        query = """
        MATCH (p:Page {name: 'single_section'})-[r:HAS_CHUNK]->(c:Chunk)
        RETURN count(r) as count
        """
        result = graph_db.cypher_query(query)
        assert result[0]["col0"] == 1, "Single section page should have 1 chunk"

    def test_get_all_chunks_for_page(self, indexed_space):
        """Test retrieving all chunks for a page in order."""
        graph_db, space, files = indexed_space

        query = """
        MATCH (p:Page {name: 'multi_section'})-[r:HAS_CHUNK]->(c:Chunk)
        RETURN c.content as content
        ORDER BY r.chunk_order
        """
        result = graph_db.cypher_query(query)

        # Verify we can reconstruct page content from chunks
        contents = [r["col0"] for r in result]
        assert len(contents) >= 3
        # First chunk should have section 1 content
        assert "First section" in contents[0] or "Multi Section" in contents[0]


class TestPageLinksToRelationship:
    """Test suite for Page -[PAGE_LINKS_TO]-> Page relationships."""

    @pytest.fixture
    def graph_db(self, temp_db_path):
        """Create a test GraphDB instance."""
        return GraphDB(temp_db_path, enable_embeddings=False)

    @pytest.fixture
    def indexed_space_with_links(self, graph_db, temp_space_path):
        """Create and index a test space with inter-page links."""
        space = Path(temp_space_path)

        # Create pages with wikilinks
        file1 = space / "page_a.md"
        file1.write_text(
            """# Page A
Links to [[page_b]] and [[page_c]].
"""
        )

        file2 = space / "page_b.md"
        file2.write_text(
            """# Page B
Links back to [[page_a]].
"""
        )

        file3 = space / "page_c.md"
        file3.write_text(
            """# Page C
Standalone page, no outgoing links.
"""
        )

        # Index all files
        parser = SpaceParser()
        chunks = parser.parse_space(str(space))
        graph_db.index_chunks(chunks)

        return graph_db, space, [file1, file2, file3]

    def test_page_links_to_relationship_exists(self, indexed_space_with_links):
        """Test that PAGE_LINKS_TO relationships are created."""
        graph_db, space, files = indexed_space_with_links

        # Check that page_a links to page_b
        query = """
        MATCH (source:Page {name: 'page_a'})-[:PAGE_LINKS_TO]->(target:Page {name: 'page_b'})
        RETURN count(*) as count
        """
        result = graph_db.cypher_query(query)
        assert result[0]["col0"] == 1, "page_a should link to page_b"

    def test_page_links_to_multiple_targets(self, indexed_space_with_links):
        """Test that a page can link to multiple targets."""
        graph_db, space, files = indexed_space_with_links

        # page_a links to both page_b and page_c
        query = """
        MATCH (source:Page {name: 'page_a'})-[:PAGE_LINKS_TO]->(target:Page)
        RETURN target.name as target_name
        """
        result = graph_db.cypher_query(query)
        targets = {r["col0"] for r in result}
        assert targets == {"page_b", "page_c"}, (
            "page_a should link to both page_b and page_c"
        )

    def test_backlinks_query(self, indexed_space_with_links):
        """Test finding all pages that link to a specific page."""
        graph_db, space, files = indexed_space_with_links

        # Find all pages linking to page_a
        query = """
        MATCH (source:Page)-[:PAGE_LINKS_TO]->(target:Page {name: 'page_a'})
        RETURN source.name as source_name
        """
        result = graph_db.cypher_query(query)
        sources = {r["col0"] for r in result}
        assert "page_b" in sources, "page_b should link to page_a"

    def test_page_with_no_outgoing_links(self, indexed_space_with_links):
        """Test that pages without links have no outgoing PAGE_LINKS_TO edges."""
        graph_db, space, files = indexed_space_with_links

        # page_c has no outgoing links
        query = """
        MATCH (source:Page {name: 'page_c'})-[:PAGE_LINKS_TO]->(target:Page)
        RETURN count(*) as count
        """
        result = graph_db.cypher_query(query)
        assert result[0]["col0"] == 0, "page_c should have no outgoing links"

    def test_chunk_links_to_still_exists(self, indexed_space_with_links):
        """Test that Chunk -[LINKS_TO]-> Page relationships still exist."""
        graph_db, space, files = indexed_space_with_links

        # The original Chunk -> Page link should still exist for granular queries
        query = """
        MATCH (c:Chunk)-[:LINKS_TO]->(p:Page {name: 'page_b'})
        RETURN c.file_path as file_path
        """
        result = graph_db.cypher_query(query)
        assert len(result) > 0, "Chunk -> Page LINKS_TO should still exist"


class TestPageRelationshipCleanup:
    """Test cleanup of Page relationships when files are deleted."""

    @pytest.fixture
    def graph_db(self, temp_db_path):
        """Create a test GraphDB instance."""
        return GraphDB(temp_db_path, enable_embeddings=False)

    @pytest.fixture
    def indexed_space(self, graph_db, temp_space_path):
        """Create and index a test space."""
        space = Path(temp_space_path)

        file1 = space / "source.md"
        file1.write_text(
            """# Source
Links to [[target]].
"""
        )

        file2 = space / "target.md"
        file2.write_text(
            """# Target
The target page.
"""
        )

        parser = SpaceParser()
        chunks = parser.parse_space(str(space))
        graph_db.index_chunks(chunks)

        return graph_db, space, [file1, file2]

    def test_delete_file_removes_has_chunk_edges(self, indexed_space):
        """Test that deleting a file removes its HAS_CHUNK edges."""
        graph_db, space, files = indexed_space
        file_to_delete = files[0]  # source.md

        # Verify HAS_CHUNK exists before
        query = """
        MATCH (p:Page {name: 'source'})-[:HAS_CHUNK]->(c:Chunk)
        RETURN count(*) as count
        """
        result = graph_db.cypher_query(query)
        assert result[0]["col0"] > 0, "Should have HAS_CHUNK before deletion"

        # Delete the file
        graph_db.delete_chunks_by_file(str(file_to_delete))

        # Verify HAS_CHUNK is gone (chunks are deleted)
        result = graph_db.cypher_query(query)
        # Note: The Page node might still exist if it's linked to,
        # but it won't have HAS_CHUNK edges since chunks are gone
        count = result[0]["col0"] if result else 0
        assert count == 0, "HAS_CHUNK edges should be removed after file deletion"

    def test_delete_file_removes_page_links_to_edges(self, indexed_space):
        """Test that deleting a file's chunks also affects PAGE_LINKS_TO."""
        graph_db, space, files = indexed_space
        file_to_delete = files[0]  # source.md (links to target)

        # Verify PAGE_LINKS_TO exists before
        query = """
        MATCH (p:Page {name: 'source'})-[:PAGE_LINKS_TO]->(t:Page)
        RETURN count(*) as count
        """
        result = graph_db.cypher_query(query)
        assert result[0]["col0"] > 0, "Should have PAGE_LINKS_TO before deletion"

        # Delete the file
        graph_db.delete_chunks_by_file(str(file_to_delete))

        # After deletion, the source Page node should be cleaned up
        # (it has no HAS_CHUNK, no incoming LINKS_TO, etc.)
        # So PAGE_LINKS_TO from source should also be gone
        result = graph_db.cypher_query(query)
        count = result[0]["col0"] if result else 0
        # The Page node for 'source' should be deleted as orphaned
        assert count == 0, (
            "PAGE_LINKS_TO edges should be removed after source file deletion"
        )
