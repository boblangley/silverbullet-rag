"""Tests for init_index module."""

import os
import json
from pathlib import Path
from unittest.mock import patch

from server.init_index import init_index


class TestInitIndex:
    """Tests for init_index function."""

    def test_init_index_creates_config_json_from_config_md(
        self, temp_db_path: str, temp_space_path: str
    ):
        """Test that init_index parses CONFIG.md and creates space_config.json."""
        # Create CONFIG.md with test configuration
        config_content = """# Configuration

```space-lua
config.set("mcp.proposals.path_prefix", "_Proposals/")
config.set("mcp.proposals.cleanup_after_days", 14)
```
"""
        config_file = Path(temp_space_path) / "CONFIG.md"
        config_file.write_text(config_content)

        # Run init_index
        init_index(
            space_path=temp_space_path,
            db_path=temp_db_path,
            enable_embeddings=False,
            rebuild=False,
        )

        # Verify space_config.json was created
        config_json_path = Path(temp_db_path).parent / "space_config.json"
        assert config_json_path.exists(), (
            f"space_config.json not found at {config_json_path}"
        )

        # Verify content
        config = json.loads(config_json_path.read_text())
        assert config["mcp"]["proposals"]["path_prefix"] == "_Proposals/"
        assert config["mcp"]["proposals"]["cleanup_after_days"] == 14

    def test_init_index_without_config_md(
        self, temp_db_path: str, temp_space_path: str
    ):
        """Test that init_index works without CONFIG.md."""
        # Run init_index without CONFIG.md
        count = init_index(
            space_path=temp_space_path,
            db_path=temp_db_path,
            enable_embeddings=False,
            rebuild=False,
        )

        # Should complete without error
        assert count == 0  # No markdown files

        # space_config.json should NOT exist
        config_json_path = Path(temp_db_path).parent / "space_config.json"
        assert not config_json_path.exists()

    def test_init_index_indexes_markdown_files(
        self, temp_db_path: str, temp_space_path: str, sample_markdown_file: Path
    ):
        """Test that init_index indexes markdown files."""
        count = init_index(
            space_path=temp_space_path,
            db_path=temp_db_path,
            enable_embeddings=False,
            rebuild=False,
        )

        # Should have indexed chunks from the sample file
        assert count > 0

    def test_init_index_rebuild_clears_database(
        self, temp_db_path: str, temp_space_path: str, sample_markdown_file: Path
    ):
        """Test that rebuild=True clears the database first."""
        # First index
        count1 = init_index(
            space_path=temp_space_path,
            db_path=temp_db_path,
            enable_embeddings=False,
            rebuild=False,
        )

        # Second index with rebuild
        count2 = init_index(
            space_path=temp_space_path,
            db_path=temp_db_path,
            enable_embeddings=False,
            rebuild=True,
        )

        # Both should index the same number of chunks
        assert count1 == count2

    def test_init_index_uses_environment_variables(
        self, temp_db_path: str, temp_space_path: str
    ):
        """Test that init_index uses environment variables as defaults."""
        with patch.dict(
            os.environ,
            {
                "SPACE_PATH": temp_space_path,
                "DB_PATH": temp_db_path,
                "ENABLE_EMBEDDINGS": "false",
            },
        ):
            # Call without arguments - should use env vars
            count = init_index()
            assert count == 0  # Empty space

    def test_init_index_config_json_location_relative_to_db_file(
        self, temp_db_path: str, temp_space_path: str
    ):
        """Test that space_config.json is created next to the database file."""
        # Create CONFIG.md
        config_content = """```space-lua
config.set("test.key", "value")
```"""
        config_file = Path(temp_space_path) / "CONFIG.md"
        config_file.write_text(config_content)

        # temp_db_path is like /tmp/test_db_xyz/test.lbug
        # space_config.json should be at /tmp/test_db_xyz/space_config.json
        expected_config_path = Path(temp_db_path).parent / "space_config.json"

        init_index(
            space_path=temp_space_path,
            db_path=temp_db_path,
            enable_embeddings=False,
        )

        assert expected_config_path.exists()
        config = json.loads(expected_config_path.read_text())
        assert config["test"]["key"] == "value"

    def test_init_index_handles_malformed_config_md(
        self, temp_db_path: str, temp_space_path: str
    ):
        """Test that init_index handles malformed CONFIG.md gracefully."""
        # Create malformed CONFIG.md
        config_content = """# Configuration

This is not valid lua config
```space-lua
not valid lua syntax here {{{{
```
"""
        config_file = Path(temp_space_path) / "CONFIG.md"
        config_file.write_text(config_content)

        # Should not raise, just log warning
        count = init_index(
            space_path=temp_space_path,
            db_path=temp_db_path,
            enable_embeddings=False,
        )

        # Should complete (even if config parsing fails)
        # CONFIG.md is still indexed as content, just config parsing may fail
        assert count >= 0

    def test_init_index_indexes_folders(self, temp_db_path: str, temp_space_path: str):
        """Test that init_index indexes folder hierarchy."""
        # Create nested folder structure
        nested_dir = Path(temp_space_path) / "Projects" / "SubProject"
        nested_dir.mkdir(parents=True)

        # Create a file in the nested folder
        test_file = nested_dir / "test.md"
        test_file.write_text("# Test\n\nContent here.")

        count = init_index(
            space_path=temp_space_path,
            db_path=temp_db_path,
            enable_embeddings=False,
        )

        assert count > 0
