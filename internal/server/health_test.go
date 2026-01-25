package server

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestHealthServerEndpoints(t *testing.T) {
	// Create a health server with test configuration
	h := &HealthServer{
		port:     0, // Will be overridden by httptest
		grpcPort: 0, // No real gRPC server
		mcpPort:  0, // No real MCP server
	}

	tests := []struct {
		name       string
		path       string
		wantStatus int
		checkBody  func(t *testing.T, body map[string]interface{})
	}{
		{
			name:       "liveness always returns OK",
			path:       "/live",
			wantStatus: http.StatusOK,
			checkBody: func(t *testing.T, body map[string]interface{}) {
				if alive, ok := body["alive"].(bool); !ok || !alive {
					t.Error("expected alive: true")
				}
			},
		},
		{
			name:       "readiness returns unhealthy when services down",
			path:       "/ready",
			wantStatus: http.StatusServiceUnavailable,
			checkBody: func(t *testing.T, body map[string]interface{}) {
				if ready, ok := body["ready"].(bool); !ok || ready {
					t.Error("expected ready: false")
				}
			},
		},
		{
			name:       "health returns unhealthy when services down",
			path:       "/health",
			wantStatus: http.StatusServiceUnavailable,
			checkBody: func(t *testing.T, body map[string]interface{}) {
				if status, ok := body["status"].(string); !ok || status != "unhealthy" {
					t.Errorf("expected status: unhealthy, got %v", status)
				}
				services, ok := body["services"].(map[string]interface{})
				if !ok {
					t.Fatal("expected services map")
				}
				if grpc, ok := services["grpc"].(string); !ok || grpc != "down" {
					t.Error("expected grpc: down")
				}
				if mcp, ok := services["mcp"].(string); !ok || mcp != "down" {
					t.Error("expected mcp: down")
				}
			},
		},
		{
			name:       "root path returns health",
			path:       "/",
			wantStatus: http.StatusServiceUnavailable,
			checkBody: func(t *testing.T, body map[string]interface{}) {
				if _, ok := body["status"]; !ok {
					t.Error("expected status field")
				}
			},
		},
		{
			name:       "grpc health endpoint",
			path:       "/health/grpc",
			wantStatus: http.StatusServiceUnavailable,
			checkBody: func(t *testing.T, body map[string]interface{}) {
				if status, ok := body["status"].(string); !ok || status != "down" {
					t.Errorf("expected status: down, got %v", status)
				}
			},
		},
		{
			name:       "mcp health endpoint",
			path:       "/health/mcp",
			wantStatus: http.StatusServiceUnavailable,
			checkBody: func(t *testing.T, body map[string]interface{}) {
				if status, ok := body["status"].(string); !ok || status != "down" {
					t.Errorf("expected status: down, got %v", status)
				}
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var handler http.HandlerFunc
			switch tt.path {
			case "/live":
				handler = h.handleLive
			case "/ready":
				handler = h.handleReady
			case "/health", "/":
				handler = h.handleHealth
			case "/health/grpc":
				handler = h.handleGRPCHealth
			case "/health/mcp":
				handler = h.handleMCPHealth
			}

			req := httptest.NewRequest(http.MethodGet, tt.path, nil)
			rec := httptest.NewRecorder()
			handler(rec, req)

			if rec.Code != tt.wantStatus {
				t.Errorf("status = %d, want %d", rec.Code, tt.wantStatus)
			}

			if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
				t.Errorf("Content-Type = %s, want application/json", ct)
			}

			var body map[string]interface{}
			if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
				t.Fatalf("failed to parse response: %v", err)
			}

			if tt.checkBody != nil {
				tt.checkBody(t, body)
			}
		})
	}
}

func TestHealthServerWithRealServices(t *testing.T) {
	// Start a TCP listener to simulate MCP
	mcpListener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to start mock MCP listener: %v", err)
	}
	defer mcpListener.Close()
	mcpPort := mcpListener.Addr().(*net.TCPAddr).Port

	// Accept connections in background to keep port open
	go func() {
		for {
			conn, err := mcpListener.Accept()
			if err != nil {
				return
			}
			conn.Close()
		}
	}()

	// Create health server pointing to the mock MCP
	h := &HealthServer{
		grpcPort: 0,       // No gRPC, will fail
		mcpPort:  mcpPort, // Has listener, will pass
	}

	// Test MCP health - should be up
	req := httptest.NewRequest(http.MethodGet, "/health/mcp", nil)
	rec := httptest.NewRecorder()
	h.handleMCPHealth(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("MCP health status = %d, want 200", rec.Code)
	}

	var body map[string]interface{}
	json.Unmarshal(rec.Body.Bytes(), &body)
	if status := body["status"]; status != "up" {
		t.Errorf("MCP status = %v, want up", status)
	}
}

func TestHealthServerStartStop(t *testing.T) {
	h := NewHealthServer(HealthConfig{
		Port:     0, // Let OS assign port
		GRPCPort: 50051,
		MCPPort:  8000,
	})

	// Find a free port
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to find free port: %v", err)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	listener.Close()

	h.port = port

	// Start in background
	errCh := make(chan error, 1)
	go func() {
		errCh <- h.Start()
	}()

	// Give it time to start
	time.Sleep(100 * time.Millisecond)

	// Make a request
	resp, err := http.Get("http://127.0.0.1:" + itoa(port) + "/live")
	if err != nil {
		t.Fatalf("failed to connect to health server: %v", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		t.Errorf("status = %d, want 200, body: %s", resp.StatusCode, body)
	}

	// Stop server
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := h.Stop(ctx); err != nil {
		t.Errorf("Stop error: %v", err)
	}

	// Wait for Start to return
	select {
	case err := <-errCh:
		if err != nil && err.Error() != "http: Server closed" {
			t.Errorf("Start returned unexpected error: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Error("Start did not return after Stop")
	}
}

func itoa(i int) string {
	if i == 0 {
		return "0"
	}
	var b [20]byte
	pos := len(b)
	for i > 0 {
		pos--
		b[pos] = byte('0' + i%10)
		i /= 10
	}
	return string(b[pos:])
}
