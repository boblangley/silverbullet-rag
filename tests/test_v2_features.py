"""Tests for Silverbullet v2 features: transclusions, inline attributes, data blocks."""

import tempfile
import shutil
from pathlib import Path
import pytest

from server.parser import SpaceParser, Chunk, Transclusion, InlineAttribute, DataBlock


class TestTransclusionParsing:
    """Tests for transclusion detection and expansion."""

    def test_extract_simple_transclusion(self):
        """Test extraction of simple transclusion ![[page]]."""
        parser = SpaceParser()
        content = "Some text before ![[MyPage]] and after."
        transclusions = parser._extract_transclusions(content)

        assert len(transclusions) == 1
        assert transclusions[0].target_page == "MyPage"
        assert transclusions[0].target_header is None

    def test_extract_transclusion_with_header(self):
        """Test extraction of transclusion with header ![[page#header]]."""
        parser = SpaceParser()
        content = "Include this section ![[Documentation#Installation]] here."
        transclusions = parser._extract_transclusions(content)

        assert len(transclusions) == 1
        assert transclusions[0].target_page == "Documentation"
        assert transclusions[0].target_header == "Installation"

    def test_extract_multiple_transclusions(self):
        """Test extraction of multiple transclusions."""
        parser = SpaceParser()
        content = """
        ![[PageOne]]
        Some text
        ![[PageTwo#Section]]
        More text
        ![[Folder/PageThree]]
        """
        transclusions = parser._extract_transclusions(content)

        assert len(transclusions) == 3
        assert transclusions[0].target_page == "PageOne"
        assert transclusions[1].target_page == "PageTwo"
        assert transclusions[1].target_header == "Section"
        assert transclusions[2].target_page == "Folder/PageThree"

    def test_transclusion_expansion(self, tmp_path):
        """Test that transclusions are expanded with target content."""
        # Create a simple space with two pages
        page_a = tmp_path / "PageA.md"
        page_b = tmp_path / "PageB.md"

        page_b.write_text("This is content from PageB.")
        page_a.write_text("Before ![[PageB]] After")

        parser = SpaceParser(str(tmp_path))
        chunks = parser.parse_space(str(tmp_path))

        # Find PageA chunk
        page_a_chunks = [c for c in chunks if "PageA" in c.file_path]
        assert len(page_a_chunks) >= 1

        # The content should include expanded transclusion
        page_a_content = page_a_chunks[0].content
        assert "This is content from PageB" in page_a_content

    def test_transclusion_expansion_with_header(self, tmp_path):
        """Test transclusion expansion targeting specific header."""
        page_a = tmp_path / "PageA.md"
        page_b = tmp_path / "PageB.md"

        page_b.write_text("""# PageB

## Section One
Content of section one.

## Section Two
Content of section two.

## Section Three
Content of section three.
""")
        page_a.write_text("Include: ![[PageB#Section Two]]")

        parser = SpaceParser(str(tmp_path))
        chunks = parser.parse_space(str(tmp_path))

        page_a_chunks = [c for c in chunks if "PageA" in c.file_path]
        assert len(page_a_chunks) >= 1

        content = page_a_chunks[0].content
        assert "Content of section two" in content
        # Should not include other sections
        assert "Content of section one" not in content
        assert "Content of section three" not in content

    def test_transclusion_max_depth(self, tmp_path):
        """Test that recursive transclusions have a max depth limit."""
        # Create circular/deep transclusion
        page_a = tmp_path / "PageA.md"
        page_b = tmp_path / "PageB.md"

        page_a.write_text("A includes ![[PageB]]")
        page_b.write_text("B includes ![[PageA]]")

        parser = SpaceParser(str(tmp_path))
        # Should not hang due to max_depth limit
        chunks = parser.parse_space(str(tmp_path))
        assert len(chunks) >= 2


class TestInlineAttributeParsing:
    """Tests for inline attribute [name: value] parsing."""

    def test_extract_simple_attribute(self):
        """Test extraction of simple inline attribute."""
        parser = SpaceParser()
        content = "Task item [status: done]"
        attributes = parser._extract_inline_attributes(content)

        assert len(attributes) == 1
        assert attributes[0].name == "status"
        assert attributes[0].value == "done"

    def test_extract_multiple_attributes(self):
        """Test extraction of multiple inline attributes."""
        parser = SpaceParser()
        content = "Item [priority: high] [assignee: John] [due: 2024-01-15]"
        attributes = parser._extract_inline_attributes(content)

        assert len(attributes) == 3
        assert attributes[0].name == "priority"
        assert attributes[0].value == "high"
        assert attributes[1].name == "assignee"
        assert attributes[1].value == "John"
        assert attributes[2].name == "due"
        assert attributes[2].value == "2024-01-15"

    def test_attribute_with_spaces_in_value(self):
        """Test attribute with spaces in value."""
        parser = SpaceParser()
        content = "[description: A longer description with spaces]"
        attributes = parser._extract_inline_attributes(content)

        assert len(attributes) == 1
        assert attributes[0].name == "description"
        assert attributes[0].value == "A longer description with spaces"

    def test_attribute_not_confused_with_markdown_link(self):
        """Test that markdown links are not parsed as attributes."""
        parser = SpaceParser()
        content = "[Click here](https://example.com) and [status: active]"
        attributes = parser._extract_inline_attributes(content)

        # Should only find the actual attribute, not the link
        assert len(attributes) == 1
        assert attributes[0].name == "status"

    def test_attribute_underscore_in_name(self):
        """Test attribute with underscore in name."""
        parser = SpaceParser()
        content = "[due_date: 2024-12-31]"
        attributes = parser._extract_inline_attributes(content)

        assert len(attributes) == 1
        assert attributes[0].name == "due_date"


