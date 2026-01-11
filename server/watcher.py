"""File watcher for automatic reindexing."""

import time
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .db import GraphDB
from .parser import SpaceParser


class SpaceWatcher(FileSystemEventHandler):
    """Handle file system events in the Silverbullet space."""

    def __init__(self, space_path: str, graph_db: GraphDB = None, parser: SpaceParser = None):
        self.space_path = space_path
        self.graph_db = graph_db if graph_db else GraphDB("/db")
        self.parser = parser if parser else SpaceParser()
        self.debounce_time = {}

    def _should_process(self, path: str) -> bool:
        """Check if file should be processed (debouncing)."""
        now = time.time()
        last_time = self.debounce_time.get(path, 0)

        # Debounce: only process if 1 second has passed
        if now - last_time < 1.0:
            return False

        self.debounce_time[path] = now
        return True

    def on_modified(self, event):
        """Handle file modification."""
        if event.is_directory or not event.src_path.endswith('.md'):
            return

        if not self._should_process(event.src_path):
            return

        logging.info(f"File modified: {event.src_path}")
        self._reindex()

    def on_created(self, event):
        """Handle file creation."""
        if event.is_directory or not event.src_path.endswith('.md'):
            return

        logging.info(f"File created: {event.src_path}")
        self._reindex()

    def on_deleted(self, event):
        """Handle file deletion."""
        if event.is_directory or not event.src_path.endswith('.md'):
            return

        logging.info(f"File deleted: {event.src_path}")

        # Remove deleted file's chunks from graph
        try:
            self.graph_db.delete_chunks_by_file(event.src_path)
            logging.info(f"Deleted chunks for {event.src_path}")
        except Exception as e:
            logging.error(f"Error deleting chunks: {e}")

    def _reindex(self):
        """Reindex the entire space."""
        try:
            chunks = self.parser.parse_space(self.space_path)
            self.graph_db.index_chunks(chunks)
            logging.info(f"Reindexed {len(chunks)} chunks")
        except Exception as e:
            logging.error(f"Reindexing error: {e}")


def watch_space(space_path: str = "/space"):
    """Start watching the Silverbullet space for changes.

    Args:
        space_path: Path to the space directory
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
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
