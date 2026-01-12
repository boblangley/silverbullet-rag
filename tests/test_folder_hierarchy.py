"""Tests for folder hierarchy support in the RAG system.

Phase 1: Foundation - Add Folder nodes and hierarchy parsing for context scoping.

Key concepts:
- Folder nodes represent directories in the Silverbullet space
- (Folder)-[:CONTAINS]->(Page) relationships
- (Folder)-[:CONTAINS]->(Folder) for nested directories
- Silverbullet convention: Folder.md (sibling file) is the folder's index, not Folder/index.md
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestFolderNodesInGraph:
    """Test Folder node creation and relationships in GraphDB."""

    def test_init_schema_creates_folder_table(self, temp_db_path):
        """GraphDB should create a Folder node table during schema initialization."""
        with patch("openai.OpenAI"):
            from server.db.graph import GraphDB

            db = GraphDB(temp_db_path, enable_embeddings=False)

            # Query for Folder nodes should not raise an error
            result = db.cypher_query("MATCH (f:Folder) RETURN f LIMIT 1")
            # Should return empty list (no folders yet), not an error
            assert isinstance(result, list)

    def test_folder_node_has_required_properties(self, temp_db_path):
        """Folder nodes should have: name, path, has_index_page properties."""
        with patch("openai.OpenAI"):
            from server.db.graph import GraphDB

            db = GraphDB(temp_db_path, enable_embeddings=False)

            # Manually create a folder node to test schema
            db.cypher_query("""
                CREATE (f:Folder {
                    name: $name,
                    path: $path,
                    has_index_page: $has_index
                })
            """, {"name": "Projects", "path": "Projects", "has_index": True})

            result = db.cypher_query("""
                MATCH (f:Folder {name: 'Projects'})
                RETURN f.name, f.path, f.has_index_page
            """)

            assert len(result) == 1
            assert result[0]["col0"] == "Projects"
            assert result[0]["col1"] == "Projects"
            assert result[0]["col2"] is True

    def test_folder_contains_page_relationship(self, temp_db_path):
        """Test that FOLDER_CONTAINS_PAGE relationship can be created between Folder and Page."""
        with patch("openai.OpenAI"):
            from server.db.graph import GraphDB

            db = GraphDB(temp_db_path, enable_embeddings=False)

            # Create folder and page, then connect them
            db.cypher_query("""
                CREATE (f:Folder {name: 'Projects', path: 'Projects'})
                CREATE (p:Page {name: 'MyProject'})
                CREATE (f)-[:FOLDER_CONTAINS_PAGE]->(p)
            """)

            result = db.cypher_query("""
                MATCH (f:Folder)-[:FOLDER_CONTAINS_PAGE]->(p:Page)
                RETURN f.name, p.name
            """)

            assert len(result) == 1
            assert result[0]["col0"] == "Projects"
            assert result[0]["col1"] == "MyProject"

    def test_folder_contains_folder_relationship(self, temp_db_path):
        """Test nested folder hierarchy: Folder-[:CONTAINS]->Folder."""
        with patch("openai.OpenAI"):
            from server.db.graph import GraphDB

            db = GraphDB(temp_db_path, enable_embeddings=False)

            # Create nested folder structure
            db.cypher_query("""
                CREATE (root:Folder {name: 'Projects', path: 'Projects'})
                CREATE (sub:Folder {name: 'SubProject', path: 'Projects/SubProject'})
                CREATE (root)-[:CONTAINS]->(sub)
            """)

            result = db.cypher_query("""
                MATCH (parent:Folder)-[:CONTAINS]->(child:Folder)
                RETURN parent.name, child.name, child.path
            """)

            assert len(result) == 1
            assert result[0]["col0"] == "Projects"
            assert result[0]["col1"] == "SubProject"
            assert result[0]["col2"] == "Projects/SubProject"

    def test_index_folders_creates_hierarchy(self, temp_db_path):
        """GraphDB.index_folders() should create folder hierarchy from paths."""
        with patch("openai.OpenAI"):
            from server.db.graph import GraphDB

            db = GraphDB(temp_db_path, enable_embeddings=False)

            # Index folders from a list of paths
            folder_paths = [
                "Projects",
                "Projects/Topic",
                "Projects/Topic/Silverbullet-RAG",
                "Area/Health"
            ]

            db.index_folders(folder_paths)

            # Verify folder nodes were created
            result = db.cypher_query("MATCH (f:Folder) RETURN f.path ORDER BY f.path")
            paths = [r["col0"] for r in result]

            assert "Projects" in paths
            assert "Projects/Topic" in paths
            assert "Projects/Topic/Silverbullet-RAG" in paths
            assert "Area" in paths
            assert "Area/Health" in paths

    def test_index_folders_creates_contains_relationships(self, temp_db_path):
        """index_folders() should create CONTAINS relationships between parent/child."""
        with patch("openai.OpenAI"):
            from server.db.graph import GraphDB

            db = GraphDB(temp_db_path, enable_embeddings=False)

            db.index_folders(["Projects", "Projects/Topic"])

            result = db.cypher_query("""
                MATCH (parent:Folder {name: 'Projects'})-[:CONTAINS]->(child:Folder {name: 'Topic'})
                RETURN parent.path, child.path
            """)

            assert len(result) == 1
            assert result[0]["col0"] == "Projects"
            assert result[0]["col1"] == "Projects/Topic"


class TestFolderHierarchyParsing:
    """Test SpaceParser folder hierarchy extraction."""

    def test_parser_extracts_folder_paths(self, temp_space_path):
        """SpaceParser should extract unique folder paths from markdown files."""
        from server.parser.space_parser import SpaceParser

        # Create nested folder structure
        Path(temp_space_path, "Projects").mkdir()
        Path(temp_space_path, "Projects/Project1").mkdir()
        Path(temp_space_path, "Projects/Project1/test.md").write_text("# Test")
        Path(temp_space_path, "Area").mkdir()
        Path(temp_space_path, "Area/Health.md").write_text("# Health")

        parser = SpaceParser()
        folders = parser.get_folder_paths(temp_space_path)

        assert "Projects" in folders
        assert "Projects/Project1" in folders
        assert "Area" in folders

    def test_parser_detects_folder_index_pages(self, temp_space_path):
        """Parser should detect when Folder.md exists (sibling, not Folder/index.md)."""
        from server.parser.space_parser import SpaceParser

        # Create folder with sibling index file (Silverbullet convention)
        Path(temp_space_path, "Projects").mkdir()
        Path(temp_space_path, "Projects.md").write_text("# Projects Index")
        Path(temp_space_path, "Projects/SubProject.md").write_text("# Sub")

        parser = SpaceParser()
        folders = parser.get_folder_paths(temp_space_path)
        index_map = parser.get_folder_index_pages(temp_space_path)

        assert "Projects" in folders
        assert index_map.get("Projects") == "Projects.md"

    def test_parser_chunks_have_folder_path(self, temp_space_path):
        """Parsed chunks should include the folder path for scoping."""
        from server.parser.space_parser import SpaceParser

        # Create nested file
        Path(temp_space_path, "Projects").mkdir()
        Path(temp_space_path, "Projects/MyProject.md").write_text("# My Project\n\nContent here")

        parser = SpaceParser()
        chunks = parser.parse_space(temp_space_path)

        assert len(chunks) > 0
        # Chunks should have folder_path attribute
        chunk = chunks[0]
        assert hasattr(chunk, 'folder_path')
        assert chunk.folder_path == "Projects"


class TestYAMLFrontmatterParsing:
    """Test YAML frontmatter extraction for project context."""

    def test_parse_yaml_frontmatter_basic(self, temp_space_path):
        """Parser should extract YAML frontmatter from markdown files."""
        from server.parser.space_parser import SpaceParser

        content = """---
