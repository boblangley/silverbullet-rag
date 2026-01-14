"""gRPC server for fast hook access."""

import asyncio
import json
import logging
from concurrent import futures
import grpc

# Import generated proto files
from .grpc import rag_pb2, rag_pb2_grpc

from .db import GraphDB
from .parser import SpaceParser
from .search import HybridSearch


class RAGServiceServicer(rag_pb2_grpc.RAGServiceServicer):
    """gRPC service implementation."""

    def __init__(self, db_path="/db", space_path="/space"):
        self.graph_db = GraphDB(db_path)
        self.parser = SpaceParser()
        self.hybrid_search = HybridSearch(self.graph_db)
        self.space_path = space_path

    def Query(self, request, context):
        """Execute a Cypher query."""
        try:
            results = self.graph_db.cypher_query(request.cypher_query)
            return rag_pb2.QueryResponse(
                results_json=json.dumps(results), success=True, error=""
            )
        except Exception as e:
            logging.error(f"Query error: {e}")
            return rag_pb2.QueryResponse(results_json="", success=False, error=str(e))

    def Search(self, request, context):
        """Search by keyword."""
        try:
            limit = request.limit if request.limit > 0 else 10
            results = self.graph_db.keyword_search(request.keyword, limit=limit)
            return rag_pb2.SearchResponse(
                results_json=json.dumps(results), success=True, error=""
            )
        except Exception as e:
            logging.error(f"Search error: {e}")
            return rag_pb2.SearchResponse(results_json="", success=False, error=str(e))

    def SemanticSearch(self, request, context):
        """Semantic search using vector embeddings."""
        try:
            # Convert repeated fields to lists (empty list if not provided)
            filter_tags = list(request.filter_tags) if request.filter_tags else None
            filter_pages = list(request.filter_pages) if request.filter_pages else None

            # Use default limit if not provided
            limit = request.limit if request.limit > 0 else 10

            results = self.graph_db.semantic_search(
                query=request.query,
                limit=limit,
                filter_tags=filter_tags,
                filter_pages=filter_pages,
            )

            return rag_pb2.SemanticSearchResponse(
                results_json=json.dumps(results), success=True, error=""
            )
        except Exception as e:
            logging.error(f"SemanticSearch error: {e}")
            return rag_pb2.SemanticSearchResponse(
                results_json="", success=False, error=str(e)
            )

    def HybridSearch(self, request, context):
        """Hybrid search combining keyword and semantic search."""
        try:
            # Convert repeated fields to lists (empty list if not provided)
            filter_tags = list(request.filter_tags) if request.filter_tags else None
            filter_pages = list(request.filter_pages) if request.filter_pages else None

            # Use default values if not provided
            limit = request.limit if request.limit > 0 else 10
            fusion_method = request.fusion_method if request.fusion_method else "rrf"
            semantic_weight = (
                request.semantic_weight if request.semantic_weight > 0 else 0.5
            )
            keyword_weight = (
                request.keyword_weight if request.keyword_weight > 0 else 0.5
            )

            results = self.hybrid_search.search(
                query=request.query,
                limit=limit,
                filter_tags=filter_tags,
                filter_pages=filter_pages,
                fusion_method=fusion_method,
                semantic_weight=semantic_weight,
                keyword_weight=keyword_weight,
            )

            return rag_pb2.HybridSearchResponse(
                results_json=json.dumps(results), success=True, error=""
            )
        except Exception as e:
            logging.error(f"HybridSearch error: {e}")
            return rag_pb2.HybridSearchResponse(
                results_json="", success=False, error=str(e)
            )

    def UpdatePage(self, request, context):
        """Update a page and reindex."""
        try:
            from pathlib import Path

            space_dir = Path(self.space_path)
            page_path = space_dir / request.page_name

            # Security check
            if not page_path.resolve().is_relative_to(space_dir.resolve()):
                raise ValueError("Invalid page name")

            page_path.write_text(request.content)

            # Re-index
            chunks = self.parser.parse_space(str(space_dir))
            self.graph_db.index_chunks(chunks)

            return rag_pb2.UpdatePageResponse(success=True, error="")
        except Exception as e:
            logging.error(f"UpdatePage error: {e}")
            return rag_pb2.UpdatePageResponse(success=False, error=str(e))


async def serve(db_path="/db", space_path="/space"):
    """Run the gRPC server.

    Args:
        db_path: Path to database directory
        space_path: Path to space directory
    """
    logging.basicConfig(level=logging.INFO)

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))

    # Register the service
    rag_pb2_grpc.add_RAGServiceServicer_to_server(
        RAGServiceServicer(db_path, space_path), server
    )

    server.add_insecure_port("[::]:50051")
    logging.info("gRPC server starting on port 50051...")

    await server.start()
    await server.wait_for_termination()


def main():
    """Main entry point."""
    asyncio.run(serve())


if __name__ == "__main__":
    main()
