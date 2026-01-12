# Silverbullet RAG

A RAG (Retrieval-Augmented Generation) system for [Silverbullet](https://silverbullet.md) that indexes your knowledge base into a searchable graph with vector embeddings, exposed via MCP and gRPC for AI assistant integration.

## Features

- **Knowledge Graph**: Pages, chunks, links, tags, and folders stored in LadybugDB
- **Semantic Search**: OpenAI or local (fastembed) embeddings with HNSW vector indexing
- **BM25 Keyword Search**: Tag boosting, technical term detection, header boosting
- **Hybrid Search**: Combines keyword + semantic using Reciprocal Rank Fusion
- **Silverbullet v2**: Transclusion expansion, inline attributes `[key: value]`, data blocks
- **MCP Server**: 7 tools for AI assistants (Claude, Cursor, etc.)
- **gRPC API**: Fast access for Silverbullet hooks
- **File Watcher**: Auto-reindex on changes

## Quick Start

### 1. Initialize the Index

```bash
docker run --rm \
  -v silverbullet-space:/space:ro \
  -v ladybug-db:/data \
  -e DB_PATH=/data/ladybug \
  -e SPACE_PATH=/space \
  -e OPENAI_API_KEY=${OPENAI_API_KEY} \
  ghcr.io/YOUR_USERNAME/silverbullet-rag:latest \
  python -m server.init_index
```

Use `--rebuild` to clear and rebuild the database from scratch.

### 2. Start the Server

```bash
# Create .env file
echo "OPENAI_API_KEY=your-key-here" > .env

# Start with docker-compose
docker-compose up -d
```

### 3. Connect Your AI Assistant

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
| `update_page` | Create or update a page |

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

**Local** (fastembed): Uses local models via [fastembed](https://github.com/qdrant/fastembed). No API key required.
- Default model: `BAAI/bge-small-en-v1.5` (384 dimensions)
- Good for privacy-sensitive deployments or testing without API costs

## Architecture

```
Silverbullet Space → File Watcher → Space Parser → Embedding Service
                                         ↓
                                    LadybugDB
                              (Graph + Vector Index)
                                         ↓
                    ┌────────────────────┼────────────────────┐
                    ↓                    ↓                    ↓
                MCP Server          gRPC Server          Open WebUI
               (Port 8000)         (Port 50051)            Pipe
```

## Documentation

| Document | Description |
|----------|-------------|
| [docs/deployment.md](docs/deployment.md) | Docker setup, compose files, production config |
| [docs/mcp.md](docs/mcp.md) | MCP integration for various AI assistants |
| [docs/grpc.md](docs/grpc.md) | gRPC client examples (Python, TypeScript, Rust, Go, C#) |
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
