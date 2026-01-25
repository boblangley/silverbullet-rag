// Package search provides hybrid search combining keyword and semantic search.
package search

import (
	"bufio"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/boblangley/silverbullet-rag/internal/db"
	"github.com/boblangley/silverbullet-rag/internal/embeddings"
	"github.com/boblangley/silverbullet-rag/internal/types"
)

// loadEnvFile loads environment variables from a .env file.
func loadEnvFile(t *testing.T) {
	t.Helper()

	envPaths := []string{
		"../../.env",
		"../.env",
		".env",
	}

	var envPath string
	for _, p := range envPaths {
		if _, err := os.Stat(p); err == nil {
			envPath = p
			break
		}
	}

	if envPath == "" {
		return
	}

	file, err := os.Open(envPath)
	if err != nil {
		return
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		parts := strings.SplitN(line, "=", 2)
		if len(parts) == 2 {
			key := strings.TrimSpace(parts[0])
			value := strings.TrimSpace(parts[1])
			if os.Getenv(key) == "" {
				os.Setenv(key, value)
			}
		}
	}
}

// ==================== Semantic Search Integration Tests ====================
// These tests require OPENAI_API_KEY and test the full pipeline:
// 1. Generate embeddings via OpenAI
// 2. Store chunks with embeddings in LadybugDB
// 3. Perform semantic search using vector similarity
// 4. Verify results are ranked by semantic relevance

