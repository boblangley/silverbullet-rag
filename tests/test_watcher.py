"""Tests for the file watcher module."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from server.watcher import SpaceWatcher


class TestSpaceWatcherInit:
    """Tests for SpaceWatcher initialization."""

    def test_init_with_defaults(self, temp_space_path, temp_db_path):
        """Test initialization with default values."""
        from server.db.graph import GraphDB

        # Must provide a graph_db since default path /db is not accessible
        graph_db = GraphDB(temp_db_path)
        watcher = SpaceWatcher(temp_space_path, graph_db=graph_db)

        assert watcher.space_path == temp_space_path
        assert watcher.graph_db is not None
        assert watcher.parser is not None
        assert watcher.debounce_time == {}
        assert watcher.currently_processing == set()
        assert watcher.file_hashes == {}

    def test_init_with_custom_db(self, temp_space_path, temp_db_path):
        """Test initialization with custom database."""
        from server.db.graph import GraphDB

        graph_db = GraphDB(temp_db_path)
        watcher = SpaceWatcher(temp_space_path, graph_db=graph_db)

        assert watcher.graph_db is graph_db

    def test_init_with_custom_parser(self, temp_space_path, temp_db_path):
        """Test initialization with custom parser."""
        from server.db.graph import GraphDB
        from server.parser import SpaceParser

        parser = SpaceParser()
        graph_db = GraphDB(temp_db_path)
        watcher = SpaceWatcher(temp_space_path, graph_db=graph_db, parser=parser)

        assert watcher.parser is parser

    def test_init_uses_db_path_env_var(
        self, temp_space_path, temp_db_path, monkeypatch
    ):
        """Test that SpaceWatcher uses DB_PATH env var for GraphDB."""
        monkeypatch.setenv("DB_PATH", temp_db_path)

        # Create watcher without passing graph_db - should use DB_PATH env var
        watcher = SpaceWatcher(temp_space_path)

        assert watcher.db_path == temp_db_path
        assert watcher.graph_db is not None


class TestHashCaching:
    """Tests for file hash caching functionality."""

    def test_compute_file_hash(self, temp_space_path, temp_db_path):
        """Test computing MD5 hash of file contents."""
        from server.db.graph import GraphDB

        # Create a test file
        test_file = Path(temp_space_path) / "test.md"
        test_file.write_text("# Test content")

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )
        hash1 = watcher._compute_file_hash(str(test_file))

        assert hash1 is not None
        assert len(hash1) == 32  # MD5 hash length

    def test_compute_file_hash_same_content(self, temp_space_path, temp_db_path):
        """Test that same content produces same hash."""
        from server.db.graph import GraphDB

        # Create two files with same content
        file1 = Path(temp_space_path) / "file1.md"
        file2 = Path(temp_space_path) / "file2.md"
        content = "# Same content"
        file1.write_text(content)
        file2.write_text(content)

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )

        assert watcher._compute_file_hash(str(file1)) == watcher._compute_file_hash(
            str(file2)
        )

    def test_compute_file_hash_different_content(self, temp_space_path, temp_db_path):
        """Test that different content produces different hash."""
        from server.db.graph import GraphDB

        file1 = Path(temp_space_path) / "file1.md"
        file2 = Path(temp_space_path) / "file2.md"
        file1.write_text("# Content A")
        file2.write_text("# Content B")

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )

        assert watcher._compute_file_hash(str(file1)) != watcher._compute_file_hash(
            str(file2)
        )

    def test_compute_file_hash_nonexistent(self, temp_space_path, temp_db_path):
        """Test computing hash of nonexistent file returns None."""
        from server.db.graph import GraphDB

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )
        result = watcher._compute_file_hash("/nonexistent/file.md")

        assert result is None

    def test_update_file_hash(self, temp_space_path, temp_db_path):
        """Test updating stored hash for a file."""
        from server.db.graph import GraphDB

        test_file = Path(temp_space_path) / "test.md"
        test_file.write_text("# Test")

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )
        watcher._update_file_hash(str(test_file))

        assert str(test_file) in watcher.file_hashes
        assert len(watcher.file_hashes[str(test_file)]) == 32

    def test_has_content_changed_new_file(self, temp_space_path, temp_db_path):
        """Test content change detection for new file."""
        from server.db.graph import GraphDB

        test_file = Path(temp_space_path) / "test.md"
        test_file.write_text("# Test")

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )

        # New file should be considered changed
        assert watcher._has_content_changed(str(test_file)) is True

    def test_has_content_changed_unchanged(self, temp_space_path, temp_db_path):
        """Test content change detection for unchanged file."""
        from server.db.graph import GraphDB

        test_file = Path(temp_space_path) / "test.md"
        test_file.write_text("# Test")

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )

        # Cache the hash
        watcher._update_file_hash(str(test_file))

        # Same content should not be considered changed
        assert watcher._has_content_changed(str(test_file)) is False

    def test_has_content_changed_modified(self, temp_space_path, temp_db_path):
        """Test content change detection for modified file."""
        from server.db.graph import GraphDB

        test_file = Path(temp_space_path) / "test.md"
        test_file.write_text("# Original")

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )

        # Cache the hash
        watcher._update_file_hash(str(test_file))

        # Modify the file
        test_file.write_text("# Modified")

        # Modified content should be considered changed
        assert watcher._has_content_changed(str(test_file)) is True


class TestDebouncingAndDeduplication:
    """Tests for debouncing and deduplication logic."""

    def test_should_process_first_time(self, temp_space_path, temp_db_path):
        """Test that first processing is allowed."""
        from server.db.graph import GraphDB

        test_file = Path(temp_space_path) / "test.md"
        test_file.write_text("# Test")

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )

        assert watcher._should_process(str(test_file)) is True

    def test_should_process_debounce(self, temp_space_path, temp_db_path):
        """Test that rapid re-processing is debounced."""
        from server.db.graph import GraphDB

        test_file = Path(temp_space_path) / "test.md"
        test_file.write_text("# Test")

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )

        # First processing
        watcher.debounce_time[str(test_file)] = time.time()

        # Immediate re-processing should be debounced
        assert watcher._should_process(str(test_file)) is False

    def test_mark_processing(self, temp_space_path, temp_db_path):
        """Test marking a file as being processed."""
        from server.db.graph import GraphDB

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )
        path = "/test/file.md"

        # First mark should succeed
        assert watcher._mark_processing(path) is True
        assert path in watcher.currently_processing

        # Second mark should fail
        assert watcher._mark_processing(path) is False

    def test_unmark_processing(self, temp_space_path, temp_db_path):
        """Test unmarking a file as being processed."""
        from server.db.graph import GraphDB

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )
        path = "/test/file.md"

        watcher._mark_processing(path)
        watcher._unmark_processing(path)

        assert path not in watcher.currently_processing


class TestConfigMDHandling:
    """Tests for CONFIG.md special handling."""

    def test_handle_config_change(self, temp_space_path, temp_db_path):
        """Test parsing CONFIG.md and writing space_config.json."""
        from server.db.graph import GraphDB

        # Create CONFIG.md with config values
        config_file = Path(temp_space_path) / "CONFIG.md"
        config_file.write_text("""# Configuration

