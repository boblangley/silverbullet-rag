// Package db provides graph database operations using LadybugDB.
package db

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/boblangley/silverbullet-rag/internal/types"
)

// Helper function to create a temp db directory
func createTempDB(t *testing.T) string {
	t.Helper()
	dir, err := os.MkdirTemp("", "test_db_")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	t.Cleanup(func() { os.RemoveAll(dir) })
	return filepath.Join(dir, "test.lbug")
}

// Helper to open a test database
func openTestDB(t *testing.T, enableEmbeddings bool) *GraphDB {
	t.Helper()
	dbPath := createTempDB(t)
	db, err := Open(Config{
		Path:             dbPath,
		EnableEmbeddings: enableEmbeddings,
	})
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}

// ==================== Initialization Tests ====================

func TestGraphDBInitialization(t *testing.T) {
	db := openTestDB(t, false)
	if db == nil {
		t.Fatal("GraphDB should not be nil")
	}
}

func TestGraphDBInitializationWithoutEmbeddings(t *testing.T) {
	db := openTestDB(t, false)
	if db.EnableEmbeddings() {
		t.Error("enableEmbeddings should be false")
	}
}

func TestGraphDBInitializationWithEmbeddings(t *testing.T) {
	db := openTestDB(t, true)
	if !db.EnableEmbeddings() {
		t.Error("enableEmbeddings should be true")
	}
}

// ==================== Index Chunks Tests ====================

func TestIndexChunksBasic(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	chunks := []types.Chunk{
		{
			ID:       "test.md#Section",
			FilePath: "test.md",
			Header:   "Section",
			Content:  "Test content",
			Links:    []string{"link1"},
			Tags:     []string{"tag1"},
		},
	}

	err := db.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	// Verify chunk was created
	results, err := db.Execute(ctx, "MATCH (c:Chunk) RETURN c.id as id", nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}
	if len(results) != 1 {
		t.Errorf("Expected 1 chunk, got %d", len(results))
	}
}

func TestIndexChunksMultiple(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	chunks := []types.Chunk{
		{
			ID:       "test1.md#Section1",
			FilePath: "test1.md",
			Header:   "Section 1",
			Content:  "Content 1",
			Links:    []string{},
			Tags:     []string{"tag1"},
		},
		{
			ID:       "test2.md#Section2",
			FilePath: "test2.md",
			Header:   "Section 2",
			Content:  "Content 2",
			Links:    []string{},
			Tags:     []string{"tag2"},
		},
	}

	err := db.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	// Verify chunks were created
	results, err := db.Execute(ctx, "MATCH (c:Chunk) RETURN c.id as id", nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}
	if len(results) != 2 {
		t.Errorf("Expected 2 chunks, got %d", len(results))
	}
}

// ==================== Cypher Query Tests ====================

