#!/bin/bash
# Run integration tests using Docker Compose
#
# Usage:
#   ./scripts/run-integration-tests.sh           # Run all integration tests
#   ./scripts/run-integration-tests.sh --mcp     # Run only MCP tests
#   ./scripts/run-integration-tests.sh --grpc    # Run only gRPC tests
#   ./scripts/run-integration-tests.sh --keep    # Keep containers running after tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Parse arguments
RUN_MCP=true
RUN_GRPC=true
KEEP_RUNNING=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --mcp)
            RUN_GRPC=false
            shift
            ;;
        --grpc)
            RUN_MCP=false
            shift
            ;;
        --keep)
            KEEP_RUNNING=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --mcp      Run only MCP HTTP integration tests"
            echo "  --grpc     Run only gRPC integration tests"
            echo "  --keep     Keep containers running after tests"
            echo "  --verbose  Show detailed output"
            echo "  --help     Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Silverbullet RAG Integration Tests ===${NC}"
echo ""

# Cleanup function
cleanup() {
    if [ "$KEEP_RUNNING" = false ]; then
        echo -e "${YELLOW}Cleaning up...${NC}"
        docker compose -f docker-compose.test.yml down -v --remove-orphans 2>/dev/null || true
    else
        echo -e "${YELLOW}Containers kept running. To stop: docker compose -f docker-compose.test.yml down -v${NC}"
    fi
}

# Set trap for cleanup on exit
trap cleanup EXIT

# Step 1: Build images
echo -e "${YELLOW}Step 1: Building Docker images...${NC}"
docker compose -f docker-compose.test.yml build

# Step 2: Prepare test data volume
echo -e "${YELLOW}Step 2: Preparing test data...${NC}"

# Remove old volumes if they exist
docker volume rm silverbullet-rag_test-space 2>/dev/null || true
docker volume rm silverbullet-rag_test-db 2>/dev/null || true

# Create fresh volumes
docker volume create silverbullet-rag_test-space
docker volume create silverbullet-rag_test-db

# Copy test data into volume using docker cp (works in docker-in-docker)
docker create --name temp-copy -v silverbullet-rag_test-space:/space alpine
docker cp "$PROJECT_DIR/test-data/silverbullet/." temp-copy:/space/
docker rm temp-copy

echo "Test data copied to volume"

# Step 3: Start servers
echo -e "${YELLOW}Step 3: Starting servers...${NC}"
docker compose -f docker-compose.test.yml up -d mcp-server grpc-server

# Step 4: Wait for servers to be ready
echo -e "${YELLOW}Step 4: Waiting for servers to initialize (this may take ~45 seconds for embedding model download)...${NC}"

# Wait for MCP server
MAX_WAIT=120
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if docker compose -f docker-compose.test.yml logs mcp-server 2>&1 | grep -q "Uvicorn running"; then
        echo -e "${GREEN}MCP server is ready!${NC}"
        break
    fi
    sleep 5
    WAITED=$((WAITED + 5))
    echo "  Waiting... ($WAITED seconds)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo -e "${RED}Timeout waiting for MCP server${NC}"
    docker compose -f docker-compose.test.yml logs mcp-server
    exit 1
fi

# Wait for gRPC server
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if docker compose -f docker-compose.test.yml logs grpc-server 2>&1 | grep -q "gRPC server starting"; then
        echo -e "${GREEN}gRPC server is ready!${NC}"
        break
    fi
    sleep 5
    WAITED=$((WAITED + 5))
    echo "  Waiting... ($WAITED seconds)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo -e "${RED}Timeout waiting for gRPC server${NC}"
    docker compose -f docker-compose.test.yml logs grpc-server
    exit 1
fi

# Give servers a moment to fully initialize
sleep 5

# Step 5: Run tests
echo -e "${YELLOW}Step 5: Running integration tests...${NC}"
echo ""

# Build test command based on options
TEST_FILES=""
if [ "$RUN_MCP" = true ]; then
    TEST_FILES="$TEST_FILES tests/test_mcp_http.py"
fi
if [ "$RUN_GRPC" = true ]; then
    TEST_FILES="$TEST_FILES tests/test_grpc_server.py"
fi

# Run tests using the test-runner service
docker compose -f docker-compose.test.yml run --rm \
    -e MCP_SERVER_URL=http://mcp-server:8000 \
    -e GRPC_SERVER_ADDRESS=grpc-server:50051 \
    -e RUN_INTEGRATION_TESTS=true \
    test-runner \
    python -m pytest $TEST_FILES -v --tb=short --junitxml=/app/test-results/integration-results.xml

TEST_EXIT_CODE=$?

# Step 6: Extract results
echo ""
echo -e "${YELLOW}Step 6: Extracting test results...${NC}"

# Create local results directory
mkdir -p "$PROJECT_DIR/test-results"

# Copy results from volume using docker cp (works in docker-in-docker)
docker create --name temp-results -v silverbullet-rag_test-results:/results alpine
docker cp temp-results:/results/. "$PROJECT_DIR/test-results/" 2>/dev/null || true
docker rm temp-results 2>/dev/null || true

if [ -f "$PROJECT_DIR/test-results/integration-results.xml" ]; then
    echo -e "${GREEN}Test results saved to: test-results/integration-results.xml${NC}"
fi

# Summary
echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}=== Integration tests PASSED ===${NC}"
else
    echo -e "${RED}=== Integration tests FAILED ===${NC}"
fi

exit $TEST_EXIT_CODE
