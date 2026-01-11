"""Parse Silverbullet markdown files into chunks."""

import re
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from markdown_it import MarkdownIt


@dataclass
class Chunk:
    """Represents a chunk of content from a markdown file."""

    file_path: str
    header: str
    content: str
    links: List[str]
    tags: List[str]
    folder_path: str = ""
    frontmatter: Dict[str, Any] = field(default_factory=dict)


class SpaceParser:
    """Parser for Silverbullet markdown space."""

    # Regex to match YAML frontmatter block
    FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)

    def __init__(self):
        self.md = MarkdownIt()
        self.link_pattern = re.compile(r'\[\[([^\]]+)\]\]')
        self.tag_pattern = re.compile(r'#(\w+)')
        self._frontmatter_cache: Dict[str, Dict[str, Any]] = {}

    def parse_space(self, dir_path: str) -> List[Chunk]:
        """Parse all markdown files in a directory.

        Args:
            dir_path: Path to the Silverbullet space directory

        Returns:
            List of chunks extracted from markdown files
        """
        chunks = []
        space_path = Path(dir_path).resolve()

        for md_file in space_path.glob("**/*.md"):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Calculate folder path relative to space root
                relative_path = md_file.relative_to(space_path)
                folder_path = str(relative_path.parent) if relative_path.parent != Path('.') else ""

                # Extract frontmatter
                frontmatter = self._extract_frontmatter(content)

                # Parse file into chunks (with frontmatter stripped from content)
                file_chunks = self._parse_file(
                    str(md_file),
                    content,
                    folder_path=folder_path,
                    frontmatter=frontmatter
                )
                chunks.extend(file_chunks)

                # Cache frontmatter for later retrieval
                self._frontmatter_cache[str(md_file)] = frontmatter
            except Exception as e:
                print(f"Error parsing {md_file}: {e}")

        return chunks

    def _parse_file(
        self,
        file_path: str,
        content: str,
        folder_path: str = "",
        frontmatter: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """Parse a single markdown file into chunks.

        Chunks are split by ## headings or whole file if no headings.

        Args:
            file_path: Path to the file
            content: File content
            folder_path: Folder path relative to space root
            frontmatter: Extracted YAML frontmatter dict

        Returns:
            List of chunks from this file
        """
        if frontmatter is None:
            frontmatter = {}

        # Strip frontmatter from content before parsing
        content = self._strip_frontmatter(content)

        chunks = []
        tokens = self.md.parse(content)

        current_header = Path(file_path).stem
        current_content = []

        for token in tokens:
            if token.type == 'heading_open' and token.tag == 'h2':
                # Save previous chunk if exists
                if current_content:
                    chunk_text = '\n'.join(current_content).strip()
                    if chunk_text:
                        chunks.append(self._create_chunk(
                            file_path,
                            current_header,
                            chunk_text,
                            folder_path=folder_path,
                            frontmatter=frontmatter
                        ))
                    current_content = []

            elif token.type == 'inline':
                # Extract heading text
                if token.content:
                    # Check if this is heading content
                    parent_open = [t for t in tokens if t.type == 'heading_open']
                    if parent_open:
                        current_header = token.content
                    current_content.append(token.content)

            elif token.type in ('paragraph_open', 'list_item_open', 'blockquote_open'):
                # Collect content
                pass

            elif token.content:
                current_content.append(token.content)

        # Save last chunk
        if current_content:
            chunk_text = '\n'.join(current_content).strip()
            if chunk_text:
                chunks.append(self._create_chunk(
                    file_path,
                    current_header,
                    chunk_text,
                    folder_path=folder_path,
                    frontmatter=frontmatter
                ))

        return chunks

    def _create_chunk(
        self,
        file_path: str,
        header: str,
        content: str,
        folder_path: str = "",
        frontmatter: Optional[Dict[str, Any]] = None
    ) -> Chunk:
        """Create a chunk with extracted links and tags.

        Args:
            file_path: Path to the source file
            header: Header/title for this chunk
            content: Content text
            folder_path: Folder path relative to space root
            frontmatter: Extracted YAML frontmatter dict

        Returns:
            Chunk object
        """
        if frontmatter is None:
            frontmatter = {}

        links = self.link_pattern.findall(content)

        # Collect tags from both #hashtags in content and frontmatter tags property
        content_tags = self.tag_pattern.findall(content)
        frontmatter_tags = frontmatter.get('tags', [])

        # Normalize frontmatter tags (could be a single string or list)
        if isinstance(frontmatter_tags, str):
            frontmatter_tags = [frontmatter_tags]
        elif not isinstance(frontmatter_tags, list):
            frontmatter_tags = []

        # Combine and deduplicate tags (preserve order, content tags first)
        all_tags = list(content_tags)
        for tag in frontmatter_tags:
            if tag and tag not in all_tags:
                all_tags.append(tag)

        return Chunk(
            file_path=file_path,
            header=header,
            content=content,
            links=links,
            tags=all_tags,
            folder_path=folder_path,
            frontmatter=frontmatter
        )

    def _extract_frontmatter(self, content: str) -> Dict[str, Any]:
        """Extract YAML frontmatter from markdown content.

        Args:
            content: Full markdown file content

        Returns:
            Parsed frontmatter as dict, or empty dict if none found
        """
        match = self.FRONTMATTER_PATTERN.match(content)
        if match:
            try:
                return yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                return {}
        return {}

    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter from markdown content.

        Args:
            content: Full markdown file content

        Returns:
            Content with frontmatter block removed
        """
        return self.FRONTMATTER_PATTERN.sub('', content)

    def get_frontmatter(self, file_path: str) -> Dict[str, Any]:
        """Get cached frontmatter for a file, or parse it.

        Args:
            file_path: Path to the markdown file

        Returns:
            Frontmatter dict for the file
        """
        if file_path in self._frontmatter_cache:
            return self._frontmatter_cache[file_path]

        # Parse if not cached
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            frontmatter = self._extract_frontmatter(content)
            self._frontmatter_cache[file_path] = frontmatter
            return frontmatter
        except Exception:
            return {}

    def get_folder_paths(self, dir_path: str) -> List[str]:
        """Get all unique folder paths from a space directory.

        Args:
            dir_path: Path to the Silverbullet space directory

        Returns:
            List of unique folder paths relative to space root
        """
        folders = set()
        space_path = Path(dir_path).resolve()

        for md_file in space_path.glob("**/*.md"):
            relative_path = md_file.relative_to(space_path)

            # Add all parent folders
            current = relative_path.parent
            while current != Path('.'):
                folders.add(str(current))
                current = current.parent

        # Also add any directories that exist (even without .md files)
        for item in space_path.rglob('*'):
            if item.is_dir():
                relative = item.relative_to(space_path)
                folders.add(str(relative))

        return sorted(list(folders))

    def get_folder_index_pages(self, dir_path: str) -> Dict[str, str]:
        """Get mapping of folder paths to their index pages.

        In Silverbullet, the index file for Folder/ is Folder.md (sibling),
        NOT Folder/index.md.

        Args:
            dir_path: Path to the Silverbullet space directory

        Returns:
            Dict mapping folder path to index page filename (e.g., {"Projects": "Projects.md"})
        """
        index_map = {}
        space_path = Path(dir_path).resolve()

        for folder in space_path.rglob('*'):
            if folder.is_dir():
                relative_folder = folder.relative_to(space_path)
                # Check for sibling .md file with same name as folder
                index_file = folder.parent / f"{folder.name}.md"
                if index_file.exists():
                    relative_index = index_file.relative_to(space_path)
                    index_map[str(relative_folder)] = str(relative_index)

        return index_map
