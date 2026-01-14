"""Tests for the proposal system."""

import json
import pytest
from pathlib import Path

from server.proposals import (
    library_installed,
    get_proposal_path,
    page_exists,
    parse_proposal_file,
    find_proposals,
    create_proposal_content,
    get_proposals_config,
)


class TestLibraryInstalled:
    """Tests for library detection."""

    def test_library_not_installed(self, tmp_path: Path):
        """Test when library is not installed."""
        assert library_installed(tmp_path) is False

    def test_library_installed(self, tmp_path: Path):
        """Test when library is installed."""
        library_dir = tmp_path / "Library"
        library_dir.mkdir()
        (library_dir / "AI-Proposals.md").write_text("# AI Proposals")

        assert library_installed(tmp_path) is True

    def test_library_dir_exists_but_no_file(self, tmp_path: Path):
        """Test when Library dir exists but AI-Proposals.md doesn't."""
        library_dir = tmp_path / "Library"
        library_dir.mkdir()

        assert library_installed(tmp_path) is False


class TestGetProposalPath:
    """Tests for proposal path generation."""

    def test_default_prefix(self):
        """Test with default prefix."""
        result = get_proposal_path("Projects/MyProject.md")
        assert result == "_Proposals/Projects/MyProject.md.proposal"

    def test_custom_prefix(self):
        """Test with custom prefix."""
        result = get_proposal_path("Notes/Note.md", "proposals/")
        assert result == "proposals/Notes/Note.md.proposal"

    def test_empty_prefix(self):
        """Test with empty prefix (sibling mode)."""
        result = get_proposal_path("Projects/MyProject.md", "")
        assert result == "Projects/MyProject.md.proposal"

    def test_simple_page(self):
        """Test with simple page name."""
        result = get_proposal_path("index.md")
        assert result == "_Proposals/index.md.proposal"


class TestPageExists:
    """Tests for page existence check."""

    def test_page_exists(self, tmp_path: Path):
        """Test when page exists."""
        page_path = tmp_path / "Projects" / "MyProject.md"
        page_path.parent.mkdir(parents=True)
        page_path.write_text("# My Project")

        assert page_exists(tmp_path, "Projects/MyProject.md") is True

    def test_page_not_exists(self, tmp_path: Path):
        """Test when page doesn't exist."""
        assert page_exists(tmp_path, "Projects/NonExistent.md") is False


class TestParseProposalFile:
    """Tests for parsing .proposal files."""

    def test_valid_proposal(self):
        """Test parsing a valid proposal file."""
        content = """---
type: proposal
target_page: Projects/MyProject.md
title: Add implementation notes
description: Added notes about the architecture
proposed_by: claude-code
created_at: 2024-01-15T10:30:00
status: pending
is_new_page: false
---

# My Project

Updated content here.
"""
        result = parse_proposal_file(content)

        assert result["metadata"]["type"] == "proposal"
        assert result["metadata"]["target_page"] == "Projects/MyProject.md"
        assert result["metadata"]["title"] == "Add implementation notes"
        assert result["metadata"]["status"] == "pending"
        assert result["metadata"]["is_new_page"] is False
        assert "# My Project" in result["body"]

    def test_no_frontmatter(self):
        """Test parsing content without frontmatter."""
        content = "# Just content\n\nNo frontmatter here."
        result = parse_proposal_file(content)

        assert result["metadata"] == {}
        assert result["body"] == content

    def test_empty_frontmatter(self):
        """Test parsing with empty frontmatter."""
        content = """---
---

Content after empty frontmatter.
"""
        result = parse_proposal_file(content)
        assert result["metadata"] == {}
        assert "Content after empty frontmatter." in result["body"]


