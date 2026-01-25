// Package embeddings provides embedding generation for semantic search.
package embeddings

import (
	"bufio"
	"context"
	"math"
	"os"
	"strings"
	"testing"
)

// loadEnvFile loads environment variables from a .env file.
func loadEnvFile(t *testing.T) {
	t.Helper()

	// Try to find .env file in project root
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
		return // No .env file found
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

// ==================== Content Cleaning Tests ====================
// These match the Python TestEmbeddingServiceLocal cleaning tests

func TestCleanContentRemovesWikilinks(t *testing.T) {
	text := "This has [[wikilink]] and [[page|alias]] references."
	cleaned := CleanContent(text)

	if strings.Contains(cleaned, "[[") {
		t.Error("cleaned content should not contain [[")
	}
	if strings.Contains(cleaned, "]]") {
		t.Error("cleaned content should not contain ]]")
	}
	if !strings.Contains(cleaned, "wikilink") {
		t.Error("cleaned content should contain 'wikilink'")
	}
	if !strings.Contains(cleaned, "alias") {
		t.Error("cleaned content should contain 'alias'")
	}
	if strings.Contains(cleaned, "page|alias") {
		t.Error("cleaned content should not contain 'page|alias'")
	}
}

func TestCleanContentRemovesTags(t *testing.T) {
	text := "This has #tag and #another-tag references."
	cleaned := CleanContent(text)

	if strings.Contains(cleaned, "#tag") {
		t.Error("cleaned content should not contain '#tag'")
	}
	if !strings.Contains(cleaned, "tag") {
		t.Error("cleaned content should contain 'tag'")
	}
}

func TestCleanContentRemovesMentions(t *testing.T) {
	text := "Hello @user and @another."
	cleaned := CleanContent(text)

	if strings.Contains(cleaned, "@user") {
		t.Error("cleaned content should not contain '@user'")
	}
	if !strings.Contains(cleaned, "user") {
		t.Error("cleaned content should contain 'user'")
	}
	if !strings.Contains(cleaned, "another") {
		t.Error("cleaned content should contain 'another'")
	}
}

func TestCleanContentRemovesFrontMatter(t *testing.T) {
	text := `---
title: Test
---
Content here`
	cleaned := CleanContent(text)

	if strings.Contains(cleaned, "---") {
		t.Error("cleaned content should not contain '---'")
	}
	if !strings.Contains(cleaned, "Content here") {
		t.Error("cleaned content should contain 'Content here'")
	}
}

func TestCleanContentNormalizesWhitespace(t *testing.T) {
	text := "This  has    multiple   spaces\n\n\n\nand newlines"
	cleaned := CleanContent(text)

	if strings.Contains(cleaned, "  ") {
		t.Error("cleaned content should not contain double spaces")
	}
	if strings.Contains(cleaned, "\n\n\n") {
		t.Error("cleaned content should not contain triple newlines")
	}
}

func TestCleanContentComprehensive(t *testing.T) {
	// Complex Silverbullet content (matches Python test)
	text := `---
title: Test Page
tags: #tag1, #tag2
---

# Main Header

This is content with [[wikilink]] and [[page|alias]].

It has @mentions and #tags everywhere.

## Section

More [[links]] and #more-tags here.
`
	cleaned := CleanContent(text)

	if strings.Contains(cleaned, "[[") {
		t.Error("cleaned content should not contain [[")
	}
	if strings.Contains(cleaned, "]]") {
		t.Error("cleaned content should not contain ]]")
	}
	if strings.Contains(cleaned, "---") {
		t.Error("cleaned content should not contain ---")
	}
	if strings.Contains(cleaned, "@mentions") {
		t.Error("cleaned content should not contain @mentions")
	}
	// But content words should remain
	if !strings.Contains(cleaned, "Main Header") {
		t.Error("cleaned content should contain 'Main Header'")
	}
	if !strings.Contains(cleaned, "content") {
		t.Error("cleaned content should contain 'content'")
	}
}

// ==================== OpenAI Provider Unit Tests ====================
// These match Python TestEmbeddingServiceOpenAI tests

func TestGetEmbeddingDimensionOpenAI(t *testing.T) {
	svc := &Service{
		config: Config{Model: "text-embedding-3-small"},
	}
	if dim := svc.GetDimension(); dim != 1536 {
		t.Errorf("GetDimension() = %d, want 1536", dim)
	}
}

func TestGetDimensionModels(t *testing.T) {
	tests := []struct {
		model    string
		expected int
	}{
		{"text-embedding-3-small", 1536},
		{"text-embedding-3-large", 3072},
		{"text-embedding-ada-002", 1536},
		{"unknown-model", 1536}, // Default
	}

	for _, tt := range tests {
		t.Run(tt.model, func(t *testing.T) {
			svc := &Service{
				config: Config{Model: tt.model},
			}
			if dim := svc.GetDimension(); dim != tt.expected {
				t.Errorf("GetDimension() = %d, want %d", dim, tt.expected)
			}
		})
	}
}

// ==================== Error Handling Tests ====================
// These match Python TestEmbeddingServiceErrors tests

func TestInitializationWithoutAPIKeyForOpenAI(t *testing.T) {
	// Clear any existing API key
	originalKey := os.Getenv("OPENAI_API_KEY")
	os.Unsetenv("OPENAI_API_KEY")
	defer func() {
		if originalKey != "" {
			os.Setenv("OPENAI_API_KEY", originalKey)
		}
	}()

	_, err := NewService(Config{Provider: ProviderOpenAI})
	if err == nil {
		t.Error("Expected error when API key is missing")
	}
	if !strings.Contains(err.Error(), "API key") {
		t.Errorf("Error should mention API key, got: %v", err)
	}
}

// ==================== OpenAI Integration Tests ====================
// These tests require OPENAI_API_KEY environment variable
// Match Python TestEmbeddingServiceOpenAI tests

func TestGenerateEmbeddingOpenAI(t *testing.T) {
	loadEnvFile(t)

	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		t.Skip("OPENAI_API_KEY not set, skipping integration test")
	}

	svc, err := NewService(Config{
		Provider: ProviderOpenAI,
		APIKey:   apiKey,
		Model:    "text-embedding-3-small",
	})
	if err != nil {
		t.Fatalf("Failed to create service: %v", err)
	}

	ctx := context.Background()

	// Test single embedding (matches Python test)
	embedding, err := svc.GenerateEmbedding(ctx, "test content", false)
	if err != nil {
		t.Fatalf("GenerateEmbedding failed: %v", err)
	}

	if len(embedding) != 1536 {
		t.Errorf("Expected 1536 dimensions, got %d", len(embedding))
	}

	// Verify all values are floats (non-zero check)
	hasNonZero := false
	for _, v := range embedding {
		if v != 0 {
			hasNonZero = true
			break
		}
	}
	if !hasNonZero {
		t.Error("Embedding should have non-zero values")
	}
}

