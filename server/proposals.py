"""
Proposal management for Silverbullet Proposals system.

This module provides utilities for managing change proposals that external tools
can create for user review. Proposals are stored as .proposal files in the
Silverbullet space.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .config_parser import load_config_json


def library_installed(space_path: Path) -> bool:
    """Check if Proposals library is installed in the space.

    The library is considered installed if Library/Proposals.md exists.

    Args:
        space_path: Path to the Silverbullet space

    Returns:
        True if library marker file exists
    """
    library_marker = space_path / "Library" / "Proposals.md"
    return library_marker.exists()


def get_proposal_path(target_page: str, prefix: str = "_Proposals/") -> str:
    """Generate proposal file path from target page.

    Args:
        target_page: Target page path (e.g., "Projects/MyProject.md")
        prefix: Path prefix for proposals (default: "_Proposals/")

    Returns:
        Proposal file path (e.g., "_Proposals/Projects/MyProject.md.proposal")
    """
    return f"{prefix}{target_page}.proposal"


def page_exists(space_path: Path, page: str) -> bool:
    """Check if a page exists in the space.

    Args:
        space_path: Path to the Silverbullet space
        page: Page path relative to space

    Returns:
        True if the page file exists
    """
    return (space_path / page).exists()


def parse_proposal_file(content: str) -> Dict[str, Any]:
    """Parse a .proposal file and return metadata + body.

    Args:
        content: Raw content of the .proposal file

    Returns:
        Dict with "metadata" (parsed frontmatter) and "body" (content after frontmatter)
    """
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if not match:
        return {"metadata": {}, "body": content}

    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        metadata = {}

    return {"metadata": metadata, "body": match.group(2).strip()}


def find_proposals(
    space_path: Path, prefix: str, status: str = "pending"
) -> List[Dict[str, Any]]:
    """Find all proposals matching status.

    Args:
        space_path: Path to the Silverbullet space
        prefix: Path prefix where proposals are stored
        status: Filter by status ("pending", "accepted", "rejected", or "all")

    Returns:
        List of proposal metadata dicts
    """
    proposals = []
    proposals_dir = space_path / prefix.rstrip("/")

    if not proposals_dir.exists():
        return []

    for proposal_file in proposals_dir.glob("**/*.proposal"):
        try:
            content = proposal_file.read_text(encoding="utf-8")
            parsed = parse_proposal_file(content)
            meta = parsed["metadata"]

            proposal_status = meta.get("status", "pending")
            if status == "all" or proposal_status == status:
                proposals.append(
                    {
                        "path": str(proposal_file.relative_to(space_path)),
                        "target_page": meta.get("target_page"),
                        "title": meta.get("title"),
                        "description": meta.get("description"),
                        "status": proposal_status,
                        "is_new_page": meta.get("is_new_page", False),
                        "proposed_by": meta.get("proposed_by"),
                        "created_at": meta.get("created_at"),
                    }
                )
        except Exception:
            # Skip files that can't be parsed
            continue

    # Sort by created_at descending (newest first)
    proposals.sort(key=lambda p: p.get("created_at") or "", reverse=True)

    return proposals


def create_proposal_content(
    target_page: str,
    content: str,
    title: str,
    description: str,
    is_new_page: bool,
    proposed_by: str = "claude-code",
) -> str:
    """Generate the full .proposal file content.

    Args:
        target_page: Target page path
        content: Proposed page content
        title: Short title for the proposal
        description: Why this change is proposed
        is_new_page: Whether this creates a new page
        proposed_by: Identifier of the proposer

    Returns:
        Complete .proposal file content with YAML frontmatter
    """
    # Escape any special characters in strings for YAML
    # Using yaml.dump for the frontmatter to handle escaping properly
    frontmatter = {
        "type": "proposal",
        "target_page": target_page,
        "title": title,
        "description": description,
        "proposed_by": proposed_by,
        "created_at": datetime.now().isoformat(),
        "status": "pending",
        "is_new_page": is_new_page,
    }

    yaml_frontmatter = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)

    return f"---\n{yaml_frontmatter}---\n\n{content}\n"


def get_proposals_config(db_path: Path) -> Dict[str, Any]:
    """Get proposal-related configuration from space config.

    Args:
        db_path: Path to the database file (e.g., /data/ladybug)

    Returns:
        Dict with proposal config (path_prefix, cleanup_after_days, etc.)
    """
    config = load_config_json(db_path)
    return config.get("mcp", {}).get("proposals", {})
