# Information for Coding Assistants

This document provides context for AI coding assistants working on the Silverbullet RAG codebase.

## Project Overview

Silverbullet RAG is a Python-based RAG (Retrieval-Augmented Generation) system for [Silverbullet](https://silverbullet.md), a personal knowledge management system. It indexes a Silverbullet space into a knowledge graph with vector embeddings, then exposes search capabilities via MCP and gRPC.

## Architecture

```
Silverbullet Space (markdown files)
         ↓
    SpaceParser (markdown-it-py)
         ↓
    GraphDB (LadybugDB)
    ├── Knowledge Graph (Cypher queries)
    ├── BM25 Keyword Index
    └── HNSW Vector Index (OpenAI embeddings)
         ↓
    ┌────┴────┐
    ▼         ▼
  MCP      gRPC
 Server   Server
```

## Key Components

| Component          | Location                        | Purpose                                                          |
| ------------------ | ------------------------------- | ---------------------------------------------------------------- |
| `SpaceParser`      | `server/parser/space_parser.py` | Parses markdown, extracts chunks, wikilinks, tags, transclusions |
| `GraphDB`          | `server/db/graph.py`            | LadybugDB wrapper with Cypher, BM25, and vector search           |
| `EmbeddingService` | `server/embeddings.py`          | Embedding generation (OpenAI or local fastembed)                 |
| `HybridSearch`     | `server/search/hybrid.py`       | Combines keyword + semantic search with RRF                      |
| `MCP Server`       | `server/mcp_http_server.py`     | FastMCP HTTP server with 9 tools                                 |
| `Proposals`        | `server/proposals.py`           | Proposal management (propose, list, withdraw)                    |
| `ConfigParser`     | `server/config_parser.py`       | Parse CONFIG.md space-lua blocks                                 |
| `gRPC Server`      | `server/grpc_server.py`         | Fast binary protocol for hooks                                   |
| `Watcher`          | `server/watcher.py`             | File system monitoring for auto-reindex                          |

## Conventions

### Code Style

- **Formatter/Linter**: Ruff (replaces Black, isort, flake8)
- **Pre-commit**: Hooks configured in `.pre-commit-config.yaml`
- **Type hints**: Required for all public functions
- **Docstrings**: Google-style docstrings
- **Imports**: Auto-sorted by ruff, grouped by stdlib → third-party → local

### Testing

- **Framework**: pytest with pytest-asyncio for async tests
- **Local embeddings**: Tests use fastembed (local provider) to avoid API calls
- **Coverage**: Maintain high coverage, especially for search and parsing
- **TDD**: Write tests first when adding features

Run tests:
```bash
python -m pytest tests/ -v
python -m pytest tests/ --cov=server --cov-report=term-missing
```

Run linting:
```bash
pre-commit run --all-files
# Or directly:
ruff check server/ tests/ --fix
ruff format server/ tests/
```

### Dependencies

**IMPORTANT**: This project has two dependency files that must stay in sync:
- `pyproject.toml` - Used for local development (`pip install -e .`)
- `requirements.txt` - Used by CI (`.github/workflows/ci.yml`)

When adding a new dependency:
1. Add to `pyproject.toml` under `[project.dependencies]`
2. Also add to `requirements.txt` with the same version constraint
3. CI will fail if a dependency is in pyproject.toml but missing from requirements.txt

### Version Tagging

Use semantic versioning without the `v` prefix:
- `0.2.0` ✓ (correct)
- `v0.2.0` ✗ (incorrect - don't use `v` prefix)

### File Organization

```
server/
├── db/           # Database layer (GraphDB, schema)
├── parser/       # Markdown parsing (SpaceParser, Chunk dataclass)
├── search/       # Search implementations (BM25, semantic, hybrid)
├── grpc/         # gRPC protocol and service
├── pipe/         # Open WebUI integration
└── *.py          # Server entry points (mcp, grpc, watcher)

tests/
├── conftest.py   # Shared fixtures (mock OpenAI, temp paths)
└── test_*.py     # Test modules matching server structure
```

## Important Patterns

### Chunk Processing

Chunks are the core data unit:
```python
@dataclass
class Chunk:
    file_path: str
    header: str
    content: str
    wikilinks: List[str]
    tags: List[str]
    frontmatter: Dict[str, Any]
    transclusions: List[Transclusion]      # v2: ![[page]]
    inline_attributes: List[InlineAttribute]  # v2: [key: value]
    data_blocks: List[DataBlock]           # v2: ```#tag yaml```
```

### Graph Relationships

When modifying the graph schema, update both:
1. `server/db/graph.py` - Schema creation in `__init__`
2. `README.md` - Graph Schema section

Current relationships:
- `LINKS_TO`: Chunk → Page (wikilinks)
- `EMBEDS`: Chunk → Page (transclusions)
- `TAGGED`: Chunk → Tag
- `IN_FOLDER`: Chunk → Folder
- `CONTAINS`: Folder → Folder
- `HAS_ATTRIBUTE`: Chunk → Attribute
- `HAS_DATA_BLOCK`: Chunk → DataBlock
- `DATA_TAGGED`: DataBlock → Tag

### Security Considerations

- **Cypher injection**: Always use parameterized queries
- **Path traversal**: Validate all file paths against space root
- **Input sanitization**: Handle unicode, special chars in search queries

## Environment Variables

| Variable            | Default                  | Purpose                                    |
| ------------------- | ------------------------ | ------------------------------------------ |
| `SPACE_PATH`        | `/space`                 | Path to Silverbullet space                 |
| `DB_PATH`           | `/data/ladybug`          | Path to LadybugDB database                 |
| `EMBEDDING_PROVIDER`| `openai`                 | Provider: `openai` or `local` (fastembed)  |
| `OPENAI_API_KEY`    | (required for openai)    | OpenAI API key for embeddings              |
| `EMBEDDING_MODEL`   | varies by provider       | Model name (provider-specific)             |
| `ENABLE_EMBEDDINGS` | `true`                   | Enable/disable embedding generation        |

## Common Tasks

### Adding a New MCP Tool

1. Add the tool function in `server/mcp_http_server.py`:
   ```python
   @mcp.tool()
   async def my_tool(arg: str) -> Dict[str, Any]:
       """Tool description for LLM."""
       try:
           # implementation
           return {"success": True, "result": ...}
       except Exception as e:
           return {"success": False, "error": str(e)}
   ```

2. Add tests in `tests/test_mcp_http.py`
3. Update `README.md` features section

### Adding a New Graph Relationship

1. Add schema in `GraphDB.__init__`:
   ```python
   conn.execute("CREATE REL TABLE IF NOT EXISTS NEW_REL(FROM NodeA TO NodeB, prop STRING)")
   ```

2. Create relationships in `index_chunks`:
   ```python
   conn.execute(
       "MERGE (a:NodeA {id: $a_id})-[:NEW_REL {prop: $prop}]->(b:NodeB {id: $b_id})",
       {"a_id": ..., "b_id": ..., "prop": ...}
   )
   ```

3. Clean up in `delete_chunks_by_file` and `clear_database`
4. Update README Graph Schema section
5. Add tests

### Modifying the Parser

1. Update `SpaceParser` in `server/parser/space_parser.py`
2. Update `Chunk` dataclass if adding new fields
3. Export new classes from `server/parser/__init__.py`
4. Add tests in `tests/test_v2_features.py` or create new test file

## Debugging Tips

- **LadybugDB issues**: Check database file permissions, try `--rebuild` flag
- **Embedding failures**: Verify `OPENAI_API_KEY`, check rate limits
- **Parser issues**: Use `SpaceParser._extract_*` methods for isolated testing
- **gRPC issues**: Compile proto with `python -m grpc_tools.protoc`

## Dependencies

Key dependencies:
- `real-ladybug`: LadybugDB Python client
- `mcp`: Model Context Protocol SDK
- `markdown-it-py`: Markdown AST parsing
- `openai`: Embedding generation
- `grpcio`: gRPC server/client
- `watchdog`: File system events

See `pyproject.toml` for full dependency list.

## Proposals System

The proposal system allows external tools to suggest changes that users review before applying.

### How It Works

1. Tool calls `propose_change` MCP/gRPC method with target page and proposed content
2. System creates a `.proposal` file in `_Proposals/` folder
3. User opens proposal in Silverbullet to see inline diff
4. User clicks Accept (applies change) or Reject (moves to `_Rejected/`)

### Key Files

| File | Purpose |
|------|---------|
| `server/proposals.py` | Proposal management utilities |
| `server/config_parser.py` | Parse CONFIG.md for settings |
| `library/Proposals/` | Silverbullet plug with document editor |

### Configuration

Users configure in their Silverbullet `CONFIG.md`:

```space-lua
config.set("mcp.proposals.path_prefix", "_Proposals/")
config.set("mcp.proposals.cleanup_after_days", 30)
```

The watcher parses CONFIG.md and writes `space_config.json` for MCP server use.

### Conditional Tool Registration

Proposal tools are only enabled if the Proposals library is installed:

```python
# In mcp_http_server.py
if library_installed(space_path):
    proposals_enabled = True
```

This prevents errors when the library isn't installed.
