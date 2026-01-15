"""Health check HTTP server for container readiness probes."""

import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import socket
import threading
from typing import Callable

import grpc

logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check endpoint."""

    # Class-level attributes set by the server
    check_grpc: Callable[[], bool] = lambda: False
    check_mcp: Callable[[], bool] = lambda: False

    def log_message(self, format: str, *args) -> None:
        """Suppress default logging to avoid noise."""
        pass

    def do_GET(self) -> None:
        """Handle GET requests for health checks."""
        if self.path == "/health" or self.path == "/":
            self._handle_health()
        elif self.path == "/health/grpc":
            self._handle_grpc_health()
        elif self.path == "/health/mcp":
            self._handle_mcp_health()
        elif self.path == "/ready":
            self._handle_ready()
        elif self.path == "/live":
            self._handle_live()
        else:
            self.send_error(404, "Not Found")

    def _handle_health(self) -> None:
        """Combined health check for all services."""
        grpc_ok = self.check_grpc()
        mcp_ok = self.check_mcp()
        all_ok = grpc_ok and mcp_ok

        status = {
            "status": "healthy" if all_ok else "unhealthy",
            "services": {
                "grpc": "up" if grpc_ok else "down",
                "mcp": "up" if mcp_ok else "down",
            },
        }

        self._send_json(status, 200 if all_ok else 503)

    def _handle_grpc_health(self) -> None:
        """Health check for gRPC service only."""
        ok = self.check_grpc()
        status = {"status": "up" if ok else "down"}
        self._send_json(status, 200 if ok else 503)

    def _handle_mcp_health(self) -> None:
        """Health check for MCP service only."""
        ok = self.check_mcp()
        status = {"status": "up" if ok else "down"}
        self._send_json(status, 200 if ok else 503)

    def _handle_ready(self) -> None:
        """Kubernetes-style readiness probe."""
        grpc_ok = self.check_grpc()
        mcp_ok = self.check_mcp()
        all_ok = grpc_ok and mcp_ok
        self._send_json({"ready": all_ok}, 200 if all_ok else 503)

    def _handle_live(self) -> None:
        """Kubernetes-style liveness probe (always returns OK if server is running)."""
        self._send_json({"alive": True}, 200)

    def _send_json(self, data: dict, status_code: int) -> None:
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


def check_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a port is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def check_grpc_health(host: str, port: int) -> bool:
    """Check if gRPC server is healthy by attempting a connection."""
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        # Use channel ready future with short timeout
        grpc.channel_ready_future(channel).result(timeout=1.0)
        channel.close()
        return True
    except grpc.FutureTimeoutError:
        return False
    except Exception:
        return False


class HealthServer:
    """Health check HTTP server."""

    def __init__(
        self,
        port: int = 8080,
        grpc_port: int = 50051,
        mcp_port: int = 8000,
    ):
        self.port = port
        self.grpc_port = grpc_port
        self.mcp_port = mcp_port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _check_grpc(self) -> bool:
        """Check gRPC server health."""
        return check_grpc_health("localhost", self.grpc_port)

    def _check_mcp(self) -> bool:
        """Check MCP server health (port open check)."""
        return check_port_open("localhost", self.mcp_port)

    def start(self) -> None:
        """Start the health check server in a background thread."""
        # Set up the handler with our check functions
        HealthCheckHandler.check_grpc = self._check_grpc
        HealthCheckHandler.check_mcp = self._check_mcp

        self._server = HTTPServer(("0.0.0.0", self.port), HealthCheckHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info(f"Health check server started on port {self.port}")

    def stop(self) -> None:
        """Stop the health check server."""
        if self._server:
            self._server.shutdown()
            logger.info("Health check server stopped")
