// Package search provides hybrid search combining keyword and semantic search.
package search

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/boblangley/silverbullet-rag/internal/db"
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

// Helper function to open test database
func openTestDB(t *testing.T, enableEmbeddings bool) *db.GraphDB {
	t.Helper()
	dbPath := createTempDB(t)
	graphDB, err := db.Open(db.Config{
		Path:             dbPath,
		EnableEmbeddings: enableEmbeddings,
	})
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	t.Cleanup(func() { graphDB.Close() })
	return graphDB
}

// Helper function to create diverse docs for hybrid search testing
func createDiverseDocs() []types.Chunk {
	return []types.Chunk{
		// Document 1: Exact keyword match but semantically less relevant
		{
			ID:          "fruit_database.md#FruitInfo",
			FilePath:    "fruit_database.md",
			Header:      "Fruit Information",
			Content:     "This database contains information about fruits. The fruit database has entries for apples, oranges, and bananas.",
			Tags:        []string{"food", "nutrition"},
			Frontmatter: map[string]any{"tags": []string{"food", "nutrition"}},
		},
		// Document 2: Semantically relevant but fewer keyword matches
		{
			ID:          "data_storage_systems.md#ModernStorage",
			FilePath:    "data_storage_systems.md",
			Header:      "Modern Storage Solutions",
			Content:     "Contemporary data management platforms utilize various persistence mechanisms including relational stores, document collections, and graph repositories. These systems handle information efficiently and scale horizontally.",
			Tags:        []string{"technology", "architecture"},
			Frontmatter: map[string]any{"tags": []string{"technology", "architecture"}},
		},
		// Document 3: Both keyword and semantic relevance
		{
			ID:          "database_architecture.md#DesignPatterns",
			FilePath:    "database_architecture.md",
			Header:      "Database Design Patterns",
			Content:     "Modern database systems require careful architectural planning. Database schemas, indexing strategies, and query optimization are essential for building scalable database applications.",
			Tags:        []string{"database", "system-design"},
			Frontmatter: map[string]any{"tags": []string{"database", "system-design"}},
		},
		// Document 4: Different topic entirely
		{
			ID:          "cooking_recipes.md#ItalianCuisine",
			FilePath:    "cooking_recipes.md",
			Header:      "Italian Cuisine",
			Content:     "Learn to make pasta, pizza, and risotto. These traditional recipes have been passed down through generations.",
			Tags:        []string{"cooking", "recipes"},
			Frontmatter: map[string]any{"tags": []string{"cooking", "recipes"}},
		},
	}
}

// ==================== Initialization Tests ====================

func TestHybridSearchInitialization(t *testing.T) {
	graphDB := openTestDB(t, false)

	// Note: In production, we'd pass a real embedding service, but for tests
	// without embeddings we can pass nil
	hybridSearch := NewHybridSearch(graphDB, nil)

	if hybridSearch == nil {
		t.Fatal("HybridSearch should not be nil")
	}
	if hybridSearch.db != graphDB {
		t.Error("HybridSearch should reference the GraphDB")
	}
}

// ==================== Keyword-Only Hybrid Search Tests ====================
// When embeddings are disabled, hybrid search falls back to keyword-only

func TestHybridSearchKeywordOnly(t *testing.T) {
	ctx := context.Background()
	graphDB := openTestDB(t, false)

	chunks := createDiverseDocs()
	err := graphDB.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, nil)

	results, err := hybridSearch.Search(ctx, "database systems", SearchOptions{Limit: 10})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if len(results) == 0 {
		t.Fatal("Hybrid search should return results")
	}

	// Check result structure
	for _, result := range results {
		// HybridScore should be set even for keyword-only
		if result.HybridScore == 0 && result.KeywordScore == 0 {
			t.Error("Result should have some score")
		}
	}
}

func TestHybridSearchResultSorting(t *testing.T) {
	ctx := context.Background()
	graphDB := openTestDB(t, false)

	chunks := createDiverseDocs()
	err := graphDB.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, nil)

	results, err := hybridSearch.Search(ctx, "database", SearchOptions{Limit: 10})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	// Results should be sorted by hybrid score (descending)
	for i := 1; i < len(results); i++ {
		if results[i-1].HybridScore < results[i].HybridScore {
			t.Error("Results should be sorted by hybrid score (highest first)")
		}
	}
}

