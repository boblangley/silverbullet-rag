# Silverbullet RAG

A RAG (Retrieval-Augmented Generation) system for [Silverbullet](https://silverbullet.md) that indexes your knowledge base into a searchable graph with vector embeddings, exposed via MCP for AI assistant integration and gRPC for automation/programmatic use.

## Features

- **Knowledge Graph**: Pages, chunks, links, tags, and folders stored in LadybugDB
- **Semantic Search**: OpenAI or local (fastembed) embeddings with HNSW vector indexing
- **BM25 Keyword Search**: Tag boosting, technical term detection, header boosting
- **Hybrid Search**: Combines keyword + semantic using Reciprocal Rank Fusion
- **Silverbullet v2**: Transclusion expansion, inline attributes `[key: value]`, data blocks
- **MCP Server**: 9 tools for AI assistants (Claude, Cursor, etc.)
- **Open WebUI Pipe**: RAG integration with folder context mapping
- **Proposals**: Propose changes for user review before applying
- **gRPC API**: Fast access for Silverbullet hooks
- **File Watcher**: Auto-reindex on changes

## Quick Start

### 1. Start the Server

```bash
# Start with docker-compose
docker-compose up -d
```

The server will automatically index your Silverbullet space on startup.

### 2. Connect Your AI Assistant

Add to your MCP client config (e.g., `.mcp.json`):

```json
{
  "mcpServers": {
    "silverbullet-rag": {
      "type": "url",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

See [docs/mcp.md](docs/mcp.md) for Claude Code, Cursor, VS Code, and JetBrains setup.

## MCP Tools

| Tool | Description |
|------|-------------|
| `cypher_query` | Execute Cypher queries against the knowledge graph |
| `keyword_search` | BM25-ranked keyword search |
| `semantic_search` | Vector similarity search |
| `hybrid_search_tool` | Combined keyword + semantic with RRF fusion |
| `get_project_context` | Get project context by GitHub remote or folder path |
| `read_page` | Read a Silverbullet page |
| `propose_change` | Propose a change for user review (requires Proposals library) |
| `list_proposals` | List pending/accepted/rejected proposals |
| `withdraw_proposal` | Withdraw a pending proposal |

## Silverbullet Library

This project includes the **Proposals** library for Silverbullet that enables external tools to propose changes for user review. Instead of directly modifying pages, tools create proposals that you can review with inline diffs and accept or reject.

### Installing the Library

Use Silverbullet's built-in Library Manager:

1. Run the `Library: Manager` command in Silverbullet
2. Add this repository to your repositories list
3. Install the Proposals library

Once installed, the proposal MCP tools become available, and you can review proposals directly in Silverbullet.

See [docs/library.md](docs/library.md) for detailed documentation on the proposal system.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SPACE_PATH` | `/space` | Path to Silverbullet space |
| `DB_PATH` | `/data/ladybug` | Path to LadybugDB database |
| `EMBEDDING_PROVIDER` | `openai` | Embedding provider: `openai` or `local` |
| `OPENAI_API_KEY` | (required for openai) | OpenAI API key for embeddings |
| `EMBEDDING_MODEL` | varies by provider | Model name (see below) |
| `ENABLE_EMBEDDINGS` | `true` | Set to `false` for keyword-only search |

### Embedding Providers

**OpenAI** (default): Uses OpenAI API for embeddings. Requires `OPENAI_API_KEY`.
- Default model: `text-embedding-3-small` (1536 dimensions)

**Local**: Uses local ONNX models via [hugot](https://github.com/knights-analytics/hugot). No API key required.
- Default model: `BAAI/bge-small-en-v1.5` (384 dimensions)
- Good for privacy-sensitive deployments or testing without API costs

## Building from Source

```bash
# Build with CGO (requires LadybugDB native library)
go build -o rag-server ./cmd/rag-server

# Run
./rag-server -space /path/to/space -db /data/ladybug.db
```

### Command Line Flags

| Flag | Default | Description |
|------|---------|-------------|
| `-space` | (required) | Path to SilverBullet space directory |
| `-db` | `<space>/.silverbullet-rag/ladybug.db` | Path to LadybugDB database |
| `-grpc` | `:50051` | gRPC server address |
| `-mcp` | `:8000` | MCP HTTP server address |
| `-health-port` | `8080` | Health check HTTP port (0 to disable) |
| `-log-level` | `info` | Log level (debug, info, warn, error) |
| `-rebuild` | `false` | Rebuild index from scratch |
| `-no-embeddings` | `false` | Disable embedding generation |
| `-library-path` | `./library` | Path to bundled library files |
| `-allow-library-management` | `false` | Enable library install/update MCP tools |

### Docker

```bash
# Build the image
docker build -t silverbullet-rag .

# Run
docker run --rm \
  -v /path/to/space:/space:ro \
  -v ladybug-db:/data \
  -p 50051:50051 \
  -p 8000:8000 \
  -p 8080:8080 \
  silverbullet-rag
```

### Health Endpoints

The server provides Kubernetes-compatible health endpoints on port 8080:

| Endpoint | Description |
|----------|-------------|
| `/health` | Combined health status of gRPC and MCP services |
| `/health/grpc` | gRPC server health |
| `/health/mcp` | MCP server health |
| `/ready` | Readiness probe (services ready to accept traffic) |
| `/live` | Liveness probe (process is running) |

## Architecture

```
Silverbullet Space → File Watcher → Space Parser → Embedding Service
                                         ↓
                                    LadybugDB
                              (Graph + Vector Index)
                                         ↓
                    ┌────────────────────┐
                    ↓                    ↓
                MCP Server          gRPC Server
               (Port 8000)         (Port 50051)
```

## Documentation

| Document | Description |
|----------|-------------|
| [docs/deployment.md](docs/deployment.md) | Docker setup, compose files, production config |
| [docs/mcp.md](docs/mcp.md) | MCP integration for various AI assistants |
| [docs/openwebui-pipe.md](docs/openwebui-pipe.md) | Open WebUI pipe setup and folder context mapping |
| [docs/grpc.md](docs/grpc.md) | gRPC client examples (Python, TypeScript, Rust, Go, C#) |
| [docs/library.md](docs/library.md) | Proposals Silverbullet library |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup, testing, code quality |
| [AGENTS.md](AGENTS.md) | Coding assistant instructions, architecture details |

## Graph Schema

The knowledge graph includes these node types and relationships:

**Nodes**: `Chunk`, `Page`, `Tag`, `Folder`, `Attribute`, `DataBlock`

**Relationships**:
- `LINKS_TO`: Wikilinks `[[page]]`
- `EMBEDS`: Transclusions `![[page]]`
- `TAGGED`: Hashtags and frontmatter tags
- `IN_FOLDER`, `CONTAINS`: Folder hierarchy
- `HAS_ATTRIBUTE`, `HAS_DATA_BLOCK`, `DATA_TAGGED`: Silverbullet v2 features

See [AGENTS.md](AGENTS.md) for detailed schema and example Cypher queries.

## Security

- Cypher injection protection (parameterized queries)
- Path traversal protection
- Input validation for unicode and special characters

## License

MIT
