# Information for Coding Assistants

This document provides context for AI coding assistants working on the Silverbullet RAG codebase.

## Project Overview

Silverbullet RAG is a Go-based RAG (Retrieval-Augmented Generation) system for [Silverbullet](https://silverbullet.md), a personal knowledge management system. It indexes a Silverbullet space into a knowledge graph with vector embeddings, then exposes search capabilities via MCP and gRPC.

## Architecture

```
Silverbullet Space (markdown files)
         ↓
    SpaceParser (goldmark)
         ↓
    GraphDB (LadybugDB)
    ├── Knowledge Graph (Cypher queries)
    ├── BM25 Keyword Index
    └── HNSW Vector Index (OpenAI/local embeddings)
         ↓
    ┌────┴────┐
    ▼         ▼
  MCP      gRPC
 Server   Server
```

## Key Components

| Component          | Location                        | Purpose                                                          |
| ------------------ | ------------------------------- | ---------------------------------------------------------------- |
| `SpaceParser`      | `internal/parser/`              | Parses markdown, extracts chunks, wikilinks, tags, transclusions |
| `GraphDB`          | `internal/db/`                  | LadybugDB wrapper with Cypher, BM25, and vector search           |
| `EmbeddingService` | `internal/embeddings/`          | Embedding generation (OpenAI or local hugot/ONNX)                |
| `HybridSearch`     | `internal/search/`              | Combines keyword + semantic search with RRF                      |
| `MCP Server`       | `internal/server/mcp.go`        | Streamable HTTP MCP server with 10 tools                         |
| `Proposals`        | `internal/server/`              | Proposal management (propose, list, withdraw)                    |
| `ConfigParser`     | `internal/config/`              | Parse CONFIG.md space-lua blocks via Deno sidecar                |
| `gRPC Server`      | `internal/server/grpc.go`       | Fast binary protocol for hooks                                   |
| `Watcher`          | `internal/watcher/`             | File system monitoring for auto-reindex                          |
| `Open WebUI Pipe`  | `openwebui/silverbullet_rag.py` | Single-file gRPC client for Open WebUI integration               |

## Conventions

### Code Style

- **Formatter/Linter**: golangci-lint
- **Pre-commit**: Hooks configured in `.pre-commit-config.yaml`
- **Imports**: Auto-sorted by gofmt, grouped by stdlib → third-party → local

### Testing

- **Framework**: Go standard testing with testify assertions
- **Local embeddings**: Tests use hugot (local ONNX provider) to avoid API calls
- **Coverage**: Maintain high coverage, especially for search and parsing
- **TDD**: Write tests first when adding features

Run tests:
```bash
go test ./... -v
go test ./... -cover
```

Run linting:
```bash
golangci-lint run
pre-commit run --all-files
```

### Version Tagging

Use semantic versioning without the `v` prefix:
- `0.2.0` ✓ (correct)
- `v0.2.0` ✗ (incorrect - don't use `v` prefix)

A pre-push hook validates this. Run `scripts/install-hooks.sh` to install it.

### File Organization

```
proto/
└── rag.proto           # gRPC service definition (shared between server and clients)

cmd/
└── rag-server/         # Main entry point

internal/
├── config/             # Configuration parsing (CONFIG.md, space-lua)
├── db/                 # Database layer (GraphDB, schema)
├── embeddings/         # Embedding generation (OpenAI, local)
├── parser/             # Markdown parsing (SpaceParser, Chunk struct)
├── proto/              # Generated gRPC stubs
├── search/             # Search implementations (BM25, semantic, hybrid)
├── server/             # MCP and gRPC server implementations
├── types/              # Shared types (Chunk, etc.)
├── version/            # Version information
└── watcher/            # File system monitoring

deno/
└── space_lua_runner.ts # Deno sidecar for space-lua execution

openwebui/
└── silverbullet_rag.py # Open WebUI pipe (generated, single-file gRPC client)

scripts/
└── build_openwebui_pipe.py  # Build script for Open WebUI pipe

tests/
└── golden/             # Golden test files for parity testing
```

## Important Patterns

### Chunk Processing

Chunks are the core data unit (see `internal/types/chunk.go`):
```go
type Chunk struct {
    FilePath         string
    Header           string
    Content          string
    Wikilinks        []string
    Tags             []string
    Frontmatter      map[string]any
    Transclusions    []Transclusion
    InlineAttributes []InlineAttribute
    DataBlocks       []DataBlock
    Embedding        []float32
}
```

### Graph Relationships

When modifying the graph schema, update both:
1. `internal/db/graph.go` - Schema creation in `InitSchema`
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

## Configuration

The server uses CLI flags:

| Flag                  | Default         | Purpose                                    |
| --------------------- | --------------- | ------------------------------------------ |
| `--space-path`        | `/space`        | Path to Silverbullet space                 |
| `--db-path`           | `/data/ladybug` | Path to LadybugDB database                 |
| `--mcp-port`          | `8000`          | MCP HTTP server port                       |
| `--grpc-port`         | `50051`         | gRPC server port                           |
| `--health-port`       | `8080`          | Health check endpoint port                 |
| `--embedding-provider`| `openai`        | Provider: `openai` or `local`              |
| `--embedding-model`   | varies          | Model name (provider-specific)             |
| `--enable-embeddings` | `true`          | Enable/disable embedding generation        |

Environment variables are also supported (e.g., `SPACE_PATH`, `DB_PATH`, `OPENAI_API_KEY`).

## Common Tasks

- **MCP tools**: Add to `internal/server/mcp.go`, test in `internal/server/mcp_test.go`
- **Graph relationships**: Add schema in `internal/db/graph.go`, update `README.md` Graph Schema
- **Parser changes**: Update `internal/parser/`, `internal/types/chunk.go`
- **Open WebUI pipe**: Run `python scripts/build_openwebui_pipe.py` after proto changes

## Proposals System

Allows external tools to suggest changes users review before applying:
1. Tool calls `propose_change` → creates `.proposal` file in `_Proposals/`
2. User opens in Silverbullet → sees inline diff via custom document editor
3. Accept (applies) or Reject (moves to `_Rejected/`)

Proposal tools only enabled if `Library/Proposals.md` is installed in the space.

### Library Structure

The Proposals library in `library/` contains:
- `Proposals.md` - Main library file with Space-Lua code (must have `tags: meta/library`)
- `Proposals/Proposals.md` - Dashboard page
- `Proposals/plug.yaml` - Plug manifest for document editor
- `Proposals/proposal_editor.ts` - TypeScript source for `.proposal` file editor
- `Proposals/Proposals.plug.js` - Compiled plug (committed, rebuild with deno)

To rebuild the plug after changes to `proposal_editor.ts`:
```bash
cd silverbullet
deno run -A bin/plug-compile.ts ../../library/Proposals/plug.yaml --dist ../../library/Proposals --config deno.json
```

## Open WebUI Pipe

See [docs/openwebui-pipe.md](docs/openwebui-pipe.md) for setup. Key points:
- Generated file embedding protobuf stubs for single-file deployment
- Rebuild with `python scripts/build_openwebui_pipe.py` after proto changes
- Pipe logic is in `PIPE_TEMPLATE` in the build script

## Deno Sidecar

The CONFIG.md space-lua execution uses a Deno sidecar (`deno/space_lua_runner.ts`):
- Imports the same space-lua runtime as Silverbullet
- Called via subprocess with JSON stdin/stdout
- Returns parsed config values as JSON
- Falls back to AST parsing if Deno is unavailable