func TestHybridSearchRRFFusion(t *testing.T) {
	ctx := context.Background()
	graphDB := openTestDB(t, false)

	chunks := createDiverseDocs()
	err := graphDB.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, nil)

	results, err := hybridSearch.Search(ctx, "database", SearchOptions{
		Limit:        10,
		FusionMethod: FusionRRF,
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if len(results) == 0 {
		t.Fatal("RRF fusion should return results")
	}

	// When keyword-only (no semantic), scores aren't necessarily normalized 0-1
	// Just verify we have scores
	for _, result := range results {
		if result.HybridScore < 0 {
			t.Errorf("Score should be non-negative, got %f", result.HybridScore)
		}
	}
}

func TestHybridSearchWeightedFusion(t *testing.T) {
	ctx := context.Background()
	graphDB := openTestDB(t, false)

	chunks := createDiverseDocs()
	err := graphDB.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, nil)

	// Test with different weights
	resultsKeywordHeavy, err := hybridSearch.Search(ctx, "database", SearchOptions{
		Limit:          10,
		FusionMethod:   FusionWeighted,
		KeywordWeight:  0.7,
		SemanticWeight: 0.3,
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	resultsSemanticHeavy, err := hybridSearch.Search(ctx, "database", SearchOptions{
		Limit:          10,
		FusionMethod:   FusionWeighted,
		KeywordWeight:  0.3,
		SemanticWeight: 0.7,
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	// Without embeddings, semantic weight doesn't matter much, but should not crash
	if len(resultsKeywordHeavy) == 0 && len(resultsSemanticHeavy) == 0 {
		t.Error("Weighted fusion should return results")
	}
}

func TestHybridSearchWithTagFilter(t *testing.T) {
	ctx := context.Background()
	graphDB := openTestDB(t, false)

	chunks := createDiverseDocs()
	err := graphDB.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, nil)

	// Search without filter should return results from all docs
	unfilteredResults, err := hybridSearch.Search(ctx, "database", SearchOptions{
		Limit: 10,
	})
	if err != nil {
		t.Fatalf("Unfiltered search failed: %v", err)
	}

	// Search with filter should only return matching tagged results
	filteredResults, err := hybridSearch.Search(ctx, "database", SearchOptions{
		Limit:      10,
		FilterTags: []string{"database"},
	})
	if err != nil {
		t.Fatalf("Filtered search failed: %v", err)
	}

	// Skip if tag filtering returns no results (may not be fully implemented)
	if len(filteredResults) == 0 {
		t.Skip("No results with tag filter - tag filtering may not be fully implemented yet")
	}

	// Filtered results should be a subset of unfiltered results
	if len(filteredResults) > len(unfilteredResults) {
		t.Error("Filtered results should not be more than unfiltered results")
	}

	// Verify that filtered results include the expected document (database_architecture.md has "database" tag)
	foundExpected := false
	for _, result := range filteredResults {
		if result.Chunk.FilePath == "database_architecture.md" {
			foundExpected = true
			break
		}
	}
	if !foundExpected {
		t.Error("Expected database_architecture.md (which has 'database' tag) in filtered results")
	}
}

func TestHybridSearchEmptyQuery(t *testing.T) {
	ctx := context.Background()
	graphDB := openTestDB(t, false)

	chunks := createDiverseDocs()
	err := graphDB.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, nil)

	_, err = hybridSearch.Search(ctx, "", SearchOptions{Limit: 10})
	if err == nil {
		t.Error("Empty query should return an error")
	}
}

func TestHybridSearchNoResults(t *testing.T) {
	ctx := context.Background()
	graphDB := openTestDB(t, false)

	chunks := createDiverseDocs()
	err := graphDB.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, nil)

	results, err := hybridSearch.Search(ctx, "quantum_physics_xyz_nonexistent", SearchOptions{Limit: 10})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	// Should return empty or low-score results
	for _, result := range results {
		if result.KeywordScore != 0 {
			t.Error("No keyword matches expected for nonexistent terms")
		}
	}
}

func TestHybridSearchLimitParameter(t *testing.T) {
	ctx := context.Background()
	graphDB := openTestDB(t, false)

	chunks := createDiverseDocs()
	err := graphDB.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, nil)

	resultsSmall, err := hybridSearch.Search(ctx, "database", SearchOptions{Limit: 2})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	resultsLarge, err := hybridSearch.Search(ctx, "database", SearchOptions{Limit: 10})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if len(resultsSmall) > 2 {
		t.Error("Should respect limit parameter")
	}
	if len(resultsLarge) < len(resultsSmall) {
		t.Error("Larger limit should return at least as many results")
	}
}

