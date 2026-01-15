#!/usr/bin/env python3
"""Build script to generate the Open WebUI pipe with embedded gRPC stubs.

This script:
1. Compiles proto/rag.proto to generate protobuf stubs
2. Extracts the client-side code (messages + stub)
3. Merges everything into a single openwebui/silverbullet_rag.py file

Run from project root:
    python scripts/build_openwebui_pipe.py
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PROTO_FILE = PROJECT_ROOT / "proto" / "rag.proto"
OUTPUT_FILE = PROJECT_ROOT / "openwebui" / "silverbullet_rag.py"
SERVER_GRPC_DIR = PROJECT_ROOT / "server" / "grpc"

# The pipe template with gRPC client logic
PIPE_TEMPLATE = '''\
"""
title: Silverbullet RAG Pipe
author: silverbullet-rag
author_url: https://github.com/silverbullet-rag/silverbullet-rag
version: 0.4.0
description: RAG pipe that queries a Silverbullet knowledge graph via gRPC with folder context support
license: MIT
"""

import json
from typing import Any, Dict, Generator, Iterator, List, Optional, Union

import grpc
from pydantic import BaseModel, Field

# =============================================================================
# Embedded protobuf stubs (generated from proto/rag.proto)
# =============================================================================

{protobuf_code}

# =============================================================================
# Open WebUI Pipe
# =============================================================================


class Pipe:
    """Open WebUI Pipe for Silverbullet RAG via gRPC.

    Features:
    - Folder context injection: Maps Open WebUI folders to Silverbullet pages
      via 'openwebui-folder' frontmatter property
    - Hybrid search: Combines keyword and semantic search per message
    - Search scoping: When folder context is found, searches are scoped to
      the corresponding Silverbullet folder
    """

    class Valves(BaseModel):
        """Configuration valves for the pipe (admin settings)."""

        GRPC_HOST: str = Field(
            default="localhost:50051",
            description="gRPC server address (host:port)"
        )
        MAX_RESULTS: int = Field(
            default=5,
            description="Maximum search results to return"
        )
        SEARCH_TYPE: str = Field(
            default="hybrid",
            description="Search type: 'hybrid', 'semantic', or 'keyword'"
        )
        ENABLE_FOLDER_CONTEXT: bool = Field(
            default=True,
            description="Enable folder-to-page mapping via openwebui-folder frontmatter"
        )

    class UserValves(BaseModel):
        """Per-user configurable settings."""

        # Scope customization
        include_paths: str = Field(
            default="",
            description="Additional folder paths to always include in results (comma-separated, e.g., 'Reference,Shared/Templates')"
        )
        include_tags: str = Field(
            default="",
            description="Tags to always include in results regardless of scope (comma-separated, e.g., 'reference,glossary')"
        )
        scope_mode: str = Field(
            default="prefer",
            description="How to handle folder scoping: 'strict' (only scoped), 'prefer' (scoped first, then global), 'none' (no scoping)"
        )

        # Context budget
        max_context_chars: int = Field(
            default=8000,
            description="Maximum total characters for injected context (0 = unlimited)"
        )
        project_context_chars: int = Field(
            default=4000,
            description="Maximum characters for project/folder context (0 = full page)"
        )
        truncate_results: bool = Field(
            default=True,
            description="Truncate individual search results to fit within budget"
        )

    def __init__(self):
        self.type = "filter"
        self.name = "Silverbullet RAG"
        self.valves = self.Valves()
        self.user_valves = self.UserValves()
        self._channel = None
        self._stub = None
        # Cache folder context per chat to avoid repeated lookups
        self._folder_context_cache: Dict[str, Dict[str, Any]] = {{}}

    def _ensure_connected(self):
        """Lazy initialization of gRPC connection."""
        if self._channel is None:
            self._channel = grpc.insecure_channel(self.valves.GRPC_HOST)
            self._stub = RAGServiceStub(self._channel)

    def pipes(self) -> List[dict]:
        """Return list of available pipes."""
        return [{{"id": "silverbullet_rag", "name": "Silverbullet RAG"}}]

    def _get_folder_path(self, body: dict) -> Optional[str]:
        """Extract folder path from Open WebUI request body.

        Open WebUI passes chat metadata including folder information.
        This extracts the folder path if available.

        Args:
            body: Request body from Open WebUI

        Returns:
            Folder path string or None if not in a folder
        """
        # Check for __metadata__ which contains chat info
        metadata = body.get("__metadata__", {{}})

        # Try to get folder from chat metadata
        chat_info = metadata.get("chat", {{}})
        folder_id = chat_info.get("folder_id")

        if folder_id:
            # If we have folder hierarchy, construct the path
            folders = metadata.get("folders", {{}})
            if folders:
                return self._build_folder_path(folder_id, folders)
            return folder_id

        return None

    def _build_folder_path(self, folder_id: str, folders: dict) -> str:
        """Build folder path from folder hierarchy.

        Args:
            folder_id: Current folder ID
            folders: Dictionary of folder info by ID

        Returns:
            Full folder path like "Projects/MyProject"
        """
        path_parts = []
        current_id = folder_id

        while current_id and current_id in folders:
            folder_info = folders[current_id]
            path_parts.insert(0, folder_info.get("name", current_id))
            current_id = folder_info.get("parent_id")

        return "/".join(path_parts) if path_parts else folder_id

    def _get_folder_context(self, folder_path: str) -> Optional[Dict[str, Any]]:
        """Fetch folder context from the gRPC server.

        Args:
            folder_path: Open WebUI folder path

        Returns:
            Dict with page_name, page_content, folder_scope if found, else None
        """
        try:
            response = self._stub.GetFolderContext(
                GetFolderContextRequest(folder_path=folder_path)
            )

            if response.success and response.found:
                return {{
                    "page_name": response.page_name,
                    "page_content": response.page_content,
                    "folder_scope": response.folder_scope,
                }}
        except grpc.RpcError as e:
            print(f"GetFolderContext error: {{e.code()}}: {{e.details()}}")
        except Exception as e:
            print(f"GetFolderContext error: {{e}}")

        return None

    def _get_user_valves(self, __user__: Optional[dict]) -> "Pipe.UserValves":
        """Get user valves, merging with defaults.

        Args:
            __user__: User dict from Open WebUI (contains 'valves' key)

        Returns:
            UserValves instance with user overrides applied
        """
        if __user__ and "valves" in __user__:
            try:
                return self.UserValves(**__user__["valves"])
            except Exception:
                pass
        return self.user_valves

    def _parse_comma_list(self, value: str) -> List[str]:
        """Parse comma-separated string into list of trimmed values.

        Args:
            value: Comma-separated string

        Returns:
            List of trimmed, non-empty strings
        """
        if not value:
            return []
        return [v.strip() for v in value.split(",") if v.strip()]

    def _truncate_text(self, text: str, max_chars: int) -> str:
        """Truncate text to max characters, ending at word boundary.

        Args:
            text: Text to truncate
            max_chars: Maximum characters (0 = no limit)

        Returns:
            Truncated text with ellipsis if needed
        """
        if max_chars <= 0 or len(text) <= max_chars:
            return text

        # Find last space before limit
        truncated = text[:max_chars]
        last_space = truncated.rfind(" ")
        if last_space > max_chars * 0.7:  # Only use space if reasonably close
            truncated = truncated[:last_space]

        return truncated.rstrip() + "..."

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict,
        __user__: Optional[dict] = None
    ) -> Union[str, Generator, Iterator]:
        """Process messages and inject RAG context.

        This method:
        1. Checks for folder context (maps Open WebUI folder to Silverbullet page)
        2. Injects project/folder context if found
        3. Performs hybrid search (scoped to folder if applicable)
        4. Injects search results as additional context
        5. Applies context budget limits

        Args:
            user_message: The latest user message
            model_id: Selected model ID
            messages: Full conversation history
            body: Request body
            __user__: User info including user valves

        Returns:
            Modified messages with RAG context injected
        """
        self._ensure_connected()

        if not user_message or len(user_message.strip()) < 3:
            return body

        # Get user-specific settings
        uv = self._get_user_valves(__user__)

        # Get chat ID for caching folder context
        chat_id = body.get("__metadata__", {{}}).get("chat", {{}}).get("id", "default")
        folder_scope = None
        folder_context = None

        try:
            # Check for folder context (only on first lookup per chat)
            if self.valves.ENABLE_FOLDER_CONTEXT:
                if chat_id not in self._folder_context_cache:
                    folder_path = self._get_folder_path(body)
                    if folder_path:
                        folder_context = self._get_folder_context(folder_path)
                        self._folder_context_cache[chat_id] = folder_context or {{"_checked": True}}
                    else:
                        self._folder_context_cache[chat_id] = {{"_checked": True}}
                else:
                    cached = self._folder_context_cache[chat_id]
                    if cached and not cached.get("_checked"):
                        folder_context = cached

                if folder_context:
                    folder_scope = folder_context.get("folder_scope")

            # Parse user include paths and tags
            include_paths = self._parse_comma_list(uv.include_paths)
            include_tags = self._parse_comma_list(uv.include_tags)

            # Perform search with scope mode handling
            search_results = self._perform_search(
                query=user_message,
                scope=folder_scope,
                scope_mode=uv.scope_mode,
                include_paths=include_paths,
                include_tags=include_tags,
            )

            # Track context budget
            total_budget = uv.max_context_chars
            remaining_budget = total_budget if total_budget > 0 else float("inf")

            # Build combined context
            context_parts = []

            # Add folder/project context if this is a new chat with folder context
            if folder_context and folder_context.get("page_content"):
                page_name = folder_context.get("page_name", "Project")
                page_content = folder_context.get("page_content", "")

                # Apply project context budget
                if uv.project_context_chars > 0:
                    page_content = self._truncate_text(page_content, uv.project_context_chars)

                project_context = f"# Project Context: {{page_name}}\\n\\n{{page_content}}"

                # Check against total budget
                if remaining_budget == float("inf") or len(project_context) <= remaining_budget:
                    context_parts.append(project_context)
                    if remaining_budget != float("inf"):
                        remaining_budget -= len(project_context)

            # Add search results context within remaining budget
            if search_results and remaining_budget > 100:  # Need at least some space
                search_context = self._build_context(
                    search_results,
                    max_chars=int(remaining_budget) if remaining_budget != float("inf") else 0,
                    truncate=uv.truncate_results,
                )
                if search_context:
                    context_parts.append(f"# Relevant Knowledge\\n\\n{{search_context}}")

            if not context_parts:
                return body

            # Build system message with all context
            full_context = "\\n\\n---\\n\\n".join(context_parts)
            system_message = {{
                "role": "system",
                "content": f"""You have access to the user's Silverbullet knowledge base.

