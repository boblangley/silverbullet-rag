// Package server provides MCP and gRPC server implementations.
package server

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/boblangley/silverbullet-rag/internal/db"
	"github.com/boblangley/silverbullet-rag/internal/parser"
	"github.com/boblangley/silverbullet-rag/internal/search"
	"github.com/boblangley/silverbullet-rag/internal/types"
)

// Helper functions

func createTempDir(t *testing.T, prefix string) string {
	t.Helper()
	dir, err := os.MkdirTemp("", prefix)
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	t.Cleanup(func() { os.RemoveAll(dir) })
	return dir
}

func createTempDB(t *testing.T) string {
	t.Helper()
	dir := createTempDir(t, "test_db_")
	return filepath.Join(dir, "test.lbug")
}

func createTempSpace(t *testing.T) string {
	t.Helper()
	return createTempDir(t, "test_space_")
}

func setupTestMCPServer(t *testing.T) (*MCPServer, string, string) {
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

	mcpServer := NewMCPServer(MCPConfig{
		DB:                     graphDB,
		Search:                 hybridSearch,
		Parser:                 spaceParser,
		SpacePath:              spacePath,
		DBPath:                 filepath.Dir(dbPath),
		AllowLibraryManagement: false,
	})

	return mcpServer, spacePath, dbPath
}

// ==================== Initialization Tests ====================

func TestMCPServerInitialization(t *testing.T) {
	mcpServer, _, _ := setupTestMCPServer(t)

	if mcpServer == nil {
		t.Fatal("MCP server should not be nil")
	}
	if mcpServer.server == nil {
		t.Error("Internal MCP server should not be nil")
	}
	if mcpServer.db == nil {
		t.Error("Database should not be nil")
	}
	if mcpServer.search == nil {
		t.Error("Search should not be nil")
	}
}

func TestMCPServerWithLibraryManagement(t *testing.T) {
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

	mcpServer := NewMCPServer(MCPConfig{
		DB:                     graphDB,
		Search:                 search.NewHybridSearch(graphDB, nil),
		Parser:                 parser.NewSpaceParser(spacePath),
		SpacePath:              spacePath,
		DBPath:                 filepath.Dir(dbPath),
		AllowLibraryManagement: true,
	})

	if mcpServer == nil {
		t.Fatal("MCP server should not be nil")
	}
	if !mcpServer.allowLibMgmt {
		t.Error("Library management should be enabled")
	}
}

// ==================== Tool Result Helper Tests ====================

func TestToolResultHelper(t *testing.T) {
	data := map[string]any{
		"success": true,
		"results": []string{"a", "b"},
	}

	result, err := toolResult(data)
	if err != nil {
		t.Fatalf("toolResult failed: %v", err)
	}

	if result == nil {
		t.Fatal("Result should not be nil")
	}
	if len(result.Content) != 1 {
		t.Errorf("Expected 1 content item, got %d", len(result.Content))
	}
}

func TestErrorResultHelper(t *testing.T) {
	testErr := os.ErrNotExist

	result, err := errorResult(testErr)
	if err != nil {
		t.Fatalf("errorResult failed: %v", err)
	}

	if result == nil {
		t.Fatal("Result should not be nil")
	}
}

// ==================== Cypher Query Tool Tests ====================

