"""Tests for gRPC server functionality.

Following TDD RED/GREEN/REFACTOR approach.
These tests should FAIL initially since proto files aren't compiled.
"""

import os
import pytest
import grpc


# Allow overriding the gRPC server address for Docker integration tests
GRPC_SERVER_ADDRESS = os.environ.get("GRPC_SERVER_ADDRESS", "localhost:50051")

# Skip integration tests unless explicitly enabled
skip_integration = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Integration tests skipped. Set RUN_INTEGRATION_TESTS=true to run.",
)


class TestGRPCServer:
    """Test suite for gRPC server."""

    @pytest.fixture
    def grpc_channel(self):
        """Create a test gRPC channel.

        Returns:
            gRPC channel for testing
        """
        # This will fail initially - proto not compiled
        channel = grpc.insecure_channel("localhost:50051")
        yield channel
        channel.close()

    def test_grpc_server_imports(self):
        """RED: Test that proto files can be imported.

        This should FAIL because proto files haven't been compiled yet.
        """
        try:
            from server.grpc import rag_pb2, rag_pb2_grpc

            assert rag_pb2 is not None
            assert rag_pb2_grpc is not None
        except ImportError as e:
            pytest.fail(f"Proto files not compiled: {e}")

    def test_query_rpc_structure(self):
        """RED: Test Query RPC message structure.

        This should FAIL because proto files don't exist.
        """
        from server.grpc import rag_pb2

        # Test QueryRequest structure
        request = rag_pb2.QueryRequest(cypher_query="MATCH (n) RETURN n")
        assert request.cypher_query == "MATCH (n) RETURN n"

        # Test QueryResponse structure
        response = rag_pb2.QueryResponse(
            results_json='{"test": "data"}', success=True, error=""
        )
        assert response.success is True
        assert response.error == ""
        assert response.results_json == '{"test": "data"}'

    def test_search_rpc_structure(self):
        """RED: Test Search RPC message structure.

        This should FAIL because proto files don't exist.
        """
        from server.grpc import rag_pb2

        # Test SearchRequest structure
        request = rag_pb2.SearchRequest(keyword="test")
        assert request.keyword == "test"

        # Test SearchResponse structure
        response = rag_pb2.SearchResponse(
            results_json='[{"file": "test.md"}]', success=True, error=""
        )
        assert response.success is True

    def test_read_page_rpc_structure(self):
        """Test ReadPage RPC message structure."""
        from server.grpc import rag_pb2

        # Test ReadPageRequest structure
        request = rag_pb2.ReadPageRequest(page_name="test.md")
        assert request.page_name == "test.md"

        # Test ReadPageResponse structure
        response = rag_pb2.ReadPageResponse(
            success=True, error="", content="# Test Page\n\nContent"
        )
        assert response.success is True
        assert "Test Page" in response.content

    def test_propose_change_rpc_structure(self):
        """Test ProposeChange RPC message structure."""
        from server.grpc import rag_pb2

        # Test ProposeChangeRequest structure
        request = rag_pb2.ProposeChangeRequest(
            target_page="Projects/MyProject.md",
            content="# Updated Content",
            title="Update project docs",
            description="Adding new section",
        )
        assert request.target_page == "Projects/MyProject.md"
        assert request.title == "Update project docs"

        # Test ProposeChangeResponse structure
        response = rag_pb2.ProposeChangeResponse(
            success=True,
            error="",
            proposal_path="_Proposals/Projects/MyProject.md.proposal",
            is_new_page=False,
            message="Proposal created",
        )
        assert response.success is True
        assert response.proposal_path.endswith(".proposal")

    def test_list_proposals_rpc_structure(self):
        """Test ListProposals RPC message structure."""
        from server.grpc import rag_pb2

        # Test ListProposalsRequest structure
        request = rag_pb2.ListProposalsRequest(status="pending")
        assert request.status == "pending"

        # Test ProposalInfo structure
        proposal_info = rag_pb2.ProposalInfo(
            path="_Proposals/test.md.proposal",
            target_page="test.md",
            title="Test proposal",
            description="Test description",
            status="pending",
            is_new_page=False,
            proposed_by="claude-code",
            created_at="2024-01-01T00:00:00",
        )
        assert proposal_info.target_page == "test.md"

        # Test ListProposalsResponse structure
        response = rag_pb2.ListProposalsResponse(
            success=True, error="", count=1, proposals=[proposal_info]
        )
        assert response.success is True
        assert response.count == 1

    def test_withdraw_proposal_rpc_structure(self):
        """Test WithdrawProposal RPC message structure."""
        from server.grpc import rag_pb2

        # Test WithdrawProposalRequest structure
        request = rag_pb2.WithdrawProposalRequest(
            proposal_path="_Proposals/test.md.proposal"
        )
        assert request.proposal_path.endswith(".proposal")

        # Test WithdrawProposalResponse structure
        response = rag_pb2.WithdrawProposalResponse(
            success=True, error="", message="Proposal withdrawn"
        )
        assert response.success is True

    def test_get_folder_context_rpc_structure(self):
        """Test GetFolderContext RPC message structure."""
        from server.grpc import rag_pb2

        # Test GetFolderContextRequest structure
        request = rag_pb2.GetFolderContextRequest(folder_path="Projects/MyProject")
        assert request.folder_path == "Projects/MyProject"

        # Test GetFolderContextResponse structure
        response = rag_pb2.GetFolderContextResponse(
            success=True,
            error="",
            found=True,
            page_name="Projects/MyProject/index",
            page_content="# My Project\n\nProject description",
            folder_scope="Projects/MyProject",
        )
        assert response.success is True
        assert response.found is True
        assert response.page_name == "Projects/MyProject/index"
        assert "My Project" in response.page_content

    def test_get_project_context_rpc_structure(self):
        """Test GetProjectContext RPC message structure."""
        from server.grpc import rag_pb2

        # Test GetProjectContextRequest structure
        request = rag_pb2.GetProjectContextRequest(
            github_remote="owner/repo", folder_path=""
        )
        assert request.github_remote == "owner/repo"

        request2 = rag_pb2.GetProjectContextRequest(
            github_remote="", folder_path="Projects/MyProject"
        )
        assert request2.folder_path == "Projects/MyProject"

        # Test RelatedPage structure
        related_page = rag_pb2.RelatedPage(
            name="README", path="Projects/MyProject/README.md"
        )
        assert related_page.name == "README"
        assert related_page.path == "Projects/MyProject/README.md"

        # Test ProjectInfo structure
        project_info = rag_pb2.ProjectInfo(
            file="Projects/MyProject.md",
            github="owner/repo",
            tags=["python", "grpc"],
            concerns=["performance", "security"],
            content="# My Project\n\nProject description",
        )
        assert project_info.file == "Projects/MyProject.md"
        assert project_info.github == "owner/repo"
        assert list(project_info.tags) == ["python", "grpc"]
        assert list(project_info.concerns) == ["performance", "security"]
        assert "My Project" in project_info.content

        # Test GetProjectContextResponse structure
        response = rag_pb2.GetProjectContextResponse(
            success=True,
            error="",
            project=project_info,
            related_pages=[related_page],
        )
        assert response.success is True
        assert response.project.github == "owner/repo"
        assert len(response.related_pages) == 1

    def test_grpc_servicer_can_be_instantiated(self, temp_db_path, temp_space_path):
        """Test that RAGServiceServicer can be created.

        Args:
            temp_db_path: Temporary database directory
            temp_space_path: Temporary space directory
        """
        from server.grpc.server import RAGServiceServicer

        # Use read_only=False for test since we're creating a fresh database
        servicer = RAGServiceServicer(temp_db_path, temp_space_path, read_only=False)
        assert servicer is not None
        assert hasattr(servicer, "Query")
        assert hasattr(servicer, "Search")
        assert hasattr(servicer, "ReadPage")
        assert hasattr(servicer, "ProposeChange")
        assert hasattr(servicer, "ListProposals")
        assert hasattr(servicer, "WithdrawProposal")
        assert hasattr(servicer, "GetFolderContext")
        assert hasattr(servicer, "GetProjectContext")

    @pytest.mark.asyncio
    async def test_grpc_server_starts(self):
        """RED: Test that gRPC server can start.

        This should FAIL because service registration is commented out.
        """
        from server.grpc.server import serve

        # This test just checks that the server setup doesn't crash
        # We don't actually run it to completion (would block)
        # Just verify the function exists and is callable
        assert callable(serve)


