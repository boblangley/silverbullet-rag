# Deployment Guide

This guide covers how to deploy Silverbullet RAG using Docker, including initialization, configuration, and updates.

## Prerequisites

- Docker and Docker Compose
- OpenAI API key (for embeddings)
- Silverbullet space (mounted volume or local directory)

## Quick Start with Docker

### 1. Pull or Build the Image

```bash
# Option A: Pull from GitHub Container Registry
docker pull ghcr.io/YOUR_USERNAME/silverbullet-rag:latest

# Option B: Build locally
git clone https://github.com/YOUR_USERNAME/silverbullet-rag.git
cd silverbullet-rag
docker build -t silverbullet-rag .
```

### 2. Initialize the Database

Before running the servers, initialize the index:

```bash
docker run --rm \
  -e OPENAI_API_KEY="your-api-key" \
  -v /path/to/your/space:/space:ro \
  -v silverbullet-rag-db:/data \
  silverbullet-rag \
  python -m server.init_index
```

This parses your Silverbullet space and creates:
- Knowledge graph (pages, chunks, tags, folders)
- Vector embeddings for semantic search
- BM25 keyword index

### 3. Run the MCP Server

```bash
docker run -d \
  --name silverbullet-rag-mcp \
  -p 8000:8000 \
  -e OPENAI_API_KEY="your-api-key" \
  -v /path/to/your/space:/space:ro \
  -v silverbullet-rag-db:/data \
  silverbullet-rag
```

The MCP server is now available at `http://localhost:8000/mcp`.

---

## Docker Compose Setup

For production deployments, use Docker Compose to run all services.

### 1. Create docker-compose.yml

```yaml
version: '3.8'

services:
  # MCP HTTP Server (primary service)
  mcp-server:
    image: ghcr.io/YOUR_USERNAME/silverbullet-rag:latest
    # Or build locally:
    # build: .
    container_name: silverbullet-rag-mcp
    volumes:
      - silverbullet-space:/space:ro
      - ladybug-db:/data
    ports:
      - "8000:8000"
    environment:
      - DB_PATH=/data/ladybug
      - SPACE_PATH=/space
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-3-small}
    restart: unless-stopped
    command: python -m server.mcp_http_server

  # gRPC server for hooks
  grpc-server:
    image: ghcr.io/YOUR_USERNAME/silverbullet-rag:latest
    container_name: silverbullet-rag-grpc
    volumes:
      - silverbullet-space:/space:ro
      - ladybug-db:/data
    ports:
      - "50051:50051"
    environment:
      - DB_PATH=/data/ladybug
      - SPACE_PATH=/space
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-3-small}
    restart: unless-stopped
    command: python -m server.grpc_server

  # File watcher service
  watcher:
    image: ghcr.io/YOUR_USERNAME/silverbullet-rag:latest
    container_name: silverbullet-rag-watcher
    volumes:
      - silverbullet-space:/space:ro
      - ladybug-db:/data
    environment:
      - DB_PATH=/data/ladybug
      - SPACE_PATH=/space
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-3-small}
    restart: unless-stopped
    command: python -m server.watcher

volumes:
  silverbullet-space:
    external: true  # Should match your Silverbullet volume
  ladybug-db:
```

### 2. Create .env File

```bash
# .env
OPENAI_API_KEY=sk-your-api-key-here
EMBEDDING_MODEL=text-embedding-3-small
```

### 3. Initialize the Database

```bash
# First time setup - initialize the index
docker compose run --rm mcp-server python -m server.init_index

# Or rebuild from scratch
docker compose run --rm mcp-server python -m server.init_index --rebuild
```

### 4. Start All Services

```bash
docker compose up -d
```

### 5. View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f mcp-server
docker compose logs -f watcher
```

---

## Sharing Volumes with Silverbullet

If you're running Silverbullet in Docker, you'll want to share the same volume.

### Example: Silverbullet + RAG

```yaml
version: '3.8'

services:
  silverbullet:
    image: zefhemel/silverbullet
    container_name: silverbullet
    volumes:
      - silverbullet-space:/space
    ports:
      - "3000:3000"
    restart: unless-stopped

  silverbullet-rag-mcp:
    image: ghcr.io/YOUR_USERNAME/silverbullet-rag:latest
    container_name: silverbullet-rag-mcp
    volumes:
      - silverbullet-space:/space:ro  # Read-only access
      - ladybug-db:/data
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - silverbullet
    restart: unless-stopped

  silverbullet-rag-watcher:
    image: ghcr.io/YOUR_USERNAME/silverbullet-rag:latest
    container_name: silverbullet-rag-watcher
    volumes:
      - silverbullet-space:/space:ro
      - ladybug-db:/data
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - silverbullet
    command: python -m server.watcher
    restart: unless-stopped