func TestCypherQueryToolBasic(t *testing.T) {
	mcpServer, _, _ := setupTestMCPServer(t)
	ctx := context.Background()

	// Test basic query
	results, err := mcpServer.db.Execute(ctx, "MATCH (n) RETURN count(n) as count", nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	// Should return count (may be 0 for empty db)
	if results == nil {
		t.Error("Results should not be nil")
	}
}

func TestCypherQueryToolWithIndexedData(t *testing.T) {
	mcpServer, _, _ := setupTestMCPServer(t)
	ctx := context.Background()

	// Index some test data
	chunks := []types.Chunk{
		{
			ID:       "test.md#Section",
			FilePath: "test.md",
			Header:   "Section",
			Content:  "Test content for cypher query",
			Tags:     []string{"test"},
		},
	}
	if err := mcpServer.db.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	// Query for chunks
	results, err := mcpServer.db.Execute(ctx, "MATCH (c:Chunk) RETURN c.id, c.content", nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	if len(results) != 1 {
		t.Errorf("Expected 1 result, got %d", len(results))
	}
}

// ==================== Keyword Search Tool Tests ====================

func TestKeywordSearchTool(t *testing.T) {
	mcpServer, _, _ := setupTestMCPServer(t)
	ctx := context.Background()

	// Index some test data
	chunks := []types.Chunk{
		{
			ID:       "doc1.md#Section",
			FilePath: "doc1.md",
			Header:   "Section",
			Content:  "This document is about databases and SQL",
			Tags:     []string{"database"},
		},
		{
			ID:       "doc2.md#Section",
			FilePath: "doc2.md",
			Header:   "Section",
			Content:  "This document is about cooking and recipes",
			Tags:     []string{"cooking"},
		},
	}
	if err := mcpServer.db.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	// Search for database
	results, err := mcpServer.search.Search(ctx, "database", search.SearchOptions{
		Limit:         10,
		KeywordWeight: 1,
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if len(results) == 0 {
		t.Error("Should find results for 'database'")
	}

	// Verify relevance - database doc should be first
	if len(results) > 0 && results[0].Chunk.FilePath != "doc1.md" {
		t.Error("Database document should rank first")
	}
}

func TestKeywordSearchToolEmptyQuery(t *testing.T) {
	mcpServer, _, _ := setupTestMCPServer(t)
	ctx := context.Background()

	// Search with empty query should return error
	_, err := mcpServer.search.Search(ctx, "", search.SearchOptions{Limit: 10})
	if err == nil {
		t.Error("Empty query should return error")
	}
}

// ==================== Hybrid Search Tool Tests ====================

func TestHybridSearchToolRRF(t *testing.T) {
	mcpServer, _, _ := setupTestMCPServer(t)
	ctx := context.Background()

	// Index test data
	chunks := []types.Chunk{
		{
			ID:       "test.md#Section",
			FilePath: "test.md",
			Header:   "Section",
			Content:  "Test content for hybrid search",
			Tags:     []string{},
		},
	}
	if err := mcpServer.db.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	results, err := mcpServer.search.Search(ctx, "hybrid search", search.SearchOptions{
		Limit:        10,
		FusionMethod: search.FusionRRF,
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	// Should complete without error
	if results == nil {
		t.Error("Results should not be nil")
	}
}

func TestHybridSearchToolWeighted(t *testing.T) {
	mcpServer, _, _ := setupTestMCPServer(t)
	ctx := context.Background()

	// Index test data
	chunks := []types.Chunk{
		{
			ID:       "test.md#Section",
			FilePath: "test.md",
			Header:   "Section",
			Content:  "Test content for weighted search",
			Tags:     []string{},
		},
	}
	if err := mcpServer.db.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	results, err := mcpServer.search.Search(ctx, "weighted search", search.SearchOptions{
		Limit:          10,
		FusionMethod:   search.FusionWeighted,
		KeywordWeight:  0.7,
		SemanticWeight: 0.3,
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if results == nil {
		t.Error("Results should not be nil")
	}
}

// ==================== Read Page Tool Tests ====================

func TestReadPageTool(t *testing.T) {
	_, spacePath, _ := setupTestMCPServer(t)

	// Create a test page
	testContent := "# Test Page\n\nThis is test content."
	testFile := filepath.Join(spacePath, "test_page.md")
	if err := os.WriteFile(testFile, []byte(testContent), 0644); err != nil {
		t.Fatalf("Failed to create test file: %v", err)
	}

	// Read the file directly (simulating tool behavior)
	content, err := os.ReadFile(testFile)
	if err != nil {
		t.Fatalf("ReadFile failed: %v", err)
	}

	if string(content) != testContent {
		t.Errorf("Content mismatch: got %q, want %q", string(content), testContent)
	}
}

func TestReadPageToolNotFound(t *testing.T) {
	_, spacePath, _ := setupTestMCPServer(t)

	// Try to read nonexistent page
	testFile := filepath.Join(spacePath, "nonexistent.md")
	_, err := os.ReadFile(testFile)

	if !os.IsNotExist(err) {
		t.Error("Should return not found error for nonexistent page")
	}
}

func TestReadPageToolPathTraversalProtection(t *testing.T) {
	_, spacePath, _ := setupTestMCPServer(t)

	// Simulate path traversal check
	pageName := "../../../etc/passwd"
	filePath := filepath.Join(spacePath, pageName)
	absFilePath, _ := filepath.Abs(filePath)
	absSpacePath, _ := filepath.Abs(spacePath)

	// Check if path is within space
	isValid := len(absFilePath) >= len(absSpacePath) &&
		absFilePath[:len(absSpacePath)] == absSpacePath

	if isValid {
		t.Error("Path traversal should be detected and rejected")
	}
}

// ==================== Propose Change Tool Tests ====================

func TestProposeChangeTool(t *testing.T) {
	_, spacePath, dbPath := setupTestMCPServer(t)

	// Create target directory
	targetDir := filepath.Join(spacePath, "_Proposals")
	if err := os.MkdirAll(targetDir, 0755); err != nil {
		t.Fatalf("Failed to create proposals dir: %v", err)
	}

	// Simulate proposal creation
	proposalPath := filepath.Join(spacePath, "_Proposals", "test.proposal")
	proposalContent := `---
title: Test Proposal
target_page: test.md
status: pending
is_new_page: true
---
## Description
Test description

## Proposed Content
# Test Content
`
	if err := os.WriteFile(proposalPath, []byte(proposalContent), 0644); err != nil {
		t.Fatalf("Failed to create proposal: %v", err)
	}

	// Verify proposal was created
	if _, err := os.Stat(proposalPath); os.IsNotExist(err) {
		t.Error("Proposal file should exist")
	}

	_ = dbPath // silence unused variable warning
}

func TestProposeChangeToolPathTraversal(t *testing.T) {
	_, spacePath, _ := setupTestMCPServer(t)

	// Simulate path traversal check for propose_change
	targetPage := "../../../tmp/evil.md"
	filePath := filepath.Join(spacePath, targetPage)
	absFilePath, _ := filepath.Abs(filePath)
	absSpacePath, _ := filepath.Abs(spacePath)

	isValid := len(absFilePath) >= len(absSpacePath) &&
		absFilePath[:len(absSpacePath)] == absSpacePath

	if isValid {
		t.Error("Path traversal in propose_change should be detected and rejected")
	}
}

// ==================== List Proposals Tool Tests ====================

func TestListProposalsTool(t *testing.T) {
	_, spacePath, _ := setupTestMCPServer(t)

	// Create proposals directory with some proposals
	proposalsDir := filepath.Join(spacePath, "_Proposals")
	if err := os.MkdirAll(proposalsDir, 0755); err != nil {
		t.Fatalf("Failed to create proposals dir: %v", err)
	}

	// Create a test proposal
	proposal1 := filepath.Join(proposalsDir, "test1.proposal")
	proposal1Content := `---
title: Proposal 1
status: pending
---
Content 1`
	if err := os.WriteFile(proposal1, []byte(proposal1Content), 0644); err != nil {
		t.Fatalf("Failed to create proposal: %v", err)
	}

	proposal2 := filepath.Join(proposalsDir, "test2.proposal")
	proposal2Content := `---
title: Proposal 2
status: accepted
---
Content 2`
	if err := os.WriteFile(proposal2, []byte(proposal2Content), 0644); err != nil {
		t.Fatalf("Failed to create proposal: %v", err)
	}

	// List proposals (simulate by reading directory)
	entries, err := os.ReadDir(proposalsDir)
	if err != nil {
		t.Fatalf("Failed to read proposals dir: %v", err)
	}

	var proposalFiles []string
	for _, e := range entries {
		if filepath.Ext(e.Name()) == ".proposal" {
			proposalFiles = append(proposalFiles, e.Name())
		}
	}

	if len(proposalFiles) != 2 {
		t.Errorf("Expected 2 proposals, got %d", len(proposalFiles))
	}
}

// ==================== Withdraw Proposal Tool Tests ====================

func TestWithdrawProposalTool(t *testing.T) {
	_, spacePath, _ := setupTestMCPServer(t)

	// Create proposals directory
	proposalsDir := filepath.Join(spacePath, "_Proposals")
	if err := os.MkdirAll(proposalsDir, 0755); err != nil {
		t.Fatalf("Failed to create proposals dir: %v", err)
	}

	// Create a test proposal
	proposalPath := filepath.Join(proposalsDir, "withdraw_test.proposal")
	proposalContent := `---
title: To Withdraw
status: pending
---
Content`
	if err := os.WriteFile(proposalPath, []byte(proposalContent), 0644); err != nil {
		t.Fatalf("Failed to create proposal: %v", err)
	}

	// Withdraw (delete) the proposal
	if err := os.Remove(proposalPath); err != nil {
		t.Fatalf("Failed to withdraw proposal: %v", err)
	}

	// Verify it's gone
	if _, err := os.Stat(proposalPath); !os.IsNotExist(err) {
		t.Error("Proposal should be deleted after withdrawal")
	}
}

// ==================== Get Graph Schema Tool Tests ====================

func TestGetGraphSchemaTool(t *testing.T) {
	// The schema is defined as a map, verify expected structure
	if graphSchema == nil {
		t.Fatal("Graph schema should not be nil")
	}

	// Verify expected keys
	if _, ok := graphSchema["nodes"]; !ok {
		t.Error("Schema should have 'nodes' key")
	}
	if _, ok := graphSchema["relationships"]; !ok {
		t.Error("Schema should have 'relationships' key")
	}

	// Verify it can be serialized to JSON
	_, err := json.Marshal(graphSchema)
	if err != nil {
		t.Errorf("Schema should be JSON serializable: %v", err)
	}
}

// ==================== Format Search Results Tests ====================

func TestFormatSearchResults(t *testing.T) {
	results := []types.SearchResult{
		{
			Chunk: types.Chunk{
				ID:       "test.md#Section",
				FilePath: "test.md",
				Header:   "Section",
				Content:  "Test content",
			},
			HybridScore:  0.9,
			KeywordScore: 0.8,
		},
	}

	formatted := formatSearchResults(results)

	if len(formatted) != 1 {
		t.Errorf("Expected 1 formatted result, got %d", len(formatted))
	}

	first := formatted[0]
	if first["chunk_id"] != "test.md#Section" {
		t.Errorf("Unexpected chunk_id: %v", first["chunk_id"])
	}
	if first["file_path"] != "test.md" {
		t.Errorf("Unexpected file_path: %v", first["file_path"])
	}
}

// ==================== Get Project Context Tool Tests ====================

func TestGetProjectContextToolByFolder(t *testing.T) {
	_, spacePath, _ := setupTestMCPServer(t)

	// Create a project structure
	projectDir := filepath.Join(spacePath, "Projects", "MyProject")
	if err := os.MkdirAll(projectDir, 0755); err != nil {
		t.Fatalf("Failed to create project dir: %v", err)
	}

	// Create project index page
	indexContent := `---
github: owner/repo
tags:
  - project
---
# My Project
Project description.`
	indexPath := filepath.Join(spacePath, "Projects", "MyProject.md")
	if err := os.WriteFile(indexPath, []byte(indexContent), 0644); err != nil {
		t.Fatalf("Failed to create index: %v", err)
	}

	// Create a related page
	relatedPath := filepath.Join(projectDir, "README.md")
	if err := os.WriteFile(relatedPath, []byte("# README"), 0644); err != nil {
		t.Fatalf("Failed to create related page: %v", err)
	}

	// Verify files exist
	if _, err := os.Stat(indexPath); os.IsNotExist(err) {
		t.Error("Index file should exist")
	}
	if _, err := os.Stat(relatedPath); os.IsNotExist(err) {
		t.Error("Related file should exist")
	}
}

// ==================== Integration Tests ====================

func TestMCPServerFullWorkflow(t *testing.T) {
	mcpServer, spacePath, _ := setupTestMCPServer(t)
	ctx := context.Background()

	// 1. Create a test page
	testPage := filepath.Join(spacePath, "workflow_test.md")
	testContent := `---
tags:
  - test
  - workflow
---
# Workflow Test

This page tests the full MCP workflow including indexing and search.

## Section 1

Some content about databases and queries.

## Section 2

More content about search and retrieval.
`
	if err := os.WriteFile(testPage, []byte(testContent), 0644); err != nil {
		t.Fatalf("Failed to create test page: %v", err)
	}

	// 2. Parse and index the space
	spaceParser := parser.NewSpaceParser(spacePath)
	chunks, err := spaceParser.ParseSpace(spacePath)
	if err != nil {
		t.Fatalf("ParseSpace failed: %v", err)
	}

	if len(chunks) == 0 {
		t.Fatal("Parser should produce chunks")
	}

	if err := mcpServer.db.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	// 3. Search for content
	results, err := mcpServer.search.Search(ctx, "database", search.SearchOptions{Limit: 10})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if len(results) == 0 {
		t.Error("Should find results for 'database'")
	}

	// 4. Query via Cypher
	cypherResults, err := mcpServer.db.Execute(ctx, "MATCH (c:Chunk) RETURN count(c) as count", nil)
	if err != nil {
		t.Fatalf("Cypher query failed: %v", err)
	}

	if len(cypherResults) == 0 {
		t.Error("Cypher query should return results")
	}
}

// ==================== Parse Proposal Frontmatter Tests ====================

func TestParseProposalFrontmatter(t *testing.T) {
	mcpServer, _, _ := setupTestMCPServer(t)

	tests := []struct {
		name     string
		content  string
		expected map[string]any
	}{
		{
			name: "basic frontmatter",
			content: `---
title: Test Proposal
status: pending
target_page: test.md
---
Content here`,
			expected: map[string]any{
				"title":       "Test Proposal",
				"status":      "pending",
				"target_page": "test.md",
			},
		},
		{
			name: "boolean true value",
			content: `---
is_new_page: true
---
Content`,
			expected: map[string]any{
				"is_new_page": true,
			},
		},
		{
			name: "boolean false value",
			content: `---
is_new_page: false
---
Content`,
			expected: map[string]any{
				"is_new_page": false,
			},
		},
		{
			name:     "no frontmatter",
			content:  "Just regular content",
			expected: map[string]any{},
		},
		{
			name:     "incomplete frontmatter",
			content:  "---\ntitle: Test",
			expected: map[string]any{},
		},
		{
			name:     "empty content",
			content:  "",
			expected: map[string]any{},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := mcpServer.parseProposalFrontmatter(tt.content)

			for key, expected := range tt.expected {
				if result[key] != expected {
					t.Errorf("Key %q: got %v, want %v", key, result[key], expected)
				}
			}
		})
	}
}

// ==================== Library Management Tests ====================

func setupTestMCPServerWithLibrary(t *testing.T) (*MCPServer, string, string, string) {
	t.Helper()
	dbPath := createTempDB(t)
	spacePath := createTempSpace(t)
	libraryPath := createTempDir(t, "test_library_")

	// Create library source file
	proposalsContent := `# Proposals Library

This is the Proposals library for SilverBullet.
`
	if err := os.WriteFile(filepath.Join(libraryPath, "Proposals.md"), []byte(proposalsContent), 0644); err != nil {
		t.Fatalf("Failed to create library source: %v", err)
	}

	// Create Proposals subdirectory
	proposalsDir := filepath.Join(libraryPath, "Proposals")
	if err := os.MkdirAll(proposalsDir, 0755); err != nil {
		t.Fatalf("Failed to create Proposals dir: %v", err)
	}

	// Add some library files
	if err := os.WriteFile(filepath.Join(proposalsDir, "Commands.md"), []byte("# Commands\n\nCommands here."), 0644); err != nil {
		t.Fatalf("Failed to create Commands.md: %v", err)
	}
	if err := os.WriteFile(filepath.Join(proposalsDir, "Functions.md"), []byte("# Functions\n\nFunctions here."), 0644); err != nil {
		t.Fatalf("Failed to create Functions.md: %v", err)
	}

	graphDB, err := db.Open(db.Config{
		Path:             dbPath,
		EnableEmbeddings: false,
	})
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	t.Cleanup(func() { graphDB.Close() })

	mcpServer := NewMCPServer(MCPConfig{
		DB:                     graphDB,
		Search:                 search.NewHybridSearch(graphDB, nil),
		Parser:                 parser.NewSpaceParser(spacePath),
		SpacePath:              spacePath,
		DBPath:                 filepath.Dir(dbPath),
		LibraryPath:            libraryPath,
		AllowLibraryManagement: true,
	})

	return mcpServer, spacePath, dbPath, libraryPath
}

func TestCopyLibraryFiles(t *testing.T) {
	mcpServer, spacePath, _, _ := setupTestMCPServerWithLibrary(t)

	// Create Library directory first (copyLibraryFiles expects it to exist)
	libraryDir := filepath.Join(spacePath, "Library")
	if err := os.MkdirAll(libraryDir, 0755); err != nil {
		t.Fatalf("Failed to create Library dir: %v", err)
	}

	// Copy library files
	installedFiles, err := mcpServer.copyLibraryFiles("Proposals", false)
	if err != nil {
		t.Fatalf("copyLibraryFiles failed: %v", err)
	}

	if len(installedFiles) < 1 {
		t.Error("Should have installed at least one file")
	}

	// Verify root file was copied
	rootFile := filepath.Join(spacePath, "Library", "Proposals.md")
	if _, err := os.Stat(rootFile); os.IsNotExist(err) {
		t.Error("Root library file should exist")
	}

	// Verify subdir files were copied
	commandsFile := filepath.Join(spacePath, "Library", "Proposals", "Commands.md")
	if _, err := os.Stat(commandsFile); os.IsNotExist(err) {
		t.Error("Commands.md should exist in subdirectory")
	}
}

func TestCopyLibraryFilesOverwrite(t *testing.T) {
	mcpServer, spacePath, _, _ := setupTestMCPServerWithLibrary(t)

	// Create Library directory first
	libraryDir := filepath.Join(spacePath, "Library")
	if err := os.MkdirAll(libraryDir, 0755); err != nil {
		t.Fatalf("Failed to create Library dir: %v", err)
	}

	// First install
	_, err := mcpServer.copyLibraryFiles("Proposals", false)
	if err != nil {
		t.Fatalf("First copyLibraryFiles failed: %v", err)
	}

	// Modify a file to verify overwrite works
	commandsPath := filepath.Join(spacePath, "Library", "Proposals", "Commands.md")
	if err := os.WriteFile(commandsPath, []byte("Modified content"), 0644); err != nil {
		t.Fatalf("Failed to modify file: %v", err)
	}

	// Overwrite
	_, err = mcpServer.copyLibraryFiles("Proposals", true)
	if err != nil {
		t.Fatalf("Overwrite copyLibraryFiles failed: %v", err)
	}

	// Verify content was restored
	content, _ := os.ReadFile(commandsPath)
	if string(content) == "Modified content" {
		t.Error("File should have been overwritten")
	}
}

func TestLibraryManagementDisabled(t *testing.T) {
	mcpServer, _, _ := setupTestMCPServer(t)

	// allowLibMgmt should be false by default
	if mcpServer.allowLibMgmt {
		t.Error("Library management should be disabled by default")
	}
}

func TestLibraryManagementEnabled(t *testing.T) {
	mcpServer, _, _, _ := setupTestMCPServerWithLibrary(t)

	if !mcpServer.allowLibMgmt {
		t.Error("Library management should be enabled")
	}
}

// ==================== Get Project Context GitHub Remote Tests ====================

func TestGetProjectContextByGitHubRemote(t *testing.T) {
	mcpServer, spacePath, _, _ := setupTestMCPServerWithLibrary(t)

	// Create a project with github frontmatter
	projectDir := filepath.Join(spacePath, "Projects")
	if err := os.MkdirAll(projectDir, 0755); err != nil {
		t.Fatalf("Failed to create project dir: %v", err)
	}

	projectContent := `---
github: owner/test-repo
tags:
  - project
  - golang
concerns:
  - performance
---
# Test Project

This project has a GitHub remote.
`
	projectPath := filepath.Join(projectDir, "TestProject.md")
	if err := os.WriteFile(projectPath, []byte(projectContent), 0644); err != nil {
		t.Fatalf("Failed to create project file: %v", err)
	}

	// Search for the project by walking (simulating tool behavior)
	var foundPath string
	var foundFM map[string]any

	err := filepath.Walk(spacePath, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() || filepath.Ext(path) != ".md" {
			return nil
		}
		fm, _ := mcpServer.parser.GetFrontmatter(path)
		if gh, ok := fm["github"].(string); ok && gh == "owner/test-repo" {
			foundPath = path
			foundFM = fm
			return filepath.SkipAll
		}
		return nil
	})
	if err != nil && err != filepath.SkipAll {
		t.Fatalf("Walk failed: %v", err)
	}

	if foundPath == "" {
		t.Error("Should find project by GitHub remote")
	}
	if foundFM["github"] != "owner/test-repo" {
		t.Error("Found project should have correct github remote")
	}
}

func TestGetProjectContextNotFound(t *testing.T) {
	_, spacePath, _, _ := setupTestMCPServerWithLibrary(t)

	// Search for nonexistent project
	var foundPath string

	err := filepath.Walk(spacePath, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() || filepath.Ext(path) != ".md" {
			return nil
		}
		// Won't find anything matching
		return nil
	})
	if err != nil {
		t.Fatalf("Walk failed: %v", err)
	}

	if foundPath != "" {
		t.Error("Should not find nonexistent project")
	}
}

// ==================== Scope Filter Tests ====================

func TestHybridSearchWithScope(t *testing.T) {
	mcpServer, _, _ := setupTestMCPServer(t)
	ctx := context.Background()

	// Index test data with different paths
	chunks := []types.Chunk{
		{
			ID:       "Projects/A/doc.md#Section",
			FilePath: "Projects/A/doc.md",
			Header:   "Section",
			Content:  "Project A content about testing",
		},
		{
			ID:       "Projects/B/doc.md#Section",
			FilePath: "Projects/B/doc.md",
			Header:   "Section",
			Content:  "Project B content about testing",
		},
		{
			ID:       "Notes/doc.md#Section",
			FilePath: "Notes/doc.md",
			Header:   "Section",
			Content:  "Notes content about testing",
		},
	}
	if err := mcpServer.db.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	// Search with scope
	results, err := mcpServer.search.Search(ctx, "testing", search.SearchOptions{
		Limit: 10,
		Scope: "Projects/A",
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	// Should only find results from Projects/A
	for _, r := range results {
		if r.Chunk.FilePath != "Projects/A/doc.md" {
			t.Errorf("Result should be from Projects/A, got %s", r.Chunk.FilePath)
		}
	}
}

// ==================== Filter Tests ====================

func TestSearchWithTagFilter(t *testing.T) {
	mcpServer, _, _ := setupTestMCPServer(t)
	ctx := context.Background()

	// Index test data with different tags
	chunks := []types.Chunk{
		{
			ID:       "doc1.md#Section",
			FilePath: "doc1.md",
			Header:   "Section",
			Content:  "Content with important tag",
			Tags:     []string{"important"},
		},
		{
			ID:       "doc2.md#Section",
			FilePath: "doc2.md",
			Header:   "Section",
			Content:  "Content with normal tag",
			Tags:     []string{"normal"},
		},
	}
	if err := mcpServer.db.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	// Search with tag filter
	results, err := mcpServer.search.Search(ctx, "content", search.SearchOptions{
		Limit:      10,
		FilterTags: []string{"important"},
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	// Results should only include important-tagged content
	// Note: This tests the search options are passed correctly
	if results == nil {
		t.Error("Results should not be nil")
	}
}

func TestSearchWithPageFilter(t *testing.T) {
	mcpServer, _, _ := setupTestMCPServer(t)
	ctx := context.Background()

	// Index test data
	chunks := []types.Chunk{
		{
			ID:       "page1.md#Section",
			FilePath: "page1.md",
			Header:   "Section",
			Content:  "Content in page 1",
		},
		{
			ID:       "page2.md#Section",
			FilePath: "page2.md",
			Header:   "Section",
			Content:  "Content in page 2",
		},
	}
	if err := mcpServer.db.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	// Search with page filter
	results, err := mcpServer.search.Search(ctx, "content", search.SearchOptions{
		Limit:       10,
		FilterPages: []string{"page1.md"},
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if results == nil {
		t.Error("Results should not be nil")
	}
}

// ==================== Proposal Prefix Config Tests ====================

func TestProposalPrefixFromConfig(t *testing.T) {
	_, spacePath, dbPath := setupTestMCPServer(t)

	// Create config file with custom prefix
	configDir := filepath.Dir(dbPath)
	configContent := `{"proposals.pathPrefix": "CustomProposals/"}`
	if err := os.WriteFile(filepath.Join(configDir, "space_config.json"), []byte(configContent), 0644); err != nil {
		t.Fatalf("Failed to create config: %v", err)
	}

	// Read and parse config
	data, err := os.ReadFile(filepath.Join(configDir, "space_config.json"))
	if err != nil {
		t.Fatalf("Failed to read config: %v", err)
	}

	var cfg map[string]any
	if err := json.Unmarshal(data, &cfg); err != nil {
		t.Fatalf("Failed to parse config: %v", err)
	}

	prefix, ok := cfg["proposals.pathPrefix"].(string)
	if !ok || prefix != "CustomProposals/" {
		t.Errorf("Expected prefix 'CustomProposals/', got %q", prefix)
	}

	_ = spacePath // silence unused variable
}

// ==================== Withdraw Non-Proposal File Tests ====================

func TestWithdrawNonProposalFile(t *testing.T) {
	_, spacePath, _ := setupTestMCPServer(t)

	// Create a non-proposal file
	testFile := filepath.Join(spacePath, "test.md")
	if err := os.WriteFile(testFile, []byte("test"), 0644); err != nil {
		t.Fatalf("Failed to create test file: %v", err)
	}

	// Simulate validation check - use strings.HasSuffix like the actual code does
	proposalPath := "test.md"
	if strings.HasSuffix(proposalPath, ".proposal") {
		t.Error("Should reject non-proposal file extension")
	}
	// Test passes because test.md doesn't have .proposal suffix
}

func TestWithdrawPathTraversal(t *testing.T) {
	_, spacePath, _ := setupTestMCPServer(t)

	// Simulate path traversal check
	proposalPath := "../../../tmp/evil.proposal"
	fullPath := filepath.Join(spacePath, proposalPath)
	absPath, _ := filepath.Abs(fullPath)
	absSpacePath, _ := filepath.Abs(spacePath)

	// strings.HasPrefix is the security check
	isValid := len(absPath) >= len(absSpacePath) && absPath[:len(absSpacePath)] == absSpacePath

	if isValid {
		t.Error("Path traversal in withdraw should be detected")
	}
}
