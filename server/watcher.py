"""File watcher for automatic reindexing."""

import hashlib
import os
import time
import logging
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .db import GraphDB
from .parser import SpaceParser
from .config_parser import parse_config_page, write_config_json


class SpaceWatcher(FileSystemEventHandler):
    """Handle file system events in the Silverbullet space."""

    def __init__(
        self,
        space_path: str,
        graph_db: GraphDB = None,
        parser: SpaceParser = None,
        db_path: str = None,
    ):
        self.space_path = space_path
        self.graph_db = graph_db if graph_db else GraphDB("/db")
        self.parser = parser if parser else SpaceParser()
        self.db_path = db_path or os.getenv("DB_PATH", "/data/ladybug")
        self.debounce_time = {}
        self.processing_lock = threading.Lock()
        self.currently_processing = set()
        self.file_hashes = {}  # Track content hashes to avoid unnecessary reindexing

    def _compute_file_hash(self, path: str) -> str | None:
        """Compute MD5 hash of file contents.

        Args:
            path: Path to the file

        Returns:
            MD5 hash string, or None if file cannot be read
        """
        try:
            with open(path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logging.debug(f"Could not hash {path}: {e}")
            return None

    def _has_content_changed(self, path: str) -> bool:
        """Check if file content has actually changed since last indexing.

        Args:
            path: Path to the file

        Returns:
            True if content has changed or file is new, False otherwise
        """
        current_hash = self._compute_file_hash(path)
        if current_hash is None:
            return True  # Assume changed if we can't read it

        previous_hash = self.file_hashes.get(path)
        if previous_hash is None:
            # New file, hasn't been indexed before
            return True

        if current_hash == previous_hash:
            logging.debug(
                f"Skipping {path} - content unchanged (hash: {current_hash[:8]}...)"
            )
            return False

        return True

    def _update_file_hash(self, path: str):
        """Update the stored hash for a file after successful indexing."""
        current_hash = self._compute_file_hash(path)
        if current_hash:
            self.file_hashes[path] = current_hash

    def _should_process(self, path: str) -> bool:
        """Check if file should be processed (debouncing, deduplication, and content check)."""
        now = time.time()
        last_time = self.debounce_time.get(path, 0)

        # Debounce: only process if 5 seconds have passed since last processing
        if now - last_time < 5.0:
            return False

        # Check if already being processed
        with self.processing_lock:
            if path in self.currently_processing:
                logging.debug(f"Skipping {path} - already being processed")
                return False

        # Check if content has actually changed
        if not self._has_content_changed(path):
            # Update debounce time even for unchanged files to prevent repeated checks
            self.debounce_time[path] = now
            return False

        return True

    def _mark_processing(self, path: str) -> bool:
        """Mark a file as being processed. Returns False if already processing."""
        with self.processing_lock:
            if path in self.currently_processing:
                return False
            self.currently_processing.add(path)
            self.debounce_time[path] = time.time()
            return True

    def _unmark_processing(self, path: str):
        """Unmark a file as being processed."""
        with self.processing_lock:
            self.currently_processing.discard(path)

    def on_modified(self, event):
        """Handle file modification."""
        if event.is_directory or not event.src_path.endswith(".md"):
            return

        if not self._should_process(event.src_path):
            return

        logging.info(f"File modified: {event.src_path}")
        self._reindex_file(event.src_path)

    def on_created(self, event):
        """Handle file creation."""
        if event.is_directory or not event.src_path.endswith(".md"):
            return

        if not self._should_process(event.src_path):
            return

        logging.info(f"File created: {event.src_path}")
        self._reindex_file(event.src_path)

    def on_deleted(self, event):
        """Handle file deletion."""
        if event.is_directory or not event.src_path.endswith(".md"):
            return

        logging.info(f"File deleted: {event.src_path}")

        # Remove deleted file's chunks from graph
        try:
            self.graph_db.delete_chunks_by_file(event.src_path)
            logging.info(f"Deleted chunks for {event.src_path}")
        except Exception as e:
            logging.error(f"Error deleting chunks: {e}")

    def _handle_config_change(self, file_path: str) -> None:
        """Parse CONFIG.md and write space_config.json.

        This extracts config.set() values from space-lua blocks and writes
        them to a JSON file that the MCP server can read.

        Args:
            file_path: Path to the CONFIG.md file
        """
        try:
            content = Path(file_path).read_text(encoding="utf-8")
            config = parse_config_page(content)
            db_path = Path(self.db_path)
            write_config_json(config, db_path)
            logging.info(f"Updated space_config.json from {file_path}")
        except Exception as e:
            logging.error(f"Failed to parse CONFIG.md: {e}")

    def _reindex_file(self, file_path: str):
        """Reindex a single file instead of the entire space."""
        if not self._mark_processing(file_path):
            logging.debug(f"Skipping {file_path} - already being processed")
            return

        try:
            # Special handling for CONFIG.md - parse config values
            if file_path.endswith("CONFIG.md"):
                self._handle_config_change(file_path)

            # Delete existing chunks for this file
            self.graph_db.delete_chunks_by_file(file_path)

            # Parse only the changed file
            chunks = self.parser.parse_file(file_path)
            if chunks:
                self.graph_db.index_chunks(chunks)
                logging.info(f"Reindexed {len(chunks)} chunks from {file_path}")
            else:
                logging.info(f"No chunks found in {file_path}")

            # Update hash after successful indexing
            self._update_file_hash(file_path)
        except Exception as e:
            logging.error(f"Reindexing error for {file_path}: {e}")
        finally:
            self._unmark_processing(file_path)

    def reindex_all(self):
        """Reindex the entire space. Use for initial indexing."""
        try:
            chunks = self.parser.parse_space(self.space_path)
            self.graph_db.index_chunks(chunks)
            logging.info(f"Reindexed {len(chunks)} chunks from entire space")

            # Build initial hash cache for all markdown files
            space_path = Path(self.space_path)
            for md_file in space_path.glob("**/*.md"):
                self._update_file_hash(str(md_file))
            logging.info(f"Cached hashes for {len(self.file_hashes)} files")
        except Exception as e:
            logging.error(f"Full reindexing error: {e}")


def watch_space(space_path: str = "/space"):
    """Start watching the Silverbullet space for changes.

    Args:
        space_path: Path to the space directory
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    event_handler = SpaceWatcher(space_path)
    observer = Observer()
    observer.schedule(event_handler, space_path, recursive=True)

    logging.info(f"Starting file watcher on {space_path}")
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logging.info("File watcher stopped")

    observer.join()


# Alias for backward compatibility
SpaceEventHandler = SpaceWatcher


if __name__ == "__main__":
    watch_space()
