# Build stage
FROM golang:1.24-bookworm AS builder

WORKDIR /build

# Install build dependencies for CGO
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Download LadybugDB native library
RUN curl -L -o liblbug.tar.gz https://github.com/LadybugDB/ladybug/releases/latest/download/liblbug-linux-x86_64.tar.gz \
    && tar -xzf liblbug.tar.gz \
    && mkdir -p /usr/local/lib \
    && mv liblbug.so /usr/local/lib/ \
    && rm liblbug.tar.gz lbug.h \
    && ldconfig

# Copy go mod files
COPY go.mod go.sum ./

# Download dependencies
RUN go mod download

# Copy source code
COPY cmd/ ./cmd/
COPY internal/ ./internal/
COPY proto/ ./proto/

# Build the binary with CGO enabled
ENV CGO_ENABLED=1
ENV LD_LIBRARY_PATH=/usr/local/lib
RUN go build -o rag-server ./cmd/rag-server

# Runtime stage
FROM debian:bookworm-slim

WORKDIR /app

# Install runtime dependencies including gosu for user switching and Deno for CONFIG.md
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    gosu \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Deno for CONFIG.md space-lua execution
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh

# Download LadybugDB native library
RUN curl -L -o liblbug.tar.gz https://github.com/LadybugDB/ladybug/releases/latest/download/liblbug-linux-x86_64.tar.gz \
    && tar -xzf liblbug.tar.gz \
    && mv liblbug.so /usr/local/lib/ \
    && rm liblbug.tar.gz lbug.h \
    && ldconfig

# Copy binary from builder
COPY --from=builder /build/rag-server /app/rag-server

# Copy Deno runner script for CONFIG.md parsing
COPY deno/ /app/deno/

# Copy SilverBullet submodule for space-lua runtime
COPY silverbullet/ /app/silverbullet/

# Copy library files for installation tool
COPY library/ /app/library/

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Configure library path
ENV LD_LIBRARY_PATH=/usr/local/lib

# Create directories for database and space
RUN mkdir -p /data /space

# Expose ports
# 8000: MCP HTTP server
# 50051: gRPC
# 8080: Health check endpoint
EXPOSE 8000 50051 8080

# Use entrypoint to handle user switching
ENTRYPOINT ["/entrypoint.sh"]

# Default command
CMD ["/app/rag-server", "-space", "/space", "-db", "/data/ladybug.db", "-mcp", ":8000", "-grpc", ":50051", "-health-port", "8080"]
