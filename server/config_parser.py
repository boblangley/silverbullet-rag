"""
Parse CONFIG.md and extract config.set() values from space-lua blocks.

This module parses Silverbullet's CONFIG.md file which contains space-lua
code blocks with config.set() calls. The parsed configuration is written
to space_config.json for the MCP server to read.

Uses luaparser for proper AST-based parsing instead of brittle regex.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict

from luaparser import ast
from luaparser import astnodes

logger = logging.getLogger(__name__)


def _lua_value_to_python(node: astnodes.Node) -> Any:
    """Convert a Lua AST value node to Python equivalent.

    Args:
        node: A luaparser AST node representing a Lua value

    Returns:
        Python equivalent (str, int, float, bool, None, or dict)
    """
    if isinstance(node, astnodes.String):
        return node.s.decode() if isinstance(node.s, bytes) else node.s
    elif isinstance(node, astnodes.Number):
        return node.n
    elif isinstance(node, astnodes.TrueExpr):
        return True
    elif isinstance(node, astnodes.FalseExpr):
        return False
    elif isinstance(node, astnodes.Nil):
        return None
    elif isinstance(node, astnodes.Table):
        return _lua_table_to_dict(node)
    else:
        logger.warning(f"Unknown Lua node type: {type(node).__name__}")
        return None


def _lua_table_to_dict(table_node: astnodes.Table) -> Dict[str, Any]:
    """Convert a Lua Table AST node to Python dict.

    Args:
        table_node: A luaparser Table node

    Returns:
        Python dictionary with string keys
    """
    result: Dict[str, Any] = {}
    for field in table_node.fields:
        if isinstance(field, astnodes.Field):
            # Get key - could be Name or String
            if isinstance(field.key, astnodes.Name):
                key = field.key.id
            elif isinstance(field.key, astnodes.String):
                key = (
                    field.key.s.decode()
                    if isinstance(field.key.s, bytes)
                    else field.key.s
                )
            else:
                continue  # Skip non-string keys

            value = _lua_value_to_python(field.value)
            result[key] = value
    return result


def _set_nested(d: Dict[str, Any], key: str, value: Any) -> None:
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


def _parse_lua_config(lua_code: str) -> Dict[str, Any]:
    """Parse Lua code and extract all config.set() calls.

    Uses luaparser AST to find config.set() calls with any syntax:
    - config.set("key", value)
    - config.set { key = value }

    Args:
        lua_code: Raw Lua code from a space-lua block

    Returns:
        Parsed configuration dictionary
    """
    config: Dict[str, Any] = {}

    try:
        tree = ast.parse(lua_code)
    except Exception as e:
        logger.warning(f"Failed to parse Lua code: {e}")
        return config

    for node in ast.walk(tree):
        if not isinstance(node, astnodes.Call):
            continue

        # Check if this is config.set(...)
        func = node.func
        if not isinstance(func, astnodes.Index):
            continue
        if not isinstance(func.value, astnodes.Name) or func.value.id != "config":
            continue
        if not isinstance(func.idx, astnodes.Name) or func.idx.id != "set":
            continue

        args = node.args

        # Pattern 1: config.set("key", value)
        if len(args) == 2 and isinstance(args[0], astnodes.String):
            key = args[0].s.decode() if isinstance(args[0].s, bytes) else args[0].s
            value = _lua_value_to_python(args[1])
            _set_nested(config, key, value)
            logger.debug(f"Parsed config.set({key!r}, {value!r})")

        # Pattern 2: config.set { table }
        elif len(args) == 1 and isinstance(args[0], astnodes.Table):
            table_dict = _lua_table_to_dict(args[0])
            config = _deep_merge(config, table_dict)
            logger.debug(f"Parsed config.set table: {table_dict}")

    return config


def parse_config_page(content: str) -> Dict[str, Any]:
    """Parse CONFIG.md and extract config.set() values.

    Extracts space-lua code blocks from the markdown content and parses
    config.set() calls using proper AST parsing. Supports all syntaxes:

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
        block_config = _parse_lua_config(block)
        config = _deep_merge(config, block_config)

    return config


# Keep these as public API for backward compatibility
def set_nested(d: Dict[str, Any], key: str, value: Any) -> None:
    """Set a value in a nested dict using dot-notation key.

    Args:
        d: Dictionary to modify
        key: Dot-notation key (e.g., "mcp.proposals.path_prefix")
        value: Value to set
    """
    _set_nested(d, key, value)


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
