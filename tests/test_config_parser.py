"""Tests for CONFIG.md parsing."""

import json
from pathlib import Path

from server.config_parser import (
    set_nested,
    parse_config_page,
    write_config_json,
    load_config_json,
)


class TestSetNested:
    """Tests for set_nested utility function."""

    def test_single_key(self):
        """Test setting a simple key."""
        d = {}
        set_nested(d, "key", "value")
        assert d == {"key": "value"}

    def test_nested_key(self):
        """Test setting a nested key with dots."""
        d = {}
        set_nested(d, "mcp.proposals.path_prefix", "_Proposals/")
        assert d == {"mcp": {"proposals": {"path_prefix": "_Proposals/"}}}

    def test_deeply_nested(self):
        """Test deeply nested keys."""
        d = {}
        set_nested(d, "a.b.c.d.e", 42)
        assert d == {"a": {"b": {"c": {"d": {"e": 42}}}}}

    def test_preserves_existing(self):
        """Test that existing values are preserved."""
        d = {"mcp": {"other": "value"}}
        set_nested(d, "mcp.proposals.prefix", "_Proposals/")
        assert d == {
            "mcp": {
                "other": "value",
                "proposals": {"prefix": "_Proposals/"},
            }
        }


class TestParseConfigPage:
    """Tests for parsing CONFIG.md content."""

    def test_simple_string(self):
        """Test parsing a simple string value."""
        content = """# Configuration

```space-lua
config.set("mcp.proposals.path_prefix", "_Proposals/")
```
"""
        config = parse_config_page(content)
        assert config == {"mcp": {"proposals": {"path_prefix": "_Proposals/"}}}

    def test_integer_value(self):
        """Test parsing an integer value."""
        content = """```space-lua
config.set("mcp.proposals.cleanup_after_days", 30)
```
"""
        config = parse_config_page(content)
        assert config == {"mcp": {"proposals": {"cleanup_after_days": 30}}}

    def test_boolean_values(self):
        """Test parsing boolean values."""
        content = """```space-lua
config.set("feature.enabled", true)
config.set("feature.disabled", false)
```
"""
        config = parse_config_page(content)
        assert config == {
            "feature": {
                "enabled": True,
                "disabled": False,
            }
        }

    def test_multiple_values(self):
        """Test parsing multiple config.set calls."""
        content = """# My Config

```space-lua
config.set("mcp.proposals.path_prefix", "_Proposals/")
config.set("mcp.proposals.cleanup_after_days", 14)
config.set("editor.theme", "dark")
```
"""
        config = parse_config_page(content)
        assert config == {
            "mcp": {
                "proposals": {
                    "path_prefix": "_Proposals/",
                    "cleanup_after_days": 14,
                }
            },
            "editor": {"theme": "dark"},
        }

    def test_multiple_lua_blocks(self):
        """Test parsing multiple space-lua blocks."""
        content = """# Config Part 1

```space-lua
config.set("section1.key", "value1")
```

# Config Part 2

```space-lua
config.set("section2.key", "value2")
```
"""
        config = parse_config_page(content)
        assert config == {
            "section1": {"key": "value1"},
            "section2": {"key": "value2"},
        }

    def test_empty_content(self):
        """Test parsing empty content."""
        config = parse_config_page("")
        assert config == {}

    def test_no_lua_blocks(self):
        """Test parsing content without space-lua blocks."""
        content = """# Just Markdown

No lua blocks here.
"""
        config = parse_config_page(content)
        assert config == {}

    def test_comments_in_lua(self):
        """Test that Lua comments don't break parsing."""
        content = """```space-lua
-- This is a comment
config.set("key", "value")
-- Another comment
```
"""
        config = parse_config_page(content)
        assert config == {"key": "value"}

    def test_float_value(self):
        """Test parsing float values."""
        content = """```space-lua
config.set("threshold", 0.75)
```
"""
        config = parse_config_page(content)
        assert config == {"threshold": 0.75}