github: owner/repo
tags:
  - python
  - rag
---
# Project Page

Content here.
"""
        Path(temp_space_path, "project.md").write_text(content)

        parser = SpaceParser()
        chunks = parser.parse_space(temp_space_path)
        frontmatter = parser.get_frontmatter(temp_space_path + "/project.md")

        assert frontmatter is not None
        assert frontmatter.get("github") == "owner/repo"
        assert "python" in frontmatter.get("tags", [])
        assert "rag" in frontmatter.get("tags", [])

    def test_parse_yaml_frontmatter_with_concerns(self, temp_space_path):
        """Parser should extract concerns from frontmatter."""
        from server.parser.space_parser import SpaceParser

        content = """---
github: owner/repo
concerns:
  - Python/AsyncIO
  - Testing/Pytest
---
# Project

Content.
"""
        Path(temp_space_path, "project.md").write_text(content)

        parser = SpaceParser()
        frontmatter = parser.get_frontmatter(temp_space_path + "/project.md")

        assert frontmatter is not None
        assert "Python/AsyncIO" in frontmatter.get("concerns", [])
        assert "Testing/Pytest" in frontmatter.get("concerns", [])

    def test_chunks_include_frontmatter_metadata(self, temp_space_path):
        """Parsed chunks should have frontmatter metadata attached."""
        from server.parser.space_parser import SpaceParser

        content = """---