volumes:
  silverbullet-space:
  ladybug-db:
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SPACE_PATH` | `/space` | Path to Silverbullet space directory |
| `DB_PATH` | `/data/ladybug` | Path to LadybugDB database directory |
| `EMBEDDING_PROVIDER` | `openai` | Embedding provider: `openai` or `local` |
| `OPENAI_API_KEY` | (required for openai) | OpenAI API key for embeddings |
| `EMBEDDING_MODEL` | varies by provider | Embedding model to use |
| `ENABLE_EMBEDDINGS` | `true` | Set to `false` to disable embeddings |

### Embedding Providers

**OpenAI** (default):
```bash
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
EMBEDDING_MODEL=text-embedding-3-small  # default
```

**Local (fastembed)** - no API key required:
```bash
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5  # default
```

### init_index Options

```bash
# Full rebuild (clears database first)
python -m server.init_index --rebuild

# Custom paths
python -m server.init_index \
  --space-path /custom/space \
  --db-path /custom/db

# Disable embeddings (faster, keyword-only search)
python -m server.init_index --no-embeddings
```

### Ports

| Port | Service | Protocol |
|------|---------|----------|
| 8000 | MCP HTTP Server | HTTP (Streamable) |
| 50051 | gRPC Server | gRPC |

---

## Updating

### Update Container Image

```bash
# Pull latest image
docker compose pull

# Recreate containers
docker compose up -d

# Optional: Rebuild index if schema changed
docker compose run --rm mcp-server python -m server.init_index --rebuild
```

### Update with Local Build

```bash
# Pull latest code
git pull origin main

# Rebuild image
docker compose build

# Recreate containers
docker compose up -d
```

### Rebuild Index Only

If you need to reindex without updating the container:

```bash
# Full rebuild
docker compose run --rm mcp-server python -m server.init_index --rebuild

# Or use exec on running container
docker exec silverbullet-rag-mcp python -m server.init_index --rebuild
```

---

## Production Considerations

### Reverse Proxy with Nginx

```nginx
server {
    listen 443 ssl;
    server_name rag.yourdomain.com;

    ssl_certificate /etc/ssl/certs/your-cert.pem;
    ssl_certificate_key /etc/ssl/private/your-key.pem;

    # MCP HTTP endpoint
    location /mcp {
        proxy_pass http://localhost:8000/mcp;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }
}
```

### Resource Limits

```yaml
services:
  mcp-server:
    # ... other config ...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '0.5'
          memory: 1G
```

### Health Checks

```yaml
services:
  mcp-server:
    # ... other config ...
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Logging

```yaml
services:
  mcp-server:
    # ... other config ...
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## Backup and Restore

### Backup Database

```bash
# Stop services
docker compose stop

# Backup volume
docker run --rm \
  -v ladybug-db:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/ladybug-db-$(date +%Y%m%d).tar.gz -C /data .

# Restart services
docker compose start
```

### Restore Database

```bash
# Stop services
docker compose stop

# Restore volume
docker run --rm \
  -v ladybug-db:/data \
  -v $(pwd)/backups:/backup \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/ladybug-db-YYYYMMDD.tar.gz -C /data"

# Restart services
docker compose start
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose logs mcp-server

# Common issues:
# - Missing OPENAI_API_KEY
# - Space path doesn't exist or is empty
# - Database path not writable
```

### Slow Indexing

Initial indexing with embeddings can be slow for large spaces:

1. Consider disabling embeddings initially: `--no-embeddings`
2. Run index during off-hours
3. Increase container memory limits

### Watcher Not Detecting Changes

```bash
# Check watcher logs
docker compose logs watcher

# Common issues:
# - Volume mounted without inotify support
# - macOS: fsevents may not propagate to Docker
# - Solution: Use polling mode or trigger manual reindex
```

### Database Corruption

If the database becomes corrupted:

```bash
# Rebuild from scratch
docker compose run --rm mcp-server python -m server.init_index --rebuild
```

### Memory Issues

LadybugDB can use significant memory for large spaces:

1. Increase container memory limits
2. Reduce embedding batch sizes
3. Consider chunking by smaller headers
