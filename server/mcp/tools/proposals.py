"""Proposal-related MCP tools."""

import logging
from typing import Any, Dict

from ..dependencies import get_dependencies
from ...proposals import (
    get_proposal_path,
    page_exists,
    find_proposals,
    create_proposal_content,
    get_proposals_config,
)

logger = logging.getLogger(__name__)


def _check_proposals_enabled() -> Dict[str, Any] | None:
    """Check if proposals are enabled. Returns error dict if not."""
    deps = get_dependencies()
    if not deps.proposals_enabled:
        return {"success": False, "error": "Proposals library not installed"}
    return None


async def propose_change(
    target_page: str,
    content: str,
    title: str,
    description: str,
) -> Dict[str, Any]:
    """
    Propose a change to a page. Requires Proposals library installed.

    Creates a proposal that the user can review and apply in Silverbullet.
    The change is NOT applied until the user accepts it.

    Args:
        target_page: Page path (e.g., 'Projects/MyProject.md')
        content: Proposed page content
        title: Short title for the proposal
        description: Explanation of why this change is proposed

    Returns:
        Proposal path and status
    """
    if error := _check_proposals_enabled():
        error["instructions"] = "Install the Proposals library from Library Manager"
        return error

    try:
        deps = get_dependencies()

        # Security check - prevent path traversal
        file_path = deps.space_path / target_page
        if not file_path.resolve().is_relative_to(deps.space_path.resolve()):
            return {"success": False, "error": f"Invalid page name: {target_page}"}

        # Get config for path prefix
        proposals_config = get_proposals_config(deps.db_path)
        prefix = proposals_config.get("path_prefix", "_Proposals/")

        is_new_page = not page_exists(deps.space_path, target_page)
        proposal_path = get_proposal_path(target_page, prefix)

        proposal_content = create_proposal_content(
            target_page=target_page,
            content=content,
            title=title,
            description=description,
            is_new_page=is_new_page,
        )

        # Write proposal file
        full_path = deps.space_path / proposal_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(proposal_content, encoding="utf-8")

        logger.info(f"Created proposal: {proposal_path}")

        return {
            "success": True,
            "proposal_path": proposal_path,
            "is_new_page": is_new_page,
            "message": f"Proposal created. User can review at {proposal_path}",
        }
    except Exception as e:
        logger.error(f"Failed to create proposal: {e}")
        return {"success": False, "error": str(e)}


async def list_proposals(status: str = "pending") -> Dict[str, Any]:
    """
    List change proposals by status.

    Args:
        status: Filter by proposal status ('pending', 'accepted', 'rejected', 'all')

    Returns:
        List of proposals with summary information
    """
    if error := _check_proposals_enabled():
        return error

    try:
        deps = get_dependencies()

        proposals_config = get_proposals_config(deps.db_path)
        prefix = proposals_config.get("path_prefix", "_Proposals/")

        proposals = find_proposals(deps.space_path, prefix, status)

        return {"success": True, "count": len(proposals), "proposals": proposals}
    except Exception as e:
        logger.error(f"Failed to list proposals: {e}")
        return {"success": False, "error": str(e)}


async def withdraw_proposal(proposal_path: str) -> Dict[str, Any]:
    """
    Withdraw a pending proposal.

    Args:
        proposal_path: Path to the .proposal file

    Returns:
        Success confirmation
    """
    if error := _check_proposals_enabled():
        return error

    try:
        deps = get_dependencies()

        full_path = deps.space_path / proposal_path
        if not full_path.resolve().is_relative_to(deps.space_path.resolve()):
            return {
                "success": False,
                "error": f"Invalid proposal path: {proposal_path}",
            }

        if not full_path.exists():
            return {"success": False, "error": "Proposal not found"}

        if not proposal_path.endswith(".proposal"):
            return {"success": False, "error": "Not a proposal file"}

        full_path.unlink()
        logger.info(f"Withdrew proposal: {proposal_path}")

        return {"success": True, "message": "Proposal withdrawn"}
    except Exception as e:
        logger.error(f"Failed to withdraw proposal: {e}")
        return {"success": False, "error": str(e)}