func TestGenerateEmbeddingsBatchOpenAI(t *testing.T) {
	loadEnvFile(t)

	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		t.Skip("OPENAI_API_KEY not set, skipping integration test")
	}

	svc, err := NewService(Config{
		Provider: ProviderOpenAI,
		APIKey:   apiKey,
	})
	if err != nil {
		t.Fatalf("Failed to create service: %v", err)
	}

	ctx := context.Background()

	// Match Python test
	texts := []string{"text 1", "text 2"}
	embeddings, err := svc.GenerateEmbeddingsBatch(ctx, texts, false)
	if err != nil {
		t.Fatalf("GenerateEmbeddingsBatch failed: %v", err)
	}

	if len(embeddings) != 2 {
		t.Errorf("Expected 2 embeddings, got %d", len(embeddings))
	}

	for i, emb := range embeddings {
		if len(emb) != 1536 {
			t.Errorf("Embedding %d: expected 1536 dimensions, got %d", i, len(emb))
		}
	}
}

func TestGenerateEmbeddingWithCleaning(t *testing.T) {
	loadEnvFile(t)

	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		t.Skip("OPENAI_API_KEY not set, skipping integration test")
	}

	svc, err := NewService(Config{
		Provider: ProviderOpenAI,
		APIKey:   apiKey,
	})
	if err != nil {
		t.Fatalf("Failed to create service: %v", err)
	}

	ctx := context.Background()

	// Test with SilverBullet content that needs cleaning
	content := "Content with [[wikilink]] and #tag"
	embedding, err := svc.GenerateEmbedding(ctx, content, true)
	if err != nil {
		t.Fatalf("GenerateEmbedding failed: %v", err)
	}

	if len(embedding) != 1536 {
		t.Errorf("Expected 1536 dimensions, got %d", len(embedding))
	}
}

