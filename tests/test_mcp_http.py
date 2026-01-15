"""
Tests for MCP HTTP Server with Streamable HTTP Transport.

Following TDD RED/GREEN/REFACTOR approach.
These tests should FAIL initially since the HTTP server doesn't exist yet.
"""

import os
import pytest
import pytest_asyncio
import httpx


# Allow overriding the MCP server URL for Docker integration tests
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8000")

# Skip integration tests unless explicitly enabled
skip_integration = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Integration tests skipped. Set RUN_INTEGRATION_TESTS=true to run.",
)


@pytest_asyncio.fixture
async def http_client():
    """Create an async HTTP client for testing.

    Returns:
        httpx.AsyncClient configured for local MCP server
    """
    async with httpx.AsyncClient(base_url=MCP_SERVER_URL, timeout=10.0) as client:
        yield client


class TestMCPHTTPServer:
    """Test suite for MCP HTTP server with FastMCP."""

    @pytest.mark.asyncio
    async def test_server_startup(self):
        """GREEN: Test FastMCP server can be imported and initialized.

        This should PASS now that server/mcp_http_server.py exists.
        """
        try:
            from server.mcp_http_server import mcp, initialize_server

            assert mcp is not None
            assert callable(initialize_server)
        except ImportError as e:
            pytest.fail(f"FastMCP server module not found: {e}")

    @pytest.mark.asyncio
    async def test_all_tools_registered(self):
        """GREEN: Test that core tools are registered with FastMCP.

        This should PASS - verifies all tools are properly decorated.
        """
        from server.mcp_http_server import (
            cypher_query,
            keyword_search,
            semantic_search,
            hybrid_search_tool,
            read_page,
            propose_change,
            list_proposals,
            withdraw_proposal,
        )

        # All tools should be callable
        assert callable(cypher_query)
        assert callable(keyword_search)
        assert callable(semantic_search)
        assert callable(hybrid_search_tool)
        assert callable(read_page)
        assert callable(propose_change)
        assert callable(list_proposals)
        assert callable(withdraw_proposal)

    @pytest.mark.asyncio
    async def test_cypher_query_tool_directly(self, temp_db_path, temp_space_path):
        """GREEN: Test cypher_query tool function directly (without HTTP).

        This should PASS - tests tool logic without server.
        """
        from server.mcp_http_server import cypher_query
        from server.db.graph import GraphDB

        # Initialize graph_db for testing
        import server.mcp_http_server as mcp_module

        mcp_module.graph_db = GraphDB(temp_db_path)

        # Test query execution
        result = await cypher_query("MATCH (n) RETURN count(n) as count")
        assert "success" in result
        # Empty database should return count of 0
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_keyword_search_tool_directly(self, temp_db_path):
        """GREEN: Test keyword_search tool function directly.

        This should PASS - tests tool logic without server.
        """
        from server.mcp_http_server import keyword_search
        from server.db.graph import GraphDB

        # Initialize graph_db for testing
        import server.mcp_http_server as mcp_module

        mcp_module.graph_db = GraphDB(temp_db_path)

        # Test search execution
        result = await keyword_search("test")
        assert "success" in result
        assert result["success"] is True
        assert "results" in result

    @pytest.mark.asyncio
    async def test_read_page_tool_directly(
        self, sample_markdown_file, temp_space_path, monkeypatch
    ):
        """GREEN: Test read_page tool function directly.

        This should PASS - tests tool logic without server.
        """
        from server.mcp_http_server import read_page

        # Set SPACE_PATH environment variable
        monkeypatch.setenv("SPACE_PATH", temp_space_path)

        # Test reading existing page
        result = await read_page("test_page.md")
        assert result["success"] is True
        assert "content" in result
        assert "Test Page" in result["content"]

    @pytest.mark.asyncio
    async def test_read_page_not_found(self, temp_space_path, monkeypatch):
        """GREEN: Test read_page with nonexistent page.

        This should PASS - tests error handling.
        """
        from server.mcp_http_server import read_page

        # Set SPACE_PATH environment variable
        monkeypatch.setenv("SPACE_PATH", temp_space_path)

        # Test reading nonexistent page
        result = await read_page("nonexistent.md")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_propose_change_tool_disabled(self, temp_space_path, monkeypatch):
        """GREEN: Test propose_change returns error when library not installed.

        This should PASS - proposal tools disabled without Proposals library.
        """
        from server.mcp_http_server import propose_change
        import server.mcp_http_server as mcp_module

        # Set SPACE_PATH environment variable
        monkeypatch.setenv("SPACE_PATH", temp_space_path)

        # Ensure proposals are disabled (no library installed)
        mcp_module.proposals_enabled = False

        # Test proposing a change
        result = await propose_change(
            target_page="test.md",
            content="# Test",
            title="Test proposal",
            description="Testing",
        )
        assert result["success"] is False
        assert "not installed" in result["error"]

    @pytest.mark.asyncio
    async def test_path_traversal_protection_read(self, temp_space_path, monkeypatch):
        """GREEN: Test path traversal attack protection in read_page.

        This should PASS - security check.
        """
        from server.mcp_http_server import read_page

        # Set SPACE_PATH environment variable
        monkeypatch.setenv("SPACE_PATH", temp_space_path)

        # Attempt path traversal
        result = await read_page("../../../etc/passwd")
        assert result["success"] is False
        assert "Invalid page name" in result["error"]

    @pytest.mark.asyncio
    async def test_path_traversal_protection_propose(
        self, temp_space_path, temp_db_path, monkeypatch
    ):
        """GREEN: Test path traversal attack protection in propose_change.

        This should PASS - security check.
        """
        from server.mcp_http_server import propose_change
        import server.mcp_http_server as mcp_module

        # Set environment variables
        monkeypatch.setenv("SPACE_PATH", temp_space_path)
        monkeypatch.setenv("DB_PATH", temp_db_path)

        # Enable proposals for this test
        mcp_module.proposals_enabled = True

        # Attempt path traversal
        result = await propose_change(
            target_page="../../../tmp/evil.md",
            content="malicious content",
            title="Evil",
            description="Path traversal attempt",
        )
        assert result["success"] is False
        assert "Invalid page name" in result["error"]

    @skip_integration
    @pytest.mark.asyncio
    async def test_mcp_client_connection(self):
        """Integration test: Test MCP client can connect to server.

        Uses the proper MCP client library for streaming HTTP transport.
        """
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                # Connection successful if we get here
                assert session is not None

    @skip_integration
    @pytest.mark.asyncio
    async def test_mcp_list_tools(self):
        """Integration test: List available MCP tools."""
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]

                # Verify expected tools are available
                assert "cypher_query" in tool_names
                assert "keyword_search" in tool_names
                assert "semantic_search" in tool_names
                assert "hybrid_search_tool" in tool_names
                assert "read_page" in tool_names
                assert "propose_change" in tool_names

    @skip_integration
    @pytest.mark.asyncio
    async def test_mcp_keyword_search(self):
        """Integration test: Execute keyword search via MCP."""
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "keyword_search", arguments={"query": "markdown"}
                )
                # Should return results (the test data has markdown content)
                assert result is not None

    @skip_integration
    @pytest.mark.asyncio
    async def test_mcp_cypher_query(self):
        """Integration test: Execute Cypher query via MCP."""
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "cypher_query",
                    arguments={"query": "MATCH (n:Page) RETURN count(n) as count"},
                )
                assert result is not None

    @skip_integration
    @pytest.mark.asyncio
    async def test_mcp_semantic_search(self):
        """Integration test: Execute semantic search via MCP."""
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "semantic_search",
                    arguments={"query": "how to use markdown", "limit": 5},
                )
                assert result is not None

    @skip_integration
    @pytest.mark.asyncio
    async def test_mcp_hybrid_search(self):
        """Integration test: Execute hybrid search via MCP."""
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "hybrid_search_tool",
                    arguments={
                        "query": "markdown syntax",
                        "limit": 10,
                        "fusion_method": "rrf",
                    },
                )
                assert result is not None


class TestMCPHTTPIntegration:
    """Integration tests requiring a running server."""

    @skip_integration
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Integration test: Search, and verify results.

        Uses proper MCP client for streaming HTTP transport.
        """
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # 1. List tools to verify connection
                tools = await session.list_tools()
                assert len(tools.tools) >= 6

                # 2. Search for content (test data should have markdown content)
                search_result = await session.call_tool(
                    "keyword_search", arguments={"query": "markdown"}
                )
                assert search_result is not None

                # 3. Execute a Cypher query
                cypher_result = await session.call_tool(
                    "cypher_query",
                    arguments={"query": "MATCH (n:Chunk) RETURN count(n) as count"},
                )
                assert cypher_result is not None