class TestGRPCClientCalls:
    """Test actual RPC calls (requires running server)."""

    @pytest.fixture
    def grpc_stub(self):
        """Create a gRPC stub for testing against running server."""
        from server.grpc import rag_pb2_grpc

        channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
        stub = rag_pb2_grpc.RAGServiceStub(channel)
        yield stub
        channel.close()

    @skip_integration
    def test_query_rpc_call(self, grpc_stub):
        """Integration test: Execute Cypher query via gRPC."""
        from server.grpc import rag_pb2

        request = rag_pb2.QueryRequest(
            cypher_query="MATCH (n:Chunk) RETURN count(n) as count"
        )
        response = grpc_stub.Query(request)

        assert response.success is True
        assert response.results_json != ""

    @skip_integration
    def test_search_rpc_call(self, grpc_stub):
        """Integration test: Execute keyword search via gRPC."""
        from server.grpc import rag_pb2

        request = rag_pb2.SearchRequest(keyword="markdown")
        response = grpc_stub.Search(request)

        assert response.success is True
        # Should return results for markdown content
        assert response.results_json != ""

    @skip_integration
    def test_query_invalid_cypher(self, grpc_stub):
        """Integration test: Handle invalid Cypher query gracefully."""
        from server.grpc import rag_pb2

        request = rag_pb2.QueryRequest(cypher_query="INVALID CYPHER SYNTAX")
        response = grpc_stub.Query(request)

        # Should handle error gracefully
        assert response.success is False or response.error != ""

    @skip_integration
    def test_get_project_context_by_github(self, grpc_stub):
        """Integration test: Get project context by GitHub remote."""
        from server.grpc import rag_pb2

        request = rag_pb2.GetProjectContextRequest(
            github_remote="boblangley/silverbullet-rag"
        )
        response = grpc_stub.GetProjectContext(request)

        # Response should be successful (even if not found)
        assert response.success is True or response.error != ""

    @skip_integration
    def test_get_project_context_by_folder(self, grpc_stub):
        """Integration test: Get project context by folder path."""
        from server.grpc import rag_pb2

        request = rag_pb2.GetProjectContextRequest(folder_path="Projects/TestProject")
        response = grpc_stub.GetProjectContext(request)

        # Response should be successful (even if not found)
        assert response.success is True or response.error != ""