func TestGenerateEmbeddingEmptyText(t *testing.T) {
	loadEnvFile(t)

	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		t.Skip("OPENAI_API_KEY not set, skipping integration test")
	}

	svc, err := NewService(Config{
		Provider: ProviderOpenAI,
		APIKey:   apiKey,
	})
	if err != nil {
		t.Fatalf("Failed to create service: %v", err)
	}

	ctx := context.Background()

	// Empty text should return zero vector (matches Python test)
	embedding, err := svc.GenerateEmbedding(ctx, "", false)
	if err != nil {
		t.Fatalf("GenerateEmbedding failed: %v", err)
	}

	if len(embedding) != 1536 {
		t.Errorf("Expected 1536 dimensions, got %d", len(embedding))
	}

	for _, v := range embedding {
		if v != 0.0 {
			t.Error("Empty text embedding should be all zeros")
			break
		}
	}
}

func TestGenerateEmbeddingsBatchWithEmptyTexts(t *testing.T) {
	loadEnvFile(t)

	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		t.Skip("OPENAI_API_KEY not set, skipping integration test")
	}

	svc, err := NewService(Config{
		Provider: ProviderOpenAI,
		APIKey:   apiKey,
	})
	if err != nil {
		t.Fatalf("Failed to create service: %v", err)
	}

	ctx := context.Background()

	// Match Python test: batch with some empty texts
	texts := []string{"", "text 2", ""}
	embeddings, err := svc.GenerateEmbeddingsBatch(ctx, texts, false)
	if err != nil {
		t.Fatalf("GenerateEmbeddingsBatch failed: %v", err)
	}

	if len(embeddings) != 3 {
		t.Errorf("Expected 3 embeddings, got %d", len(embeddings))
	}

	// First and third should be zero vectors
	for _, v := range embeddings[0] {
		if v != 0.0 {
			t.Error("First (empty) embedding should be all zeros")
			break
		}
	}
	for _, v := range embeddings[2] {
		if v != 0.0 {
			t.Error("Third (empty) embedding should be all zeros")
			break
		}
	}

	// Second should have real embedding
	if len(embeddings[1]) != 1536 {
		t.Errorf("Second embedding: expected 1536 dimensions, got %d", len(embeddings[1]))
	}
	hasNonZero := false
	for _, v := range embeddings[1] {
		if v != 0 {
			hasNonZero = true
			break
		}
	}
	if !hasNonZero {
		t.Error("Second embedding should have non-zero values")
	}
}

func TestGenerateEmbeddingsBatchAllEmpty(t *testing.T) {
	loadEnvFile(t)

	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		t.Skip("OPENAI_API_KEY not set, skipping integration test")
	}

	svc, err := NewService(Config{
		Provider: ProviderOpenAI,
		APIKey:   apiKey,
	})
	if err != nil {
		t.Fatalf("Failed to create service: %v", err)
	}

	ctx := context.Background()

	// Match Python test: all empty texts
	texts := []string{"", "", ""}
	embeddings, err := svc.GenerateEmbeddingsBatch(ctx, texts, false)
	if err != nil {
		t.Fatalf("GenerateEmbeddingsBatch failed: %v", err)
	}

	if len(embeddings) != 3 {
		t.Errorf("Expected 3 embeddings, got %d", len(embeddings))
	}

	for i, emb := range embeddings {
		if len(emb) != 1536 {
			t.Errorf("Embedding %d: expected 1536 dimensions, got %d", i, len(emb))
		}
		for _, v := range emb {
			if v != 0.0 {
				t.Errorf("Embedding %d should be all zeros", i)
				break
			}
		}
	}
}

// ==================== Semantic Similarity Tests ====================
// Additional tests beyond Python coverage