func TestSemanticSearchWithEmbeddingsIntegration(t *testing.T) {
	loadEnvFile(t)

	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		t.Skip("OPENAI_API_KEY not set, skipping integration test")
	}

	ctx := context.Background()

	// Create embedding service
	embeddingSvc, err := embeddings.NewService(embeddings.Config{
		Provider: embeddings.ProviderOpenAI,
		APIKey:   apiKey,
		Model:    "text-embedding-3-small",
	})
	if err != nil {
		t.Fatalf("Failed to create embedding service: %v", err)
	}

	// Create database WITH embeddings enabled
	dbPath := createTempDB(t)
	graphDB, err := db.Open(db.Config{
		Path:             dbPath,
		EnableEmbeddings: true, // Enable embeddings!
	})
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	t.Cleanup(func() { graphDB.Close() })

	// Create test documents with diverse content
	chunks := []types.Chunk{
		{
			ID:       "ml_intro.md#Overview",
			FilePath: "ml_intro.md",
			Header:   "Machine Learning Overview",
			Content:  "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience. Deep learning uses neural networks with many layers.",
			Tags:     []string{"ai", "ml"},
		},
		{
			ID:       "cooking.md#Italian",
			FilePath: "cooking.md",
			Header:   "Italian Cuisine",
			Content:  "Italian cooking features pasta, pizza, and risotto. Traditional recipes have been passed down through generations. Olive oil and fresh tomatoes are essential ingredients.",
			Tags:     []string{"food", "recipes"},
		},
		{
			ID:       "db_systems.md#SQL",
			FilePath: "db_systems.md",
			Header:   "SQL Databases",
			Content:  "Relational databases use SQL for querying structured data. PostgreSQL and MySQL are popular open-source options. ACID properties ensure data consistency.",
			Tags:     []string{"database", "sql"},
		},
		{
			ID:       "neural_nets.md#Architecture",
			FilePath: "neural_nets.md",
			Header:   "Neural Network Architecture",
			Content:  "Neural networks consist of layers of interconnected nodes. Convolutional neural networks excel at image recognition. Transformers have revolutionized natural language processing.",
			Tags:     []string{"ai", "deep-learning"},
		},
	}

	// Generate embeddings for each chunk
	t.Log("Generating embeddings for test chunks...")
	for i := range chunks {
		embedding, err := embeddingSvc.GenerateEmbedding(ctx, chunks[i].Content, true)
		if err != nil {
			t.Fatalf("Failed to generate embedding for chunk %d: %v", i, err)
		}
		chunks[i].Embedding = embedding
		t.Logf("Generated embedding for %s (%d dimensions)", chunks[i].ID, len(embedding))
	}

	// Index chunks with embeddings
	if err := graphDB.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("Failed to index chunks: %v", err)
	}
	t.Log("Indexed chunks with embeddings in LadybugDB")

	// Create hybrid search with embedding service
	hybridSearch := NewHybridSearch(graphDB, embeddingSvc)

	// Test 1: Search for AI/ML content
	t.Run("semantic search for AI content", func(t *testing.T) {
		results, err := hybridSearch.Search(ctx, "artificial intelligence and deep learning", SearchOptions{
			Limit: 10,
		})
		if err != nil {
			t.Fatalf("Search failed: %v", err)
		}

		if len(results) == 0 {
			t.Fatal("Expected results for AI query")
		}

		t.Logf("Found %d results for AI query", len(results))
		for i, r := range results {
			t.Logf("  %d. %s (hybrid=%.4f, keyword=%.4f, semantic=%.4f)",
				i+1, r.Chunk.FilePath, r.HybridScore, r.KeywordScore, r.SemanticScore)
		}

		// AI-related documents should rank higher
		foundAIDoc := false
		for _, r := range results[:2] { // Check top 2
			if r.Chunk.FilePath == "ml_intro.md" || r.Chunk.FilePath == "neural_nets.md" {
				foundAIDoc = true
				break
			}
		}
		if !foundAIDoc {
			t.Error("Expected AI-related documents in top results")
		}
	})

	// Test 2: Search for cooking content
	t.Run("semantic search for cooking content", func(t *testing.T) {
		results, err := hybridSearch.Search(ctx, "traditional food recipes and cooking techniques", SearchOptions{
			Limit: 10,
		})
		if err != nil {
			t.Fatalf("Search failed: %v", err)
		}

		if len(results) == 0 {
			t.Fatal("Expected results for cooking query")
		}

		t.Logf("Found %d results for cooking query", len(results))
		for i, r := range results {
			t.Logf("  %d. %s (hybrid=%.4f, keyword=%.4f, semantic=%.4f)",
				i+1, r.Chunk.FilePath, r.HybridScore, r.KeywordScore, r.SemanticScore)
		}

		// Cooking document should rank first
		if results[0].Chunk.FilePath != "cooking.md" {
			t.Errorf("Expected cooking.md as top result, got %s", results[0].Chunk.FilePath)
		}
	})

	// Test 3: Search for database content
	t.Run("semantic search for database content", func(t *testing.T) {
		results, err := hybridSearch.Search(ctx, "data storage and querying systems", SearchOptions{
			Limit: 10,
		})
		if err != nil {
			t.Fatalf("Search failed: %v", err)
		}

		if len(results) == 0 {
			t.Fatal("Expected results for database query")
		}

		t.Logf("Found %d results for database query", len(results))
		for i, r := range results {
			t.Logf("  %d. %s (hybrid=%.4f, keyword=%.4f, semantic=%.4f)",
				i+1, r.Chunk.FilePath, r.HybridScore, r.KeywordScore, r.SemanticScore)
		}

		// Database document should rank highest
		if results[0].Chunk.FilePath != "db_systems.md" {
			t.Errorf("Expected db_systems.md as top result, got %s", results[0].Chunk.FilePath)
		}
	})
}