class TestWriteAndLoadConfigJson:
    """Tests for writing and loading config JSON."""

    def test_write_and_load(self, tmp_path: Path):
        """Test writing and loading config JSON."""
        db_path = tmp_path / "data" / "ladybug"
        db_path.mkdir(parents=True)

        config = {"mcp": {"proposals": {"path_prefix": "_Proposals/"}}}
        write_config_json(config, db_path)

        loaded = load_config_json(db_path)
        assert loaded == config

    def test_load_nonexistent(self, tmp_path: Path):
        """Test loading when config file doesn't exist."""
        db_path = tmp_path / "data" / "ladybug"
        db_path.mkdir(parents=True)

        loaded = load_config_json(db_path)
        assert loaded == {}

    def test_write_creates_parent_dirs(self, tmp_path: Path):
        """Test that write_config_json creates parent directories."""
        db_path = tmp_path / "deeply" / "nested" / "path" / "db"

        config = {"key": "value"}
        write_config_json(config, db_path)

        config_path = db_path.parent / "space_config.json"
        assert config_path.exists()
        assert json.loads(config_path.read_text()) == config


class TestTableSyntax:
    """Tests for Lua table syntax: config.set { key = value }."""

    def test_simple_table(self):
        """Test parsing simple table syntax."""
        content = """```space-lua
config.set {
  theme = "dark"
}
```
"""
        config = parse_config_page(content)
        assert config == {"theme": "dark"}

    def test_nested_table(self):
        """Test parsing nested table syntax."""
        content = """```space-lua
config.set {
  mcp = {
    proposals = {
      path_prefix = "_Proposals/"
    }
  }
}
```
"""
        config = parse_config_page(content)
        assert config == {"mcp": {"proposals": {"path_prefix": "_Proposals/"}}}

    def test_multiple_keys_in_table(self):
        """Test parsing multiple keys in one table."""
        content = """```space-lua
config.set {
  theme = "dark",
  editor = "vim"
}
```
"""
        config = parse_config_page(content)
        assert config == {"theme": "dark", "editor": "vim"}

    def test_mixed_syntax(self):
        """Test mixing dot-notation and table syntax."""
        content = """```space-lua
config.set("mcp.proposals.path_prefix", "_Proposals/")
config.set {
  theme = "dark"
}
```
"""
        config = parse_config_page(content)
        assert config == {
            "mcp": {"proposals": {"path_prefix": "_Proposals/"}},
            "theme": "dark",
        }

    def test_table_with_boolean(self):
        """Test parsing table with boolean values."""
        content = """```space-lua
config.set {
  feature_enabled = true,
  debug_mode = false
}
```
"""
        config = parse_config_page(content)
        assert config == {"feature_enabled": True, "debug_mode": False}

    def test_table_with_number(self):
        """Test parsing table with numeric values."""
        content = """```space-lua
config.set {
  max_items = 100,
  threshold = 0.5
}
```
"""
        config = parse_config_page(content)
        assert config == {"max_items": 100, "threshold": 0.5}

    def test_real_silverbullet_default_config(self):
        """Test parsing real Silverbullet default CONFIG.md style."""
        content = """This is where you configure SilverBullet to your liking. See [[^Library/Std/Config]] for a full list of configuration options.

```space-lua
config.set {
  theme = "dark"
}
```
"""
        config = parse_config_page(content)
        assert config == {"theme": "dark"}


class TestRealWorldConfig:
    """Tests with real-world CONFIG.md content."""

    def test_silverbullet_style_config(self):
        """Test parsing a realistic Silverbullet CONFIG.md."""
        content = """---
displayName: Configuration
---

# Space Configuration

This page configures your Silverbullet space.

## AI Proposals

```space-lua
-- Configure where proposals are stored
config.set("mcp.proposals.path_prefix", "_Proposals/")

-- Auto-cleanup rejected proposals after this many days
config.set("mcp.proposals.cleanup_after_days", 30)
```

## Editor Settings

```space-lua
config.set("editor.vim_mode", true)
config.set("editor.line_numbers", true)
```
"""
        config = parse_config_page(content)
        assert config == {
            "mcp": {
                "proposals": {
                    "path_prefix": "_Proposals/",
                    "cleanup_after_days": 30,
                }
            },
            "editor": {
                "vim_mode": True,
                "line_numbers": True,
            },
        }