func TestEmbeddingSimilarity(t *testing.T) {
	loadEnvFile(t)

	apiKey := os.Getenv("OPENAI_API_KEY")
	if apiKey == "" {
		t.Skip("OPENAI_API_KEY not set, skipping integration test")
	}

	svc, err := NewService(Config{
		Provider: ProviderOpenAI,
		APIKey:   apiKey,
	})
	if err != nil {
		t.Fatalf("Failed to create service: %v", err)
	}

	ctx := context.Background()

	// Generate embeddings for semantically similar and different texts
	texts := []string{
		"The quick brown fox jumps over the lazy dog",
		"A fast brown fox leaps over a sleeping dog",
		"Quantum physics and particle acceleration",
	}

	embeddings, err := svc.GenerateEmbeddingsBatch(ctx, texts, false)
	if err != nil {
		t.Fatalf("GenerateEmbeddingsBatch failed: %v", err)
	}

	// Calculate cosine similarity between pairs
	sim01 := cosineSimilarity(embeddings[0], embeddings[1])
	sim02 := cosineSimilarity(embeddings[0], embeddings[2])

	t.Logf("Similarity between similar texts: %.4f", sim01)
	t.Logf("Similarity between different texts: %.4f", sim02)

	// Similar texts should have higher similarity
	if sim01 <= sim02 {
		t.Errorf("Similar texts (%.4f) should have higher similarity than different texts (%.4f)", sim01, sim02)
	}

	// Similar texts should have reasonably high similarity (> 0.7 typically)
	if sim01 < 0.7 {
		t.Errorf("Similar texts should have similarity > 0.7, got %.4f", sim01)
	}
}

// cosineSimilarity calculates cosine similarity between two vectors.
func cosineSimilarity(a, b []float32) float64 {
	if len(a) != len(b) {
		return 0
	}

	var dotProduct, normA, normB float64
	for i := range a {
		dotProduct += float64(a[i]) * float64(b[i])
		normA += float64(a[i]) * float64(a[i])
		normB += float64(b[i]) * float64(b[i])
	}

	if normA == 0 || normB == 0 {
		return 0
	}

	return dotProduct / (math.Sqrt(normA) * math.Sqrt(normB))
}

// ==================== Local Embedding Tests ====================
// These match Python TestEmbeddingServiceLocal tests

func TestInitializationWithLocalProvider(t *testing.T) {
	svc, err := NewService(Config{Provider: ProviderLocal})
	if err != nil {
		t.Fatalf("Failed to create local service: %v", err)
	}
	defer svc.Close()

	if svc.GetProvider() != ProviderLocal {
		t.Errorf("Expected provider 'local', got '%s'", svc.GetProvider())
	}
	if svc.GetModel() != DefaultLocalModel {
		t.Errorf("Expected model '%s', got '%s'", DefaultLocalModel, svc.GetModel())
	}
}

func TestGetEmbeddingDimensionLocal(t *testing.T) {
	svc := &Service{
		config: Config{Provider: ProviderLocal, Model: "BAAI/bge-small-en-v1.5"},
	}
	if dim := svc.GetDimension(); dim != 384 {
		t.Errorf("GetDimension() = %d, want 384", dim)
	}
}

func TestGenerateEmbeddingLocal(t *testing.T) {
	svc, err := NewService(Config{Provider: ProviderLocal})
	if err != nil {
		t.Fatalf("Failed to create local service: %v", err)
	}
	defer svc.Close()

	ctx := context.Background()
	embedding, err := svc.GenerateEmbedding(ctx, "test content", false)
	if err != nil {
		t.Fatalf("GenerateEmbedding failed: %v", err)
	}

	if len(embedding) != 384 {
		t.Errorf("Expected 384 dimensions, got %d", len(embedding))
	}

	// Verify embedding has non-zero values
	hasNonZero := false
	for _, v := range embedding {
		if v != 0 {
			hasNonZero = true
			break
		}
	}
	if !hasNonZero {
		t.Error("Embedding should have non-zero values")
	}
}

func TestGenerateEmbeddingLocalWithCleaning(t *testing.T) {
	svc, err := NewService(Config{Provider: ProviderLocal})
	if err != nil {
		t.Fatalf("Failed to create local service: %v", err)
	}
	defer svc.Close()

	ctx := context.Background()
	content := "Content with [[wikilink]] and #tag"
	embedding, err := svc.GenerateEmbedding(ctx, content, true)
	if err != nil {
		t.Fatalf("GenerateEmbedding failed: %v", err)
	}

	if len(embedding) != 384 {
		t.Errorf("Expected 384 dimensions, got %d", len(embedding))
	}
}

