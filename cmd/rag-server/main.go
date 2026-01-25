// Package main provides the entry point for the silverbullet-rag server.
package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"
	"time"

	"github.com/boblangley/silverbullet-rag/internal/config"
	"github.com/boblangley/silverbullet-rag/internal/db"
	"github.com/boblangley/silverbullet-rag/internal/embeddings"
	"github.com/boblangley/silverbullet-rag/internal/parser"
	"github.com/boblangley/silverbullet-rag/internal/search"
	"github.com/boblangley/silverbullet-rag/internal/server"
	"github.com/boblangley/silverbullet-rag/internal/watcher"
)

func main() {
	// Parse flags
	spacePath := flag.String("space", "", "Path to SilverBullet space directory")
	dbPath := flag.String("db", "", "Path to LadybugDB database (default: <space>/.silverbullet-rag/ladybug.db)")
	mcpAddr := flag.String("mcp", ":8000", "MCP HTTP server address (host:port)")
	grpcAddr := flag.String("grpc", ":50051", "gRPC server address")
	healthPort := flag.Int("health-port", 8080, "Health check HTTP server port (0 to disable)")
	logLevel := flag.String("log-level", "info", "Log level (debug, info, warn, error)")
	rebuild := flag.Bool("rebuild", false, "Rebuild index from scratch")
	noEmbeddings := flag.Bool("no-embeddings", false, "Disable embedding generation")
	libraryPath := flag.String("library-path", "", "Path to bundled library files (default: ./library)")
	allowLibMgmt := flag.Bool("allow-library-management", false, "Enable library install/update MCP tools")
	flag.Parse()

	// Set default library path
	if *libraryPath == "" {
		// Try relative to executable first
		exeDir := filepath.Dir(os.Args[0])
		*libraryPath = filepath.Join(exeDir, "..", "..", "library")
		if _, err := os.Stat(*libraryPath); os.IsNotExist(err) {
			// Fall back to current directory
			*libraryPath = "library"
		}
	}

	// Configure logging
	var level slog.Level
	switch *logLevel {
	case "debug":
		level = slog.LevelDebug
	case "warn":
		level = slog.LevelWarn
	case "error":
		level = slog.LevelError
	default:
		level = slog.LevelInfo
	}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: level}))
	slog.SetDefault(logger)

	// Validate required flags
	if *spacePath == "" {
		fmt.Fprintln(os.Stderr, "error: -space flag is required")
		flag.Usage()
		os.Exit(1)
	}

	// Resolve absolute path
	absSpacePath, err := filepath.Abs(*spacePath)
	if err != nil {
		slog.Error("failed to resolve space path", "error", err)
		os.Exit(1)
	}

	// Set default database path
	if *dbPath == "" {
		*dbPath = filepath.Join(absSpacePath, ".silverbullet-rag", "ladybug.db")
	}

	slog.Info("starting silverbullet-rag server",
		"space", absSpacePath,
		"db", *dbPath,
		"mcp", *mcpAddr,
		"grpc", *grpcAddr,
		"embeddings", !*noEmbeddings,
	)

	// Setup context with cancellation
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Handle shutdown signals
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		sig := <-sigCh
		slog.Info("received shutdown signal", "signal", sig)
		cancel()
	}()

	// Open database
	graphDB, err := db.Open(db.Config{
		Path:             *dbPath,
		EnableEmbeddings: !*noEmbeddings,
		AutoRecover:      true,
		Logger:           logger,
	})
	if err != nil {
		slog.Error("failed to open database", "error", err)
		os.Exit(1)
	}
	defer graphDB.Close()

	// Initialize embedding service
	var embeddingSvc *embeddings.Service
	if !*noEmbeddings {
		embeddingSvc, err = embeddings.NewService(embeddings.Config{})
		if err != nil {
			slog.Warn("failed to initialize embedding service, continuing without embeddings", "error", err)
		}
	}

	// Initialize Deno runner for config parsing
	denoPath := config.FindDeno()
	var denoRunner *config.DenoRunner
	if denoPath != "" {
		// Find the deno runner script relative to executable or in known locations
		runnerPath := filepath.Join(filepath.Dir(os.Args[0]), "..", "..", "deno", "space_lua_runner.ts")
		if _, err := os.Stat(runnerPath); os.IsNotExist(err) {
			// Try relative to current directory
			runnerPath = "deno/space_lua_runner.ts"
		}
		denoDir := filepath.Dir(runnerPath)
		denoRunner = config.NewDenoRunner(denoPath, runnerPath, denoDir)
		slog.Info("Deno runner initialized", "path", denoPath)
	} else {
		slog.Warn("Deno not found, CONFIG.md parsing will use AST fallback")
	}

	// Initialize watcher
	w, err := watcher.New(watcher.Config{
		SpacePath:  absSpacePath,
		DB:         graphDB,
		Embedding:  embeddingSvc,
		DenoRunner: denoRunner,
		DBPath:     filepath.Dir(*dbPath),
		Logger:     logger,
	})
	if err != nil {
		slog.Error("failed to create watcher", "error", err)
		os.Exit(1)
	}

	// Perform initial index
	count, err := w.InitialIndex(ctx, *rebuild)
	if err != nil {
		slog.Error("failed to perform initial index", "error", err)
		os.Exit(1)
	}
	slog.Info("initial index complete", "chunks", count)

	// Start file watcher
	if err := w.Start(ctx); err != nil {
		slog.Error("failed to start watcher", "error", err)
		os.Exit(1)
	}
	defer func() { _ = w.Stop() }()

	// Initialize parser and search
	spaceParser := parser.NewSpaceParser(absSpacePath)
	hybridSearch := search.NewHybridSearch(graphDB, embeddingSvc)

	// Start MCP HTTP server
	var mcpHTTPServer *http.Server
	if *mcpAddr != "" {
		mcpServer := server.NewMCPServer(server.MCPConfig{
			DB:                     graphDB,
			Search:                 hybridSearch,
			Parser:                 spaceParser,
			SpacePath:              absSpacePath,
			DBPath:                 filepath.Dir(*dbPath),
			LibraryPath:            *libraryPath,
			AllowLibraryManagement: *allowLibMgmt,
			Logger:                 logger,
		})

		mcpHTTPServer = &http.Server{
			Addr:    *mcpAddr,
			Handler: mcpServer.HTTPHandler(),
		}

		go func() {
			slog.Info("starting MCP HTTP server", "addr", *mcpAddr)
			if err := mcpHTTPServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
				slog.Error("MCP HTTP server error", "error", err)
			}
		}()
	}

	// Start gRPC server
	var grpcServer *server.GRPCServer
	if *grpcAddr != "" {
		grpcServer = server.NewGRPCServer(server.GRPCConfig{
			DB:        graphDB,
			Search:    hybridSearch,
			Parser:    spaceParser,
			SpacePath: absSpacePath,
			DBPath:    filepath.Dir(*dbPath),
			Logger:    logger,
		})

		go func() {
			if err := grpcServer.Serve(*grpcAddr); err != nil {
				slog.Error("gRPC server error", "error", err)
			}
		}()
	}

	// Start health check server
	var healthServer *server.HealthServer
	if *healthPort > 0 {
		// Extract port numbers for health checks
		grpcPort := 50051
		if _, p, err := parseHostPort(*grpcAddr, 50051); err == nil {
			grpcPort = p
		}
		mcpPort := 8000
		if _, p, err := parseHostPort(*mcpAddr, 8000); err == nil {
			mcpPort = p
		}

		healthServer = server.NewHealthServer(server.HealthConfig{
			Port:     *healthPort,
			GRPCPort: grpcPort,
			MCPPort:  mcpPort,
			Logger:   logger,
		})

		go func() {
			if err := healthServer.Start(); err != nil && err.Error() != "http: Server closed" {
				slog.Error("health server error", "error", err)
			}
		}()
	}

	slog.Info("server ready",
		"mcp", *mcpAddr,
		"grpc", *grpcAddr,
		"health", *healthPort,
	)

	// Wait for shutdown
	<-ctx.Done()

	// Graceful shutdown
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()

	if mcpHTTPServer != nil {
		if err := mcpHTTPServer.Shutdown(shutdownCtx); err != nil {
			slog.Error("MCP HTTP server shutdown error", "error", err)
		}
	}
	if healthServer != nil {
		if err := healthServer.Stop(shutdownCtx); err != nil {
			slog.Error("health server shutdown error", "error", err)
		}
	}
	if grpcServer != nil {
		grpcServer.Stop()
	}
	slog.Info("server shutdown complete")
}

// parseHostPort extracts host and port from an address string.
func parseHostPort(addr string, defaultPort int) (string, int, error) {
	if addr == "" {
		return "", defaultPort, nil
	}
	host, portStr, err := net.SplitHostPort(addr)
	if err != nil {
		// Maybe it's just a port like ":50051"
		if addr[0] == ':' {
			portStr = addr[1:]
			host = ""
		} else {
			return "", 0, err
		}
	}
	port, err := strconv.Atoi(portStr)
	if err != nil {
		return host, defaultPort, nil
	}
	return host, port, nil
}
