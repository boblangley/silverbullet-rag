# Silverbullet RAG

A production-ready RAG (Retrieval-Augmented Generation) system for Silverbullet that uses LadybugDB for graph-based knowledge storage, OpenAI embeddings for semantic search, and Model Context Protocol (MCP) for AI assistant integration.

## Features

- **Graph-based Knowledge Storage**: Uses LadybugDB to store pages, chunks, links, tags, and folders as a graph
- **Folder Hierarchy**: Tracks folder structure with `CONTAINS` relationships for scoped searches
- **Project Context**: Automatic context injection via `get_project_context` tool using GitHub remotes or folder paths
- **YAML Frontmatter Parsing**: Extracts `github` and `tags` metadata from markdown files
- **Scoped Search**: Filter search results to specific folders/projects using `scope` parameter
- **Semantic Search**: AI-powered search using OpenAI embeddings with HNSW vector indexing
- **BM25 Keyword Search**: Professional-grade keyword search with tag boosting and technical term detection
- **Hybrid Search**: Combines keyword and semantic search using Reciprocal Rank Fusion (RRF) or weighted fusion
- **MCP Server**: Exposes 7 tools via Model Context Protocol for AI assistants like Claude
- **gRPC API**: Fast access for Silverbullet hooks and other integrations
- **File Watcher**: Automatically reindexes when files change
- **Open WebUI Pipe**: RAG integration for Open WebUI
- **Markdown Parsing**: Chunks documents by headings, extracts wikilinks and tags
- **Content Cleaning**: Removes Silverbullet syntax noise before embedding

## Quick Start

Initialize your RAG

```bash
docker run --rm \
  -v silverbullet-space:/space:ro \
  -v ladybug-db:/data \
  -e DB_PATH=/data/ladybug \
  -e SPACE_PATH=/space \
  -e OPENAI_API_KEY=${OPENAI_API_KEY} \
  -e ENABLE_EMBEDDINGS=true \
  silverbullet-rag \
  python -m server.init_index
```

### Option 1: Using Pre-built Image from GitHub Container Registry

```bash
# Set OpenAI API key in .env file
echo "OPENAI_API_KEY=your-key-here" > .env
echo "EMBEDDING_MODEL=text-embedding-3-small" >> .env

# Pull the latest image
docker pull ghcr.io/YOUR_USERNAME/silverbullet-rag:latest

# Start services using docker-compose
docker-compose up -d

# View logs
docker-compose logs -f mcp-server
```

### Option 2: Build from Source

```bash
# Set OpenAI API key
echo "OPENAI_API_KEY=your-key-here" > .env
echo "EMBEDDING_MODEL=text-embedding-3-small" >> .env

# Build and start services
docker-compose up -d --build

# View logs
docker-compose logs -f mcp-server
```

## Connecting to the MCP Server

### From Claude Desktop (or other MCP clients)