github: owner/repo
---
# Section 1

Content for section 1.
"""
        Path(temp_space_path, "test.md").write_text(content)

        parser = SpaceParser()
        chunks = parser.parse_space(temp_space_path)

        assert len(chunks) > 0
        chunk = chunks[0]
        assert hasattr(chunk, 'frontmatter')
        assert chunk.frontmatter.get("github") == "owner/repo"

    def test_frontmatter_not_included_in_chunk_content(self, temp_space_path):
        """Frontmatter should be parsed separately, not in chunk content."""
        from server.parser.space_parser import SpaceParser

        content = """---
github: owner/repo
---
# Title

Body content.
"""
        Path(temp_space_path, "test.md").write_text(content)

        parser = SpaceParser()
        chunks = parser.parse_space(temp_space_path)

        assert len(chunks) > 0
        chunk = chunks[0]
        # Frontmatter delimiter should not be in content
        assert "---" not in chunk.content
        assert "github:" not in chunk.content

    def test_frontmatter_tags_merged_into_chunk_tags(self, temp_space_path):
        """Frontmatter tags should be merged with content hashtags."""
        from server.parser.space_parser import SpaceParser

        content = """---
tags:
  - project
  - active
---
# Title

Body content with #hashtag and #another.
"""
        Path(temp_space_path, "test.md").write_text(content)

        parser = SpaceParser()
        chunks = parser.parse_space(temp_space_path)

        assert len(chunks) > 0
        chunk = chunks[0]
        # Should have both content hashtags and frontmatter tags
        assert "hashtag" in chunk.tags
        assert "another" in chunk.tags
        assert "project" in chunk.tags
        assert "active" in chunk.tags

    def test_frontmatter_tags_single_string(self, temp_space_path):
        """Frontmatter tags can be a single string instead of list."""
        from server.parser.space_parser import SpaceParser

        content = """---
tags: solo-tag
---
# Title

Body content.
"""
        Path(temp_space_path, "test.md").write_text(content)

        parser = SpaceParser()
        chunks = parser.parse_space(temp_space_path)

        assert len(chunks) > 0
        chunk = chunks[0]
        assert "solo-tag" in chunk.tags

    def test_frontmatter_tags_deduplicated(self, temp_space_path):
        """Duplicate tags from content and frontmatter should be deduplicated."""
        from server.parser.space_parser import SpaceParser

        content = """---
tags:
  - duplicate
---
# Title