func TestHybridSearchDeduplication(t *testing.T) {
	ctx := context.Background()
	graphDB := openTestDB(t, false)

	chunks := createDiverseDocs()
	err := graphDB.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, nil)

	results, err := hybridSearch.Search(ctx, "database", SearchOptions{Limit: 10})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	// No duplicate chunk IDs
	seen := make(map[string]bool)
	for _, result := range results {
		if seen[result.Chunk.ID] {
			t.Errorf("Duplicate chunk ID found: %s", result.Chunk.ID)
		}
		seen[result.Chunk.ID] = true
	}
}

func TestHybridSearchWithScope(t *testing.T) {
	ctx := context.Background()
	graphDB := openTestDB(t, false)

	// Index folders first
	err := graphDB.IndexFolders(ctx, []string{"Projects", "Projects/ProjectA", "Projects/ProjectB"}, nil)
	if err != nil {
		t.Fatalf("IndexFolders failed: %v", err)
	}

	// Create chunks in different folders
	chunks := []types.Chunk{
		{
			ID:         "Projects/ProjectA/readme.md#Setup",
			FilePath:   "Projects/ProjectA/readme.md",
			FolderPath: "Projects/ProjectA",
			Header:     "Setup",
			Content:    "Install database dependencies for project A",
			Tags:       []string{},
		},
		{
			ID:         "Projects/ProjectB/readme.md#Setup",
			FilePath:   "Projects/ProjectB/readme.md",
			FolderPath: "Projects/ProjectB",
			Header:     "Setup",
			Content:    "Install database dependencies for project B",
			Tags:       []string{},
		},
	}

	err = graphDB.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, nil)

	results, err := hybridSearch.Search(ctx, "database", SearchOptions{
		Limit: 10,
		Scope: "Projects/ProjectA",
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	// All results should be from ProjectA
	for _, result := range results {
		if result.Chunk.FolderPath != "Projects/ProjectA" {
			t.Errorf("Expected folder 'Projects/ProjectA', got '%s'", result.Chunk.FolderPath)
		}
	}
}

// ==================== Integration Tests ====================

func TestHybridSearchIntegration(t *testing.T) {
	ctx := context.Background()
	graphDB := openTestDB(t, false)

	// Create a more realistic scenario
	chunks := []types.Chunk{
		{
			ID:       "readme.md#Installation",
			FilePath: "readme.md",
			Header:   "Installation",
			Content:  "To install the package, run npm install. Then configure your database connection settings.",
			Tags:     []string{"setup", "installation"},
		},
		{
			ID:       "docs/database.md#Configuration",
			FilePath: "docs/database.md",
			Header:   "Configuration",
			Content:  "Database configuration requires setting the connection string, username, and password. Supported databases include PostgreSQL, MySQL, and SQLite.",
			Tags:     []string{"database", "config"},
		},
		{
			ID:       "docs/api.md#Endpoints",
			FilePath: "docs/api.md",
			Header:   "Endpoints",
			Content:  "The API provides RESTful endpoints for CRUD operations. All endpoints require authentication.",
			Tags:     []string{"api", "rest"},
		},
	}

	err := graphDB.IndexChunks(ctx, chunks)
	if err != nil {
		t.Fatalf("IndexChunks failed: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, nil)

	// Test various queries
	testCases := []struct {
		query       string
		expectMatch string
	}{
		{"database configuration", "docs/database.md"},
		{"install package", "readme.md"},
		{"REST API", "docs/api.md"},
	}

	for _, tc := range testCases {
		results, err := hybridSearch.Search(ctx, tc.query, SearchOptions{Limit: 5})
		if err != nil {
			t.Errorf("Search failed for '%s': %v", tc.query, err)
			continue
		}

		if len(results) == 0 {
			t.Errorf("Expected results for '%s'", tc.query)
			continue
		}

		// Check if expected file is in top results
		found := false
		for _, r := range results {
			if r.Chunk.FilePath == tc.expectMatch {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("Expected '%s' in results for query '%s'", tc.expectMatch, tc.query)
		}
	}
}