{{full_context}}

Use this information to provide more informed and personalized responses. Reference specific pages or notes when relevant.""",
            }}

            # Insert system message before the last user message
            modified_messages = messages[:-1] + [system_message] + [messages[-1]]
            body["messages"] = modified_messages

        except grpc.RpcError as e:
            print(f"gRPC error: {{e.code()}}: {{e.details()}}")
        except Exception as e:
            print(f"RAG pipe error: {{e}}")

        return body

    def _perform_search(
        self,
        query: str,
        scope: Optional[str] = None,
        scope_mode: str = "prefer",
        include_paths: Optional[List[str]] = None,
        include_tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Perform search with scope mode and include filters.

        Args:
            query: Search query
            scope: Optional folder path to scope results
            scope_mode: How to handle scoping ('strict', 'prefer', 'none')
            include_paths: Additional paths to always include
            include_tags: Tags to always include regardless of scope

        Returns:
            List of search results
        """
        include_paths = include_paths or []
        include_tags = include_tags or []

        try:
            # Request more results if we need to filter/reorder
            fetch_limit = self.valves.MAX_RESULTS
            if scope and scope_mode in ("strict", "prefer"):
                fetch_limit = self.valves.MAX_RESULTS * 3  # Fetch extra for filtering

            if self.valves.SEARCH_TYPE == "hybrid":
                response = self._stub.HybridSearch(
                    HybridSearchRequest(
                        query=query,
                        limit=fetch_limit,
                        filter_tags=list(include_tags) if include_tags else [],
                    )
                )
            elif self.valves.SEARCH_TYPE == "semantic":
                response = self._stub.SemanticSearch(
                    SemanticSearchRequest(
                        query=query,
                        limit=fetch_limit,
                        filter_tags=list(include_tags) if include_tags else [],
                    )
                )
            else:  # keyword
                response = self._stub.Search(
                    SearchRequest(
                        keyword=query,
                        limit=fetch_limit,
                    )
                )

            if not response.success:
                print(f"RAG search error: {{response.error}}")
                return []

            results = json.loads(response.results_json)
            if not results:
                return []

            # Apply scope mode filtering
            if scope_mode == "none" or not scope:
                # No scoping - return results as-is
                return results[: self.valves.MAX_RESULTS]

            elif scope_mode == "strict":
                # Only scoped results + include_paths
                filtered = []
                for r in results:
                    if self._result_in_scope(r, scope):
                        filtered.append(r)
                    elif self._result_in_include_paths(r, include_paths):
                        filtered.append(r)
                    elif self._result_has_include_tags(r, include_tags):
                        filtered.append(r)
                return filtered[: self.valves.MAX_RESULTS]

            else:  # prefer
                # Scoped results first, then others
                scoped = []
                included = []
                other = []

                for r in results:
                    if self._result_in_scope(r, scope):
                        scoped.append(r)
                    elif self._result_in_include_paths(r, include_paths):
                        included.append(r)
                    elif self._result_has_include_tags(r, include_tags):
                        included.append(r)
                    else:
                        other.append(r)

                # Combine: scoped first, then included, then others
                combined = scoped + included + other
                return combined[: self.valves.MAX_RESULTS]

        except Exception as e:
            print(f"Search error: {{e}}")

        return []

    def _result_in_scope(self, result: Dict[str, Any], scope: str) -> bool:
        """Check if a search result is within the folder scope.

        Args:
            result: Search result dict
            scope: Folder scope path

        Returns:
            True if result is in scope
        """
        # Results are nested under 'col0' from the search response
        chunk = result.get("col0", result)
        file_path = chunk.get("file_path", "")

        # Normalize paths and check if file is in scope folder
        # e.g., scope="Projects/MyProject", file="/space/Projects/MyProject/notes.md"
        return scope.lower() in file_path.lower()

    def _result_in_include_paths(self, result: Dict[str, Any], include_paths: List[str]) -> bool:
        """Check if a search result is in one of the include paths.

        Args:
            result: Search result dict
            include_paths: List of folder paths to include

        Returns:
            True if result is in any include path
        """
        if not include_paths:
            return False

        chunk = result.get("col0", result)
        file_path = chunk.get("file_path", "").lower()

        for path in include_paths:
            if path.lower() in file_path:
                return True
        return False

    def _result_has_include_tags(self, result: Dict[str, Any], include_tags: List[str]) -> bool:
        """Check if a search result has any of the include tags.

        Args:
            result: Search result dict
            include_tags: List of tags to include

        Returns:
            True if result has any include tag
        """
        if not include_tags:
            return False

        chunk = result.get("col0", result)
        result_tags = chunk.get("tags", [])
        if isinstance(result_tags, str):
            result_tags = [result_tags]

        result_tags_lower = [t.lower() for t in result_tags]
        for tag in include_tags:
            if tag.lower() in result_tags_lower:
                return True
        return False

    def _build_context(
        self,
        results: List[dict],
        max_chars: int = 0,
        truncate: bool = True,
    ) -> str:
        """Build context text from search results with budget limits.

        Args:
            results: List of search result dictionaries
            max_chars: Maximum characters for context (0 = unlimited)
            truncate: Whether to truncate individual results to fit

        Returns:
            Formatted context string
        """
        if not results:
            return ""

        context_parts = []
        seen_sources = set()
        total_chars = 0

        for result in results[: self.valves.MAX_RESULTS]:
            # Results are nested under 'col0' from the search response
            chunk = result.get("col0", result)

            content = chunk.get("content", "")
            header = chunk.get("header", "Unknown")
            file_path = chunk.get("file_path", chunk.get("page", ""))

            # Skip if no content
            if not content:
                continue

            source = f"{{file_path}}#{{header}}"
            if source in seen_sources:
                continue
            seen_sources.add(source)

            # Build the context entry
            entry = f"## {{header}}\\n{{content}}\\n\\nSource: {{file_path}}"

            # Check budget
            if max_chars > 0:
                separator_len = len("\\n\\n---\\n\\n") if context_parts else 0
                entry_len = len(entry) + separator_len

                if total_chars + entry_len > max_chars:
                    if truncate and total_chars < max_chars:
                        # Truncate this entry to fit remaining budget
                        remaining = max_chars - total_chars - separator_len - 50  # Reserve for header/source
                        if remaining > 100:
                            truncated_content = self._truncate_text(content, remaining)
                            entry = f"## {{header}}\\n{{truncated_content}}\\n\\nSource: {{file_path}}"
                            context_parts.append(entry)
                    break  # Budget exhausted

                total_chars += entry_len

            context_parts.append(entry)

        return "\\n\\n---\\n\\n".join(context_parts)