class TestDataBlockParsing:
    """Tests for data block (```#tagname YAML) parsing."""

    def test_extract_simple_data_block(self):
        """Test extraction of simple data block."""
        parser = SpaceParser()
        content = '''Some text

```#person
name: John Doe
age: 30
```

More text'''
        data_blocks = parser._extract_data_blocks(content, "/test/file.md")

        assert len(data_blocks) == 1
        assert data_blocks[0].tag == "person"
        assert data_blocks[0].data["name"] == "John Doe"
        assert data_blocks[0].data["age"] == 30
        assert data_blocks[0].file_path == "/test/file.md"

    def test_extract_multiple_data_blocks(self):
        """Test extraction of multiple data blocks."""
        parser = SpaceParser()
        content = '''
```#contact
name: Alice
email: alice@example.com
```

Some text between

```#contact
name: Bob
email: bob@example.com
```
'''
        data_blocks = parser._extract_data_blocks(content, "/test/file.md")

        assert len(data_blocks) == 2
        assert data_blocks[0].data["name"] == "Alice"
        assert data_blocks[1].data["name"] == "Bob"

    def test_data_block_with_nested_yaml(self):
        """Test data block with nested YAML structure."""
        parser = SpaceParser()
        content = '''
```#project
name: My Project
metadata:
  version: "1.0"
  status: active
```
'''
        data_blocks = parser._extract_data_blocks(content, "/test/file.md")

        assert len(data_blocks) == 1
        assert data_blocks[0].data["name"] == "My Project"
        assert data_blocks[0].data["metadata"]["version"] == "1.0"

    def test_invalid_yaml_skipped(self):
        """Test that invalid YAML blocks are skipped."""
        parser = SpaceParser()
        content = '''
```#invalid
this: is: not: valid: yaml:
  - broken
    indentation
```
'''
        data_blocks = parser._extract_data_blocks(content, "/test/file.md")
        # Should be empty due to YAML parse error
        assert len(data_blocks) == 0

    def test_regular_code_block_not_parsed(self):
        """Test that regular code blocks without # tag are not parsed."""
        parser = SpaceParser()
        content = '''
```python
def hello():
    print("Hello")
```
'''
        data_blocks = parser._extract_data_blocks(content, "/test/file.md")
        assert len(data_blocks) == 0


class TestChunkWithNewFeatures:
    """Tests for Chunk dataclass with new features."""

    def test_chunk_has_transclusions(self, tmp_path):
        """Test that parsed chunks contain transclusion data."""
        page = tmp_path / "test.md"
        page.write_text("Content with ![[OtherPage]] transclusion")

        parser = SpaceParser(str(tmp_path))
        chunks = parser.parse_space(str(tmp_path), expand_transclusions=False)

        assert len(chunks) >= 1
        # Transclusions should be detected even when not expanded
        assert len(chunks[0].transclusions) == 1
        assert chunks[0].transclusions[0].target_page == "OtherPage"

    def test_chunk_has_inline_attributes(self, tmp_path):
        """Test that parsed chunks contain inline attribute data."""
        page = tmp_path / "test.md"
        page.write_text("Task [status: pending] [priority: high]")

        parser = SpaceParser(str(tmp_path))
        chunks = parser.parse_space(str(tmp_path))

        assert len(chunks) >= 1
        assert len(chunks[0].inline_attributes) == 2

    def test_chunk_has_data_blocks(self, tmp_path):
        """Test that parsed chunks contain data block data."""
        page = tmp_path / "test.md"
        page.write_text('''
# Test Page

```#metadata
key: value
```
''')

        parser = SpaceParser(str(tmp_path))
        chunks = parser.parse_space(str(tmp_path))

        assert len(chunks) >= 1
        # Find chunk with data blocks
        chunks_with_data = [c for c in chunks if c.data_blocks]
        assert len(chunks_with_data) >= 1
        assert chunks_with_data[0].data_blocks[0].tag == "metadata"


class TestSectionExtraction:
    """Tests for section extraction from headers."""

    def test_extract_section_by_header(self):
        """Test extracting a section by header name."""
        parser = SpaceParser()
        content = """# Main Title

## First Section
Content of first section.

## Second Section
Content of second section.
More content here.

## Third Section
Content of third section.
"""
        section = parser._extract_section(content, "Second Section")

        assert "## Second Section" in section
        assert "Content of second section" in section
        assert "More content here" in section
        assert "First Section" not in section
        assert "Third Section" not in section

    def test_extract_section_case_insensitive(self):
        """Test that header matching is case insensitive."""
        parser = SpaceParser()
        content = """## My Section
Some content here.

## Another Section
Other content.
"""
        section = parser._extract_section(content, "my section")
        assert "Some content here" in section

    def test_extract_nested_section(self):
        """Test extracting section that contains nested headers."""
        parser = SpaceParser()
        content = """## Parent Section
Parent content.

### Child Section
Child content.

## Next Section
Next content.
"""
        section = parser._extract_section(content, "Parent Section")

        assert "Parent content" in section
        assert "Child Section" in section
        assert "Child content" in section
        assert "Next Section" not in section
