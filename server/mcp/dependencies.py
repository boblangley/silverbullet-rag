"""Dependency container for MCP server."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..db.graph import GraphDB
from ..parser.space_parser import SpaceParser
from ..search import HybridSearch
from ..proposals import library_installed

logger = logging.getLogger(__name__)


@dataclass
class Dependencies:
    """Container for MCP server dependencies."""

    graph_db: GraphDB
    space_parser: SpaceParser
    hybrid_search: HybridSearch
    space_path: Path
    db_path: Path
    proposals_enabled: bool = False


# Singleton instance
_deps: Optional[Dependencies] = None


def get_dependencies() -> Dependencies:
    """Get the initialized dependencies. Raises if not initialized."""
    if _deps is None:
        raise RuntimeError("Dependencies not initialized. Call initialize() first.")
    return _deps


def refresh_proposals_status() -> None:
    """Refresh the proposals_enabled status after library installation.

    Call this after installing or updating a library to update the
    proposals_enabled flag without restarting the server.
    """
    global _deps
    if _deps is not None:
        _deps.proposals_enabled = library_installed(_deps.space_path)
        if _deps.proposals_enabled:
            logger.info("Proposals library detected, proposal tools enabled")
        else:
            logger.info("Proposals library not detected, proposal tools disabled")


async def initialize() -> Dependencies:
    """Initialize all dependencies."""
    global _deps

    logger.info("Initializing Silverbullet RAG server...")

    db_path = Path(os.getenv("DB_PATH", "/data/ladybug"))
    space_path = Path(os.getenv("SPACE_PATH", "/space"))

    logger.info(f"Initializing GraphDB at {db_path} (read-only)...")
    graph_db = GraphDB(str(db_path), read_only=True)

    logger.info(f"Initializing SpaceParser for {space_path}...")
    space_parser = SpaceParser(str(space_path))

    hybrid_search = HybridSearch(graph_db)

    proposals_enabled = library_installed(space_path)
    if proposals_enabled:
        logger.info("Proposals library found, proposal tools enabled")
    else:
        logger.info("Proposals library not installed, proposal tools disabled")

    _deps = Dependencies(
        graph_db=graph_db,
        space_parser=space_parser,
        hybrid_search=hybrid_search,
        space_path=space_path,
        db_path=db_path,
        proposals_enabled=proposals_enabled,
    )

    logger.info("Server initialization complete!")
    return _deps