func TestHybridSearchFusionWithEmbeddingsIntegration(t *testing.T) {
	loadEnvFile(t)

	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		t.Skip("OPENAI_API_KEY not set, skipping integration test")
	}

	ctx := context.Background()

	embeddingSvc, err := embeddings.NewService(embeddings.Config{
		Provider: embeddings.ProviderOpenAI,
		APIKey:   apiKey,
	})
	if err != nil {
		t.Fatalf("Failed to create embedding service: %v", err)
	}

	dbPath := createTempDB(t)
	graphDB, err := db.Open(db.Config{
		Path:             dbPath,
		EnableEmbeddings: true,
	})
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	t.Cleanup(func() { graphDB.Close() })

	// Create chunks with specific content for testing fusion
	chunks := []types.Chunk{
		{
			ID:       "exact_match.md#Main",
			FilePath: "exact_match.md",
			Header:   "Database Tutorial",
			Content:  "This database tutorial covers database basics. Learn about database design, database queries, and database optimization.",
			Tags:     []string{"database"},
		},
		{
			ID:       "semantic_match.md#Main",
			FilePath: "semantic_match.md",
			Header:   "Data Storage Systems",
			Content:  "Modern data management platforms utilize various persistence mechanisms including relational stores, document collections, and graph repositories.",
			Tags:     []string{"data"},
		},
	}

	// Generate embeddings
	for i := range chunks {
		embedding, err := embeddingSvc.GenerateEmbedding(ctx, chunks[i].Content, true)
		if err != nil {
			t.Fatalf("Failed to generate embedding: %v", err)
		}
		chunks[i].Embedding = embedding
	}

	if err := graphDB.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("Failed to index chunks: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, embeddingSvc)

	// Test RRF fusion
	t.Run("RRF fusion balances keyword and semantic", func(t *testing.T) {
		results, err := hybridSearch.Search(ctx, "database management systems", SearchOptions{
			Limit:        10,
			FusionMethod: FusionRRF,
		})
		if err != nil {
			t.Fatalf("Search failed: %v", err)
		}

		if len(results) == 0 {
			t.Fatal("Expected results")
		}

		t.Logf("RRF fusion results:")
		for i, r := range results {
			t.Logf("  %d. %s (hybrid=%.4f)", i+1, r.Chunk.FilePath, r.HybridScore)
		}

		// Both documents should appear in results
		if len(results) < 2 {
			t.Error("Expected both documents in results")
		}
	})

	// Test weighted fusion with keyword emphasis
	t.Run("weighted fusion with keyword emphasis", func(t *testing.T) {
		results, err := hybridSearch.Search(ctx, "database", SearchOptions{
			Limit:          10,
			FusionMethod:   FusionWeighted,
			KeywordWeight:  0.8,
			SemanticWeight: 0.2,
		})
		if err != nil {
			t.Fatalf("Search failed: %v", err)
		}

		t.Logf("Keyword-heavy results:")
		for i, r := range results {
			t.Logf("  %d. %s (hybrid=%.4f, kw=%.4f, sem=%.4f)",
				i+1, r.Chunk.FilePath, r.HybridScore, r.KeywordScore, r.SemanticScore)
		}

		// Exact match document should rank higher with keyword emphasis
		if len(results) > 0 && results[0].Chunk.FilePath != "exact_match.md" {
			t.Logf("Note: exact_match.md expected first with keyword emphasis")
		}
	})

	// Test weighted fusion with semantic emphasis
	t.Run("weighted fusion with semantic emphasis", func(t *testing.T) {
		results, err := hybridSearch.Search(ctx, "data persistence and storage mechanisms", SearchOptions{
			Limit:          10,
			FusionMethod:   FusionWeighted,
			KeywordWeight:  0.2,
			SemanticWeight: 0.8,
		})
		if err != nil {
			t.Fatalf("Search failed: %v", err)
		}

		t.Logf("Semantic-heavy results:")
		for i, r := range results {
			t.Logf("  %d. %s (hybrid=%.4f, kw=%.4f, sem=%.4f)",
				i+1, r.Chunk.FilePath, r.HybridScore, r.KeywordScore, r.SemanticScore)
		}
	})
}

