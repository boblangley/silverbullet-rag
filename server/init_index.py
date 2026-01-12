"""Initialize the RAG index by parsing and indexing the Silverbullet space."""

import argparse
import os
import logging
import sys

from .db import GraphDB
from .parser import SpaceParser


def init_index(
    space_path: str = None,
    db_path: str = None,
    enable_embeddings: bool = None,
    rebuild: bool = False,
) -> int:
    """Parse the Silverbullet space and index all content.

    Args:
        space_path: Path to the Silverbullet space (default: SPACE_PATH env or /space)
        db_path: Path to the database directory (default: DB_PATH env or /data/ladybug)
        enable_embeddings: Whether to generate embeddings (default: ENABLE_EMBEDDINGS env or True)
        rebuild: If True, clear the database before indexing (default: False)

    Returns:
        Number of chunks indexed
    """
    # Get configuration from environment or arguments
    space_path = space_path or os.getenv("SPACE_PATH", "/space")
    db_path = db_path or os.getenv("DB_PATH", "/data/ladybug")

    if enable_embeddings is None:
        enable_embeddings = os.getenv("ENABLE_EMBEDDINGS", "true").lower() == "true"

    logging.info("Initializing index...")
    logging.info(f"  Space path: {space_path}")
    logging.info(f"  Database path: {db_path}")
    logging.info(f"  Embeddings enabled: {enable_embeddings}")
    logging.info(f"  Rebuild mode: {rebuild}")

    # Initialize parser and database
    parser = SpaceParser()
    db = GraphDB(db_path, enable_embeddings=enable_embeddings)

    # Clear database if rebuild requested
    if rebuild:
        logging.info("Rebuild requested - clearing existing data...")
        db.clear_database()

    # Parse the space
    logging.info("Parsing space...")
    chunks = parser.parse_space(space_path)
    logging.info(f"Found {len(chunks)} chunks")

    # Index folder hierarchy
    logging.info("Indexing folder hierarchy...")
    folder_paths = parser.get_folder_paths(space_path)
    index_pages = parser.get_folder_index_pages(space_path)
    db.index_folders(folder_paths, index_pages)
    logging.info(f"Indexed {len(folder_paths)} folders")

    # Index chunks (this also generates embeddings if enabled)
    logging.info("Indexing chunks...")
    db.index_chunks(chunks)
    logging.info(f"Indexed {len(chunks)} chunks")

    logging.info("Index initialization complete!")
    return len(chunks)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Initialize the RAG index for a Silverbullet space"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Clear the database and rebuild from scratch",
    )
    parser.add_argument(
        "--space-path",
        type=str,
        default=None,
        help="Path to the Silverbullet space (default: SPACE_PATH env or /space)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to the database directory (default: DB_PATH env or /data/ladybug)",
    )
    parser.add_argument(
        "--no-embeddings", action="store_true", help="Disable embedding generation"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Determine embeddings setting
    enable_embeddings = None
    if args.no_embeddings:
        enable_embeddings = False

    try:
        count = init_index(
            space_path=args.space_path,
            db_path=args.db_path,
            enable_embeddings=enable_embeddings,
            rebuild=args.rebuild,
        )
        logging.info(f"Successfully indexed {count} chunks")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Failed to initialize index: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