Body with #duplicate tag.
"""
        Path(temp_space_path, "test.md").write_text(content)

        parser = SpaceParser()
        chunks = parser.parse_space(temp_space_path)

        assert len(chunks) > 0
        chunk = chunks[0]
        # Should only appear once
        assert chunk.tags.count("duplicate") == 1


class TestGetProjectContextTool:
    """Test the get_project_context MCP tool."""

    @pytest.mark.asyncio
    async def test_get_project_context_by_github_remote(self, temp_space_path, monkeypatch):
        """get_project_context should find context by github org/repo."""
        monkeypatch.setenv("SPACE_PATH", temp_space_path)

        # Create a project page with github frontmatter
        content = """---
github: anthropics/claude-code
---
# Claude Code Project

This is the project index for Claude Code development.

## Setup

Run `npm install` to get started.
"""
        Path(temp_space_path, "Projects").mkdir()
        Path(temp_space_path, "Projects/ClaudeCode.md").write_text(content)

        # Initialize the space_parser global variable
        import server.mcp_http_server as mcp_module
        from server.parser.space_parser import SpaceParser
        mcp_module.space_parser = SpaceParser()

        from server.mcp_http_server import get_project_context

        result = await get_project_context(github_remote="anthropics/claude-code")

        assert result["success"] is True
        assert "project" in result
        assert result["project"]["github"] == "anthropics/claude-code"
        assert "content" in result["project"]

    @pytest.mark.asyncio
    async def test_get_project_context_by_folder_path(self, temp_space_path, monkeypatch):
        """get_project_context should find context by folder path."""
        monkeypatch.setenv("SPACE_PATH", temp_space_path)

        # Create folder structure with index
        Path(temp_space_path, "Projects").mkdir()
        Path(temp_space_path, "Projects/MyProject").mkdir()
        Path(temp_space_path, "Projects/MyProject.md").write_text("""---
tags:
  - python
---
# My Project

Project documentation.
""")

        # Initialize the space_parser global variable
        import server.mcp_http_server as mcp_module
        from server.parser.space_parser import SpaceParser
        mcp_module.space_parser = SpaceParser()

        from server.mcp_http_server import get_project_context

        result = await get_project_context(folder_path="Projects/MyProject")

        assert result["success"] is True
        assert "project" in result
        assert "python" in result["project"].get("tags", [])

    @pytest.mark.asyncio
    async def test_get_project_context_not_found(self, temp_space_path, monkeypatch):
        """get_project_context should return error when project not found."""
        monkeypatch.setenv("SPACE_PATH", temp_space_path)

        # Initialize the space_parser global variable
        import server.mcp_http_server as mcp_module
        from server.parser.space_parser import SpaceParser
        mcp_module.space_parser = SpaceParser()

        from server.mcp_http_server import get_project_context

        result = await get_project_context(github_remote="nonexistent/repo")

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_project_context_includes_related_pages(self, temp_space_path, monkeypatch):
        """get_project_context should include linked pages from the folder."""
        monkeypatch.setenv("SPACE_PATH", temp_space_path)

        # Create project with multiple pages
        Path(temp_space_path, "Projects").mkdir()
        Path(temp_space_path, "Projects/Project").mkdir()
        Path(temp_space_path, "Projects/Project.md").write_text("""---
github: test/project
---
# Project Index

