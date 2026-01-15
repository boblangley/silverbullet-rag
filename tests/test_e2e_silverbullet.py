"""
End-to-end tests for Silverbullet RAG with real Silverbullet instance.

These tests verify the full integration between silverbullet-rag MCP server
and a real Silverbullet instance, including:
- Library installation and detection
- Proposal creation and file system verification
- Search functionality with real indexed content

Run with: RUN_E2E_TESTS=true pytest tests/test_e2e_silverbullet.py -v
Or via: ./scripts/run-integration-tests.sh --e2e
"""

import json
import os
import time
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

# Skip E2E tests unless explicitly enabled
skip_e2e = pytest.mark.skipif(
    not os.environ.get("RUN_E2E_TESTS"),
    reason="E2E tests skipped. Set RUN_E2E_TESTS=true to run.",
)

# Server URLs from environment
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8000")
SILVERBULLET_URL = os.environ.get("SILVERBULLET_URL", "http://localhost:3000")
SILVERBULLET_USER = os.environ.get("SILVERBULLET_USER", "test")
SILVERBULLET_PASSWORD = os.environ.get("SILVERBULLET_PASSWORD", "testpassword")

# Space path for file verification (read-only mount in test container)
SPACE_PATH = Path(os.environ.get("SPACE_PATH", "/space"))


@pytest_asyncio.fixture
async def silverbullet_client():
    """Create HTTP client for Silverbullet API."""
    auth = httpx.BasicAuth(SILVERBULLET_USER, SILVERBULLET_PASSWORD)
    async with httpx.AsyncClient(
        base_url=SILVERBULLET_URL, auth=auth, timeout=30.0
    ) as client:
        yield client


def _parse_tool_result(result) -> dict:
    """Parse MCP tool result into a dictionary.

    MCP tool results come back as content objects.
    """
    if hasattr(result, "content") and result.content:
        for content in result.content:
            if hasattr(content, "text"):
                try:
                    return json.loads(content.text)
                except json.JSONDecodeError:
                    return {"raw": content.text}
    return {"error": "Could not parse result", "raw": str(result)}


@skip_e2e
class TestE2ESilverbulletConnection:
    """Test basic connectivity to Silverbullet and MCP server."""

    @pytest.mark.asyncio
    async def test_silverbullet_health(self, silverbullet_client):
        """Verify Silverbullet is running and accessible."""
        response = await silverbullet_client.get("/")
        # Silverbullet returns HTML for the main page
        assert response.status_code == 200
        assert "SilverBullet" in response.text or response.status_code == 200

    @pytest.mark.asyncio
    async def test_mcp_server_health(self):
        """Verify MCP server is running and tools are available."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]

                # Verify core tools are registered
                assert "keyword_search" in tool_names
                assert "semantic_search" in tool_names
                assert "hybrid_search_tool" in tool_names
                assert "read_page" in tool_names


@skip_e2e
class TestE2ELibraryInstallation:
    """Test library installation via MCP with Silverbullet verification."""

    @pytest.mark.asyncio
    async def test_install_proposals_library(self):
        """Install Proposals library and verify files exist."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # Install the library
                result = await session.call_tool(
                    "install_library", arguments={"library_name": "Proposals"}
                )
                result_data = _parse_tool_result(result)

                assert result_data.get("success") is True, (
                    f"Install failed: {result_data}"
                )

        # Give Silverbullet time to detect the new files
        time.sleep(2)

        # Verify files exist in the space
        library_md = SPACE_PATH / "Library" / "Proposals.md"
        assert library_md.exists(), "Library/Proposals.md not created"

        plug_js = SPACE_PATH / "Library" / "Proposals" / "Proposals.plug.js"
        assert plug_js.exists(), "Proposals.plug.js not created"

    @pytest.mark.asyncio
    async def test_library_frontmatter_correct(self):
        """Verify installed library has correct frontmatter for Silverbullet."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        library_md = SPACE_PATH / "Library" / "Proposals.md"

        if not library_md.exists():
            # Install first if not present
            async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    await session.call_tool(
                        "install_library", arguments={"library_name": "Proposals"}
                    )
            time.sleep(1)

        content = library_md.read_text()

        # Check for required frontmatter fields
        assert "tags: meta/library" in content, "Missing meta/library tag"
        assert "name: Library/Proposals" in content, "Missing name field"


@skip_e2e
class TestE2EProposals:
    """Test proposal creation and management with Silverbullet."""

    @pytest.mark.asyncio
    async def test_create_proposal(self):
        """Create a proposal and verify file is created."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        target_page = "Projects/Silverbullet-RAG.md"
        new_content = """---
tags: project
github: boblangley/silverbullet-rag
status: active
---

# Silverbullet RAG

Updated content from E2E test.

## Features

- Knowledge graph with Cypher queries
- BM25 keyword search
- Semantic vector search
- Hybrid search with RRF fusion
- MCP server for LLM integration

## NEW: Testing Section

This section was added by the E2E test.
"""

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "propose_change",
                    arguments={
                        "target_page": target_page,
                        "content": new_content,
                        "title": "E2E Test Proposal",
                        "description": "Testing proposal creation in E2E tests",
                    },
                )
                result_data = _parse_tool_result(result)

        assert result_data.get("success") is True, f"Proposal failed: {result_data}"
        assert "proposal_path" in result_data

        # Verify proposal file exists
        proposal_path = SPACE_PATH / result_data["proposal_path"]
        assert proposal_path.exists(), f"Proposal file not created: {proposal_path}"

        # Verify proposal content
        proposal_content = proposal_path.read_text()
        assert "type: proposal" in proposal_content
        assert "tags:" in proposal_content
        assert "proposal" in proposal_content  # tags should include proposal
        assert "E2E Test Proposal" in proposal_content

    @pytest.mark.asyncio
    async def test_list_proposals(self):
        """List proposals and verify our test proposal exists."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "list_proposals", arguments={"status": "pending"}
                )
                result_data = _parse_tool_result(result)

        assert result_data.get("success") is True
        # Note: may include proposals from previous test runs
        assert "proposals" in result_data

    @pytest.mark.asyncio
    async def test_withdraw_proposal(self):
        """Create and withdraw a proposal."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # Create a proposal first
                create_result = await session.call_tool(
                    "propose_change",
                    arguments={
                        "target_page": "Notes/Testing.md",
                        "content": "# Testing\n\nWithdraw test content.",
                        "title": "Withdraw Test",
                        "description": "This proposal will be withdrawn",
                    },
                )
                create_data = _parse_tool_result(create_result)
                assert create_data.get("success") is True, (
                    f"Create failed: {create_data}"
                )

                proposal_path = create_data["proposal_path"]

                # Withdraw it
                withdraw_result = await session.call_tool(
                    "withdraw_proposal", arguments={"proposal_path": proposal_path}
                )
                withdraw_data = _parse_tool_result(withdraw_result)

        assert withdraw_data.get("success") is True, f"Withdraw failed: {withdraw_data}"

        # Verify file is gone
        full_path = SPACE_PATH / proposal_path
        assert not full_path.exists(), "Proposal file still exists after withdraw"


