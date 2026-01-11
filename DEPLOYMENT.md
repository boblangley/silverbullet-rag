# Deployment Guide

This guide covers deploying Silverbullet RAG to various environments.

## Prerequisites

- Docker and Docker Compose
- OpenAI API key
- Existing Silverbullet instance with a named volume

## GitHub Container Registry (GHCR)

### Automatic Builds

The GitHub Actions workflow automatically builds and publishes Docker images to GHCR on:
- **Push to main branch**: Tagged as `latest` and `main-<sha>`
- **Tagged releases**: Tagged as `v1.0.0`, `v1.0`, `v1`, etc.
- **Pull requests**: Build only (no push)

### Image Tags

Images are available at: `ghcr.io/YOUR_USERNAME/silverbullet-rag`

Available tags:
- `latest` - Latest build from main branch
- `main` - Latest main branch build
- `v1.0.0` - Specific version (if using semantic versioning)
- `v1.0` - Latest patch for minor version
- `v1` - Latest minor for major version
- `main-abc1234` - Specific commit SHA

### Making the Repository Private

To keep your GHCR images private:

1. **Set repository visibility to private**:
   - Go to repository Settings → Danger Zone → Change visibility → Private

2. **Configure package visibility** (if different from repo):
   - Go to your profile → Packages
   - Find `silverbullet-rag` package
   - Package settings → Change visibility → Private

3. **Authentication for pulling**:
   ```bash
   # Create a Personal Access Token (PAT) with read:packages scope
   # GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
   # Select: read:packages scope

   # Login to GHCR
   echo $YOUR_PAT | docker login ghcr.io -u YOUR_USERNAME --password-stdin
   ```

## Deployment Options

### Option 1: Using Pre-built GHCR Image (Recommended)

1. **Authenticate with GHCR** (for private repos):
   ```bash
   echo $YOUR_PAT | docker login ghcr.io -u YOUR_USERNAME --password-stdin
   ```

2. **Update docker-compose.yml**:
   ```yaml
   services:
     mcp-server:
       image: ghcr.io/YOUR_USERNAME/silverbullet-rag:latest
       # Comment out: build: .
   ```

3. **Create .env file**:
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

4. **Start services**:
   ```bash
   docker-compose pull  # Pull latest images
   docker-compose up -d
   ```

### Option 2: Build from Source

1. **Clone repository**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/silverbullet-rag.git
   cd silverbullet-rag
   git submodule update --init --recursive
   ```

2. **Create .env file**:
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

3. **Build and start**:
   ```bash
   docker-compose up -d --build
   ```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required: OpenAI API key for embeddings
OPENAI_API_KEY=sk-your-key-here

# Optional: Embedding model (default: text-embedding-3-small)
EMBEDDING_MODEL=text-embedding-3-small

# Optional: Paths (defaults shown, typically set in docker-compose.yml)
# DB_PATH=/data/ladybug
# SPACE_PATH=/space
```

### Docker Compose Configuration

The `docker-compose.yml` file defines three services:

1. **mcp-server** (Port 8000): MCP HTTP server for AI assistants
2. **grpc-server** (Port 50051): gRPC server for Silverbullet hooks
3. **watcher**: File system monitor for automatic reindexing

#### Volume Configuration

You need to connect to your existing Silverbullet space:

```yaml
volumes:
  silverbullet-space:
    external: true  # Use your existing Silverbullet volume
    # OR specify a path:
    # driver: local
    # driver_opts:
    #   type: none
    #   o: bind
    #   device: /path/to/silverbullet/space

  ladybug-db:
    # Creates new volume for LadybugDB
```

**Important**: Replace `silverbullet-space` with your actual Silverbullet volume name:

```bash
# List Docker volumes to find your Silverbullet volume
docker volume ls | grep silverbullet

# Update docker-compose.yml with the correct volume name
```

## Home Network Deployment

### Setup

1. **Choose a host machine** (e.g., home server, NAS, Raspberry Pi)

2. **Install Docker and Docker Compose**:
   ```bash
   # Ubuntu/Debian
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo systemctl enable docker
   sudo systemctl start docker

   # Install Docker Compose
   sudo apt-get install docker-compose-plugin
   ```

3. **Deploy the application**:
   ```bash
   # Create project directory
   mkdir -p ~/silverbullet-rag
   cd ~/silverbullet-rag

   # Create .env file
   echo "OPENAI_API_KEY=your-key-here" > .env
   echo "EMBEDDING_MODEL=text-embedding-3-small" >> .env

   # Create docker-compose.yml (copy from repository)

   # Update volume configuration for your Silverbullet space

   # Login to GHCR (if using private image)
   echo $YOUR_PAT | docker login ghcr.io -u YOUR_USERNAME --password-stdin

   # Start services
   docker-compose up -d
   ```

4. **Verify deployment**:
   ```bash
   # Check logs
   docker-compose logs -f mcp-server

   # Test MCP endpoint
   curl http://localhost:8000/mcp

   # Test gRPC (requires grpcurl)
   grpcurl -plaintext localhost:50051 list
   ```

### Network Access

#### Local Network (LAN)

