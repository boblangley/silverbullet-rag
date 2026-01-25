// Package server provides MCP and gRPC server implementations.
package server

import (
	"context"
	"encoding/json"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"github.com/boblangley/silverbullet-rag/internal/db"
	"github.com/boblangley/silverbullet-rag/internal/parser"
	pb "github.com/boblangley/silverbullet-rag/internal/proto"
	"github.com/boblangley/silverbullet-rag/internal/search"
	"github.com/boblangley/silverbullet-rag/internal/types"
)

func setupTestGRPCServer(t *testing.T) (*GRPCServer, *db.GraphDB, string, string) {
	t.Helper()
	dbPath := createTempDB(t)
	spacePath := createTempSpace(t)

	graphDB, err := db.Open(db.Config{
		Path:             dbPath,
		EnableEmbeddings: false,
	})
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	t.Cleanup(func() { graphDB.Close() })

	spaceParser := parser.NewSpaceParser(spacePath)
	hybridSearch := search.NewHybridSearch(graphDB, nil)

	grpcServer := NewGRPCServer(GRPCConfig{
		DB:        graphDB,
		Search:    hybridSearch,
		Parser:    spaceParser,
		SpacePath: spacePath,
		DBPath:    filepath.Dir(dbPath),
	})

	return grpcServer, graphDB, spacePath, dbPath
}

func startTestGRPCServer(t *testing.T, server *GRPCServer) (pb.RAGServiceClient, func()) {
	t.Helper()

	// Find an available port
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("Failed to listen: %v", err)
	}
	addr := lis.Addr().String()

	// Start server in background
	go func() {
		if err := server.server.Serve(lis); err != nil && err != grpc.ErrServerStopped {
			t.Logf("Server error: %v", err)
		}
	}()

	// Create client connection
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("Failed to connect: %v", err)
	}

	client := pb.NewRAGServiceClient(conn)

	cleanup := func() {
		conn.Close()
		server.Stop()
	}

	return client, cleanup
}

// ==================== Initialization Tests ====================

func TestGRPCServerInitialization(t *testing.T) {
	grpcServer, _, _, _ := setupTestGRPCServer(t)

	if grpcServer == nil {
		t.Fatal("gRPC server should not be nil")
	}
	if grpcServer.server == nil {
		t.Error("Internal gRPC server should not be nil")
	}
	if grpcServer.db == nil {
		t.Error("Database should not be nil")
	}
	if grpcServer.search == nil {
		t.Error("Search should not be nil")
	}
}

// ==================== Query Tests ====================

func TestGRPCQuery(t *testing.T) {
	grpcServer, graphDB, _, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Index some test data
	chunks := []types.Chunk{
		{
			FilePath:   "/test/page1.md",
			Header:     "Test Page",
			Content:    "Test content",
			FolderPath: "test",
		},
	}
	if err := graphDB.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("Failed to index chunks: %v", err)
	}

	// Test query
	resp, err := client.Query(ctx, &pb.QueryRequest{
		CypherQuery: "MATCH (c:Chunk) RETURN c.header AS header LIMIT 1",
	})
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	if !resp.Success {
		t.Errorf("Query should succeed, got error: %s", resp.Error)
	}
	if resp.ResultsJson == "" {
		t.Error("Results should not be empty")
	}
}

func TestGRPCQueryInvalid(t *testing.T) {
	grpcServer, _, _, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	resp, err := client.Query(ctx, &pb.QueryRequest{
		CypherQuery: "INVALID CYPHER QUERY",
	})
	if err != nil {
		t.Fatalf("Query RPC failed: %v", err)
	}

	if resp.Success {
		t.Error("Query should fail for invalid cypher")
	}
	if resp.Error == "" {
		t.Error("Error message should not be empty")
	}
}

// ==================== Search Tests ====================

