"""Tests for the unified server (gRPC + MCP + watcher)."""

from pathlib import Path

import pytest


class TestUnifiedServerIntegration:
    """Integration tests for the unified server."""

    @pytest.fixture
    def server_env(self, temp_db_path, temp_space_path):
        """Set up environment for unified server."""
        # Create a test markdown file
        test_file = Path(temp_space_path) / "test_page.md"
        test_file.write_text("""---
tags:
  - test
---
# Test Page

This is test content for the unified server.

[[AnotherPage]]
""")

        return {
            "db_path": temp_db_path,
            "space_path": temp_space_path,
            "test_file": test_file,
        }

    def test_unified_server_imports(self):
        """Test that UnifiedServer can be imported."""
        from server.__main__ import UnifiedServer, main

        assert UnifiedServer is not None
        assert callable(main)

    def test_unified_server_initialization(self, server_env):
        """Test that UnifiedServer initializes all components."""
        from server.__main__ import UnifiedServer

        server = UnifiedServer(
            db_path=server_env["db_path"],
            space_path=server_env["space_path"],
            grpc_port=50052,  # Use non-default ports for testing
            mcp_port=8001,
        )

        # Verify shared components are initialized
        assert server.graph_db is not None
        assert server.parser is not None
        assert server.hybrid_search is not None
        assert server.db_path == Path(server_env["db_path"])
        assert server.space_path == Path(server_env["space_path"])

    def test_unified_server_shared_db(self, server_env):
        """Test that all components share the same database instance."""
        from server.__main__ import UnifiedServer

        server = UnifiedServer(
            db_path=server_env["db_path"],
            space_path=server_env["space_path"],
            grpc_port=50053,
            mcp_port=8002,
        )

        # Initialize MCP dependencies
        server._init_mcp_dependencies()

        # Create gRPC servicer
        servicer = server._create_grpc_servicer()

        # All should share the same GraphDB instance
        from server.mcp import dependencies as mcp_deps

        assert servicer.graph_db is server.graph_db
        assert mcp_deps._deps.graph_db is server.graph_db

        # Cleanup
        mcp_deps._deps = None

    def test_watcher_uses_shared_db(self, server_env):
        """Test that the watcher uses the shared database."""
        from server.__main__ import UnifiedServer

        server = UnifiedServer(
            db_path=server_env["db_path"],
            space_path=server_env["space_path"],
            grpc_port=50054,
            mcp_port=8003,
        )

        # Start the watcher (this does initial indexing)
        server._start_watcher()

        # Watcher should use the same GraphDB
        assert server.space_watcher.graph_db is server.graph_db

        # Verify initial indexing happened - check if page was indexed
        results = server.graph_db.cypher_query(
            "MATCH (p:Page {name: 'test_page'}) RETURN p.name as name"
        )
        assert len(results) > 0
        assert results[0]["col0"] == "test_page"

        # Cleanup
        if server.watcher_observer:
            server.watcher_observer.stop()
            server.watcher_observer.join(timeout=2)

    def test_grpc_servicer_creation(self, server_env):
        """Test that gRPC servicer is created with correct attributes."""
        from server.__main__ import UnifiedServer
        from server.grpc_server import RAGServiceServicer

        server = UnifiedServer(
            db_path=server_env["db_path"],
            space_path=server_env["space_path"],
            grpc_port=50055,
            mcp_port=8004,
        )

        servicer = server._create_grpc_servicer()

        assert isinstance(servicer, RAGServiceServicer)
        assert servicer.graph_db is server.graph_db
        assert servicer.parser is server.parser
        assert servicer.hybrid_search is server.hybrid_search
        assert servicer.space_path == server.space_path
        assert servicer.read_only is False

    def test_mcp_dependencies_initialization(self, server_env):
        """Test that MCP dependencies are initialized with shared instances."""
        from server.__main__ import UnifiedServer
        from server.mcp import dependencies as mcp_deps

        # Reset any existing state
        mcp_deps._deps = None

        server = UnifiedServer(
            db_path=server_env["db_path"],
            space_path=server_env["space_path"],
            grpc_port=50056,
            mcp_port=8005,
        )

        server._init_mcp_dependencies()

        deps = mcp_deps.get_dependencies()
        assert deps.graph_db is server.graph_db
        assert deps.space_parser is server.parser
        assert deps.hybrid_search is server.hybrid_search
        assert deps.space_path == server.space_path
        assert deps.db_path == server.db_path

        # Cleanup
        mcp_deps._deps = None


class TestUnifiedServerProposalFiltering:
    """Test that proposal files are filtered in the unified server context."""

    @pytest.fixture
    def space_with_proposals(self, temp_space_path):
        """Create a space with regular and proposal files."""
        space = Path(temp_space_path)

        # Regular files
        (space / "regular.md").write_text("# Regular Page\nContent")
        (space / "Projects").mkdir()
        (space / "Projects" / "project.md").write_text("# Project\nDetails")

        # Proposal files (should be skipped)
        (space / "_Proposals").mkdir()
        (space / "_Proposals" / "change.md").write_text("# Proposal\nContent")
        (space / "_Proposals" / "new.proposal").write_text("---\ntype: proposal\n---")
        (space / "old.rejected.md").write_text("# Rejected\nThis was rejected")

        return space

    def test_indexer_skips_proposal_files(self, temp_db_path, space_with_proposals):
        """Test that the watcher/indexer skips proposal files."""
        from server.__main__ import UnifiedServer

        server = UnifiedServer(
            db_path=temp_db_path,
            space_path=str(space_with_proposals),
            grpc_port=50057,
            mcp_port=8006,
        )

        # Start watcher (does initial index)
        server._start_watcher()

        # Query for all indexed pages
        results = server.graph_db.cypher_query("MATCH (p:Page) RETURN p.name as name")
        page_names = [r["col0"] for r in results]

        # Regular files should be indexed
        assert "regular" in page_names
        # Page name might be "project" or "Projects/project" depending on parser
        assert any("project" in name for name in page_names)

        # Proposal-related files should NOT be indexed
        assert not any("_Proposals" in name for name in page_names)
        assert not any("change" in name for name in page_names)
        assert not any("rejected" in name for name in page_names)

        # Cleanup
        if server.watcher_observer:
            server.watcher_observer.stop()
            server.watcher_observer.join(timeout=2)


class TestUnifiedServerModule:
    """Test the server module entry point."""

    def test_module_entry_point(self):
        """Test that server can be run as a module."""
        from server import __main__

        # __main__ should have main and UnifiedServer
        assert hasattr(__main__, "main")
        assert hasattr(__main__, "UnifiedServer")
        assert callable(__main__.main)

    def test_main_reads_environment(self, monkeypatch):
        """Test that main() reads configuration from environment."""
        from server.__main__ import UnifiedServer, main

        # Track what UnifiedServer was initialized with
        init_calls = []

        def mock_init(self, **kwargs):
            init_calls.append(kwargs)
            # Don't actually initialize
            raise SystemExit("Test exit")

        monkeypatch.setattr(UnifiedServer, "__init__", mock_init)
        monkeypatch.setenv("DB_PATH", "/custom/db")
        monkeypatch.setenv("SPACE_PATH", "/custom/space")
        monkeypatch.setenv("GRPC_PORT", "55555")
        monkeypatch.setenv("MCP_PORT", "9999")

        with pytest.raises(SystemExit):
            main()

        assert len(init_calls) == 1
        assert init_calls[0]["db_path"] == "/custom/db"
        assert init_calls[0]["space_path"] == "/custom/space"
        assert init_calls[0]["grpc_port"] == 55555
        assert init_calls[0]["mcp_port"] == 9999
