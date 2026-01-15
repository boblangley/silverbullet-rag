---
tags: note, development
created: 2025-01-15
---

# Development Notes

## Setup

1. Clone the repository
2. Open in dev container
3. Run `pip install -r requirements.txt`

## Running Locally

### MCP Server
```bash
python -m server.mcp
```

### gRPC Server
```bash
python -m server.grpc_server
```

## Code Style

- Formatter: Ruff
- Pre-commit hooks configured
- Type hints required

## Related

- [[Projects/Silverbullet-RAG]]
- [[Notes/Testing]]