func TestGRPCSearch(t *testing.T) {
	grpcServer, graphDB, _, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Index test data
	chunks := []types.Chunk{
		{
			FilePath:   "/test/page1.md",
			Header:     "Test Page",
			Content:    "This is a test about golang programming",
			FolderPath: "test",
		},
	}
	if err := graphDB.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("Failed to index chunks: %v", err)
	}

	resp, err := client.Search(ctx, &pb.SearchRequest{
		Keyword: "golang",
		Limit:   10,
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if !resp.Success {
		t.Errorf("Search should succeed, got error: %s", resp.Error)
	}
}

func TestGRPCHybridSearch(t *testing.T) {
	grpcServer, graphDB, _, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Index test data
	chunks := []types.Chunk{
		{
			FilePath:   "/test/page1.md",
			Header:     "Test Page",
			Content:    "This is a test about golang programming",
			FolderPath: "test",
		},
	}
	if err := graphDB.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("Failed to index chunks: %v", err)
	}

	resp, err := client.HybridSearch(ctx, &pb.HybridSearchRequest{
		Query:          "golang",
		Limit:          10,
		FusionMethod:   "rrf",
		SemanticWeight: 0.5,
		KeywordWeight:  0.5,
	})
	if err != nil {
		t.Fatalf("HybridSearch failed: %v", err)
	}

	if !resp.Success {
		t.Errorf("HybridSearch should succeed, got error: %s", resp.Error)
	}
}

// ==================== ReadPage Tests ====================

func TestGRPCReadPage(t *testing.T) {
	grpcServer, _, spacePath, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Create a test page
	pageContent := "# Test Page\n\nThis is test content."
	pagePath := filepath.Join(spacePath, "TestPage.md")
	if err := os.WriteFile(pagePath, []byte(pageContent), 0644); err != nil {
		t.Fatalf("Failed to create test page: %v", err)
	}

	resp, err := client.ReadPage(ctx, &pb.ReadPageRequest{
		PageName: "TestPage.md",
	})
	if err != nil {
		t.Fatalf("ReadPage failed: %v", err)
	}

	if !resp.Success {
		t.Errorf("ReadPage should succeed, got error: %s", resp.Error)
	}
	if resp.Content != pageContent {
		t.Errorf("Content mismatch: got %q, want %q", resp.Content, pageContent)
	}
}

func TestGRPCReadPageNotFound(t *testing.T) {
	grpcServer, _, _, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	resp, err := client.ReadPage(ctx, &pb.ReadPageRequest{
		PageName: "NonExistent.md",
	})
	if err != nil {
		t.Fatalf("ReadPage RPC failed: %v", err)
	}

	if resp.Success {
		t.Error("ReadPage should fail for non-existent page")
	}
	if resp.Error == "" {
		t.Error("Error message should not be empty")
	}
}

func TestGRPCReadPagePathTraversal(t *testing.T) {
	grpcServer, _, _, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	resp, err := client.ReadPage(ctx, &pb.ReadPageRequest{
		PageName: "../../../etc/passwd",
	})
	if err != nil {
		t.Fatalf("ReadPage RPC failed: %v", err)
	}

	if resp.Success {
		t.Error("ReadPage should fail for path traversal attempts")
	}
}

// ==================== Proposal Tests ====================

func TestGRPCProposeChangeWithoutLibrary(t *testing.T) {
	grpcServer, _, _, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	resp, err := client.ProposeChange(ctx, &pb.ProposeChangeRequest{
		TargetPage:  "TestPage.md",
		Content:     "New content",
		Title:       "Test Proposal",
		Description: "Testing proposals",
	})
	if err != nil {
		t.Fatalf("ProposeChange RPC failed: %v", err)
	}

	// Should fail because Proposals library is not installed
	if resp.Success {
		t.Error("ProposeChange should fail without Proposals library")
	}
	if resp.Error != "Proposals library not installed" {
		t.Errorf("Expected 'Proposals library not installed' error, got: %s", resp.Error)
	}
}

func TestGRPCProposeChangeWithLibrary(t *testing.T) {
	grpcServer, _, spacePath, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Create Proposals library directory
	libraryPath := filepath.Join(spacePath, "Library", "Proposals")
	if err := os.MkdirAll(libraryPath, 0755); err != nil {
		t.Fatalf("Failed to create library dir: %v", err)
	}

	resp, err := client.ProposeChange(ctx, &pb.ProposeChangeRequest{
		TargetPage:  "TestPage.md",
		Content:     "New content",
		Title:       "Test Proposal",
		Description: "Testing proposals",
	})
	if err != nil {
		t.Fatalf("ProposeChange RPC failed: %v", err)
	}

	if !resp.Success {
		t.Errorf("ProposeChange should succeed, got error: %s", resp.Error)
	}
	if resp.ProposalPath == "" {
		t.Error("ProposalPath should not be empty")
	}
	if !resp.IsNewPage {
		t.Error("Should be marked as new page since TestPage.md doesn't exist")
	}

	// Verify proposal file was created
	proposalFile := filepath.Join(spacePath, resp.ProposalPath)
	if _, err := os.Stat(proposalFile); os.IsNotExist(err) {
		t.Errorf("Proposal file should exist at: %s", proposalFile)
	}

	// Verify proposal content has required metadata
	content, err := os.ReadFile(proposalFile)
	if err != nil {
		t.Fatalf("Failed to read proposal file: %v", err)
	}
	contentStr := string(content)

	// Check for required metadata fields
	requiredFields := []string{
		"type: proposal",
		"tags:",
		"- proposal",
		"target_page: TestPage.md",
		"title: Test Proposal",
		"description: Testing proposals",
		"proposed_by: claude-code",
		"created_at:",
		"status: pending",
		"is_new_page: true",
	}
	for _, field := range requiredFields {
		if !strings.Contains(contentStr, field) {
			t.Errorf("Proposal content missing field: %s", field)
		}
	}
}

