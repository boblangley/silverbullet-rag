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


def parse_config_page(content: str) -> Dict[str, Any]:
    """Parse CONFIG.md and extract config.set() values.

    Extracts space-lua code blocks from the markdown content and parses
    config.set("key", value) calls using the slpp Lua parser.

    Args:
        content: Raw markdown content of CONFIG.md

    Returns:
        Nested dict matching config key structure

    Example:
        ```space-lua
        config.set("mcp.proposals.path_prefix", "_Proposals/")
        config.set("mcp.proposals.cleanup_after_days", 14)
        ```

        Returns: {"mcp": {"proposals": {"path_prefix": "_Proposals/", "cleanup_after_days": 14}}}
    """
    # Extract space-lua blocks
    lua_blocks = re.findall(r"```space-lua\n(.*?)```", content, re.DOTALL)

    config: Dict[str, Any] = {}

    for block in lua_blocks:
        # Match config.set("key", value) calls
        # Value can be: string, number, boolean, or table
        # The lookahead ensures we stop at the next config.set, comment, end of block, or newline
        pattern = (
            r'config\.set\s*\(\s*"([^"]+)"\s*,\s*(.+?)\s*\)(?=\s*(?:config\.|--|$|\n))'
        )
        matches = re.findall(pattern, block, re.MULTILINE)

        for key, value_str in matches:
            try:
                # Use slpp to parse Lua literals
                parsed = lua.decode(value_str)
                set_nested(config, key, parsed)
                logger.debug(f"Parsed config: {key} = {parsed}")
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

    return config


def write_config_json(config: Dict[str, Any], db_path: Path) -> None:
    """Write parsed config to JSON file next to database.

    Args:
        config: Parsed configuration dictionary
        db_path: Path to the database directory
    """
    config_path = db_path.parent / "space_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
    logger.info(f"Wrote space config to {config_path}")


def load_config_json(db_path: Path) -> Dict[str, Any]:
    """Load space config from JSON file.

    Args:
        db_path: Path to the database directory

    Returns:
        Parsed configuration dictionary, or empty dict if not found
    """
    config_path = db_path.parent / "space_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {}
