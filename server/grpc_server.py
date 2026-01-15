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
                error="Proposals library not installed",
                proposal_path="",
                is_new_page=False,
                message="Install the Proposals library from Library Manager",
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
                error="Proposals library not installed",
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
                error="Proposals library not installed",
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

    def GetFolderContext(self, request, context):
        """Get context for an Open WebUI folder.

        Finds pages that have an 'openwebui-folder' frontmatter property
        matching the requested folder path.
        """
        try:
            folder_path = request.folder_path
            if not folder_path:
                return rag_pb2.GetFolderContextResponse(
                    success=False,
                    error="folder_path is required",
                    found=False,
                    page_name="",
                    page_content="",
                    folder_scope="",
                )

            # Query for chunks that have openwebui-folder in frontmatter
            # Frontmatter is stored as JSON string, so we search for the property
            results = self.graph_db.cypher_query(
                """
                MATCH (c:Chunk)
                WHERE c.frontmatter CONTAINS '"openwebui-folder"'
                RETURN c.file_path AS file_path, c.frontmatter AS frontmatter
                """
            )

            # Find the page whose openwebui-folder matches the request
            matching_page = None

            for result in results:
                try:
                    frontmatter_str = result.get("col1", "{}")
                    frontmatter = json.loads(frontmatter_str)
                    owui_folder = frontmatter.get("openwebui-folder", "")

                    # Case-insensitive comparison, normalize slashes
                    if owui_folder.lower().strip("/") == folder_path.lower().strip("/"):
                        file_path = result.get("col0", "")
                        # Convert file path to page name
                        if "/space/" in file_path:
                            matching_page = file_path.split("/space/", 1)[1]
                        else:
                            matching_page = file_path
                        if matching_page.endswith(".md"):
                            matching_page = matching_page[:-3]
                        break
                except json.JSONDecodeError:
                    continue

            if not matching_page:
                return rag_pb2.GetFolderContextResponse(
                    success=True,
                    error="",
                    found=False,
                    page_name="",
                    page_content="",
                    folder_scope="",
                )

            # Read the full page content
            page_path = self.space_path / (matching_page + ".md")
            if not page_path.exists():
                page_path = self.space_path / matching_page
                if not page_path.exists():
                    return rag_pb2.GetFolderContextResponse(
                        success=True,
                        error="",
                        found=False,
                        page_name=matching_page,
                        page_content="",
                        folder_scope="",
                    )

            page_content = page_path.read_text(encoding="utf-8")

            # Determine folder scope for search (use folder part of page path)
            folder_scope = ""
            if "/" in matching_page:
                folder_scope = "/".join(matching_page.split("/")[:-1])

            logging.info(
                f"Found folder context for '{folder_path}': "
                f"page={matching_page}, scope={folder_scope}"
            )

            return rag_pb2.GetFolderContextResponse(
                success=True,
                error="",
                found=True,
                page_name=matching_page,
                page_content=page_content,
                folder_scope=folder_scope,
            )
        except Exception as e:
            logging.error(f"GetFolderContext error: {e}")
            return rag_pb2.GetFolderContextResponse(
                success=False,
                error=str(e),
                found=False,
                page_name="",
                page_content="",
                folder_scope="",
            )

    def GetProjectContext(self, request, context):
        """Get project context by GitHub remote or folder path.

        Finds and returns the project index page and related metadata.
        """
        try:
            github_remote = request.github_remote or None
            folder_path = request.folder_path or None

            if not github_remote and not folder_path:
                return rag_pb2.GetProjectContextResponse(
                    success=False,
                    error="Must provide either github_remote or folder_path",
                    project=None,
                    related_pages=[],
                )

            project_file = None
            frontmatter = {}

            # Search by GitHub remote
            if github_remote:
                for md_file in self.space_path.glob("**/*.md"):
                    fm = self.parser.get_frontmatter(str(md_file))
                    if fm.get("github") == github_remote:
                        project_file = md_file
                        frontmatter = fm
                        break

            # Search by folder path
            elif folder_path:
                # In Silverbullet, folder index is Folder.md (sibling), not Folder/index.md
                parts = folder_path.split("/")
                if len(parts) > 1:
                    parent = "/".join(parts[:-1])
                    index_file = self.space_path / parent / f"{parts[-1]}.md"
                else:
                    index_file = self.space_path / f"{folder_path}.md"

                if index_file.exists():
                    project_file = index_file
                    frontmatter = self.parser.get_frontmatter(str(index_file))
                else:
                    # Try looking for any .md file in the folder with project metadata
                    folder_dir = self.space_path / folder_path
                    if folder_dir.exists() and folder_dir.is_dir():
                        for md_file in folder_dir.glob("*.md"):
                            fm = self.parser.get_frontmatter(str(md_file))
                            if fm:
                                project_file = md_file
                                frontmatter = fm
                                break

            if not project_file:
                return rag_pb2.GetProjectContextResponse(
                    success=False,
                    error=f"No project found for github_remote={github_remote}, folder_path={folder_path}",
                    project=None,
                    related_pages=[],
                )

            # Read the project file content
            content = project_file.read_text(encoding="utf-8")

            # Strip frontmatter from content for display
            clean_content = self.parser._strip_frontmatter(content)

            # Get related pages from the same folder
            relative_path = project_file.relative_to(self.space_path)
            folder = relative_path.parent

            related_pages = []
            if folder != Path("."):
                folder_dir = self.space_path / folder
                for md_file in folder_dir.glob("*.md"):
                    if md_file != project_file:
                        related_pages.append(
                            rag_pb2.RelatedPage(
                                name=md_file.stem,
                                path=str(md_file.relative_to(self.space_path)),
                            )
                        )

            # Also check for subdirectory matching the project file name
            project_subdir = project_file.parent / project_file.stem
            if project_subdir.exists() and project_subdir.is_dir():
                for md_file in project_subdir.glob("**/*.md"):
                    related_pages.append(
                        rag_pb2.RelatedPage(
                            name=md_file.stem,
                            path=str(md_file.relative_to(self.space_path)),
                        )
                    )

            # Build project info
            tags = frontmatter.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            concerns = frontmatter.get("concerns", [])
            if isinstance(concerns, str):
                concerns = [concerns]

            project_info = rag_pb2.ProjectInfo(
                file=str(relative_path),
                github=frontmatter.get("github", ""),
                tags=tags,
                concerns=concerns,
                content=clean_content,
            )

            logging.info(
                f"Found project context: file={relative_path}, "
                f"github={frontmatter.get('github')}, "
                f"related_pages={len(related_pages)}"
            )

            return rag_pb2.GetProjectContextResponse(
                success=True,
                error="",
                project=project_info,
                related_pages=related_pages[:20],
            )
        except Exception as e:
            logging.error(f"GetProjectContext error: {e}")
            return rag_pb2.GetProjectContextResponse(
                success=False,
                error=str(e),
                project=None,
                related_pages=[],
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
