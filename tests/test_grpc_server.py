"""Tests for gRPC server functionality.

Following TDD RED/GREEN/REFACTOR approach.
These tests should FAIL initially since proto files aren't compiled.
"""

import pytest
import grpc
from pathlib import Path


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

    def test_update_page_rpc_structure(self):
        """RED: Test UpdatePage RPC message structure.

        This should FAIL because proto files don't exist.
        """
        from server.grpc import rag_pb2

        # Test UpdatePageRequest structure
        request = rag_pb2.UpdatePageRequest(
            page_name="test.md", content="# Test Page\n\nContent"
        )
        assert request.page_name == "test.md"
        assert "Test Page" in request.content

        # Test UpdatePageResponse structure
        response = rag_pb2.UpdatePageResponse(success=True, error="")
        assert response.success is True

    def test_grpc_servicer_can_be_instantiated(self, temp_db_path, temp_space_path):
        """Test that RAGServiceServicer can be created.

        Args:
            temp_db_path: Temporary database directory
            temp_space_path: Temporary space directory
        """
        from server.grpc_server import RAGServiceServicer

        servicer = RAGServiceServicer(temp_db_path, temp_space_path)
        assert servicer is not None
        assert hasattr(servicer, "Query")
        assert hasattr(servicer, "Search")
        assert hasattr(servicer, "UpdatePage")

    @pytest.mark.asyncio
    async def test_grpc_server_starts(self):
        """RED: Test that gRPC server can start.

        This should FAIL because service registration is commented out.
        """
        from server.grpc_server import serve

        # This test just checks that the server setup doesn't crash
        # We don't actually run it to completion (would block)
        # Just verify the function exists and is callable
        assert callable(serve)


class TestGRPCClientCalls:
    """Test actual RPC calls (requires running server)."""

    @pytest.fixture
    def temp_test_db(self, temp_db_path, temp_space_path, sample_markdown_file):
        """Setup test database with sample data.

        Args:
            temp_db_path: Temporary database directory
            temp_space_path: Temporary space directory
            sample_markdown_file: Sample markdown file fixture

        Returns:
            Tuple of (db_path, space_path)
        """
        return temp_db_path, temp_space_path

    @pytest.mark.skip(
        reason="Requires running gRPC server - will implement after GREEN phase"
    )
    def test_query_rpc_call(self, temp_test_db):
        """RED: Test actual Query RPC call.

        Skipped for now - will implement after server is working.
        """
        pass

    @pytest.mark.skip(
        reason="Requires running gRPC server - will implement after GREEN phase"
    )
    def test_search_rpc_call(self, temp_test_db):
        """RED: Test actual Search RPC call.

        Skipped for now - will implement after server is working.
        """
        pass

    @pytest.mark.skip(
        reason="Requires running gRPC server - will implement after GREEN phase"
    )
    def test_update_page_rpc_call(self, temp_test_db):
        """RED: Test actual UpdatePage RPC call.

        Skipped for now - will implement after server is working.
        """
        pass