func TestCypherQueryBasic(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	// Index some data first
	chunks := []types.Chunk{
		{
			ID:       "test.md#Section",
			FilePath: "test.md",
			Header:   "Section",
			Content:  "Test content",
			Links:    []string{},
			Tags:     []string{},
		},
	}
	err := db.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	// Query for the chunk
	results, err := db.Execute(ctx, "MATCH (c:Chunk) RETURN c.id as id", nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	if len(results) == 0 {
		t.Error("Expected at least one result")
	}
}

func TestCypherQueryWithParams(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	// Index data
	chunks := []types.Chunk{
		{
			ID:       "test.md#Section",
			FilePath: "test.md",
			Header:   "Section",
			Content:  "Test content with keyword",
			Links:    []string{},
			Tags:     []string{},
		},
	}
	db.IndexChunks(ctx, chunks)

	// Query with parameters
	results, err := db.Execute(ctx, "MATCH (c:Chunk) WHERE c.content CONTAINS $keyword RETURN c.id", map[string]any{"keyword": "keyword"})
	if err != nil {
		t.Fatalf("Query with params failed: %v", err)
	}

	if len(results) != 1 {
		t.Errorf("Expected 1 result, got %d", len(results))
	}
}

// ==================== Page Relationships Tests ====================

func TestPageNodeCreatedForSourceFile(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	chunks := []types.Chunk{
		{
			ID:       "multi_section.md#Section1",
			FilePath: "multi_section.md",
			Header:   "Section 1",
			Content:  "First section content",
			Tags:     []string{},
		},
		{
			ID:       "multi_section.md#Section2",
			FilePath: "multi_section.md",
			Header:   "Section 2",
			Content:  "Second section content",
			Tags:     []string{},
		},
	}

	err := db.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	// Check that Page node exists
	results, err := db.Execute(ctx, "MATCH (p:Page {name: 'multi_section'}) RETURN p.name as name", nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	if len(results) != 1 {
		t.Errorf("Expected 1 Page node, got %d", len(results))
	}
}

func TestHasChunkRelationshipExists(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	chunks := []types.Chunk{
		{
			ID:       "page.md#Section1",
			FilePath: "page.md",
			Header:   "Section 1",
			Content:  "Content 1",
			Tags:     []string{},
		},
		{
			ID:       "page.md#Section2",
			FilePath: "page.md",
			Header:   "Section 2",
			Content:  "Content 2",
			Tags:     []string{},
		},
	}

	err := db.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	// Check HAS_CHUNK relationships
	results, err := db.Execute(ctx, `
		MATCH (p:Page {name: 'page'})-[r:HAS_CHUNK]->(c:Chunk)
		RETURN count(r) as count
	`, nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	if len(results) == 0 {
		t.Fatal("Expected results")
	}

	count, ok := results[0]["count"].(int64)
	if !ok {
		if countF, ok := results[0]["count"].(float64); ok {
			count = int64(countF)
		}
	}
	if count == 0 {
		t.Error("Should have HAS_CHUNK relationships")
	}
}

func TestPageLinksToRelationship(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	chunks := []types.Chunk{
		{
			ID:       "page_a.md#Main",
			FilePath: "page_a.md",
			Header:   "Main",
			Content:  "Links to page_b and page_c",
			Links:    []string{"page_b", "page_c"},
			Tags:     []string{},
		},
		{
			ID:       "page_b.md#Main",
			FilePath: "page_b.md",
			Header:   "Main",
			Content:  "Links back to page_a",
			Links:    []string{"page_a"},
			Tags:     []string{},
		},
		{
			ID:       "page_c.md#Main",
			FilePath: "page_c.md",
			Header:   "Main",
			Content:  "No outgoing links",
			Links:    []string{},
			Tags:     []string{},
		},
	}

	err := db.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	// Check PAGE_LINKS_TO relationship
	results, err := db.Execute(ctx, `
		MATCH (source:Page {name: 'page_a'})-[:PAGE_LINKS_TO]->(target:Page {name: 'page_b'})
		RETURN count(*) as count
	`, nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	if len(results) == 0 {
		t.Fatal("Expected results")
	}

	count, ok := results[0]["count"].(int64)
	if !ok {
		if countF, ok := results[0]["count"].(float64); ok {
			count = int64(countF)
		}
	}
	if count != 1 {
		t.Errorf("page_a should link to page_b, got count %d", count)
	}
}

// ==================== Folder Hierarchy Tests ====================

func TestInitSchemaCreatesFolderTable(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	// Query for Folder nodes should not raise an error
	results, err := db.Execute(ctx, "MATCH (f:Folder) RETURN f LIMIT 1", nil)
	if err != nil {
		t.Fatalf("Folder query should not fail: %v", err)
	}

	// Should return empty list (no folders yet), not an error
	if results == nil {
		t.Error("Results should not be nil")
	}
}

func TestIndexFoldersCreatesHierarchy(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	folderPaths := []string{
		"Projects",
		"Projects/Topic",
		"Projects/Topic/Silverbullet-RAG",
		"Area/Health",
	}

	err := db.IndexFolders(ctx, folderPaths, nil)
	if err != nil {
		t.Fatalf("IndexFolders failed: %v", err)
	}

	// Verify folder nodes were created
	results, err := db.Execute(ctx, "MATCH (f:Folder) RETURN f.path ORDER BY f.path", nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	paths := make([]string, 0)
	for _, r := range results {
		if path, ok := r["f.path"].(string); ok {
			paths = append(paths, path)
		}
	}

	expectedPaths := []string{"Area", "Area/Health", "Projects", "Projects/Topic", "Projects/Topic/Silverbullet-RAG"}
	for _, expected := range expectedPaths {
		found := false
		for _, p := range paths {
			if p == expected {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("Expected folder '%s' not found in %v", expected, paths)
		}
	}
}

func TestIndexFoldersCreatesContainsRelationships(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	err := db.IndexFolders(ctx, []string{"Projects", "Projects/Topic"}, nil)
	if err != nil {
		t.Fatalf("IndexFolders failed: %v", err)
	}

	results, err := db.Execute(ctx, `
		MATCH (parent:Folder {name: 'Projects'})-[:CONTAINS]->(child:Folder {name: 'Topic'})
		RETURN parent.path, child.path
	`, nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	if len(results) != 1 {
		t.Errorf("Expected 1 CONTAINS relationship, got %d", len(results))
	}
}

// ==================== Security Tests ====================

func TestCypherQueryWithInjectionAttempt(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	// Index some data
	chunks := []types.Chunk{
		{
			ID:       "public.md#Public",
			FilePath: "public.md",
			Header:   "Public",
			Content:  "Public content",
			Tags:     []string{"public"},
		},
		{
			ID:       "private.md#Private",
			FilePath: "private.md",
			Header:   "Private",
			Content:  "Private content",
			Tags:     []string{"private"},
		},
	}
	db.IndexChunks(ctx, chunks)

	// Using parameterized queries should be safe
	maliciousInput := "' OR 1=1 --"
	results, err := db.Execute(ctx, "MATCH (c:Chunk) WHERE c.content CONTAINS $keyword RETURN c", map[string]any{"keyword": maliciousInput})
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	// Should return 0 results (no match) since we're searching for the literal string
	if len(results) > 1 {
		t.Errorf("Injection may have succeeded - got %d results", len(results))
	}
}

func TestQueryWithQuotes(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	// Index some data
	chunks := []types.Chunk{
		{
			ID:       "test.md#Section",
			FilePath: "test.md",
			Header:   "Section",
			Content:  "Test content",
			Tags:     []string{},
		},
	}
	db.IndexChunks(ctx, chunks)

	// Search terms with quotes - parameterized queries should handle them
	inputs := []string{
		"test'quote",
		`test"doublequote`,
		"test\\'escaped",
		`test\"escaped`,
	}

	for _, searchTerm := range inputs {
		results, err := db.Execute(ctx, "MATCH (c:Chunk) WHERE c.content CONTAINS $keyword RETURN c", map[string]any{"keyword": searchTerm})
		if err != nil {
			t.Errorf("Query failed on input '%s': %v", searchTerm, err)
			continue
		}
		// Should complete without error (even if 0 results)
		if results == nil {
			t.Errorf("Results should not be nil for '%s'", searchTerm)
		}
	}
}

func TestQueryWithUnicode(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	unicodeTerms := []string{
		"日本語",
		"émojis",
		"Ñoño",
		"🔥 fire",
	}

	for _, term := range unicodeTerms {
		results, err := db.Execute(ctx, "MATCH (c:Chunk) WHERE c.content CONTAINS $keyword RETURN c", map[string]any{"keyword": term})
		if err != nil {
			t.Errorf("Unicode query failed for '%s': %v", term, err)
			continue
		}
		if results == nil {
			t.Errorf("Results should not be nil for '%s'", term)
		}
	}
}

// ==================== Delete Tests ====================

func TestDeleteChunksByFile(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	chunks := []types.Chunk{
		{
			ID:       "keep.md#Section",
			FilePath: "keep.md",
			Header:   "Section",
			Content:  "Keep this",
			Tags:     []string{},
		},
		{
			ID:       "delete.md#Section",
			FilePath: "delete.md",
			Header:   "Section",
			Content:  "Delete this",
			Tags:     []string{},
		},
	}

	db.IndexChunks(ctx, chunks)

	// Delete chunks from delete.md
	err := db.DeleteChunksByFile(ctx, "delete.md")
	if err != nil {
		t.Fatalf("DeleteChunksByFile failed: %v", err)
	}

	// Verify only keep.md chunks remain
	results, err := db.Execute(ctx, "MATCH (c:Chunk) RETURN c.file_path as path", nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	for _, r := range results {
		if path, ok := r["path"].(string); ok {
			if path == "delete.md" {
				t.Error("delete.md chunks should have been deleted")
			}
		}
	}
}

func TestClearDatabase(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	chunks := []types.Chunk{
		{
			ID:       "test.md#Section",
			FilePath: "test.md",
			Header:   "Section",
			Content:  "Content",
			Tags:     []string{"tag"},
		},
	}

	db.IndexChunks(ctx, chunks)

	// Clear database
	err := db.ClearDatabase(ctx)
	if err != nil {
		t.Fatalf("ClearDatabase failed: %v", err)
	}

	// Verify all chunks are gone
	results, err := db.Execute(ctx, "MATCH (c:Chunk) RETURN count(c) as count", nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	if len(results) > 0 {
		count, _ := results[0]["count"].(int64)
		if count != 0 {
			t.Errorf("Expected 0 chunks after clear, got %d", count)
		}
	}
}

// ==================== Tag Tests ====================

func TestTaggedRelationshipCreated(t *testing.T) {
	db := openTestDB(t, false)
	ctx := context.Background()

	chunks := []types.Chunk{
		{
			ID:       "test.md#Section",
			FilePath: "test.md",
			Header:   "Section",
			Content:  "Content",
			Tags:     []string{"tag1", "tag2"},
		},
	}

	db.IndexChunks(ctx, chunks)

	// Check TAGGED relationships
	results, err := db.Execute(ctx, `
		MATCH (c:Chunk {id: 'test.md#Section'})-[:TAGGED]->(t:Tag)
		RETURN t.name as tag
	`, nil)
	if err != nil {
		t.Fatalf("Query failed: %v", err)
	}

	if len(results) != 2 {
		t.Errorf("Expected 2 tags, got %d", len(results))
	}

	tags := make(map[string]bool)
	for _, r := range results {
		if tag, ok := r["tag"].(string); ok {
			tags[tag] = true
		}
	}

	if !tags["tag1"] || !tags["tag2"] {
		t.Errorf("Missing expected tags: %v", tags)
	}
}
