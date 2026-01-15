"""Library installation MCP tools."""

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..dependencies import get_dependencies, refresh_proposals_status

logger = logging.getLogger(__name__)

# Available libraries (currently only Proposals)
AVAILABLE_LIBRARIES = ["Proposals"]


def _get_library_source_path() -> Path:
    """Get the path to bundled library files.

    In Docker: /app/library/
    In development: /workspaces/silverbullet-rag/library/
    """
    # Navigate from server/mcp/tools/library.py to project root
    return Path(__file__).parent.parent.parent.parent / "library"


def _get_library_version(library_path: Path) -> str | None:
    """Extract version from library frontmatter."""
    try:
        content = library_path.read_text(encoding="utf-8")
        # Match version in YAML frontmatter
        match = re.search(r"^version:\s*(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return None


def _add_install_metadata(content: str, version: str) -> str:
    """Add installed_version and installed_at to frontmatter."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Check if frontmatter exists
    if not content.startswith("---"):
        return content

    # Find the end of frontmatter
    end_match = re.search(r"\n---\s*\n", content)
    if not end_match:
        return content

    frontmatter_end = end_match.start()
    frontmatter = content[: frontmatter_end + 1]
    rest = content[end_match.end() - 1 :]

    # Remove existing install metadata if present
    frontmatter = re.sub(
        r"^installed_version:.*\n", "", frontmatter, flags=re.MULTILINE
    )
    frontmatter = re.sub(r"^installed_at:.*\n", "", frontmatter, flags=re.MULTILINE)

    # Add new metadata before the closing ---
    new_metadata = f"installed_version: {version}\ninstalled_at: {now}\n"
    new_frontmatter = frontmatter + new_metadata

    return new_frontmatter + "---" + rest


def _copy_library_files(
    source_path: Path,
    dest_path: Path,
    library_name: str,
    version: str,
    overwrite: bool = False,
) -> list[str]:
    """Copy library files from source to destination.

    Returns list of installed file paths (relative to space).
    """
    installed_files = []

    # Create Library directory if needed
    dest_path.mkdir(parents=True, exist_ok=True)

    # Copy root .md file with install metadata
    src_root = source_path / f"{library_name}.md"
    dst_root = dest_path / f"{library_name}.md"

    content = src_root.read_text(encoding="utf-8")
    content_with_metadata = _add_install_metadata(content, version)
    dst_root.write_text(content_with_metadata, encoding="utf-8")
    installed_files.append(f"Library/{library_name}.md")

    # Copy subdirectory if exists
    src_subdir = source_path / library_name
    if src_subdir.exists() and src_subdir.is_dir():
        dst_subdir = dest_path / library_name
        if dst_subdir.exists() and overwrite:
            shutil.rmtree(dst_subdir)
        shutil.copytree(src_subdir, dst_subdir, dirs_exist_ok=overwrite)

        for item in src_subdir.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(source_path)
                installed_files.append(f"Library/{rel_path}")

    return installed_files


async def install_library(library_name: str = "Proposals") -> dict[str, Any]:
    """
    Install a library into the SilverBullet space.

    Copies library files from the server's bundled libraries to the space's
    Library/ folder. Currently only the 'Proposals' library is available.

    Args:
        library_name: Name of the library to install (default: "Proposals")

    Returns:
        Installation status and list of installed files
    """
    if library_name not in AVAILABLE_LIBRARIES:
        return {
            "success": False,
            "error": f"Unknown library: {library_name}. Available: {AVAILABLE_LIBRARIES}",
        }

    try:
        deps = get_dependencies()
        source_path = _get_library_source_path()

        # Verify source exists
        library_source = source_path / f"{library_name}.md"
        if not library_source.exists():
            return {
                "success": False,
                "error": f"Library source not found at {source_path}",
            }

        # Check if already installed
        dest_path = deps.space_path / "Library"
        marker_file = dest_path / f"{library_name}.md"

        if marker_file.exists():
            return {
                "success": False,
                "error": f"Library '{library_name}' is already installed. Use update_library to update.",
                "already_installed": True,
            }

        # Get version from source
        version = _get_library_version(library_source) or "unknown"

        # Copy files
        installed_files = _copy_library_files(
            source_path, dest_path, library_name, version, overwrite=False
        )

        # Refresh proposals status
        refresh_proposals_status()

        logger.info(
            f"Installed library '{library_name}' v{version} with {len(installed_files)} files"
        )

        return {
            "success": True,
            "library": library_name,
            "version": version,
            "installed_files": installed_files,
            "message": f"Library '{library_name}' v{version} installed successfully.",
        }

    except Exception as e:
        logger.error(f"Failed to install library '{library_name}': {e}")
        return {"success": False, "error": str(e)}


async def update_library(library_name: str = "Proposals") -> dict[str, Any]:
    """
    Update an existing library installation.

    Overwrites the existing library files with the bundled version.
    Use this when a newer version of the library is available.

    Args:
        library_name: Name of the library to update (default: "Proposals")

    Returns:
        Update status and list of updated files
    """
    if library_name not in AVAILABLE_LIBRARIES:
        return {
            "success": False,
            "error": f"Unknown library: {library_name}. Available: {AVAILABLE_LIBRARIES}",
        }

    try:
        deps = get_dependencies()
        source_path = _get_library_source_path()

        # Verify source exists
        library_source = source_path / f"{library_name}.md"
        if not library_source.exists():
            return {
                "success": False,
                "error": f"Library source not found at {source_path}",
            }

        # Check if installed
        dest_path = deps.space_path / "Library"
        marker_file = dest_path / f"{library_name}.md"

        if not marker_file.exists():
            return {
                "success": False,
                "error": f"Library '{library_name}' is not installed. Use install_library first.",
                "not_installed": True,
            }

        # Get current installed version
        current_version = _get_library_version(marker_file)

        # Get new version from source
        new_version = _get_library_version(library_source) or "unknown"

        # Copy files (overwrite)
        installed_files = _copy_library_files(
            source_path, dest_path, library_name, new_version, overwrite=True
        )

        # Refresh proposals status
        refresh_proposals_status()

        logger.info(
            f"Updated library '{library_name}' from v{current_version} to v{new_version}"
        )

        return {
            "success": True,
            "library": library_name,
            "previous_version": current_version,
            "version": new_version,
            "installed_files": installed_files,
            "message": f"Library '{library_name}' updated from v{current_version} to v{new_version}.",
        }

    except Exception as e:
        logger.error(f"Failed to update library '{library_name}': {e}")
        return {"success": False, "error": str(e)}
