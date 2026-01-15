"""Parse Silverbullet markdown files into chunks."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from markdown_it import MarkdownIt


@dataclass
class InlineAttribute:
    """Represents an inline attribute [name: value]."""

    name: str
    value: str


@dataclass
class DataBlock:
    """Represents a tagged data block (```#tagname YAML content)."""

    tag: str
    data: Dict[str, Any]
    file_path: str


@dataclass
class Transclusion:
    """Represents a transclusion reference ![[page]] or ![[page#header]]."""

    target_page: str
    target_header: Optional[str] = None


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
    transclusions: List[Transclusion] = field(default_factory=list)
    inline_attributes: List[InlineAttribute] = field(default_factory=list)
    data_blocks: List[DataBlock] = field(default_factory=list)


class SpaceParser:
    """Parser for Silverbullet markdown space."""

    # Regex to match YAML frontmatter block
    FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def __init__(self, space_root: Optional[str] = None):
        """Initialize the parser.

        Args:
            space_root: Root path of the Silverbullet space (for transclusion resolution)
        """
        self.md = MarkdownIt()
        self.space_root = Path(space_root).resolve() if space_root else None
        # Wikilinks: [[page]] or [[page|alias]] or [[page#header]]
        self.link_pattern = re.compile(r"\[\[([^\]]+)\]\]")
        # Hashtags: #tagname (but not inside code blocks or URLs)
        self.tag_pattern = re.compile(r"(?<![`/])#(\w+)")
        # Transclusions: ![[page]] or ![[page#header]]
        self.transclusion_pattern = re.compile(r"!\[\[([^\]#]+)(?:#([^\]]+))?\]\]")
        # Inline attributes: [name: value] (but not markdown links)
        self.inline_attr_pattern = re.compile(
            r"(?<!!)\[([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([^\]]+)\]"
        )
        # Data blocks: ```#tagname followed by YAML content
        self.data_block_pattern = re.compile(r"```#(\w+)\s*\n(.*?)\n```", re.DOTALL)
        self._frontmatter_cache: Dict[str, Dict[str, Any]] = {}
        self._content_cache: Dict[str, str] = {}

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if a file should be skipped during indexing.

        Skips:
        - .proposal files (change proposals awaiting review)
        - Files in _Proposals/ directory (proposal-related content)
        - Any file ending in .rejected.md

        Args:
            file_path: Path to check

        Returns:
            True if file should be skipped
        """
        # Skip .proposal files entirely
        if file_path.suffix == ".proposal":
            return True

        # Skip .rejected.md files
        if file_path.name.endswith(".rejected.md"):
            return True

        # Skip files in _Proposals directory (these are proposal-related)
        # They should not be indexed as regular content
        parts = file_path.parts
        if "_Proposals" in parts:
            return True

        return False

    def _should_skip_directory(self, dir_path: Path) -> bool:
        """Check if a directory should be skipped during indexing.

        Skips:
        - Hidden directories (starting with .)
        - _Proposals directory

        Args:
            dir_path: Path to check (can be relative or absolute)

        Returns:
            True if directory should be skipped
        """
        # Check each part of the path for hidden directories
        for part in dir_path.parts:
            if part.startswith("."):
                return True
            if part == "_Proposals":
                return True
        return False

    def parse_space(
        self, dir_path: str, expand_transclusions: bool = True
    ) -> List[Chunk]:
        """Parse all markdown files in a directory.

        Args:
            dir_path: Path to the Silverbullet space directory
            expand_transclusions: Whether to expand transclusion content (default: True)

        Returns:
            List of chunks extracted from markdown files
        """
        chunks = []
        space_path = Path(dir_path).resolve()
        self.space_root = space_path

        # First pass: cache all file contents for transclusion resolution
        for md_file in space_path.glob("**/*.md"):
            # Skip proposal-related files from caching (they shouldn't be transcluded)
            if self._should_skip_file(md_file):
                continue
            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()
                # Cache by page name (relative path without .md extension)
                relative_path = md_file.relative_to(space_path)
                page_name = str(relative_path.with_suffix(""))
                self._content_cache[page_name] = content
                self._frontmatter_cache[str(md_file)] = self._extract_frontmatter(
                    content
                )
            except Exception as e:
                print(f"Error caching {md_file}: {e}")

        # Second pass: parse files with transclusion expansion
        for md_file in space_path.glob("**/*.md"):
            # Skip proposal-related files
            if self._should_skip_file(md_file):
                continue
            try:
                content = self._content_cache.get(
                    str(md_file.relative_to(space_path).with_suffix("")), ""
                )
                if not content:
                    with open(md_file, "r", encoding="utf-8") as f:
                        content = f.read()

                # Calculate folder path relative to space root
                relative_path = md_file.relative_to(space_path)
                folder_path = (
                    str(relative_path.parent)
                    if relative_path.parent != Path(".")
                    else ""
                )

                # Extract frontmatter
                frontmatter = self._frontmatter_cache.get(str(md_file), {})

                # Parse file into chunks (with frontmatter stripped from content)
                file_chunks = self._parse_file(
                    str(md_file),
                    content,
                    folder_path=folder_path,
                    frontmatter=frontmatter,
                    expand_transclusions=expand_transclusions,
                )
                chunks.extend(file_chunks)
            except Exception as e:
                print(f"Error parsing {md_file}: {e}")

        return chunks

    def parse_file(
        self, file_path: str, expand_transclusions: bool = True
    ) -> List[Chunk]:
        """Parse a single markdown file into chunks.

        This is the public API for parsing individual files, useful for
        incremental reindexing when a file changes.

        Args:
            file_path: Absolute path to the markdown file
            expand_transclusions: Whether to expand transclusion content (default: True)

        Returns:
            List of chunks extracted from the file
        """
        file_path = Path(file_path).resolve()

        if not file_path.exists():
            return []

        if not file_path.suffix == ".md":
            return []

        # Skip proposal-related files
        if self._should_skip_file(file_path):
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Calculate folder path relative to space root
            if self.space_root and file_path.is_relative_to(self.space_root):
                relative_path = file_path.relative_to(self.space_root)
                folder_path = (
                    str(relative_path.parent)
                    if relative_path.parent != Path(".")
                    else ""
                )
            else:
                folder_path = ""

            # Extract frontmatter
            frontmatter = self._extract_frontmatter(content)

            # Update caches
            if self.space_root:
                page_name = str(file_path.relative_to(self.space_root).with_suffix(""))
                self._content_cache[page_name] = content
            self._frontmatter_cache[str(file_path)] = frontmatter

            # Parse file into chunks
            return self._parse_file(
                str(file_path),
                content,
                folder_path=folder_path,
                frontmatter=frontmatter,
                expand_transclusions=expand_transclusions,
            )
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return []

    def _parse_file(
        self,
        file_path: str,
        content: str,
        folder_path: str = "",
        frontmatter: Optional[Dict[str, Any]] = None,
        expand_transclusions: bool = True,
    ) -> List[Chunk]:
        """Parse a single markdown file into chunks.

        Chunks are split by ## headings or whole file if no headings.

        Args:
            file_path: Path to the file
            content: File content
            folder_path: Folder path relative to space root
            frontmatter: Extracted YAML frontmatter dict
            expand_transclusions: Whether to expand transclusion content

        Returns:
            List of chunks from this file
        """
        if frontmatter is None:
            frontmatter = {}

        # Strip frontmatter from content before parsing
        raw_content = self._strip_frontmatter(content)

        # Extract data blocks from raw content before transclusion expansion
        # (data blocks are file-level, not chunk-level since fenced blocks get lost in parsing)
        file_data_blocks = self._extract_data_blocks(raw_content, file_path)

        # Expand transclusions if enabled
        if expand_transclusions:
            raw_content = self._expand_transclusions(raw_content)

        chunks: List[Chunk] = []
        tokens = self.md.parse(raw_content)

        current_header = Path(file_path).stem
        current_content: List[str] = []

        for token in tokens:
            if token.type == "heading_open" and token.tag == "h2":
                # Save previous chunk if exists
                if current_content:
                    chunk_text = "\n".join(current_content).strip()
                    if chunk_text:
                        chunks.append(
                            self._create_chunk(
                                file_path,
                                current_header,
                                chunk_text,
                                folder_path=folder_path,
                                frontmatter=frontmatter,
                                raw_content=raw_content,
                            )
                        )
                    current_content = []

            elif token.type == "inline":
                # Extract heading text
                if token.content:
                    # Check if this is heading content
                    parent_open = [t for t in tokens if t.type == "heading_open"]
                    if parent_open:
                        current_header = token.content
                    current_content.append(token.content)

            elif token.type in ("paragraph_open", "list_item_open", "blockquote_open"):
                # Collect content
                pass

            elif token.content:
                current_content.append(token.content)

        # Save last chunk
        if current_content:
            chunk_text = "\n".join(current_content).strip()
            if chunk_text:
                chunks.append(
                    self._create_chunk(
                        file_path,
                        current_header,
                        chunk_text,
                        folder_path=folder_path,
                        frontmatter=frontmatter,
                        raw_content=raw_content,
                    )
                )

        # If no chunks were created (e.g., file has no content after parsing),
        # still record file-level data blocks in an empty chunk
        if not chunks and file_data_blocks:
            chunks.append(
                Chunk(
                    file_path=file_path,
                    header=Path(file_path).stem,
                    content="",
                    links=[],
                    tags=(
                        list(frontmatter.get("tags", []))
                        if isinstance(frontmatter.get("tags"), list)
                        else []
                    ),
                    folder_path=folder_path,
                    frontmatter=frontmatter,
                    transclusions=[],
                    inline_attributes=[],
                    data_blocks=file_data_blocks,
                )
            )
        elif chunks:
            # Associate file-level data blocks with the first chunk
            chunks[0].data_blocks.extend(file_data_blocks)

        return chunks

    def _create_chunk(
        self,
        file_path: str,
        header: str,
        content: str,
        folder_path: str = "",
        frontmatter: Optional[Dict[str, Any]] = None,
        raw_content: Optional[str] = None,
    ) -> Chunk:
        """Create a chunk with extracted links, tags, transclusions, and attributes.

        Note: Data blocks are extracted at file-level in _parse_file and added separately.

        Args:
            file_path: Path to the source file
            header: Header/title for this chunk
            content: Content text (parsed/joined from tokens)
            folder_path: Folder path relative to space root
            frontmatter: Extracted YAML frontmatter dict
            raw_content: Raw file content for extracting transclusions

        Returns:
            Chunk object
        """
        if frontmatter is None:
            frontmatter = {}

        links = self.link_pattern.findall(content)

        # Collect tags from both #hashtags in content and frontmatter tags property
        content_tags = self.tag_pattern.findall(content)
        frontmatter_tags = frontmatter.get("tags", [])

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

        # Extract transclusions from raw content (before expansion)
        # Use raw_content if available, otherwise fall back to content
        transclusion_source = raw_content if raw_content else content
        transclusions = self._extract_transclusions(transclusion_source)

        # Extract inline attributes [name: value] from parsed content
        inline_attributes = self._extract_inline_attributes(content)

        # Data blocks are added at file-level by _parse_file, not here
        return Chunk(
            file_path=file_path,
            header=header,
            content=content,
            links=links,
            tags=all_tags,
            folder_path=folder_path,
            frontmatter=frontmatter,
            transclusions=transclusions,
            inline_attributes=inline_attributes,
            data_blocks=[],  # Will be populated by _parse_file
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
        return self.FRONTMATTER_PATTERN.sub("", content)

    def _extract_transclusions(self, content: str) -> List[Transclusion]:
        """Extract transclusion references from content.

        Args:
            content: Markdown content

        Returns:
            List of Transclusion objects
        """
        transclusions = []
        for match in self.transclusion_pattern.finditer(content):
            target_page = match.group(1).strip()
            target_header = match.group(2).strip() if match.group(2) else None
            transclusions.append(
                Transclusion(target_page=target_page, target_header=target_header)
            )
        return transclusions

    def _extract_inline_attributes(self, content: str) -> List[InlineAttribute]:
        """Extract inline attributes [name: value] from content.

        Args:
            content: Markdown content

        Returns:
            List of InlineAttribute objects
        """
        attributes = []
        for match in self.inline_attr_pattern.finditer(content):
            name = match.group(1).strip()
            value = match.group(2).strip()
            attributes.append(InlineAttribute(name=name, value=value))
        return attributes

    def _extract_data_blocks(self, content: str, file_path: str) -> List[DataBlock]:
        """Extract tagged data blocks (```#tagname YAML) from content.

        Args:
            content: Markdown content
            file_path: Path to the source file

        Returns:
            List of DataBlock objects
        """
        data_blocks = []
        for match in self.data_block_pattern.finditer(content):
            tag = match.group(1)
            yaml_content = match.group(2)
            try:
                data = yaml.safe_load(yaml_content) or {}
                if isinstance(data, dict):
                    data_blocks.append(
                        DataBlock(tag=tag, data=data, file_path=file_path)
                    )
            except yaml.YAMLError:
                # Skip malformed YAML blocks
                pass
        return data_blocks

    def _expand_transclusions(
        self, content: str, depth: int = 0, max_depth: int = 5
    ) -> str:
        """Expand transclusion references by inlining the target content.

        Args:
            content: Markdown content with transclusions
            depth: Current recursion depth
            max_depth: Maximum recursion depth to prevent infinite loops

        Returns:
            Content with transclusions expanded
        """
        if depth >= max_depth:
            return content

        def replace_transclusion(match: re.Match) -> str:
            target_page = match.group(1).strip()
            target_header = match.group(2).strip() if match.group(2) else None

            # Look up the target content in cache
            target_content = self._content_cache.get(target_page, "")
            if not target_content:
                # Try with path variations (e.g., folder/page vs page)
                for cached_page in self._content_cache:
                    if (
                        cached_page.endswith("/" + target_page)
                        or cached_page == target_page
                    ):
                        target_content = self._content_cache[cached_page]
                        break

            if not target_content:
                # Return original transclusion if target not found
                return match.group(0)

            # Strip frontmatter from target
            target_content = self._strip_frontmatter(target_content)

            # If targeting a specific header, extract that section
            if target_header:
                target_content = self._extract_section(target_content, target_header)

            # Recursively expand transclusions in the included content
            target_content = self._expand_transclusions(
                target_content, depth + 1, max_depth
            )

            return target_content

        return self.transclusion_pattern.sub(replace_transclusion, content)

    def _extract_section(self, content: str, header: str) -> str:
        """Extract a section from content starting at a header.

        Args:
            content: Markdown content
            header: Header text to find

        Returns:
            Content from the header to the next same-level or higher header
        """
        lines = content.split("\n")
        in_section = False
        section_lines = []
        section_level = 0

        for line in lines:
            # Check if this is a header line
            header_match = re.match(r"^(#+)\s+(.+)$", line)
            if header_match:
                level = len(header_match.group(1))
                header_text = header_match.group(2).strip()

                if header_text.lower() == header.lower():
                    in_section = True
                    section_level = level
                    section_lines.append(line)
                elif in_section and level <= section_level:
                    # Hit a same-level or higher header, stop
                    break
                elif in_section:
                    section_lines.append(line)
            elif in_section:
                section_lines.append(line)

        return "\n".join(section_lines)

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
            with open(file_path, "r", encoding="utf-8") as f:
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

            # Skip files in hidden directories
            if self._should_skip_directory(relative_path):
                continue

            # Add all parent folders
            current = relative_path.parent
            while current != Path("."):
                if not self._should_skip_directory(current):
                    folders.add(str(current))
                current = current.parent

        # Also add any directories that exist (even without .md files)
        for item in space_path.rglob("*"):
            if item.is_dir():
                relative = item.relative_to(space_path)
                if not self._should_skip_directory(relative):
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

        for folder in space_path.rglob("*"):
            if folder.is_dir():
                relative_folder = folder.relative_to(space_path)
                # Skip hidden directories
                if self._should_skip_directory(relative_folder):
                    continue
                # Check for sibling .md file with same name as folder
                index_file = folder.parent / f"{folder.name}.md"
                if index_file.exists():
                    relative_index = index_file.relative_to(space_path)
                    index_map[str(relative_folder)] = str(relative_index)

        return index_map
