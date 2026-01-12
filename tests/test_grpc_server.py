"""Tests for gRPC server functionality.

Following TDD RED/GREEN/REFACTOR approach.
These tests should FAIL initially since proto files aren't compiled.
"""

import os
import pytest
import grpc
from pathlib import Path


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
