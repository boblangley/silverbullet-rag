"""
Tests for MCP HTTP Server with Streamable HTTP Transport.

Following TDD RED/GREEN/REFACTOR approach.
These tests should FAIL initially since the HTTP server doesn't exist yet.
"""

import pytest
import pytest_asyncio
import httpx
import asyncio
import json
from pathlib import Path


class TestMCPHTTPServer:
    """Test suite for MCP HTTP server with FastMCP."""

    @pytest_asyncio.fixture
    async def http_client(self):
        """Create an async HTTP client for testing.

        Returns:
            httpx.AsyncClient configured for local MCP server
        """
        async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=10.0) as client:
            yield client

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
        """GREEN: Test that all 6 tools are registered with FastMCP.

        This should PASS - verifies all tools are properly decorated.
        """
        from server.mcp_http_server import (
            cypher_query,
            keyword_search,
            semantic_search,
            hybrid_search_tool,
            read_page,
            update_page
        )

        # All tools should be callable
        assert callable(cypher_query)
        assert callable(keyword_search)
        assert callable(semantic_search)
        assert callable(hybrid_search_tool)
        assert callable(read_page)
        assert callable(update_page)

    @pytest.mark.asyncio
    async def test_cypher_query_tool_directly(self, temp_db_path, temp_space_path):
        """GREEN: Test cypher_query tool function directly (without HTTP).

        This should PASS - tests tool logic without server.
        """
        from server.mcp_http_server import cypher_query, graph_db
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
    async def test_read_page_tool_directly(self, sample_markdown_file, temp_space_path, monkeypatch):
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
    async def test_update_page_tool_directly(self, temp_space_path, monkeypatch):
        """GREEN: Test update_page tool function directly.

        This should PASS - tests tool logic without server.
        """
        from server.mcp_http_server import update_page
        from pathlib import Path

        # Set SPACE_PATH environment variable
        monkeypatch.setenv("SPACE_PATH", temp_space_path)

        # Test creating new page
        result = await update_page("new_test.md", "# New Test\n\nContent here")
        assert result["success"] is True

        # Verify file was created
        file_path = Path(temp_space_path) / "new_test.md"
        assert file_path.exists()
        assert "New Test" in file_path.read_text()

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
    async def test_path_traversal_protection_write(self, temp_space_path, monkeypatch):
        """GREEN: Test path traversal attack protection in update_page.

        This should PASS - security check.
        """
        from server.mcp_http_server import update_page

        # Set SPACE_PATH environment variable
        monkeypatch.setenv("SPACE_PATH", temp_space_path)

        # Attempt path traversal
        result = await update_page("../../../tmp/evil.md", "malicious content")
        assert result["success"] is False
        assert "Invalid page name" in result["error"]

    @pytest.mark.skip(reason="Requires running HTTP server - integration test")
    @pytest.mark.asyncio
    async def test_http_endpoint_accessible(self, http_client):
        """Integration test: Test /mcp endpoint responds.

        Skipped - requires running HTTP server for integration testing.
        """
        try:
            response = await http_client.get("/mcp")
            # Should get some response (even if it's an error about method not allowed)
            assert response.status_code in [200, 404, 405]
        except httpx.ConnectError:
            pytest.fail("Cannot connect to MCP server at http://localhost:8000")

    @pytest.mark.skip(reason="Requires running HTTP server - integration test")
    @pytest.mark.asyncio
    async def test_cypher_query_tool(self, http_client, temp_db_path, temp_space_path):
        """RED: Test cypher_query tool via HTTP.

        This should FAIL because tool isn't implemented yet.
        """
        # This test assumes the server is running and database is initialized
        # We'll need to mock or use a test instance
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "cypher_query",
                "arguments": {
                    "query": "MATCH (n) RETURN count(n) as count"
                }
            },
            "id": 1
        }

        response = await http_client.post("/mcp", json=payload)
        assert response.status_code == 200

        result = response.json()
        assert "result" in result
        assert result["result"].get("success") is True

    @pytest.mark.skip(reason="Requires running HTTP server - integration test")
    @pytest.mark.asyncio
    async def test_keyword_search_tool(self, http_client):
        """RED: Test keyword_search tool via HTTP.

        This should FAIL because tool isn't implemented yet.
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "keyword_search",
                "arguments": {
                    "query": "test"
                }
            },
            "id": 2
        }

        response = await http_client.post("/mcp", json=payload)
        assert response.status_code == 200

        result = response.json()
        assert "result" in result
        assert result["result"].get("success") is True

    @pytest.mark.skip(reason="Requires running HTTP server - integration test")
    @pytest.mark.asyncio
    async def test_semantic_search_tool(self, http_client, mock_openai_embeddings):
        """RED: Test semantic_search tool via HTTP.

        This should FAIL because tool isn't implemented yet.
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "semantic_search",
                "arguments": {
                    "query": "python programming",
                    "limit": 5
                }
            },
            "id": 3
        }

        response = await http_client.post("/mcp", json=payload)
        assert response.status_code == 200

        result = response.json()
        assert "result" in result
        assert result["result"].get("success") is True

    @pytest.mark.skip(reason="Requires running HTTP server - integration test")
    @pytest.mark.asyncio
    async def test_hybrid_search_tool(self, http_client, mock_openai_embeddings):
        """RED: Test hybrid_search tool via HTTP.

        This should FAIL because tool isn't implemented yet.
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "hybrid_search",
                "arguments": {
                    "query": "test search",
                    "limit": 10,
                    "fusion_method": "rrf"
                }
            },
            "id": 4
        }

        response = await http_client.post("/mcp", json=payload)
        assert response.status_code == 200

        result = response.json()
        assert "result" in result
        assert result["result"].get("success") is True

    @pytest.mark.skip(reason="Requires running HTTP server - integration test")
    @pytest.mark.asyncio
    async def test_read_page_tool(self, http_client, sample_markdown_file, temp_space_path):
        """RED: Test read_page tool via HTTP.

        This should FAIL because tool isn't implemented yet.
        """
        # sample_markdown_file creates test_page.md
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "read_page",
                "arguments": {
                    "page_name": "test_page.md"
                }
            },
            "id": 5
        }

        response = await http_client.post("/mcp", json=payload)
        assert response.status_code == 200

        result = response.json()
        assert "result" in result
        assert result["result"].get("success") is True
        assert "content" in result["result"]

    @pytest.mark.skip(reason="Requires running HTTP server - integration test")
    @pytest.mark.asyncio
    async def test_update_page_tool(self, http_client, temp_space_path):
        """RED: Test update_page tool via HTTP.

        This should FAIL because tool isn't implemented yet.
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "update_page",
                "arguments": {
                    "page_name": "new_test_page.md",
                    "content": "# New Test Page\n\nThis is a test."
                }
            },
            "id": 6
        }

        response = await http_client.post("/mcp", json=payload)
        assert response.status_code == 200

        result = response.json()
        assert "result" in result
        assert result["result"].get("success") is True

    @pytest.mark.skip(reason="Requires running HTTP server - integration test")
    @pytest.mark.asyncio
    async def test_error_handling(self, http_client):
        """RED: Test invalid inputs return proper errors.

        This should FAIL because error handling isn't implemented yet.
        """
        # Test with invalid tool name
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "nonexistent_tool",
                "arguments": {}
            },
            "id": 7
        }

        response = await http_client.post("/mcp", json=payload)
        assert response.status_code in [200, 400, 404]

        result = response.json()
        # Should return an error response
        assert "error" in result or result.get("result", {}).get("success") is False

    @pytest.mark.skip(reason="Requires running HTTP server - integration test")
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, http_client):
        """RED: Test multiple HTTP clients simultaneously.

        This should FAIL because server isn't implemented yet.
        """
        # Send multiple concurrent requests
        payloads = [
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "keyword_search",
                    "arguments": {"query": f"test{i}"}
                },
                "id": 100 + i
            }
            for i in range(5)
        ]

        # Execute all requests concurrently
        tasks = [http_client.post("/mcp", json=payload) for payload in payloads]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # All requests should succeed
        for response in responses:
            if isinstance(response, Exception):
                pytest.fail(f"Concurrent request failed: {response}")
            assert response.status_code == 200


class TestMCPHTTPIntegration:
    """Integration tests requiring a running server."""

    @pytest.mark.skip(reason="Requires running HTTP server - will enable after GREEN phase")
    @pytest.mark.asyncio
    async def test_full_workflow(self, http_client, temp_space_path):
        """Integration test: Create page, search, read, update.

        This will be enabled after GREEN phase when server is running.
        """
        # 1. Create a page
        create_payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "update_page",
                "arguments": {
                    "page_name": "workflow_test.md",
                    "content": "# Workflow Test\n\nTesting the full workflow."
                }
            },
            "id": 1
        }
        response = await http_client.post("/mcp", json=create_payload)
        assert response.status_code == 200

        # 2. Search for the page
        search_payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "keyword_search",
                "arguments": {"query": "workflow"}
            },
            "id": 2
        }
        response = await http_client.post("/mcp", json=search_payload)
        assert response.status_code == 200

        # 3. Read the page
        read_payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "read_page",
                "arguments": {"page_name": "workflow_test.md"}
            },
            "id": 3
        }
        response = await http_client.post("/mcp", json=read_payload)
        assert response.status_code == 200
        result = response.json()
        assert "Workflow Test" in result["result"]["content"]
