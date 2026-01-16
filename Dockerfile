FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including gosu for user switching
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server/ ./server/

# Copy library files for installation tool
COPY library/ ./library/

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create directories for database and space
RUN mkdir -p /data /space

# Expose ports
# 8000: MCP Streamable HTTP transport
# 50051: gRPC
# 8080: Health check endpoint
EXPOSE 8000 50051 8080

# Use entrypoint to handle user switching
ENTRYPOINT ["/entrypoint.sh"]

# Default command runs the unified server
CMD ["python", "-m", "server"]