See [[Architecture]] and [[Setup]].
""")
        Path(temp_space_path, "Projects/Project/Architecture.md").write_text("# Architecture")
        Path(temp_space_path, "Projects/Project/Setup.md").write_text("# Setup")

        # Initialize the space_parser global variable
        import server.mcp_http_server as mcp_module
        from server.parser.space_parser import SpaceParser
        mcp_module.space_parser = SpaceParser()

        from server.mcp_http_server import get_project_context

        result = await get_project_context(github_remote="test/project")

        assert result["success"] is True
        assert "related_pages" in result
        page_names = [p["name"] for p in result["related_pages"]]
        assert "Architecture" in page_names or "Projects/Project/Architecture" in page_names


class TestScopedSearch:
    """Test scope parameter on search tools."""

    def test_keyword_search_with_folder_scope(self, temp_db_path, temp_space_path):
        """keyword_search should filter results to specified folder scope."""
        with patch("openai.OpenAI"):
            from server.db.graph import GraphDB
            from server.parser.space_parser import Chunk

            db = GraphDB(temp_db_path, enable_embeddings=False)

            # First index the folders
            db.index_folders(["Projects", "Projects/ProjectA", "Projects/ProjectB"])

            # Create chunks in different folders
            chunks = [
                Chunk(
                    file_path="Projects/ProjectA/readme.md",
                    folder_path="Projects/ProjectA",
                    header="Setup",
                    content="Install Python dependencies",
                    links=[],
                    tags=[],
                    frontmatter={}
                ),
                Chunk(
                    file_path="Projects/ProjectB/readme.md",
                    folder_path="Projects/ProjectB",
                    header="Setup",
                    content="Install Python dependencies",
                    links=[],
                    tags=[],
                    frontmatter={}
                ),
            ]

            db.index_chunks(chunks)

            # Search with scope should only return matching folder
            results = db.keyword_search("Python", scope="Projects/ProjectA")

            assert len(results) == 1
            assert "ProjectA" in results[0]["col0"]["file_path"]

    def test_semantic_search_with_folder_scope(self, temp_db_path):
        """semantic_search should filter results to specified folder scope."""
        # Skip this test since LadybugDB doesn't support vector indexes in this env
        pytest.skip("LadybugDB vector index not supported in test environment")

        from server.db.graph import GraphDB
        from server.parser.space_parser import Chunk

        db = GraphDB(temp_db_path, enable_embeddings=True)

        # First index the folders
        db.index_folders(["Area", "Area/Health", "Projects", "Projects/Project"])

        # Create chunks in different folders
        chunks = [
            Chunk(
                file_path="Area/Health/diet.md",
                folder_path="Area/Health",
                header="Diet",
                content="Healthy eating habits",
                links=[],
                tags=[],
                frontmatter={}
            ),
            Chunk(
                file_path="Projects/Project/notes.md",
                folder_path="Projects/Project",
                header="Notes",
                content="Healthy coding practices",
                links=[],
                tags=[],
                frontmatter={}
            ),
        ]

        db.index_chunks(chunks)

        # Search with scope
        results = db.semantic_search(
            query="healthy practices",
            scope="Area/Health",
            limit=10
        )

        # All results should be from Area/Health folder
        for result in results:
            chunk = result.get("col0", {})
            assert chunk.get("folder_path", "").startswith("Area/Health")

    @pytest.mark.asyncio
    async def test_hybrid_search_tool_with_scope(self, temp_space_path, monkeypatch):
        """hybrid_search_tool should accept scope parameter."""
        monkeypatch.setenv("SPACE_PATH", temp_space_path)

        from server.mcp_http_server import hybrid_search_tool

        # Test that scope parameter is accepted (function signature test)
        result = await hybrid_search_tool(
            query="test query",
            limit=10,
            scope="Projects/MyProject"
        )

        # Should not raise error about unexpected parameter
        assert "success" in result


class TestChunkWithFolderPath:
    """Test that Chunk dataclass supports folder_path and frontmatter."""

    def test_chunk_has_folder_path_attribute(self):
        """Chunk should have folder_path attribute."""
        from server.parser.space_parser import Chunk

        chunk = Chunk(
            file_path="Projects/Project/readme.md",
            folder_path="Projects/Project",
            header="Title",
            content="Content",
            links=[],
            tags=[],
            frontmatter={}
        )

        assert chunk.folder_path == "Projects/Project"

    def test_chunk_has_frontmatter_attribute(self):
        """Chunk should have frontmatter dict attribute."""
        from server.parser.space_parser import Chunk

        chunk = Chunk(
            file_path="test.md",
            folder_path="",
            header="Title",
            content="Content",
            links=[],
            tags=[],
            frontmatter={"github": "owner/repo", "tags": ["python"]}
        )

        assert chunk.frontmatter["github"] == "owner/repo"
        assert "python" in chunk.frontmatter["tags"]
        assert "python" in chunk.frontmatter["tags"]
