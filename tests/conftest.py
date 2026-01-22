"""Pytest configuration and fixtures."""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator
import pytest


def pytest_configure(config):
    """Configure pytest."""
    # Register markers
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test requiring Silverbullet"
    )


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary database file path for testing.

    LadybugDB requires a file path, not a directory.

    Yields:
        Path to temporary database file
    """
    temp_dir = tempfile.mkdtemp(prefix="test_db_")
    db_file = os.path.join(temp_dir, "test.lbug")
    yield db_file
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_space_path() -> Generator[str, None, None]:
    """Create a temporary space directory for testing.

    Yields:
        Path to temporary space directory
    """
    temp_dir = tempfile.mkdtemp(prefix="test_space_")
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_markdown_file(temp_space_path: str) -> Path:
    """Create a sample markdown file for testing.

    Args:
        temp_space_path: Temporary space directory

    Returns:
        Path to the created markdown file
    """
    file_path = Path(temp_space_path) / "test_page.md"
    content = """# Test Page

## Section 1

This is a test page with [[wikilinks]] and #tags.

## Section 2

Another section with [[another-link]] and #test #example tags.
"""
    file_path.write_text(content)
    return file_path


@pytest.fixture
def silverbullet_test_data() -> Path:
    """Path to Silverbullet test data submodule.

    Returns:
        Path to vendor/silverbullet directory
    """
    return Path(__file__).parent.parent / "vendor" / "silverbullet"


@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    """Setup test environment variables.

    Uses local fastembed provider for tests to avoid OpenAI API calls.

    Args:
        monkeypatch: Pytest monkeypatch fixture
    """
    # Use local provider for tests - no API key needed
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