func TestGRPCProposeChangeWithCustomProposedBy(t *testing.T) {
	grpcServer, _, spacePath, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Create Proposals library directory
	libraryPath := filepath.Join(spacePath, "Library", "Proposals")
	if err := os.MkdirAll(libraryPath, 0755); err != nil {
		t.Fatalf("Failed to create library dir: %v", err)
	}

	resp, err := client.ProposeChange(ctx, &pb.ProposeChangeRequest{
		TargetPage:  "CustomPage.md",
		Content:     "Custom content",
		Title:       "Custom Proposal",
		Description: "Testing custom proposer",
		ProposedBy:  "custom-agent",
	})
	if err != nil {
		t.Fatalf("ProposeChange RPC failed: %v", err)
	}

	if !resp.Success {
		t.Errorf("ProposeChange should succeed, got error: %s", resp.Error)
	}

	// Verify custom proposed_by is used
	proposalFile := filepath.Join(spacePath, resp.ProposalPath)
	content, err := os.ReadFile(proposalFile)
	if err != nil {
		t.Fatalf("Failed to read proposal file: %v", err)
	}

	if !strings.Contains(string(content), "proposed_by: custom-agent") {
		t.Error("Proposal should contain custom proposed_by value")
	}
}

func TestGRPCListProposals(t *testing.T) {
	grpcServer, _, spacePath, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Create Proposals library directory
	libraryPath := filepath.Join(spacePath, "Library", "Proposals")
	if err := os.MkdirAll(libraryPath, 0755); err != nil {
		t.Fatalf("Failed to create library dir: %v", err)
	}

	// Create a test proposal
	proposalDir := filepath.Join(spacePath, "_Proposals")
	if err := os.MkdirAll(proposalDir, 0755); err != nil {
		t.Fatalf("Failed to create proposals dir: %v", err)
	}

	proposalContent := `---
type: proposal
target_page: TestPage.md
title: Test Proposal
status: pending
is_new_page: true
---
Test content`

	if err := os.WriteFile(filepath.Join(proposalDir, "TestPage.proposal"), []byte(proposalContent), 0644); err != nil {
		t.Fatalf("Failed to write proposal: %v", err)
	}

	resp, err := client.ListProposals(ctx, &pb.ListProposalsRequest{
		Status: "pending",
	})
	if err != nil {
		t.Fatalf("ListProposals RPC failed: %v", err)
	}

	if !resp.Success {
		t.Errorf("ListProposals should succeed, got error: %s", resp.Error)
	}
	if resp.Count != 1 {
		t.Errorf("Expected 1 proposal, got %d", resp.Count)
	}
	if len(resp.Proposals) != 1 {
		t.Errorf("Expected 1 proposal in list, got %d", len(resp.Proposals))
	}
}

func TestGRPCWithdrawProposal(t *testing.T) {
	grpcServer, _, spacePath, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Create Proposals library directory
	libraryPath := filepath.Join(spacePath, "Library", "Proposals")
	if err := os.MkdirAll(libraryPath, 0755); err != nil {
		t.Fatalf("Failed to create library dir: %v", err)
	}

	// Create a test proposal
	proposalDir := filepath.Join(spacePath, "_Proposals")
	if err := os.MkdirAll(proposalDir, 0755); err != nil {
		t.Fatalf("Failed to create proposals dir: %v", err)
	}

	proposalPath := "_Proposals/TestPage.proposal"
	proposalContent := `---
type: proposal
target_page: TestPage.md
title: Test Proposal
status: pending
---
Test content`

	if err := os.WriteFile(filepath.Join(spacePath, proposalPath), []byte(proposalContent), 0644); err != nil {
		t.Fatalf("Failed to write proposal: %v", err)
	}

	resp, err := client.WithdrawProposal(ctx, &pb.WithdrawProposalRequest{
		ProposalPath: proposalPath,
	})
	if err != nil {
		t.Fatalf("WithdrawProposal RPC failed: %v", err)
	}

	if !resp.Success {
		t.Errorf("WithdrawProposal should succeed, got error: %s", resp.Error)
	}

	// Verify proposal was deleted
	if _, err := os.Stat(filepath.Join(spacePath, proposalPath)); !os.IsNotExist(err) {
		t.Error("Proposal file should have been deleted")
	}
}

