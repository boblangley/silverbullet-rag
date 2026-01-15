"""Tests for the library installation MCP tools."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from server.mcp.tools.library import (
    install_library,
    update_library,
    _get_library_source_path,
    _get_library_version,
    _add_install_metadata,
)
from server.mcp.dependencies import Dependencies, refresh_proposals_status


class TestGetLibrarySourcePath:
    """Tests for library source path resolution."""

    def test_source_path_exists(self):
        """Test that the library source path exists in development."""
        source_path = _get_library_source_path()
        assert source_path.exists()
        assert (source_path / "Proposals.md").exists()


class TestGetLibraryVersion:
    """Tests for version extraction from frontmatter."""

    def test_extract_version(self, tmp_path: Path):
        """Test extracting version from frontmatter."""
        library_file = tmp_path / "Test.md"
        library_file.write_text("""---
displayName: Test
version: 1.2.3
---

# Test Library
""")
        assert _get_library_version(library_file) == "1.2.3"

    def test_no_version(self, tmp_path: Path):
        """Test when no version in frontmatter."""
        library_file = tmp_path / "Test.md"
        library_file.write_text("""---
displayName: Test
---

# Test Library
""")
        assert _get_library_version(library_file) is None

    def test_no_frontmatter(self, tmp_path: Path):
        """Test file without frontmatter."""
        library_file = tmp_path / "Test.md"
        library_file.write_text("# Test Library\n\nNo frontmatter.")
        assert _get_library_version(library_file) is None

    def test_nonexistent_file(self, tmp_path: Path):
        """Test with non-existent file."""
        library_file = tmp_path / "NonExistent.md"
        assert _get_library_version(library_file) is None


class TestAddInstallMetadata:
    """Tests for adding install metadata to frontmatter."""

    def test_add_metadata(self):
        """Test adding install metadata."""
        content = """---
displayName: Test
version: 1.0.0
---

# Content
"""
        result = _add_install_metadata(content, "1.0.0")

        assert "installed_version: 1.0.0" in result
        assert "installed_at:" in result
        assert "# Content" in result

    def test_replace_existing_metadata(self):
        """Test replacing existing install metadata."""
        content = """---
displayName: Test
version: 1.0.0
installed_version: 0.9.0
installed_at: 2024-01-01
---

# Content
"""
        result = _add_install_metadata(content, "1.0.0")

        # Should only have one installed_version
        assert result.count("installed_version:") == 1
        assert "installed_version: 1.0.0" in result
        assert "installed_version: 0.9.0" not in result

    def test_no_frontmatter(self):
        """Test content without frontmatter."""
        content = "# Just content\n\nNo frontmatter."
        result = _add_install_metadata(content, "1.0.0")

        # Should return unchanged
        assert result == content


class TestInstallLibrary:
    """Tests for the install_library tool."""

    @pytest.fixture
    def mock_deps(self, tmp_path: Path):
        """Create mock dependencies with a temporary space."""
        deps = MagicMock(spec=Dependencies)
        deps.space_path = tmp_path
        deps.proposals_enabled = False
        return deps

    @pytest.mark.asyncio
    async def test_install_success(self, mock_deps, tmp_path: Path):
        """Test successful library installation."""
        with patch("server.mcp.tools.library.get_dependencies", return_value=mock_deps):
            with patch("server.mcp.tools.library.refresh_proposals_status"):
                result = await install_library("Proposals")

        assert result["success"] is True
        assert result["library"] == "Proposals"
        assert "version" in result
        assert "installed_files" in result
        assert len(result["installed_files"]) > 0

        # Check files were created
        assert (tmp_path / "Library" / "Proposals.md").exists()
        assert (tmp_path / "Library" / "Proposals").exists()

    @pytest.mark.asyncio
    async def test_install_already_exists(self, mock_deps, tmp_path: Path):
        """Test install when library already exists."""
        # Pre-create the library
        library_dir = tmp_path / "Library"
        library_dir.mkdir()
        (library_dir / "Proposals.md").write_text("# Existing")

        with patch("server.mcp.tools.library.get_dependencies", return_value=mock_deps):
            result = await install_library("Proposals")

        assert result["success"] is False
        assert "already installed" in result["error"]
        assert result.get("already_installed") is True

    @pytest.mark.asyncio
    async def test_install_unknown_library(self, mock_deps):
        """Test install with unknown library name."""
        with patch("server.mcp.tools.library.get_dependencies", return_value=mock_deps):
            result = await install_library("UnknownLib")

        assert result["success"] is False
        assert "Unknown library" in result["error"]
        assert "Available" in result["error"]

    @pytest.mark.asyncio
    async def test_install_adds_metadata(self, mock_deps, tmp_path: Path):
        """Test that installation adds version metadata."""
        with patch("server.mcp.tools.library.get_dependencies", return_value=mock_deps):
            with patch("server.mcp.tools.library.refresh_proposals_status"):
                await install_library("Proposals")

        installed_file = tmp_path / "Library" / "Proposals.md"
        content = installed_file.read_text()

        assert "installed_version:" in content
        assert "installed_at:" in content


class TestUpdateLibrary:
    """Tests for the update_library tool."""

    @pytest.fixture
    def mock_deps(self, tmp_path: Path):
        """Create mock dependencies with a temporary space."""
        deps = MagicMock(spec=Dependencies)
        deps.space_path = tmp_path
        deps.proposals_enabled = True
        return deps

    @pytest.mark.asyncio
    async def test_update_success(self, mock_deps, tmp_path: Path):
        """Test successful library update."""
        # Pre-install the library
        library_dir = tmp_path / "Library"
        library_dir.mkdir()
        (library_dir / "Proposals.md").write_text("""---