Find your server's IP address:
```bash
# Linux
ip addr show | grep "inet "

# macOS
ifconfig | grep "inet "
```

Access from other devices on your network:
- MCP Server: `http://192.168.1.100:8000/mcp` (replace with your IP)
- gRPC Server: `192.168.1.100:50051`

#### Remote Access (Internet)

**Option 1: Port Forwarding** (Simple but less secure)

1. Configure router port forwarding:
   - External port 8000 → Internal IP:8000
   - External port 50051 → Internal IP:50051

2. Find your public IP: `curl ifconfig.me`

3. Access via: `http://YOUR_PUBLIC_IP:8000/mcp`

4. **Security considerations**:
   - Use a firewall to restrict access
   - Consider adding authentication (not built-in)
   - Monitor logs for suspicious activity

**Option 2: VPN** (Recommended for security)

Use Tailscale, WireGuard, or similar:

```bash
# Example: Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Access via Tailscale IP (e.g., 100.x.x.x:8000)
```

**Option 3: Reverse Proxy with HTTPS** (Production)

Use Caddy or Nginx with automatic HTTPS:

```bash
# Example: Caddy
caddy reverse-proxy --from rag.yourdomain.com --to localhost:8000
```

## Connecting MCP Clients

### Claude Desktop

Add to `claude_desktop_config.json`:

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

Replace `YOUR_SERVER_IP` with:
- `localhost` (local testing)
- `192.168.1.100` (LAN access)
- `your-public-ip` (internet access)
- `your-tailscale-ip` (VPN access)

### Testing Connection

```bash
# Check server is running
docker-compose ps

# Test HTTP endpoint
curl http://localhost:8000/mcp

# View server logs
docker-compose logs -f mcp-server

# Check all services status
docker-compose ps
```

## Updating

### Update Pre-built Image

```bash
# Pull latest image
docker-compose pull

# Restart services
docker-compose up -d

# View logs
docker-compose logs -f mcp-server
```

### Update from Source

```bash
# Pull latest code
git pull origin main
git submodule update --recursive

# Rebuild and restart
docker-compose up -d --build
```

## Monitoring

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f mcp-server
docker-compose logs -f grpc-server
docker-compose logs -f watcher

# Last 100 lines
docker-compose logs --tail=100 mcp-server
```

### Check Resource Usage

```bash
# Container stats
docker stats

# Disk usage
docker system df

# Database size
du -h data/ladybug
```

### Health Checks

```bash
# Check if services are running
docker-compose ps

# Test MCP endpoint
curl http://localhost:8000/mcp

# Test gRPC (requires grpcurl)
grpcurl -plaintext localhost:50051 list
```

## Backup

### Database Backup

```bash
# Stop services
docker-compose stop

# Backup LadybugDB
tar -czf ladybug-backup-$(date +%Y%m%d).tar.gz data/ladybug/

# Restart services
docker-compose start
```

### Restore from Backup

```bash
# Stop services
docker-compose stop

# Remove old database
rm -rf data/ladybug/*

# Extract backup
tar -xzf ladybug-backup-20260111.tar.gz -C .

# Restart services
docker-compose start
```

## Troubleshooting

### Services won't start

```bash
# Check logs
docker-compose logs

# Check if ports are in use
sudo netstat -tulpn | grep -E '8000|50051'

# Remove old containers and retry
docker-compose down
docker-compose up -d
```

### Can't connect to MCP server

1. Check if service is running: `docker-compose ps`
2. Check logs: `docker-compose logs mcp-server`
3. Test locally: `curl http://localhost:8000/mcp`
4. Check firewall: `sudo ufw status`
5. Verify network connectivity

### Database errors

```bash
# Check database permissions
ls -la data/ladybug/

# Reset database (WARNING: deletes all data)
docker-compose stop
rm -rf data/ladybug/*
docker-compose start

# Server will reindex on startup
```

### OpenAI API errors

1. Check API key in `.env`: `cat .env`
2. Verify key is valid: Test at https://platform.openai.com/api-keys
3. Check API quota/billing
4. View logs: `docker-compose logs mcp-server | grep -i openai`

## Security Best Practices

1. **Keep OpenAI API key secure**:
   - Never commit `.env` to git (already in `.gitignore`)
   - Use environment-specific keys (dev/prod)
   - Rotate keys periodically

2. **Network security**:
   - Use VPN for remote access (recommended)
   - If using port forwarding, add firewall rules
   - Consider adding authentication layer (reverse proxy)

3. **Regular updates**:
   - Pull latest images weekly
   - Monitor security advisories
   - Keep Docker up to date

4. **Access control**:
   - Limit who can access your server
   - Monitor access logs
   - Use private GHCR images for proprietary deployments

## Performance Tuning

### Resource Limits

Add to docker-compose.yml:

```yaml
services:
  mcp-server:
    # ...
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

### Database Optimization

LadybugDB is optimized by default, but for large spaces:

1. Increase container memory allocation
2. Use SSD storage for database volume
3. Enable vector index optimization (already enabled)

## Support

For issues or questions:
- GitHub Issues: https://github.com/YOUR_USERNAME/silverbullet-rag/issues
- Documentation: See README.md
- MCP Documentation: https://modelcontextprotocol.io
