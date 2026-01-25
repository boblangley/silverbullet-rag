// Package server provides HTTP and gRPC server implementations.
package server

import (
	"context"
	"encoding/json"
	"log/slog"
	"net"
	"net/http"
	"strconv"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// HealthServer provides HTTP health check endpoints for container probes.
type HealthServer struct {
	port     int
	grpcPort int
	mcpPort  int
	server   *http.Server
	logger   *slog.Logger
}

// HealthConfig holds configuration for the health check server.
type HealthConfig struct {
	Port     int
	GRPCPort int
	MCPPort  int
	Logger   *slog.Logger
}

// NewHealthServer creates a new health check server.
func NewHealthServer(cfg HealthConfig) *HealthServer {
	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	return &HealthServer{
		port:     cfg.Port,
		grpcPort: cfg.GRPCPort,
		mcpPort:  cfg.MCPPort,
		logger:   logger,
	}
}

// Start begins serving health check requests.
func (h *HealthServer) Start() error {
	mux := http.NewServeMux()
	mux.HandleFunc("/", h.handleHealth)
	mux.HandleFunc("/health", h.handleHealth)
	mux.HandleFunc("/health/grpc", h.handleGRPCHealth)
	mux.HandleFunc("/health/mcp", h.handleMCPHealth)
	mux.HandleFunc("/ready", h.handleReady)
	mux.HandleFunc("/live", h.handleLive)

	h.server = &http.Server{
		Addr:         net.JoinHostPort("0.0.0.0", strconv.Itoa(h.port)),
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
	}

	h.logger.Info("Health check server starting", "port", h.port)
	return h.server.ListenAndServe()
}

// Stop gracefully shuts down the health check server.
func (h *HealthServer) Stop(ctx context.Context) error {
	if h.server != nil {
		return h.server.Shutdown(ctx)
	}
	return nil
}

// handleHealth returns combined health status of all services.
func (h *HealthServer) handleHealth(w http.ResponseWriter, r *http.Request) {
	grpcOK := h.checkGRPC()
	mcpOK := h.checkMCP()
	allOK := grpcOK && mcpOK

	status := map[string]interface{}{
		"status": statusString(allOK),
		"services": map[string]string{
			"grpc": upDownString(grpcOK),
			"mcp":  upDownString(mcpOK),
		},
	}

	h.sendJSON(w, status, statusCode(allOK))
}

// handleGRPCHealth returns health status of gRPC service only.
func (h *HealthServer) handleGRPCHealth(w http.ResponseWriter, r *http.Request) {
	ok := h.checkGRPC()
	h.sendJSON(w, map[string]string{"status": upDownString(ok)}, statusCode(ok))
}

// handleMCPHealth returns health status of MCP service only.
func (h *HealthServer) handleMCPHealth(w http.ResponseWriter, r *http.Request) {
	ok := h.checkMCP()
	h.sendJSON(w, map[string]string{"status": upDownString(ok)}, statusCode(ok))
}

// handleReady implements Kubernetes-style readiness probe.
func (h *HealthServer) handleReady(w http.ResponseWriter, r *http.Request) {
	grpcOK := h.checkGRPC()
	mcpOK := h.checkMCP()
	allOK := grpcOK && mcpOK

	h.sendJSON(w, map[string]bool{"ready": allOK}, statusCode(allOK))
}

// handleLive implements Kubernetes-style liveness probe.
func (h *HealthServer) handleLive(w http.ResponseWriter, r *http.Request) {
	// Liveness always returns OK if the server is running
	h.sendJSON(w, map[string]bool{"alive": true}, http.StatusOK)
}

// checkGRPC verifies gRPC server is healthy by attempting a connection.
func (h *HealthServer) checkGRPC() bool {
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()

	addr := net.JoinHostPort("localhost", strconv.Itoa(h.grpcPort))
	conn, err := grpc.DialContext(ctx, addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock(),
	)
	if err != nil {
		return false
	}
	conn.Close()
	return true
}

// checkMCP verifies MCP server is healthy by checking if port is open.
func (h *HealthServer) checkMCP() bool {
	addr := net.JoinHostPort("localhost", strconv.Itoa(h.mcpPort))
	conn, err := net.DialTimeout("tcp", addr, time.Second)
	if err != nil {
		return false
	}
	conn.Close()
	return true
}

// sendJSON writes a JSON response with the given status code.
func (h *HealthServer) sendJSON(w http.ResponseWriter, data interface{}, statusCode int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	if err := json.NewEncoder(w).Encode(data); err != nil {
		h.logger.Error("Failed to encode health response", "error", err)
	}
}

// Helper functions

func statusString(ok bool) string {
	if ok {
		return "healthy"
	}
	return "unhealthy"
}

func upDownString(ok bool) string {
	if ok {
		return "up"
	}
	return "down"
}

func statusCode(ok bool) int {
	if ok {
		return http.StatusOK
	}
	return http.StatusServiceUnavailable
}