```space-lua
config.set("mcp.proposals.path_prefix", "_Proposals/")
config.set("mcp.proposals.cleanup_after_days", 30)
```
""")

        # Create db directory structure
        db_path = Path(temp_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=str(db_path)
        )
        watcher._handle_config_change(str(config_file))

        # Check that space_config.json was created
        config_json_path = db_path.parent / "space_config.json"
        assert config_json_path.exists()

        config = json.loads(config_json_path.read_text())
        assert config == {
            "mcp": {
                "proposals": {"path_prefix": "_Proposals/", "cleanup_after_days": 30}
            }
        }

    def test_handle_config_change_empty(self, temp_space_path, temp_db_path):
        """Test handling CONFIG.md with no config values."""
        from server.db.graph import GraphDB

        config_file = Path(temp_space_path) / "CONFIG.md"
        config_file.write_text("# Just a header\n\nNo config here.")

        db_path = Path(temp_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=str(db_path)
        )
        watcher._handle_config_change(str(config_file))

        config_json_path = db_path.parent / "space_config.json"
        assert config_json_path.exists()

        config = json.loads(config_json_path.read_text())
        assert config == {}

    def test_reindex_file_calls_handle_config_change(
        self, temp_space_path, temp_db_path
    ):
        """Test that _reindex_file calls _handle_config_change for CONFIG.md."""
        from server.db.graph import GraphDB

        config_file = Path(temp_space_path) / "CONFIG.md"
        config_file.write_text("""```space-lua
config.set("key", "value")
```
""")

        db_path = Path(temp_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=str(db_path)
        )

        with patch.object(watcher, "_handle_config_change") as mock_handle:
            watcher._reindex_file(str(config_file))
            mock_handle.assert_called_once_with(str(config_file))

    def test_reindex_file_skips_non_config(self, temp_space_path, temp_db_path):
        """Test that _reindex_file does not call _handle_config_change for other files."""
        from server.db.graph import GraphDB

        regular_file = Path(temp_space_path) / "regular.md"
        regular_file.write_text("# Regular file")

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )

        with patch.object(watcher, "_handle_config_change") as mock_handle:
            watcher._reindex_file(str(regular_file))
            mock_handle.assert_not_called()


class TestReindexAll:
    """Tests for full reindexing."""

    def test_reindex_all_handles_config_md(self, temp_space_path, temp_db_path):
        """Test that reindex_all processes CONFIG.md files."""
        from server.db.graph import GraphDB

        # Create CONFIG.md
        config_file = Path(temp_space_path) / "CONFIG.md"
        config_file.write_text("""```space-lua
config.set("test.key", "test_value")
```
""")

        # Create other files
        regular_file = Path(temp_space_path) / "other.md"
        regular_file.write_text("# Other file")

        db_path = Path(temp_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=str(db_path)
        )
        watcher.reindex_all()

        # Check that space_config.json was created
        config_json_path = db_path.parent / "space_config.json"
        assert config_json_path.exists()

        config = json.loads(config_json_path.read_text())
        assert config == {"test": {"key": "test_value"}}

    def test_reindex_all_handles_nested_config_md(self, temp_space_path, temp_db_path):
        """Test that reindex_all finds CONFIG.md in subdirectories."""
        from server.db.graph import GraphDB

        # Create nested CONFIG.md
        subdir = Path(temp_space_path) / "subdir"
        subdir.mkdir()
        config_file = subdir / "CONFIG.md"
        config_file.write_text("""```space-lua
config.set("nested.key", "nested_value")
```
""")

        db_path = Path(temp_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=str(db_path)
        )
        watcher.reindex_all()

        config_json_path = db_path.parent / "space_config.json"
        assert config_json_path.exists()

        config = json.loads(config_json_path.read_text())
        assert config == {"nested": {"key": "nested_value"}}

    def test_reindex_all_caches_hashes(self, temp_space_path, temp_db_path):
        """Test that reindex_all builds hash cache."""
        from server.db.graph import GraphDB

        # Create some files
        (Path(temp_space_path) / "file1.md").write_text("# File 1")
        (Path(temp_space_path) / "file2.md").write_text("# File 2")

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )
        watcher.reindex_all()

        assert len(watcher.file_hashes) == 2


class TestFileEventHandling:
    """Tests for file system event handling."""

    def test_on_modified_ignores_directories(self, temp_space_path, temp_db_path):
        """Test that directory events are ignored."""
        from server.db.graph import GraphDB

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )

        event = MagicMock()
        event.is_directory = True
        event.src_path = temp_space_path

        with patch.object(watcher, "_reindex_file") as mock_reindex:
            watcher.on_modified(event)
            mock_reindex.assert_not_called()

    def test_on_modified_ignores_non_md(self, temp_space_path, temp_db_path):
        """Test that non-markdown files are ignored."""
        from server.db.graph import GraphDB

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )

        event = MagicMock()
        event.is_directory = False
        event.src_path = str(Path(temp_space_path) / "file.txt")

        with patch.object(watcher, "_reindex_file") as mock_reindex:
            watcher.on_modified(event)
            mock_reindex.assert_not_called()

    def test_on_modified_processes_md(self, temp_space_path, temp_db_path):
        """Test that markdown files are processed."""
        from server.db.graph import GraphDB

        test_file = Path(temp_space_path) / "test.md"
        test_file.write_text("# Test")

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )

        event = MagicMock()
        event.is_directory = False
        event.src_path = str(test_file)

        with patch.object(watcher, "_reindex_file") as mock_reindex:
            watcher.on_modified(event)
            mock_reindex.assert_called_once_with(str(test_file))

    def test_on_created_processes_md(self, temp_space_path, temp_db_path):
        """Test that created markdown files are processed."""
        from server.db.graph import GraphDB

        test_file = Path(temp_space_path) / "new.md"
        test_file.write_text("# New")

        watcher = SpaceWatcher(
            temp_space_path, graph_db=GraphDB(temp_db_path), db_path=temp_db_path
        )

        event = MagicMock()
        event.is_directory = False
        event.src_path = str(test_file)

        with patch.object(watcher, "_reindex_file") as mock_reindex:
            watcher.on_created(event)
            mock_reindex.assert_called_once_with(str(test_file))

    def test_on_deleted_removes_chunks(self, temp_space_path, temp_db_path):
        """Test that deleted files have their chunks removed."""
        from server.db.graph import GraphDB

        graph_db = GraphDB(temp_db_path)
        watcher = SpaceWatcher(temp_space_path, graph_db=graph_db, db_path=temp_db_path)

        event = MagicMock()
        event.is_directory = False
        event.src_path = str(Path(temp_space_path) / "deleted.md")

        with patch.object(graph_db, "delete_chunks_by_file") as mock_delete:
            watcher.on_deleted(event)
            mock_delete.assert_called_once_with(event.src_path)

    def test_on_deleted_ignores_non_md(self, temp_space_path, temp_db_path):
        """Test that non-markdown deletions are ignored."""
        from server.db.graph import GraphDB

        graph_db = GraphDB(temp_db_path)
        watcher = SpaceWatcher(temp_space_path, graph_db=graph_db, db_path=temp_db_path)

        event = MagicMock()
        event.is_directory = False
        event.src_path = str(Path(temp_space_path) / "file.txt")

        with patch.object(graph_db, "delete_chunks_by_file") as mock_delete:
            watcher.on_deleted(event)
            mock_delete.assert_not_called()


class TestBackwardCompatibility:
    """Tests for backward compatibility aliases."""

    def test_space_event_handler_alias(self):
        """Test that SpaceEventHandler is an alias for SpaceWatcher."""
        from server.watcher import SpaceEventHandler, SpaceWatcher

        assert SpaceEventHandler is SpaceWatcher