'''


def generate_stubs_to_temp() -> tuple[str, str]:
    """Generate protobuf stubs to a temporary directory.

    Returns:
        Tuple of (pb2_content, pb2_grpc_content)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Generate stubs
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "grpc_tools.protoc",
                f"--proto_path={PROJECT_ROOT}",
                f"--python_out={tmpdir}",
                f"--grpc_python_out={tmpdir}",
                str(PROTO_FILE),
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"protoc failed: {result.stderr}")
            sys.exit(1)

        # Read generated files
        pb2_file = tmppath / "proto" / "rag_pb2.py"
        pb2_grpc_file = tmppath / "proto" / "rag_pb2_grpc.py"

        pb2_content = pb2_file.read_text()
        pb2_grpc_content = pb2_grpc_file.read_text()

        return pb2_content, pb2_grpc_content


def generate_server_stubs():
    """Regenerate stubs for the server in server/grpc/."""
    print("Generating server stubs...")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={PROJECT_ROOT}",
            f"--python_out={PROJECT_ROOT}",
            f"--grpc_python_out={PROJECT_ROOT}",
            str(PROTO_FILE),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"protoc failed for server: {result.stderr}")
        sys.exit(1)

    # Move generated files from proto/ to server/grpc/
    proto_out = PROJECT_ROOT / "proto"
    pb2_src = proto_out / "rag_pb2.py"
    pb2_grpc_src = proto_out / "rag_pb2_grpc.py"

    if pb2_src.exists():
        # Fix imports in the generated files
        pb2_content = pb2_src.read_text()
        pb2_content = pb2_content.replace(
            'DESCRIPTOR, "proto.rag_pb2"', 'DESCRIPTOR, "server.grpc.rag_pb2"'
        )
        (SERVER_GRPC_DIR / "rag_pb2.py").write_text(pb2_content)
        pb2_src.unlink()

    if pb2_grpc_src.exists():
        pb2_grpc_content = pb2_grpc_src.read_text()
        pb2_grpc_content = pb2_grpc_content.replace(
            "from proto import rag_pb2", "from server.grpc import rag_pb2"
        )
        pb2_grpc_content = pb2_grpc_content.replace(
            "proto.rag_pb2", "server.grpc.rag_pb2"
        )
        pb2_grpc_content = pb2_grpc_content.replace(
            "proto/rag_pb2_grpc.py", "server/grpc/rag_pb2_grpc.py"
        )
        (SERVER_GRPC_DIR / "rag_pb2_grpc.py").write_text(pb2_grpc_content)
        pb2_grpc_src.unlink()

    print(f"  Written: {SERVER_GRPC_DIR / 'rag_pb2.py'}")
    print(f"  Written: {SERVER_GRPC_DIR / 'rag_pb2_grpc.py'}")


def extract_client_code(pb2_content: str, pb2_grpc_content: str) -> str:
    """Extract and merge client-side code from generated stubs.

    Args:
        pb2_content: Content of rag_pb2.py
        pb2_grpc_content: Content of rag_pb2_grpc.py

    Returns:
        Merged Python code for embedding in the pipe
    """
    # Fix the pb2 imports to be self-contained
    pb2_fixed = pb2_content
    pb2_fixed = pb2_fixed.replace(
        'DESCRIPTOR, "proto.rag_pb2"', 'DESCRIPTOR, "__embedded_rag_pb2__"'
    )

    # Extract just the RAGServiceStub class from pb2_grpc
    stub_match = re.search(
        r"(class RAGServiceStub\(object\):.*?)(?=\n\nclass |\nclass RAGServiceServicer|\Z)",
        pb2_grpc_content,
        re.DOTALL,
    )

    if not stub_match:
        print("Could not find RAGServiceStub class")
        sys.exit(1)

    stub_code = stub_match.group(1)

    # Fix the stub imports to reference local module
    stub_code = stub_code.replace("proto_dot_rag__pb2.", "")

    # Combine pb2 and stub
    combined = f"{pb2_fixed}\n\n# gRPC Stub\n{stub_code}"

    return combined


def build_pipe():
    """Main build function."""
    print("Building Open WebUI pipe...")

    # Generate stubs to temp and extract
    print("Generating protobuf stubs...")
    pb2_content, pb2_grpc_content = generate_stubs_to_temp()

    # Extract client code
    print("Extracting client code...")
    protobuf_code = extract_client_code(pb2_content, pb2_grpc_content)

    # Generate final pipe
    print("Generating pipe file...")
    pipe_content = PIPE_TEMPLATE.format(protobuf_code=protobuf_code)

    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(pipe_content)
    print(f"  Written: {OUTPUT_FILE}")

    # Also regenerate server stubs
    generate_server_stubs()

    print("\nDone!")


if __name__ == "__main__":
    build_pipe()
