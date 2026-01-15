"""
Parse CONFIG.md and extract config.set() values from space-lua blocks.

This module parses Silverbullet's CONFIG.md file which contains space-lua
code blocks with config.set() calls. The parsed configuration is written
to space_config.json for the MCP server to read.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict

from slpp import slpp as lua

logger = logging.getLogger(__name__)


def set_nested(d: Dict[str, Any], key: str, value: Any) -> None:
    """Set a value in a nested dict using dot-notation key.

    Args:
        d: Dictionary to modify
        key: Dot-notation key (e.g., "mcp.proposals.path_prefix")
        value: Value to set
    """
    parts = key.split(".")
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence.

    Args:
        base: Base dictionary
        override: Dictionary to merge in (takes precedence)

    Returns:
        Merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _extract_balanced_braces(text: str) -> str | None:
    """Extract a balanced brace expression from text starting with '{'.

    Args:
        text: Text starting with '{'

    Returns:
        The balanced brace expression including outer braces, or None if invalid
    """
    if not text or text[0] != "{":
        return None

    depth = 0
    in_string = False
    string_char = None

    for i, char in enumerate(text):
        # Handle string literals
        if char in ('"', "'") and (i == 0 or text[i - 1] != "\\"):
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char:
                in_string = False
                string_char = None
            continue

        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[: i + 1]

    return None  # Unbalanced braces


def parse_config_page(content: str) -> Dict[str, Any]:
    """Parse CONFIG.md and extract config.set() values.

    Extracts space-lua code blocks from the markdown content and parses
    config.set() calls using the slpp Lua parser. Supports both syntaxes:

    1. config.set("key", value) - dot-notation key with value
    2. config.set { key = value } - Lua table syntax

    Args:
        content: Raw markdown content of CONFIG.md

    Returns:
        Nested dict matching config key structure

    Example:
        ```space-lua
        config.set("mcp.proposals.path_prefix", "_Proposals/")
        config.set {
          theme = "dark",
          mcp = { proposals = { cleanup_after_days = 14 } }
        }
        ```

        Returns: {"theme": "dark", "mcp": {"proposals": {"path_prefix": "_Proposals/", "cleanup_after_days": 14}}}
    """
    # Extract space-lua blocks
    lua_blocks = re.findall(r"```space-lua\n(.*?)```", content, re.DOTALL)

    config: Dict[str, Any] = {}

    for block in lua_blocks:
        # Pattern 1: config.set("key", value) - dot-notation syntax
        # Value can be: string, number, boolean, or table
        # The lookahead ensures we stop at the next config.set, comment, end of block, or newline
        pattern_dotnotation = (
            r'config\.set\s*\(\s*"([^"]+)"\s*,\s*(.+?)\s*\)(?=\s*(?:config\.|--|$|\n))'
        )
        matches = re.findall(pattern_dotnotation, block, re.MULTILINE)

        for key, value_str in matches:
            try:
                # Use slpp to parse Lua literals
                parsed = lua.decode(value_str)
                set_nested(config, key, parsed)
                logger.debug(f"Parsed config (dot-notation): {key} = {parsed}")
            except Exception as e:
                # Fall back to simple parsing for edge cases
                value_str = value_str.strip()
                if value_str in ("true", "false"):
                    set_nested(config, key, value_str == "true")
                elif value_str.replace(".", "").replace("-", "").lstrip("-").isdigit():
                    set_nested(
                        config,
                        key,
                        float(value_str) if "." in value_str else int(value_str),
                    )
                elif value_str.startswith('"') and value_str.endswith('"'):
                    set_nested(config, key, value_str[1:-1])
                else:
                    logger.warning(f"Could not parse config value for {key}: {e}")

        # Pattern 2: config.set { ... } - Lua table syntax
        # Find config.set followed by opening brace, then extract balanced braces
        table_start_pattern = r"config\.set\s*\{"
        for match in re.finditer(table_start_pattern, block):
            # Position of opening { in the block
            brace_pos = match.end() - 1
            table_str = _extract_balanced_braces(block[brace_pos:])
            if table_str:
                try:
                    parsed = lua.decode(table_str)
                    if isinstance(parsed, dict):
                        config = _deep_merge(config, parsed)
                        logger.debug(f"Parsed config (table): {parsed}")
                except Exception as e:
                    logger.warning(f"Could not parse config table: {e}")

    return config


def write_config_json(config: Dict[str, Any], db_path: Path) -> None:
    """Write parsed config to JSON file next to database.

    Args:
        config: Parsed configuration dictionary
        db_path: Path to the database file (e.g., /data/ladybug)
    """
    config_path = db_path.parent / "space_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
    logger.info(f"Wrote space config to {config_path}")


def load_config_json(db_path: Path) -> Dict[str, Any]:
    """Load space config from JSON file.

    Args:
        db_path: Path to the database file (e.g., /data/ladybug)

    Returns:
        Parsed configuration dictionary, or empty dict if not found
    """
    config_path = db_path.parent / "space_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {}
