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
| `MCP Server`       | `server/mcp/`                   | FastMCP HTTP server package with 10 tools                        |
| `Proposals`        | `server/proposals.py`           | Proposal management (propose, list, withdraw)                    |
| `ConfigParser`     | `server/config_parser.py`       | Parse CONFIG.md space-lua blocks                                 |
| `gRPC Server`      | `server/grpc_server.py`         | Fast binary protocol for hooks                                   |
| `Open WebUI Pipe`  | `openwebui/silverbullet_rag.py` | Single-file gRPC client for Open WebUI integration               |
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

A pre-push hook validates this. Run `scripts/install-hooks.sh` to install it.

### File Organization

```
proto/
└── rag.proto           # gRPC service definition (shared between server and clients)

server/
├── db/                 # Database layer (GraphDB, schema)
├── parser/             # Markdown parsing (SpaceParser, Chunk dataclass)
├── search/             # Search implementations (BM25, semantic, hybrid)
├── grpc/               # Generated gRPC stubs for server
└── *.py                # Server entry points (mcp, grpc, watcher)

openwebui/
└── silverbullet_rag.py # Open WebUI pipe (generated, single-file gRPC client)

scripts/
└── build_openwebui_pipe.py  # Build script for Open WebUI pipe

tests/
├── conftest.py         # Shared fixtures (mock OpenAI, temp paths)
└── test_*.py           # Test modules matching server structure
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

- **MCP tools**: Add to `server/mcp/tools/`, register in `__init__.py`, test in `test_mcp_http.py`
- **Graph relationships**: Add schema in `GraphDB.__init__`, update `README.md` Graph Schema
- **Parser changes**: Update `SpaceParser`, `Chunk` dataclass, export from `__init__.py`
- **Open WebUI pipe**: Run `python scripts/build_openwebui_pipe.py` after proto changes

## Proposals System

Allows external tools to suggest changes users review before applying:
1. Tool calls `propose_change` → creates `.proposal` file in `_Proposals/`
2. User opens in Silverbullet → sees inline diff
3. Accept (applies) or Reject (moves to `_Rejected/`)

Proposal tools only enabled if `library/Proposals/` is installed in the space.

## Open WebUI Pipe

See [docs/openwebui-pipe.md](docs/openwebui-pipe.md) for setup. Key points:
- Generated file embedding protobuf stubs for single-file deployment
- Rebuild with `python scripts/build_openwebui_pipe.py` after proto changes
- Pipe logic is in `PIPE_TEMPLATE` in the build script
