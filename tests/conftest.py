"""Pytest configuration and fixtures."""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator
import pytest
from unittest.mock import Mock, patch


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
def mock_openai_embeddings():
    """Mock OpenAI API embedding responses for fast tests.

    Returns:
        Mock object for OpenAI embedding calls
    """
    # Mock the OpenAI client's embeddings.create method
    with patch("openai.OpenAI") as mock_client_class:
        # Create a mock client instance
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Mock the embeddings.create response
        mock_embedding_obj = Mock()
        mock_embedding_obj.embedding = [0.1] * 1536  # text-embedding-3-small dimension

        mock_response = Mock()
        mock_response.data = [mock_embedding_obj]

        mock_client.embeddings.create.return_value = mock_response

        yield mock_client


@pytest.fixture
def silverbullet_test_data() -> Path:
    """Path to Silverbullet test data submodule.

    Returns:
        Path to test-data/silverbullet directory
    """
    return Path(__file__).parent.parent / "test-data" / "silverbullet"


@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    """Setup test environment variables.

    Args:
        monkeypatch: Pytest monkeypatch fixture
    """
    monkeypatch.setenv("OPEN_AI_API_KEY", "test-key-12345")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")
