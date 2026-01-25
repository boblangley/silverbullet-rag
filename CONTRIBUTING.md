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
   - Install Go 1.24
   - Install Deno (for space-lua execution)
   - Install golangci-lint
   - Set up git hooks
   - Configure VS Code extensions

### Option 2: Local Development

1. **Prerequisites**:
   - Go 1.24+
   - Deno 2.0+ (for space-lua execution)
   - LadybugDB native library (`lib-ladybug/liblbug.so`)

2. **Clone and Install**:
   ```bash
   git clone --recurse-submodules https://github.com/YOUR_USERNAME/silverbullet-rag.git
   cd silverbullet-rag

   # Install LadybugDB native library
   sudo cp lib-ladybug/liblbug.so /usr/local/lib/
   sudo ldconfig

   # Install git hooks
   ./scripts/install-hooks.sh

   # Install golangci-lint
   go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
   ```

3. **Set Environment Variables** (optional, for OpenAI embeddings):
   ```bash
   export OPENAI_API_KEY="your-api-key"
   export EMBEDDING_MODEL="text-embedding-3-small"
   ```

## Running Tests

### All Tests

```bash
# Run all tests with verbose output
go test ./... -v

# Run with coverage report
go test ./... -cover

# Run with detailed coverage report
go test ./... -coverprofile=coverage.out
go tool cover -html=coverage.out
```

### Specific Packages

```bash
# Parser tests
go test ./internal/parser/... -v

# Search tests
go test ./internal/search/... -v

# Database tests
go test ./internal/db/... -v

# MCP/gRPC server tests
go test ./internal/server/... -v

# Config parsing tests
go test ./internal/config/... -v

# Watcher tests
go test ./internal/watcher/... -v
```

### Running a Single Test

```bash
# By test name
go test ./internal/parser/... -v -run TestParseWikilinks

# With pattern matching
go test ./... -v -run ".*Transclusion.*"
```

### Environment Variables for Tests

Tests are configured to:
- Use local embeddings by default (no OpenAI API required)
- Create temporary directories for database and space files
- Skip integration tests unless explicitly enabled

## Code Quality

### Linting

```bash
# Run golangci-lint
golangci-lint run

# Run with auto-fix (where possible)
golangci-lint run --fix

# Run pre-commit hooks
pre-commit run --all-files
```

### Formatting

```bash
# Format all Go files
go fmt ./...

# Or use gofumpt for stricter formatting
gofumpt -w .
```

## Building

### Local Build

```bash
# Build the binary
go build -o rag-server ./cmd/rag-server

# Run the server
./rag-server --space-path=/path/to/space --db-path=/tmp/ladybug
```

### Docker Build

```bash
# Build image
docker build -t silverbullet-rag .

# Run container
docker run -p 8000:8000 -p 50051:50051 \
  -e OPENAI_API_KEY="your-key" \
  -v /path/to/space:/space:ro \
  silverbullet-rag
```

## Compiling gRPC Proto

If you modify `proto/rag.proto`:

```bash
# Install protoc plugins (if not already installed)
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

# Generate Go code
protoc --go_out=. --go-grpc_out=. proto/rag.proto
```

## Compiling Silverbullet Plugs

The Proposals library includes a TypeScript plug that must be compiled to JavaScript. The dev container includes Deno for this purpose.

To compile the Proposals plug:

```bash
cd silverbullet
deno run -A bin/plug-compile.ts \
  ../library/Proposals/plug.yaml \
  --dist ../library/Proposals \
  --config deno.json
```

The compiled `Proposals.plug.js` should be committed to the repository.

## Project Structure

```
silverbullet-rag/
├── cmd/
│   └── rag-server/         # Main entry point
├── internal/               # Internal packages
│   ├── config/             # Configuration parsing
│   ├── db/                 # LadybugDB wrapper
│   ├── embeddings/         # Embedding generation
│   ├── parser/             # Markdown parsing
│   ├── proto/              # Generated gRPC stubs
│   ├── search/             # Search implementations
│   ├── server/             # MCP and gRPC servers
│   ├── types/              # Shared types
│   ├── version/            # Version info
│   └── watcher/            # File system watcher
├── deno/                   # Deno sidecar for space-lua
├── library/                # Proposals library
├── proto/                  # Protocol Buffers definitions
├── silverbullet/           # SilverBullet submodule
├── docs/                   # Additional documentation
├── Dockerfile              # Container image
└── docker-compose.yml      # Multi-service setup
```

## Pull Request Guidelines

1. **Create a branch**: `git checkout -b feature/my-feature`
2. **Write tests first**: Follow TDD - write failing tests, then implement
3. **Run all tests**: `go test ./... -v`
4. **Run linter**: `golangci-lint run`
5. **Commit with clear message**: Describe what and why
6. **Open PR**: Reference any related issues

## Release Tags

This project uses semantic versioning tags **without** the `v` prefix:
- Correct: `0.6.0`, `1.0.0`, `2.1.3`
- Incorrect: `v0.6.0`, `v1.0.0`

A pre-push hook validates tag format automatically. If you accidentally create a tag with `v` prefix:
```bash
git tag -d v1.0.0
git tag -a 1.0.0 -m "1.0.0: Description"
```

## Common Development Tasks

### Adding a New Search Feature

1. Add implementation in `internal/search/` or `internal/db/`
2. Add tests in the corresponding `*_test.go` file
3. Expose via MCP tool in `internal/server/mcp.go`
4. Expose via gRPC in `internal/server/grpc.go` (optional)
5. Update `README.md`

### Adding a New Parser Feature

1. Update parser in `internal/parser/`
2. Update `Chunk` struct in `internal/types/` if needed
3. Add tests in `internal/parser/*_test.go`
4. Update graph schema if new relationships needed
5. Update `README.md`

### Debugging Tips

- **View test output**: `go test -v` (shows t.Log output)
- **Debug with delve**: `dlv test ./internal/parser/ -- -test.run TestName`
- **Check coverage gaps**: Review `coverage.html` after coverage run
- **Database issues**: Delete temp database and retry with `--rebuild`

## Getting Help

- Open an issue for bugs or feature requests
- Check existing issues and discussions
- Review code comments and documentation