displayName: Proposals
version: 0.9.0
installed_version: 0.9.0
---

# Old version
""")
        # Create subdirectory
        (library_dir / "Proposals").mkdir()
        (library_dir / "Proposals" / "old_file.md").write_text("Old")

        with patch("server.mcp.tools.library.get_dependencies", return_value=mock_deps):
            with patch("server.mcp.tools.library.refresh_proposals_status"):
                result = await update_library("Proposals")

        assert result["success"] is True
        assert result["library"] == "Proposals"
        assert result["previous_version"] == "0.9.0"
        assert "version" in result

    @pytest.mark.asyncio
    async def test_update_not_installed(self, mock_deps, tmp_path: Path):
        """Test update when library is not installed."""
        with patch("server.mcp.tools.library.get_dependencies", return_value=mock_deps):
            result = await update_library("Proposals")

        assert result["success"] is False
        assert "not installed" in result["error"]
        assert result.get("not_installed") is True

    @pytest.mark.asyncio
    async def test_update_unknown_library(self, mock_deps):
        """Test update with unknown library name."""
        with patch("server.mcp.tools.library.get_dependencies", return_value=mock_deps):
            result = await update_library("UnknownLib")

        assert result["success"] is False
        assert "Unknown library" in result["error"]


class TestRefreshProposalsStatus:
    """Tests for refreshing proposals_enabled status."""

    def test_refresh_enables_proposals(self, tmp_path: Path):
        """Test that refresh enables proposals when library is installed."""
        # Setup
        library_dir = tmp_path / "Library"
        library_dir.mkdir()
        (library_dir / "Proposals.md").write_text("# Proposals")

        deps = Dependencies(
            graph_db=MagicMock(),
            space_parser=MagicMock(),
            hybrid_search=MagicMock(),
            space_path=tmp_path,
            db_path=tmp_path / "db",
            proposals_enabled=False,
        )

        with patch("server.mcp.dependencies._deps", deps):
            refresh_proposals_status()
            assert deps.proposals_enabled is True

    def test_refresh_disables_proposals(self, tmp_path: Path):
        """Test that refresh disables proposals when library is removed."""
        deps = Dependencies(
            graph_db=MagicMock(),
            space_parser=MagicMock(),
            hybrid_search=MagicMock(),
            space_path=tmp_path,
            db_path=tmp_path / "db",
            proposals_enabled=True,
        )

        with patch("server.mcp.dependencies._deps", deps):
            refresh_proposals_status()
            assert deps.proposals_enabled is False


class TestToolRegistration:
    """Tests for conditional tool registration."""

    def test_tools_not_registered_by_default(self, monkeypatch):
        """Test that library tools are not registered by default."""
        monkeypatch.delenv("ALLOW_LIBRARY_MANAGEMENT", raising=False)

        # Import fresh to trigger registration logic
        from importlib import reload
        import server.mcp.tools as tools_module

        mcp_mock = MagicMock()
        reload(tools_module)
        tools_module.register_tools(mcp_mock)

        # Get all registered tools
        registered_tools = [
            call[0][0].__name__ for call in mcp_mock.tool().call_args_list
        ]

        assert "install_library" not in registered_tools
        assert "update_library" not in registered_tools

    def test_tools_registered_when_enabled(self, monkeypatch):
        """Test that library tools are registered when env var is set."""
        monkeypatch.setenv("ALLOW_LIBRARY_MANAGEMENT", "true")

        from importlib import reload
        import server.mcp.tools as tools_module

        mcp_mock = MagicMock()
        reload(tools_module)
        tools_module.register_tools(mcp_mock)

        # Get all registered tools
        registered_tools = [
            call[0][0].__name__ for call in mcp_mock.tool().call_args_list
        ]

        assert "install_library" in registered_tools
        assert "update_library" in registered_tools

    def test_env_var_values(self, monkeypatch):
        """Test various env var values that enable the tools."""
        for value in ["1", "true", "TRUE", "yes", "YES"]:
            monkeypatch.setenv("ALLOW_LIBRARY_MANAGEMENT", value)

            from importlib import reload
            import server.mcp.tools as tools_module

            mcp_mock = MagicMock()
            reload(tools_module)
            tools_module.register_tools(mcp_mock)

            registered_tools = [
                call[0][0].__name__ for call in mcp_mock.tool().call_args_list
            ]
            assert "install_library" in registered_tools, f"Failed for value: {value}"