Add to your MCP client configuration file (e.g., `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "silverbullet-rag": {
      "url": "http://YOUR_SERVER_IP:8000/mcp",
      "transport": "http"
    }
  }
}
```

Replace `YOUR_SERVER_IP` with your server's IP address:
- **Local development**: `http://localhost:8000/mcp`
- **Home network**: `http://192.168.1.100:8000/mcp` (your server's LAN IP)
- **Remote access**: `http://your-domain.com:8000/mcp` (requires port forwarding or VPN)

### Testing the Connection

```bash
# Check if MCP server is running
curl http://localhost:8000/mcp

# View server logs
docker-compose logs -f mcp-server

# Check gRPC server
grpcurl -plaintext localhost:50051 list
```

## gRPC Python Client

For Python integrations (e.g., Silverbullet hooks), use the gRPC client:

```python
import grpc
import json
from server.grpc import rag_pb2, rag_pb2_grpc

# Connect to the server
channel = grpc.insecure_channel('localhost:50051')
stub = rag_pb2_grpc.RAGServiceStub(channel)

# Keyword search
response = stub.Search(rag_pb2.SearchRequest(keyword="python"))
if response.success:
    results = json.loads(response.results_json)
    for chunk in results:
        print(f"Found: {chunk['col0']['file_path']}")

# Semantic search
response = stub.SemanticSearch(rag_pb2.SemanticSearchRequest(
    query="How do I configure authentication?",
    limit=10,
    filter_tags=["config"]
))

# Hybrid search (best results)
response = stub.HybridSearch(rag_pb2.HybridSearchRequest(
    query="database optimization",
    limit=10,
    fusion_method="rrf",
    semantic_weight=0.7,
    keyword_weight=0.3
))

# Raw Cypher query
response = stub.Query(rag_pb2.QueryRequest(
    cypher_query="MATCH (c:Chunk)-[:TAGGED]->(t:Tag {name: 'python'}) RETURN c"
))

# Update a page (triggers reindexing)
response = stub.UpdatePage(rag_pb2.UpdatePageRequest(
    page_name="Notes/MyPage.md",
    content="# My Page\n\nNew content."
))

channel.close()
```

## MCP Tools

The MCP server provides seven tools for AI assistants:

1. **cypher_query** - Execute Cypher queries against the knowledge graph
2. **keyword_search** - BM25-ranked keyword search with tag boosting (supports `scope` filter)
3. **semantic_search** - AI-powered semantic search using vector embeddings (supports `scope` filter)
4. **hybrid_search** - Advanced search combining keyword and semantic methods (supports `scope` filter)
5. **get_project_context** - Get project context by GitHub remote or folder path
6. **read_page** - Read a specific Silverbullet page
7. **update_page** - Update or create a page (triggers reindexing)

### Project Context

The `get_project_context` tool enables automatic context injection when working on projects:

```python
# Find project by GitHub remote
result = await get_project_context(github_remote="anthropics/claude-code")

# Find project by folder path
result = await get_project_context(folder_path="Codex/MyProject")
```

Returns the project index page content, YAML frontmatter metadata (github, tags, concerns), and related pages.

### Scoped Search

All search tools support a `scope` parameter to filter results to a specific folder:

```python
# Search only within a project folder
results = await keyword_search(query="configuration", scope="Codex/MyProject")
results = await hybrid_search(query="setup instructions", scope="Codex/MyProject")
```

## Configuration

Set these environment variables or edit `docker-compose.yml`:

- `DB_PATH`: LadybugDB database path (default: `/data/ladybug`)
- `SPACE_PATH`: Silverbullet space path (default: `/space`)
- `OPENAI_API_KEY`: **Required** - OpenAI API key for embeddings
- `EMBEDDING_MODEL`: Embedding model (default: `text-embedding-3-small`)

**Note**: Embeddings are enabled by default. To disable (keyword search only), initialize `GraphDB` with `enable_embeddings=False`.

## Deployment

### GitHub Container Registry (GHCR)

Docker images are automatically built and published to GHCR via GitHub Actions:

- **On push to main**: Tagged as `latest` and `main-<sha>`
- **On version tags**: Tagged as `v1.0.0`, `v1.0`, `v1`
- **Multi-platform**: Built for `linux/amd64` and `linux/arm64`

For detailed deployment instructions (home network, VPN, reverse proxy, etc.), see [DEPLOYMENT.md](DEPLOYMENT.md).

## Development

### Setup
```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest tests/ -v --cov=server

# Compile proto files (if modified)
poetry run python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. --pyi_out=. server/grpc/rag.proto
```

### Test Data
The Silverbullet repo is included as a git submodule at `test-data/silverbullet/` for comprehensive testing with real-world markdown.

### Project Structure
```
server/
├── db/
│   └── graph.py         # LadybugDB wrapper with vector search (90%+ coverage)
├── parser/
│   └── space_parser.py  # Markdown parsing (95% test coverage)
├── embeddings.py        # OpenAI embedding service (95% coverage)
├── search.py            # Hybrid search with RRF fusion (90% coverage)
├── grpc/
│   └── rag.proto        # gRPC protocol (4 RPCs)
├── grpc_server.py       # gRPC endpoint (Port 50051)
├── mcp_server.py        # MCP stdio server [DEPRECATED - use mcp_http_server.py]
├── mcp_http_server.py   # MCP HTTP server (Port 8000) - PRODUCTION
├── watcher.py           # File system monitoring
└── pipe/
    └── openwebui_pipe.py # Open WebUI integration

tests/                   # 67 tests using TDD approach
├── conftest.py          # Test fixtures with OpenAI mocking
├── test_grpc_server.py  # gRPC functionality (6 tests)
├── test_graph_deletion.py # Deletion & cleanup (9 tests)
├── test_security.py     # Security protection (12 tests)
├── test_embeddings.py   # Embedding service (18 tests)
├── test_semantic_search.py # Vector search (13 tests)
├── test_hybrid_search.py   # Hybrid search
└── test_mcp_http.py     # MCP HTTP transport (9 tests)
```

### Architecture

```
┌─────────────────┐
│  Silverbullet   │
│     Space       │
└────────┬────────┘
         │ (mounted volume)
         ▼
┌─────────────────┐
│  File Watcher   │──► Detects changes
└────────┬────────┘
         ▼
┌─────────────────┐
│  Space Parser   │──► Extracts chunks, links, tags
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Embedding Svc   │──► OpenAI API (text-embedding-3-small)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   LadybugDB     │──► Graph + Vector storage
│  HNSW Index     │    (Cosine similarity)
└────────┬────────┘
         │
    ┌────┴─────┬──────────┬──────────┐
    ▼          ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Keyword │ │Semantic│ │ Hybrid │ │ Cypher │
│ Search │ │ Search │ │ Search │ │ Query  │
│ (BM25) │ │(Vector)│ │  (RRF) │ │        │
└────┬───┘ └────┬───┘ └────┬───┘ └────┬───┘
     │          │          │          │
     └──────────┴──────────┴──────────┘
                    ▼
         ┌──────────────────┐
         │   Search APIs    │
         └─────────┬────────┘
              ┌────┴─────┬──────────┐
              ▼          ▼          ▼
          ┌────────┐ ┌────────┐ ┌────────┐
          │  MCP   │ │  gRPC  │ │  Pipe  │
          │ Server │ │ Server │ │ (WebUI)│
          └────────┘ └────────┘ └────────┘
```

## Testing

All core functionality is tested using TDD (Test-Driven Development):

```bash
# Run all tests
poetry run pytest tests/ -v

# Run with coverage
poetry run pytest tests/ --cov=server --cov-report=term-missing

# Run specific test suites
poetry run pytest tests/test_embeddings.py -v        # Embedding service
poetry run pytest tests/test_semantic_search.py -v   # Vector search
poetry run pytest tests/test_security.py -v          # Security
```

**Test Results**:
- **58 tests passing** (Sprint 2 added 31 tests)
- 5 tests skipped (integration tests requiring OpenAI API/LadybugDB)
- **90%+ coverage** for new features (embeddings, semantic search, BM25, hybrid search)
- Core modules: 90-95% coverage
- Comprehensive mocking for OpenAI API (fast, no API calls in tests)

## Security

✅ **Cypher Injection Protection**: All queries use parameterized statements
✅ **Path Traversal Protection**: File operations validate paths
✅ **Input Validation**: Handles edge cases, unicode, special characters

## Usage Examples

### Semantic Search
```python
from server.db import GraphDB

db = GraphDB("/db", enable_embeddings=True)

# Natural language search
results = db.semantic_search(
    query="How do I configure the database?",
    limit=10,
    filter_tags=["configuration", "setup"]
)
```

### Hybrid Search (Best Results)
```python
from server.search import HybridSearch
from server.db import GraphDB

db = GraphDB("/db")
hybrid = HybridSearch(db)

# Combines keyword + semantic with RRF fusion
results = hybrid.search(
    query="database optimization",
    limit=10,
    fusion_method="rrf"  # or "weighted"
)
```

### BM25 Keyword Search
```python
# Professional-grade keyword search with tag boosting
results = db.keyword_search("database performance")
# Returns results sorted by BM25 score
```