func TestGenerateEmbeddingLocalEmptyText(t *testing.T) {
	svc, err := NewService(Config{Provider: ProviderLocal})
	if err != nil {
		t.Fatalf("Failed to create local service: %v", err)
	}
	defer svc.Close()

	ctx := context.Background()
	embedding, err := svc.GenerateEmbedding(ctx, "", false)
	if err != nil {
		t.Fatalf("GenerateEmbedding failed: %v", err)
	}

	if len(embedding) != 384 {
		t.Errorf("Expected 384 dimensions, got %d", len(embedding))
	}

	// Empty text should return zero vector
	for _, v := range embedding {
		if v != 0.0 {
			t.Error("Empty text embedding should be all zeros")
			break
		}
	}
}

func TestGenerateEmbeddingsBatchLocal(t *testing.T) {
	svc, err := NewService(Config{Provider: ProviderLocal})
	if err != nil {
		t.Fatalf("Failed to create local service: %v", err)
	}
	defer svc.Close()

	ctx := context.Background()
	texts := []string{"text 1", "text 2", "text 3"}
	embeddings, err := svc.GenerateEmbeddingsBatch(ctx, texts, false)
	if err != nil {
		t.Fatalf("GenerateEmbeddingsBatch failed: %v", err)
	}

	if len(embeddings) != 3 {
		t.Errorf("Expected 3 embeddings, got %d", len(embeddings))
	}

	for i, emb := range embeddings {
		if len(emb) != 384 {
			t.Errorf("Embedding %d: expected 384 dimensions, got %d", i, len(emb))
		}
	}
}

func TestGenerateEmbeddingsBatchLocalWithEmpty(t *testing.T) {
	svc, err := NewService(Config{Provider: ProviderLocal})
	if err != nil {
		t.Fatalf("Failed to create local service: %v", err)
	}
	defer svc.Close()

	ctx := context.Background()
	texts := []string{"", "text 2", ""}
	embeddings, err := svc.GenerateEmbeddingsBatch(ctx, texts, false)
	if err != nil {
		t.Fatalf("GenerateEmbeddingsBatch failed: %v", err)
	}

	if len(embeddings) != 3 {
		t.Errorf("Expected 3 embeddings, got %d", len(embeddings))
	}

	// First and third should be zero vectors
	for _, v := range embeddings[0] {
		if v != 0.0 {
			t.Error("First (empty) embedding should be all zeros")
			break
		}
	}
	for _, v := range embeddings[2] {
		if v != 0.0 {
			t.Error("Third (empty) embedding should be all zeros")
			break
		}
	}

	// Second should have real embedding
	hasNonZero := false
	for _, v := range embeddings[1] {
		if v != 0 {
			hasNonZero = true
			break
		}
	}
	if !hasNonZero {
		t.Error("Second embedding should have non-zero values")
	}
}

func TestLocalEmbeddingSimilarity(t *testing.T) {
	svc, err := NewService(Config{Provider: ProviderLocal})
	if err != nil {
		t.Fatalf("Failed to create local service: %v", err)
	}
	defer svc.Close()

	ctx := context.Background()

	// Generate embeddings for semantically similar and different texts
	texts := []string{
		"The quick brown fox jumps over the lazy dog",
		"A fast brown fox leaps over a sleeping dog",
		"Quantum physics and particle acceleration",
	}

	embeddings, err := svc.GenerateEmbeddingsBatch(ctx, texts, false)
	if err != nil {
		t.Fatalf("GenerateEmbeddingsBatch failed: %v", err)
	}

	// Calculate cosine similarity between pairs
	sim01 := cosineSimilarity(embeddings[0], embeddings[1])
	sim02 := cosineSimilarity(embeddings[0], embeddings[2])

	t.Logf("Local: Similarity between similar texts: %.4f", sim01)
	t.Logf("Local: Similarity between different texts: %.4f", sim02)

	// Similar texts should have higher similarity
	if sim01 <= sim02 {
		t.Errorf("Similar texts (%.4f) should have higher similarity than different texts (%.4f)", sim01, sim02)
	}
}

func TestInvalidProvider(t *testing.T) {
	_, err := NewService(Config{Provider: "invalid_provider"})
	if err == nil {
		t.Error("Expected error for invalid provider")
	}
	if !strings.Contains(err.Error(), "unknown embedding provider") {
		t.Errorf("Error should mention unknown provider, got: %v", err)
	}
}
