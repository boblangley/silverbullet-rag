"""Unified server combining gRPC, MCP, and file watcher.

This module provides a single process that:
1. Holds the shared database connection (READ_WRITE)
2. Runs the file watcher for incremental indexing
3. Serves the gRPC API (port 50051)
4. Serves the MCP API (port 8000)

Usage:
    python -m server
"""

import asyncio
import logging
import os
import signal
import threading
from concurrent import futures
from pathlib import Path

import grpc
from watchdog.observers import Observer

from .db import GraphDB
from .grpc import rag_pb2_grpc
from .grpc_server import RAGServiceServicer
from .mcp import dependencies as mcp_deps
from .mcp.server import create_mcp_server
from .parser import SpaceParser
from .search import HybridSearch
from .watcher import SpaceWatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class UnifiedServer:
    """Unified server managing all services with shared database."""

    def __init__(
        self,
        db_path: str = "/data/ladybug",
        space_path: str = "/space",
        grpc_port: int = 50051,
        mcp_port: int = 8000,
    ):
        self.db_path = Path(db_path)
        self.space_path = Path(space_path)
        self.grpc_port = grpc_port
        self.mcp_port = mcp_port

        # Shared database connection (READ_WRITE for indexing)
        logger.info(f"Initializing shared GraphDB at {db_path}...")
        self.graph_db = GraphDB(str(db_path), read_only=False)

        # Shared components
        self.parser = SpaceParser(str(space_path))
        self.hybrid_search = HybridSearch(self.graph_db)

        # Service components (initialized later)
        self.grpc_server = None
        self.watcher_observer = None
        self.space_watcher = None

        # Shutdown event
        self._shutdown_event = asyncio.Event()

    def _init_mcp_dependencies(self):
        """Initialize MCP dependencies with shared database."""
        from .proposals import library_installed

        proposals_enabled = library_installed(self.space_path)
        if proposals_enabled:
            logger.info("Proposals library found, proposal tools enabled")
        else:
            logger.info("Proposals library not installed, proposal tools disabled")

        # Set up the MCP dependencies singleton with shared instances
        mcp_deps._deps = mcp_deps.Dependencies(
            graph_db=self.graph_db,
            space_parser=self.parser,
            hybrid_search=self.hybrid_search,
            space_path=self.space_path,
            db_path=self.db_path,
            proposals_enabled=proposals_enabled,
        )

    def _create_grpc_servicer(self) -> RAGServiceServicer:
        """Create gRPC servicer with shared database."""
        servicer = RAGServiceServicer.__new__(RAGServiceServicer)
        servicer.db_path = self.db_path
        servicer.graph_db = self.graph_db
        servicer.parser = self.parser
        servicer.hybrid_search = self.hybrid_search
        servicer.space_path = self.space_path
        servicer.read_only = False

        from .proposals import library_installed

        servicer.proposals_enabled = library_installed(self.space_path)
        return servicer

    def _start_watcher(self):
        """Start the file watcher for incremental indexing."""
        logger.info(f"Starting file watcher on {self.space_path}...")

        # Create watcher with shared database
        self.space_watcher = SpaceWatcher(
            space_path=str(self.space_path),
            graph_db=self.graph_db,
            parser=self.parser,
            db_path=str(self.db_path),
        )

        # Do initial full index
        logger.info("Performing initial full index...")
        self.space_watcher.reindex_all()

        # Start watching for changes
        self.watcher_observer = Observer()
        self.watcher_observer.schedule(
            self.space_watcher, str(self.space_path), recursive=True
        )
        self.watcher_observer.start()
        logger.info("File watcher started")

    async def _start_grpc_server(self):
        """Start the gRPC server."""
        logger.info(f"Starting gRPC server on port {self.grpc_port}...")

        self.grpc_server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
        servicer = self._create_grpc_servicer()
        rag_pb2_grpc.add_RAGServiceServicer_to_server(servicer, self.grpc_server)

        self.grpc_server.add_insecure_port(f"[::]:{self.grpc_port}")
        await self.grpc_server.start()
        logger.info(f"gRPC server started on port {self.grpc_port}")

    def _run_mcp_server(self):
        """Run MCP server in a separate thread (blocking call)."""
        logger.info(f"Starting MCP server on port {self.mcp_port}...")
        mcp_server = create_mcp_server(self.mcp_port)
        mcp_server.run(transport="streamable-http")

    async def _shutdown(self):
        """Graceful shutdown of all services."""
        logger.info("Shutting down services...")

        # Stop file watcher
        if self.watcher_observer:
            self.watcher_observer.stop()
            self.watcher_observer.join(timeout=5)
            logger.info("File watcher stopped")

        # Stop gRPC server
        if self.grpc_server:
            await self.grpc_server.stop(grace=5)
            logger.info("gRPC server stopped")

        logger.info("Shutdown complete")

    async def run(self):
        """Run all services."""
        # Set up signal handlers
        loop = asyncio.get_event_loop()

        def signal_handler():
            logger.info("Received shutdown signal")
            self._shutdown_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)

        try:
            # Initialize shared dependencies
            self._init_mcp_dependencies()

            # Start file watcher (does initial index)
            self._start_watcher()

            # Start gRPC server
            await self._start_grpc_server()

            # Start MCP server in a separate thread (it's blocking)
            mcp_thread = threading.Thread(target=self._run_mcp_server, daemon=True)
            mcp_thread.start()

            logger.info("All services started successfully")
            logger.info(f"  - gRPC: port {self.grpc_port}")
            logger.info(f"  - MCP:  port {self.mcp_port}")
            logger.info(f"  - Watcher: monitoring {self.space_path}")

            # Wait for shutdown signal
            await self._shutdown_event.wait()

        finally:
            await self._shutdown()


def main():
    """Main entry point for the unified server."""
    db_path = os.getenv("DB_PATH", "/data/ladybug")
    space_path = os.getenv("SPACE_PATH", "/space")
    grpc_port = int(os.getenv("GRPC_PORT", "50051"))
    mcp_port = int(os.getenv("MCP_PORT", "8000"))

    server = UnifiedServer(
        db_path=db_path,
        space_path=space_path,
        grpc_port=grpc_port,
        mcp_port=mcp_port,
    )

    asyncio.run(server.run())


if __name__ == "__main__":
    main()