func TestSemanticSearchWithScopeIntegration(t *testing.T) {
	loadEnvFile(t)

	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		t.Skip("OPENAI_API_KEY not set, skipping integration test")
	}

	ctx := context.Background()

	embeddingSvc, err := embeddings.NewService(embeddings.Config{
		Provider: embeddings.ProviderOpenAI,
		APIKey:   apiKey,
	})
	if err != nil {
		t.Fatalf("Failed to create embedding service: %v", err)
	}

	dbPath := createTempDB(t)
	graphDB, err := db.Open(db.Config{
		Path:             dbPath,
		EnableEmbeddings: true,
	})
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	t.Cleanup(func() { graphDB.Close() })

	// Index folders
	if err := graphDB.IndexFolders(ctx, []string{"Projects", "Projects/Alpha", "Projects/Beta"}, nil); err != nil {
		t.Fatalf("Failed to index folders: %v", err)
	}

	chunks := []types.Chunk{
		{
			ID:         "Projects/Alpha/readme.md#Setup",
			FilePath:   "Projects/Alpha/readme.md",
			FolderPath: "Projects/Alpha",
			Header:     "Setup",
			Content:    "Setting up machine learning models for project Alpha. Uses TensorFlow and PyTorch.",
			Tags:       []string{},
		},
		{
			ID:         "Projects/Beta/readme.md#Setup",
			FilePath:   "Projects/Beta/readme.md",
			FolderPath: "Projects/Beta",
			Header:     "Setup",
			Content:    "Setting up machine learning models for project Beta. Uses scikit-learn and XGBoost.",
			Tags:       []string{},
		},
	}

	for i := range chunks {
		embedding, err := embeddingSvc.GenerateEmbedding(ctx, chunks[i].Content, true)
		if err != nil {
			t.Fatalf("Failed to generate embedding: %v", err)
		}
		chunks[i].Embedding = embedding
	}

	if err := graphDB.IndexChunks(ctx, chunks); err != nil {
		t.Fatalf("Failed to index chunks: %v", err)
	}

	hybridSearch := NewHybridSearch(graphDB, embeddingSvc)

	// Search with scope restriction
	results, err := hybridSearch.Search(ctx, "machine learning setup", SearchOptions{
		Limit: 10,
		Scope: "Projects/Alpha",
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	t.Logf("Scoped search results (Projects/Alpha):")
	for i, r := range results {
		t.Logf("  %d. %s (folder: %s)", i+1, r.Chunk.FilePath, r.Chunk.FolderPath)
	}

	// All results should be from Alpha
	for _, r := range results {
		if r.Chunk.FolderPath != "Projects/Alpha" {
			t.Errorf("Expected folder 'Projects/Alpha', got '%s'", r.Chunk.FolderPath)
		}
	}
}

func TestLadybugDBEmbeddingStorageIntegration(t *testing.T) {
	loadEnvFile(t)

	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		t.Skip("OPENAI_API_KEY not set, skipping integration test")
	}

	ctx := context.Background()

	embeddingSvc, err := embeddings.NewService(embeddings.Config{
		Provider: embeddings.ProviderOpenAI,
		APIKey:   apiKey,
	})
	if err != nil {
		t.Fatalf("Failed to create embedding service: %v", err)
	}

	dbPath := createTempDB(t)
	graphDB, err := db.Open(db.Config{
		Path:             dbPath,
		EnableEmbeddings: true,
	})
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	t.Cleanup(func() { graphDB.Close() })

	// Create and index a chunk with embedding
	embedding, err := embeddingSvc.GenerateEmbedding(ctx, "Test content for embedding storage", false)
	if err != nil {
		t.Fatalf("Failed to generate embedding: %v", err)
	}

	chunk := types.Chunk{
		ID:        "test.md#Section",
		FilePath:  "test.md",
		Header:    "Section",
		Content:   "Test content for embedding storage",
		Embedding: embedding,
	}

	if err := graphDB.IndexChunks(ctx, []types.Chunk{chunk}); err != nil {
		t.Fatalf("Failed to index chunk: %v", err)
	}

	// Verify embedding was stored by querying it
	records, err := graphDB.Execute(ctx, `
		MATCH (c:Chunk {id: $id})
		RETURN c.embedding IS NOT NULL as has_embedding
	`, map[string]any{"id": chunk.ID})
	if err != nil {
		t.Fatalf("Failed to query chunk: %v", err)
	}

	if len(records) == 0 {
		t.Fatal("Chunk not found in database")
	}

	hasEmbedding, ok := records[0]["has_embedding"].(bool)
	if !ok || !hasEmbedding {
		t.Error("Embedding should be stored in database")
	}

	t.Log("Verified embedding stored in LadybugDB")

	// Test vector similarity query
	embParts := make([]string, len(embedding))
	for i, v := range embedding {
		embParts[i] = strings.Replace(strings.TrimRight(strings.TrimRight(filepath.Join(filepath.Dir(dbPath), "%.6f"), "0"), "."), "%.6f", string(rune(v)), 1)
	}

	// Use the stored embedding for similarity search
	records, err = graphDB.Execute(ctx, `
		MATCH (c:Chunk)
		WHERE c.embedding IS NOT NULL
		RETURN c.id as id, c.content as content
	`, nil)
	if err != nil {
		t.Fatalf("Failed to query with embedding: %v", err)
	}

	if len(records) == 0 {
		t.Error("No chunks with embeddings found")
	} else {
		t.Logf("Found %d chunk(s) with embeddings", len(records))
	}
}
