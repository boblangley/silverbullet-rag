# Contributing to Silverbullet RAG

Thank you for your interest in contributing! This guide covers how to set up your development environment and run tests.

## Development Setup

### Option 1: Dev Container (Recommended)

The easiest way to get started is using the included dev container with VS Code or GitHub Codespaces.

1. **Prerequisites**:
   - [VS Code](https://code.visualstudio.com/) with [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
   - [Docker Desktop](https://www.docker.com/products/docker-desktop/)

2. **Open in Container**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/silverbullet-rag.git
   cd silverbullet-rag
   code .
   ```
   When prompted, click "Reopen in Container" or run the command palette (`Ctrl+Shift+P`) → "Dev Containers: Reopen in Container"

3. **Wait for Setup**:
   The container will automatically:
   - Install Python 3.11
   - Install Poetry and project dependencies
   - Configure VS Code extensions (Python, Black, mypy, etc.)

### Option 2: Local Development

1. **Prerequisites**:
   - Python 3.11+
   - [Poetry](https://python-poetry.org/docs/#installation)

2. **Clone and Install**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/silverbullet-rag.git
   cd silverbullet-rag
   poetry install
   ```

3. **Set Environment Variables**:
   ```bash
   export OPENAI_API_KEY="your-api-key"
   export EMBEDDING_MODEL="text-embedding-3-small"
   ```

## Running Tests

### All Tests

```bash
# Run all tests with verbose output
poetry run pytest tests/ -v

# Run with coverage report
poetry run pytest tests/ --cov=server --cov-report=term-missing

# Run with HTML coverage report
poetry run pytest tests/ --cov=server --cov-report=html
open htmlcov/index.html
```

### Specific Test Suites

```bash
# Parser and v2 features
poetry run pytest tests/test_v2_features.py -v

# Search functionality
poetry run pytest tests/test_bm25_ranking.py tests/test_semantic_search.py tests/test_hybrid_search.py -v

# Security tests
poetry run pytest tests/test_security.py -v

# gRPC server
poetry run pytest tests/test_grpc_server.py -v

# MCP HTTP server
poetry run pytest tests/test_mcp_http.py -v
```

### Running a Single Test

```bash
# By test name
poetry run pytest tests/test_v2_features.py::TestTransclusionParsing::test_extract_simple_transclusion -v

# By keyword
poetry run pytest -k "transclusion" -v
```

### Integration Tests

Some tests require running servers and are skipped by default. To run them, set `RUN_INTEGRATION_TESTS=true`.

#### Using Docker Compose Script (Recommended)

The easiest way to run integration tests is using the provided script:

```bash
# Run all integration tests
./scripts/run-integration-tests.sh

# Run only MCP HTTP tests
./scripts/run-integration-tests.sh --mcp

# Run only gRPC tests
./scripts/run-integration-tests.sh --grpc

# Keep containers running after tests (for debugging)
./scripts/run-integration-tests.sh --keep
```

The script automatically:
- Builds Docker images
- Copies test data to volumes
- Starts MCP and gRPC servers
- Waits for servers to be ready
- Runs integration tests
- Saves JUnit XML results to `test-results/integration-results.xml`
- Cleans up containers and volumes

You can also run with Docker Compose directly:

```bash
# Build and start services
docker compose -f docker-compose.test.yml build
docker compose -f docker-compose.test.yml up -d mcp-server grpc-server

# Wait for servers (~60 seconds for embedding model download)
sleep 60

# Run tests
docker compose -f docker-compose.test.yml run --rm \
  -e RUN_INTEGRATION_TESTS=true \
  test-runner \
  python -m pytest tests/test_mcp_http.py tests/test_grpc_server.py -v

# Cleanup
docker compose -f docker-compose.test.yml down -v
```

#### Using Local Servers

Alternatively, run servers locally in separate terminals:

```bash
# Terminal 1: Start the MCP HTTP server
export SPACE_PATH=/path/to/your/silverbullet/space
export DB_PATH=/tmp/test-ladybug.db
export EMBEDDING_PROVIDER=local
python -m server.mcp_http_server

# Terminal 2: Run MCP integration tests
RUN_INTEGRATION_TESTS=true pytest tests/test_mcp_http.py -v
```

```bash
# Terminal 1: Start the gRPC server
export SPACE_PATH=/path/to/your/silverbullet/space
export DB_PATH=/tmp/test-ladybug.db
export EMBEDDING_PROVIDER=local
python -m server.grpc_server

# Terminal 2: Run gRPC integration tests
RUN_INTEGRATION_TESTS=true pytest tests/test_grpc_server.py -v
```

#### OpenAI Embedding Tests

Tests that require real OpenAI API calls are skipped unless explicitly enabled:

```bash
# Set environment variables
export OPENAI_API_KEY="sk-your-actual-key"
export RUN_OPENAI_TESTS=true

# Run OpenAI-specific tests
pytest tests/test_embeddings.py -v -k "OpenAI"
pytest tests/test_semantic_search.py::TestSemanticSearchIntegration -v
```

### Test Configuration

Tests are configured to:
- Mock all OpenAI API calls (no real API calls in tests)
- Use temporary directories for database and space files
- Auto-set test environment variables via `conftest.py`

## Code Quality

### Formatting

```bash
# Format code with Black
poetry run black server/ tests/

# Check formatting without changes
poetry run black server/ tests/ --check
```

### Type Checking

```bash
# Run mypy
poetry run mypy server/
```

### Import Sorting

```bash
# Sort imports with isort
poetry run isort server/ tests/
```

## Building Docker Image

```bash
# Build image
docker build -t silverbullet-rag .

# Run MCP server
docker run -p 8000:8000 \
  -e OPENAI_API_KEY="your-key" \
  -v /path/to/space:/space:ro \
  silverbullet-rag

# Run gRPC server
docker run -p 50051:50051 \
  -e OPENAI_API_KEY="your-key" \
  -v /path/to/space:/space:ro \
  silverbullet-rag python -m server.grpc_server
```

## Compiling gRPC Proto

If you modify `server/grpc/rag.proto`:

```bash
python -m grpc_tools.protoc \
  -I server/grpc \
  --python_out=server/grpc \
  --grpc_python_out=server/grpc \
  server/grpc/rag.proto
```

## Project Structure

```
silverbullet-rag/
├── server/                 # Main application code
│   ├── db/                 # Database layer
│   │   ├── graph.py        # GraphDB with LadybugDB
│   │   └── __init__.py
│   ├── parser/             # Markdown parsing
│   │   ├── space_parser.py # SpaceParser class
│   │   └── __init__.py
│   ├── search/             # Search implementations
│   │   ├── hybrid.py       # Hybrid search
│   │   └── __init__.py
│   ├── grpc/               # gRPC service
│   │   ├── rag.proto       # Protocol definition
│   │   └── rag_pb2*.py     # Generated code
│   ├── pipe/               # Open WebUI integration
│   ├── mcp_http_server.py  # MCP HTTP server
│   ├── grpc_server.py      # gRPC server
│   ├── watcher.py          # File watcher
│   ├── embeddings.py       # Embedding service
│   └── init_index.py       # Index initialization
├── tests/                  # Test suite
│   ├── conftest.py         # Shared fixtures
│   └── test_*.py           # Test modules
├── docs/                   # Additional documentation
├── Dockerfile              # Container image
├── docker-compose.yml      # Multi-service setup
├── pyproject.toml          # Poetry configuration
└── requirements.txt        # Pip requirements
```

## Pull Request Guidelines

1. **Create a branch**: `git checkout -b feature/my-feature`
2. **Write tests first**: Follow TDD - write failing tests, then implement
3. **Run all tests**: `poetry run pytest tests/ -v`
4. **Format code**: `poetry run black server/ tests/`
5. **Type check**: `poetry run mypy server/`
6. **Commit with clear message**: Describe what and why
7. **Open PR**: Reference any related issues

## Common Development Tasks

### Adding a New Search Feature

1. Add implementation in `server/search/` or `server/db/graph.py`
2. Add tests in `tests/test_*.py`
3. Expose via MCP tool in `server/mcp_http_server.py`
4. Expose via gRPC in `server/grpc_server.py` (optional)
5. Update `README.md`

### Adding a New Parser Feature

1. Update `SpaceParser` in `server/parser/space_parser.py`
2. Update `Chunk` dataclass if needed
3. Export from `server/parser/__init__.py`
4. Add tests in `tests/test_v2_features.py`
5. Update graph schema if new relationships needed
6. Update `README.md`

### Debugging Tips

- **View test output**: `poetry run pytest -v -s` (shows print statements)
- **Debug specific test**: `poetry run pytest --pdb -k "test_name"`
- **Check coverage gaps**: Review `htmlcov/index.html` after coverage run
- **Database issues**: Delete temp database and retry with `--rebuild`

## Getting Help

- Open an issue for bugs or feature requests
- Check existing issues and discussions
- Review code comments and docstrings