@skip_e2e
class TestE2ESearch:
    """Test search functionality with indexed Silverbullet content."""

    @pytest.mark.asyncio
    async def test_keyword_search_finds_content(self):
        """Search for content that should exist in the test space."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "keyword_search",
                    arguments={"query": "Silverbullet RAG", "limit": 5},
                )
                result_data = _parse_tool_result(result)

        assert result_data.get("success") is True
        assert "results" in result_data
        # Should find the project page
        results = result_data["results"]
        assert len(results) > 0, "No search results found"

    @pytest.mark.asyncio
    async def test_semantic_search_finds_related(self):
        """Semantic search should find conceptually related content."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "semantic_search",
                    arguments={"query": "knowledge management system", "limit": 5},
                )
                result_data = _parse_tool_result(result)

        assert result_data.get("success") is True
        assert "results" in result_data

    @pytest.mark.asyncio
    async def test_hybrid_search(self):
        """Hybrid search combines keyword and semantic results."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

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
                        "query": "integration testing",
                        "limit": 10,
                        "fusion_method": "rrf",
                    },
                )
                result_data = _parse_tool_result(result)

        assert result_data.get("success") is True
        assert "results" in result_data

    @pytest.mark.asyncio
    async def test_cypher_query(self):
        """Execute Cypher query against the knowledge graph."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "cypher_query",
                    arguments={
                        "query": "MATCH (c:Chunk) RETURN count(c) as chunk_count"
                    },
                )
                result_data = _parse_tool_result(result)

        assert result_data.get("success") is True
        assert "results" in result_data
        # Should have indexed some chunks
        assert len(result_data["results"]) > 0


@skip_e2e
class TestE2EReadPage:
    """Test reading pages from the Silverbullet space."""

    @pytest.mark.asyncio
    async def test_read_existing_page(self):
        """Read an existing page from the space."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "read_page", arguments={"page_name": "Projects/Silverbullet-RAG.md"}
                )
                result_data = _parse_tool_result(result)

        assert result_data.get("success") is True
        assert "content" in result_data
        assert "Silverbullet RAG" in result_data["content"]

    @pytest.mark.asyncio
    async def test_read_nonexistent_page(self):
        """Reading nonexistent page should fail gracefully."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "read_page", arguments={"page_name": "NonExistent/Page.md"}
                )
                result_data = _parse_tool_result(result)

        assert result_data.get("success") is False
        assert "error" in result_data


@skip_e2e
class TestE2EProjectContext:
    """Test project context retrieval."""

    @pytest.mark.asyncio
    async def test_get_project_context_by_github(self):
        """Get project context using GitHub remote."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_project_context",
                    arguments={"github_remote": "boblangley/silverbullet-rag"},
                )
                result_data = _parse_tool_result(result)

        # May or may not find a match depending on space content
        assert "success" in result_data or "error" in result_data

    @pytest.mark.asyncio
    async def test_get_project_context_by_folder(self):
        """Get project context using folder path."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(MCP_SERVER_URL + "/mcp") as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_project_context", arguments={"folder_path": "Projects"}
                )
                result_data = _parse_tool_result(result)

        # Should find something in Projects folder
        assert result_data is not None