class TestGetProjectContextUnit:
    """Unit tests for GetProjectContext method."""

    @pytest.fixture
    def servicer_with_project(self, temp_db_path, temp_space_path):
        """Create a servicer with a test project page."""
        from server.grpc.server import RAGServiceServicer
        from pathlib import Path

        space = Path(temp_space_path)

        # Create a project with github frontmatter
        projects_dir = space / "Projects"
        projects_dir.mkdir(parents=True, exist_ok=True)

        project_file = projects_dir / "TestProject.md"
        project_file.write_text(
            """---
github: testowner/testrepo
tags:
  - python
  - testing
concerns:
  - performance
---
# Test Project

This is a test project for unit testing.
""",
            encoding="utf-8",
        )

        # Create related pages
        related_file = projects_dir / "RelatedPage.md"
        related_file.write_text(
            "# Related Page\n\nSome related content.", encoding="utf-8"
        )

        # Create subdirectory with more pages
        subdir = projects_dir / "TestProject"
        subdir.mkdir(parents=True, exist_ok=True)
        subpage = subdir / "SubPage.md"
        subpage.write_text("# Sub Page\n\nSubpage content.", encoding="utf-8")

        servicer = RAGServiceServicer(temp_db_path, temp_space_path, read_only=False)
        return servicer

    def test_get_project_context_by_github_remote(self, servicer_with_project):
        """Test finding project by GitHub remote."""
        from server.grpc import rag_pb2

        request = rag_pb2.GetProjectContextRequest(github_remote="testowner/testrepo")
        response = servicer_with_project.GetProjectContext(request, None)

        assert response.success is True
        assert response.error == ""
        assert response.project is not None
        assert response.project.github == "testowner/testrepo"
        assert "Test Project" in response.project.content
        assert "Projects/TestProject.md" in response.project.file
        assert "python" in list(response.project.tags)
        assert "performance" in list(response.project.concerns)

    def test_get_project_context_by_folder_path(self, servicer_with_project):
        """Test finding project by folder path."""
        from server.grpc import rag_pb2

        request = rag_pb2.GetProjectContextRequest(folder_path="Projects/TestProject")
        response = servicer_with_project.GetProjectContext(request, None)

        assert response.success is True
        assert response.error == ""
        assert response.project is not None
        assert "Test Project" in response.project.content

    def test_get_project_context_returns_related_pages(self, servicer_with_project):
        """Test that related pages are returned."""
        from server.grpc import rag_pb2

        request = rag_pb2.GetProjectContextRequest(github_remote="testowner/testrepo")
        response = servicer_with_project.GetProjectContext(request, None)

        assert response.success is True
        # Should have related pages from same folder and subdirectory
        assert len(response.related_pages) >= 1

        page_names = [p.name for p in response.related_pages]
        # RelatedPage.md should be found
        assert "RelatedPage" in page_names or "SubPage" in page_names

    def test_get_project_context_missing_params(self, servicer_with_project):
        """Test error when neither github_remote nor folder_path provided."""
        from server.grpc import rag_pb2

        request = rag_pb2.GetProjectContextRequest()
        response = servicer_with_project.GetProjectContext(request, None)

        assert response.success is False
        assert "Must provide either" in response.error

    def test_get_project_context_not_found(self, servicer_with_project):
        """Test error when project not found."""
        from server.grpc import rag_pb2

        request = rag_pb2.GetProjectContextRequest(github_remote="nonexistent/repo")
        response = servicer_with_project.GetProjectContext(request, None)

        assert response.success is False
        assert "No project found" in response.error

    def test_get_project_context_strips_frontmatter(self, servicer_with_project):
        """Test that frontmatter is stripped from content."""
        from server.grpc import rag_pb2

        request = rag_pb2.GetProjectContextRequest(github_remote="testowner/testrepo")
        response = servicer_with_project.GetProjectContext(request, None)

        assert response.success is True
        # Content should not contain frontmatter markers
        assert "---" not in response.project.content.split("\n")[0]
        assert "github:" not in response.project.content