// ==================== GetProjectContext Tests ====================

func TestGRPCGetProjectContextByGitHub(t *testing.T) {
	grpcServer, _, spacePath, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Create a project page with GitHub frontmatter
	projectDir := filepath.Join(spacePath, "Projects")
	if err := os.MkdirAll(projectDir, 0755); err != nil {
		t.Fatalf("Failed to create project dir: %v", err)
	}

	projectContent := `---
github: owner/test-repo
tags:
  - golang
  - test
---
# Test Project

This is a test project.`

	if err := os.WriteFile(filepath.Join(projectDir, "TestProject.md"), []byte(projectContent), 0644); err != nil {
		t.Fatalf("Failed to write project page: %v", err)
	}

	resp, err := client.GetProjectContext(ctx, &pb.GetProjectContextRequest{
		GithubRemote: "owner/test-repo",
	})
	if err != nil {
		t.Fatalf("GetProjectContext RPC failed: %v", err)
	}

	if !resp.Success {
		t.Errorf("GetProjectContext should succeed, got error: %s", resp.Error)
	}
	if resp.Project == nil {
		t.Fatal("Project should not be nil")
	}
	if resp.Project.Github != "owner/test-repo" {
		t.Errorf("Expected github 'owner/test-repo', got '%s'", resp.Project.Github)
	}
	if len(resp.Project.Tags) != 2 {
		t.Errorf("Expected 2 tags, got %d", len(resp.Project.Tags))
	}
}

func TestGRPCGetProjectContextByFolder(t *testing.T) {
	grpcServer, _, spacePath, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Create a project page
	projectDir := filepath.Join(spacePath, "Projects")
	if err := os.MkdirAll(projectDir, 0755); err != nil {
		t.Fatalf("Failed to create project dir: %v", err)
	}

	projectContent := `---
tags:
  - golang
---
# My Project

This is my project.`

	if err := os.WriteFile(filepath.Join(projectDir, "MyProject.md"), []byte(projectContent), 0644); err != nil {
		t.Fatalf("Failed to write project page: %v", err)
	}

	resp, err := client.GetProjectContext(ctx, &pb.GetProjectContextRequest{
		FolderPath: "Projects/MyProject",
	})
	if err != nil {
		t.Fatalf("GetProjectContext RPC failed: %v", err)
	}

	if !resp.Success {
		t.Errorf("GetProjectContext should succeed, got error: %s", resp.Error)
	}
	if resp.Project == nil {
		t.Fatal("Project should not be nil")
	}
}

func TestGRPCGetProjectContextNotFound(t *testing.T) {
	grpcServer, _, _, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	resp, err := client.GetProjectContext(ctx, &pb.GetProjectContextRequest{
		GithubRemote: "nonexistent/repo",
	})
	if err != nil {
		t.Fatalf("GetProjectContext RPC failed: %v", err)
	}

	if resp.Success {
		t.Error("GetProjectContext should fail for non-existent project")
	}
}

// ==================== Response Format Tests ====================

func TestGRPCSearchResultsFormat(t *testing.T) {
	grpcServer, graphDB, _, _ := setupTestGRPCServer(t)
	client, cleanup := startTestGRPCServer(t, grpcServer)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Index test data
	chunks := []types.Chunk{
		{
			FilePath:   "/test/page1.md",
			Header:     "Test Page",
			Content:    "This is golang content",
			FolderPath: "test",
		},
	}
	if err := graphDB.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("Failed to index chunks: %v", err)
	}

	resp, err := client.Search(ctx, &pb.SearchRequest{
		Keyword: "golang",
		Limit:   10,
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	// Verify JSON format
	var results []map[string]interface{}
	if err := json.Unmarshal([]byte(resp.ResultsJson), &results); err != nil {
		t.Errorf("Results should be valid JSON: %v", err)
	}
}