class TestFindProposals:
    """Tests for finding proposals."""

    @pytest.fixture
    def space_with_proposals(self, tmp_path: Path):
        """Create a space with some proposals."""
        proposals_dir = tmp_path / "_Proposals"
        proposals_dir.mkdir()

        # Create pending proposal
        pending = proposals_dir / "Projects" / "Project1.md.proposal"
        pending.parent.mkdir(parents=True)
        pending.write_text("""---
type: proposal
target_page: Projects/Project1.md
title: Update project
status: pending
created_at: 2024-01-15T10:00:00
---

Content
""")

        # Create accepted proposal
        accepted = proposals_dir / "Notes" / "Note1.md.proposal"
        accepted.parent.mkdir(parents=True)
        accepted.write_text("""---
type: proposal
target_page: Notes/Note1.md
title: Fix typo
status: accepted
created_at: 2024-01-14T10:00:00
---

Content
""")

        # Create rejected proposal
        rejected_dir = proposals_dir / "_Rejected"
        rejected_dir.mkdir()
        rejected = rejected_dir / "Old.md.proposal"
        rejected.write_text("""---
type: proposal
target_page: Old.md
title: Old proposal
status: rejected
created_at: 2024-01-13T10:00:00
---

Content
""")

        return tmp_path

    def test_find_pending(self, space_with_proposals):
        """Test finding pending proposals."""
        proposals = find_proposals(space_with_proposals, "_Proposals/", "pending")

        assert len(proposals) == 1
        assert proposals[0]["title"] == "Update project"
        assert proposals[0]["status"] == "pending"

    def test_find_accepted(self, space_with_proposals):
        """Test finding accepted proposals."""
        proposals = find_proposals(space_with_proposals, "_Proposals/", "accepted")

        assert len(proposals) == 1
        assert proposals[0]["title"] == "Fix typo"
        assert proposals[0]["status"] == "accepted"

    def test_find_all(self, space_with_proposals):
        """Test finding all proposals."""
        proposals = find_proposals(space_with_proposals, "_Proposals/", "all")

        assert len(proposals) == 3

    def test_find_empty_dir(self, tmp_path: Path):
        """Test finding proposals in non-existent directory."""
        proposals = find_proposals(tmp_path, "_Proposals/", "pending")
        assert proposals == []


class TestCreateProposalContent:
    """Tests for creating proposal file content."""

    def test_create_content(self):
        """Test creating proposal content."""
        content = create_proposal_content(
            target_page="Projects/MyProject.md",
            content="# My Project\n\nNew content.",
            title="Update project",
            description="Added new section",
            is_new_page=False,
        )

        assert "type: proposal" in content
        assert "target_page: Projects/MyProject.md" in content
        assert "title: Update project" in content
        assert "description: Added new section" in content
        assert "status: pending" in content
        assert "is_new_page: false" in content
        assert "# My Project" in content
        assert "New content." in content

    def test_create_new_page(self):
        """Test creating content for new page."""
        content = create_proposal_content(
            target_page="NewPage.md",
            content="# New Page\n\nContent here.",
            title="Create new page",
            description="This is a new page",
            is_new_page=True,
        )

        assert "is_new_page: true" in content

    def test_custom_proposer(self):
        """Test with custom proposed_by."""
        content = create_proposal_content(
            target_page="Test.md",
            content="Test",
            title="Test",
            description="Test",
            is_new_page=False,
            proposed_by="custom-agent",
        )

        assert "proposed_by: custom-agent" in content


class TestGetProposalsConfig:
    """Tests for getting proposals config."""

    def test_with_config(self, tmp_path: Path):
        """Test getting config when it exists."""
        db_path = tmp_path / "data" / "ladybug"
        db_path.mkdir(parents=True)

        config = {
            "mcp": {
                "proposals": {
                    "path_prefix": "custom/",
                    "cleanup_after_days": 14,
                }
            }
        }
        config_path = db_path.parent / "space_config.json"
        config_path.write_text(json.dumps(config))

        result = get_proposals_config(db_path)
        assert result == {"path_prefix": "custom/", "cleanup_after_days": 14}

    def test_without_config(self, tmp_path: Path):
        """Test getting config when it doesn't exist."""
        db_path = tmp_path / "data" / "ladybug"
        db_path.mkdir(parents=True)

        result = get_proposals_config(db_path)
        assert result == {}

    def test_config_without_proposals(self, tmp_path: Path):
        """Test getting config when mcp.proposals doesn't exist."""
        db_path = tmp_path / "data" / "ladybug"
        db_path.mkdir(parents=True)

        config = {"other": {"key": "value"}}
        config_path = db_path.parent / "space_config.json"
        config_path.write_text(json.dumps(config))

        result = get_proposals_config(db_path)
        assert result == {}


class TestSecurityChecks:
    """Tests for security-related functionality."""

    def test_proposal_path_with_traversal(self):
        """Test that path traversal in page name is preserved in proposal path."""
        # The actual security check happens in the MCP tool, not in get_proposal_path
        # This just tests the function behavior
        result = get_proposal_path("../../../etc/passwd")
        assert result == "_Proposals/../../../etc/passwd.proposal"

    def test_page_exists_path_traversal(self, tmp_path: Path):
        """Test page_exists with path traversal.

        Note: page_exists does NOT do security validation - it just checks
        if the path exists. Security checks are done in the MCP tools using
        Path.resolve().is_relative_to() before calling page_exists.
        """
        # Create a file outside the space
        outside = tmp_path.parent / "outside.md"
        outside.write_text("Outside content")

        # page_exists will find the file (it's a simple existence check)
        # The MCP tool is responsible for rejecting path traversal attempts
        assert page_exists(tmp_path, "../outside.md") is True
