# Deployment Guide

This guide covers how to deploy Silverbullet RAG using Docker, including initialization, configuration, and updates.

## Prerequisites

- Docker and Docker Compose
- OpenAI API key (for embeddings) or use local embeddings
- Silverbullet space (mounted volume or local directory)

## Quick Start with Docker

### 1. Pull or Build the Image

```bash
# Option A: Pull from GitHub Container Registry
docker pull ghcr.io/YOUR_USERNAME/silverbullet-rag:latest

# Option B: Build locally
git clone --recurse-submodules https://github.com/YOUR_USERNAME/silverbullet-rag.git
cd silverbullet-rag
docker build -t silverbullet-rag .
```

### 2. Run the Unified Server

The Go server runs MCP, gRPC, file watcher, and health check in a single process:

```bash
docker run -d \
  --name silverbullet-rag \
  -p 8000:8000 \
  -p 50051:50051 \
  -e OPENAI_API_KEY="your-api-key" \
  -v /path/to/your/space:/space:ro \
  -v silverbullet-rag-db:/data \
  silverbullet-rag
```

The server automatically indexes your space on first startup. Services available:
- MCP server: `http://localhost:8000/mcp`
- gRPC server: `localhost:50051`
- Health check: `http://localhost:8080/health`

---

## Docker Compose Setup

For production deployments, use Docker Compose.

### 1. Create docker-compose.yml

```yaml
version: '3.8'

services:
  silverbullet-rag:
    image: ghcr.io/YOUR_USERNAME/silverbullet-rag:latest
    # Or build locally:
    # build: .
    container_name: silverbullet-rag
    volumes:
      - silverbullet-space:/space:ro
      - ladybug-db:/data
    ports:
      - "8000:8000"   # MCP HTTP
      - "50051:50051" # gRPC
      # - "8080:8080" # Health check (optional)
    environment:
      - DB_PATH=/data/ladybug
      - SPACE_PATH=/space
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-3-small}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: unless-stopped

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

### 3. Start the Service

```bash
docker compose up -d
```

### 4. View Logs

```bash
# View logs
docker compose logs -f

# View specific output
docker compose logs -f silverbullet-rag
```

---

## Sharing Volumes with Silverbullet

If you're running Silverbullet in Docker, share the same volume.

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

  silverbullet-rag:
    image: ghcr.io/YOUR_USERNAME/silverbullet-rag:latest
    container_name: silverbullet-rag
    volumes:
      - silverbullet-space:/space:ro  # Read-only access
      - ladybug-db:/data
    ports:
      - "8000:8000"
      - "50051:50051"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - silverbullet
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
| `GRPC_PORT` | `50051` | gRPC server port |
| `MCP_PORT` | `8000` | MCP HTTP server port |
| `HEALTH_PORT` | `8080` | Health check endpoint port |
| `EMBEDDING_PROVIDER` | `openai` | Embedding provider: `openai` or `local` |
| `OPENAI_API_KEY` | (required for openai) | OpenAI API key for embeddings |
| `EMBEDDING_MODEL` | varies by provider | Embedding model to use |
| `ENABLE_EMBEDDINGS` | `true` | Set to `false` to disable embeddings |

### CLI Flags

The Go binary also accepts CLI flags:

```bash
./rag-server \
  --space-path=/space \
  --db-path=/data/ladybug \
  --mcp-port=8000 \
  --grpc-port=50051 \
  --health-port=8080 \
  --embedding-provider=openai \
  --embedding-model=text-embedding-3-small \
  --rebuild  # Optional: rebuild index on startup
```

### Embedding Providers

**OpenAI** (default):
```bash
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
EMBEDDING_MODEL=text-embedding-3-small  # default
```

**Local (hugot/ONNX)** - no API key required:
```bash
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5  # default
```

### Ports

| Port | Service | Protocol |
|------|---------|----------|
| 8000 | MCP HTTP Server | HTTP (Streamable) |
| 50051 | gRPC Server | gRPC |
| 8080 | Health Check | HTTP |

---

## Updating

### Update Container Image

```bash
# Pull latest image
docker compose pull

# Recreate containers
docker compose up -d
```

### Update with Local Build

```bash
# Pull latest code
git pull origin main
git submodule update --init --recursive

# Rebuild image
docker compose build

# Recreate containers
docker compose up -d
```

### Rebuild Index

To force a full reindex:

```bash
# Using environment variable
docker compose down
docker compose run --rm -e REBUILD_INDEX=true silverbullet-rag

# Or using CLI flag
docker compose run --rm silverbullet-rag ./rag-server --rebuild
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
  silverbullet-rag:
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

The server exposes a health endpoint at `/health` on port 8080:

```yaml
services:
  silverbullet-rag:
    # ... other config ...
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

### Logging

```yaml
services:
  silverbullet-rag:
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
docker compose logs silverbullet-rag

# Common issues:
# - Missing OPENAI_API_KEY (if using OpenAI embeddings)
# - Space path doesn't exist or is empty
# - Database path not writable
```

### Slow Indexing

Initial indexing with embeddings can be slow for large spaces:

1. Consider disabling embeddings initially: `ENABLE_EMBEDDINGS=false`
2. Run index during off-hours
3. Increase container memory limits

### Watcher Not Detecting Changes

```bash
# Check logs
docker compose logs silverbullet-rag | grep -i watch

# Common issues:
# - Volume mounted without inotify support
# - macOS: fsevents may not propagate to Docker
# - Solution: Use polling mode or restart container
```

### Database Corruption

If the database becomes corrupted, rebuild from scratch:

```bash
docker compose run --rm silverbullet-rag ./rag-server --rebuild
```

### Memory Issues

LadybugDB can use significant memory for large spaces:

1. Increase container memory limits
2. Reduce embedding batch sizes
3. Consider chunking by smaller headers
