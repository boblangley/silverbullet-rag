"""gRPC server for fast hook access."""

import asyncio
import json
import logging
from concurrent import futures
from pathlib import Path

import grpc

# Import generated proto files
from .grpc import rag_pb2, rag_pb2_grpc

from .db import GraphDB
from .parser import SpaceParser
from .search import HybridSearch
from .proposals import (
    library_installed,
    get_proposal_path,
    page_exists,
    find_proposals,
    create_proposal_content,
    get_proposals_config,
)


class RAGServiceServicer(rag_pb2_grpc.RAGServiceServicer):
    """gRPC service implementation."""

    def __init__(self, db_path="/db", space_path="/space", read_only=True):
        self.db_path = Path(db_path)
        self.graph_db = GraphDB(db_path, read_only=read_only)
        self.parser = SpaceParser()
        self.hybrid_search = HybridSearch(self.graph_db)
        self.space_path = Path(space_path)
        self.read_only = read_only
        self.proposals_enabled = library_installed(self.space_path)

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

    def ReadPage(self, request, context):
        """Read a page from the space."""
        try:
            page_path = self.space_path / request.page_name

            # Security check - prevent path traversal
            if not page_path.resolve().is_relative_to(self.space_path.resolve()):
                return rag_pb2.ReadPageResponse(
                    success=False, error="Invalid page name", content=""
                )

            if not page_path.exists():
                return rag_pb2.ReadPageResponse(
                    success=False,
                    error=f"Page '{request.page_name}' not found",
                    content="",
                )

            content = page_path.read_text(encoding="utf-8")
            return rag_pb2.ReadPageResponse(success=True, error="", content=content)
        except Exception as e:
            logging.error(f"ReadPage error: {e}")
            return rag_pb2.ReadPageResponse(success=False, error=str(e), content="")

    def ProposeChange(self, request, context):
        """Propose a change to a page (creates a proposal for user review)."""
        if not self.proposals_enabled:
            return rag_pb2.ProposeChangeResponse(
                success=False,
                error="AI-Proposals library not installed",
                proposal_path="",
                is_new_page=False,
                message="Install the AI-Proposals library from Library Manager",
            )

        try:
            # Security check - prevent path traversal
            target_path = self.space_path / request.target_page
            if not target_path.resolve().is_relative_to(self.space_path.resolve()):
                return rag_pb2.ProposeChangeResponse(
                    success=False,
                    error=f"Invalid page name: {request.target_page}",
                    proposal_path="",
                    is_new_page=False,
                    message="",
                )

            # Get config for path prefix
            proposals_config = get_proposals_config(self.db_path)
            prefix = proposals_config.get("path_prefix", "_Proposals/")

            is_new_page = not page_exists(self.space_path, request.target_page)
            proposal_path = get_proposal_path(request.target_page, prefix)

            proposal_content = create_proposal_content(
                target_page=request.target_page,
                content=request.content,
                title=request.title,
                description=request.description,
                is_new_page=is_new_page,
            )

            # Write proposal file
            full_path = self.space_path / proposal_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(proposal_content, encoding="utf-8")

            logging.info(f"Created proposal: {proposal_path}")

            return rag_pb2.ProposeChangeResponse(
                success=True,
                error="",
                proposal_path=proposal_path,
                is_new_page=is_new_page,
                message=f"Proposal created. User can review at {proposal_path}",
            )
        except Exception as e:
            logging.error(f"ProposeChange error: {e}")
            return rag_pb2.ProposeChangeResponse(
                success=False,
                error=str(e),
                proposal_path="",
                is_new_page=False,
                message="",
            )

    def ListProposals(self, request, context):
        """List change proposals by status."""
        if not self.proposals_enabled:
            return rag_pb2.ListProposalsResponse(
                success=False,
                error="AI-Proposals library not installed",
                count=0,
                proposals=[],
            )

        try:
            proposals_config = get_proposals_config(self.db_path)
            prefix = proposals_config.get("path_prefix", "_Proposals/")

            status = request.status if request.status else "pending"
            proposals = find_proposals(self.space_path, prefix, status)

            # Convert to proto messages
            proto_proposals = []
            for p in proposals:
                proto_proposals.append(
                    rag_pb2.ProposalInfo(
                        path=p.get("path", ""),
                        target_page=p.get("target_page", ""),
                        title=p.get("title", ""),
                        description=p.get("description", ""),
                        status=p.get("status", ""),
                        is_new_page=p.get("is_new_page", False),
                        proposed_by=p.get("proposed_by", ""),
                        created_at=p.get("created_at", ""),
                    )
                )

            return rag_pb2.ListProposalsResponse(
                success=True,
                error="",
                count=len(proto_proposals),
                proposals=proto_proposals,
            )
        except Exception as e:
            logging.error(f"ListProposals error: {e}")
            return rag_pb2.ListProposalsResponse(
                success=False, error=str(e), count=0, proposals=[]
            )

    def WithdrawProposal(self, request, context):
        """Withdraw a pending proposal."""
        if not self.proposals_enabled:
            return rag_pb2.WithdrawProposalResponse(
                success=False,
                error="AI-Proposals library not installed",
                message="",
            )

        try:
            full_path = self.space_path / request.proposal_path

            # Security check - prevent path traversal
            if not full_path.resolve().is_relative_to(self.space_path.resolve()):
                return rag_pb2.WithdrawProposalResponse(
                    success=False,
                    error=f"Invalid proposal path: {request.proposal_path}",
                    message="",
                )

            if not full_path.exists():
                return rag_pb2.WithdrawProposalResponse(
                    success=False, error="Proposal not found", message=""
                )

            if not request.proposal_path.endswith(".proposal"):
                return rag_pb2.WithdrawProposalResponse(
                    success=False, error="Not a proposal file", message=""
                )

            full_path.unlink()
            logging.info(f"Withdrew proposal: {request.proposal_path}")

            return rag_pb2.WithdrawProposalResponse(
                success=True, error="", message="Proposal withdrawn"
            )
        except Exception as e:
            logging.error(f"WithdrawProposal error: {e}")
            return rag_pb2.WithdrawProposalResponse(
                success=False, error=str(e), message=""
            )


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
