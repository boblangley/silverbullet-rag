"""Page-related MCP tools."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ..dependencies import get_dependencies

logger = logging.getLogger(__name__)


async def read_page(page_name: str) -> Dict[str, Any]:
    """
    Read the contents of a Silverbullet page.

    Args:
        page_name: Name of the page (e.g., 'MyPage.md')

    Returns:
        Page content as string
    """
    try:
        deps = get_dependencies()
        file_path = deps.space_path / page_name

        # Security check - prevent path traversal
        if not file_path.resolve().is_relative_to(deps.space_path.resolve()):
            return {"success": False, "error": f"Invalid page name: {page_name}"}

        if not file_path.exists():
            return {"success": False, "error": f"Page '{page_name}' not found"}

        content = file_path.read_text(encoding="utf-8")
        return {"success": True, "content": content}
    except Exception as e:
        logger.error(f"Failed to read page '{page_name}': {e}")
        return {"success": False, "error": str(e)}


async def get_project_context(
    github_remote: Optional[str] = None, folder_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get project context from Silverbullet space by GitHub remote or folder path.

    This tool finds and returns the project index page and related metadata.
    Use this to inject relevant context when working on a project.

    IMPORTANT: When using github_remote, first check the actual git remote of the
    repository (e.g., `git remote -v`) rather than guessing. The remote format
    should be "owner/repo" (e.g., "boblangley/silverbullet-rag").

    Args:
        github_remote: GitHub repository in "owner/repo" format. Get this from
            `git remote -v` output, not by guessing from the repo name.
        folder_path: Folder path in Silverbullet space (e.g., "Projects/MyProject")

    Returns:
        Project context including index page content, frontmatter, and related pages
    """
    try:
        deps = get_dependencies()
        space_path = deps.space_path

        if not github_remote and not folder_path:
            return {
                "success": False,
                "error": "Must provide either github_remote or folder_path",
            }

        project_file = None
        frontmatter = {}

        # Search by GitHub remote
        if github_remote:
            for md_file in space_path.glob("**/*.md"):
                fm = deps.space_parser.get_frontmatter(str(md_file))
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
                index_file = space_path / parent / f"{parts[-1]}.md"
            else:
                index_file = space_path / f"{folder_path}.md"

            if index_file.exists():
                project_file = index_file
                frontmatter = deps.space_parser.get_frontmatter(str(index_file))
            else:
                # Try looking for any .md file in the folder with project metadata
                folder_dir = space_path / folder_path
                if folder_dir.exists() and folder_dir.is_dir():
                    for md_file in folder_dir.glob("*.md"):
                        fm = deps.space_parser.get_frontmatter(str(md_file))
                        if fm:
                            project_file = md_file
                            frontmatter = fm
                            break

        if not project_file:
            return {
                "success": False,
                "error": f"No project found for github_remote={github_remote}, folder_path={folder_path}",
            }

        # Read the project file content
        content = project_file.read_text(encoding="utf-8")

        # Strip frontmatter from content for display
        clean_content = deps.space_parser._strip_frontmatter(content)

        # Get related pages from the same folder
        relative_path = project_file.relative_to(space_path)
        folder = relative_path.parent

        related_pages = []
        if folder != Path("."):
            folder_dir = space_path / folder
            for md_file in folder_dir.glob("*.md"):
                if md_file != project_file:
                    related_pages.append(
                        {
                            "name": md_file.stem,
                            "path": str(md_file.relative_to(space_path)),
                        }
                    )

        # Also check for subdirectory matching the project file name
        project_subdir = project_file.parent / project_file.stem
        if project_subdir.exists() and project_subdir.is_dir():
            for md_file in project_subdir.glob("**/*.md"):
                related_pages.append(
                    {"name": md_file.stem, "path": str(md_file.relative_to(space_path))}
                )

        return {
            "success": True,
            "project": {
                "file": str(relative_path),
                "github": frontmatter.get("github"),
                "tags": frontmatter.get("tags", []),
                "concerns": frontmatter.get("concerns", []),
                "content": clean_content,
            },
            "related_pages": related_pages[:20],
        }

    except Exception as e:
        logger.error(f"Failed to get project context: {e}")
        return {"success": False, "error": str(e)}
