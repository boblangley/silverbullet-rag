// Package search provides keyword, semantic, and hybrid search.
package search

import (
	"context"
	"fmt"
	"math"
	"sort"
	"strings"

	"github.com/boblangley/silverbullet-rag/internal/db"
	"github.com/boblangley/silverbullet-rag/internal/embeddings"
	"github.com/boblangley/silverbullet-rag/internal/types"
)

// FusionMethod defines how to combine keyword and semantic results.
type FusionMethod string

const (
	FusionRRF      FusionMethod = "rrf"
	FusionWeighted FusionMethod = "weighted"
)

// HybridSearch combines keyword and semantic search.
type HybridSearch struct {
	db        *db.GraphDB
	embedding *embeddings.Service
}

// NewHybridSearch creates a new hybrid search instance.
func NewHybridSearch(db *db.GraphDB, embedding *embeddings.Service) *HybridSearch {
	return &HybridSearch{
		db:        db,
		embedding: embedding,
	}
}

// SearchOptions configures search behavior.
type SearchOptions struct {
	Limit          int
	FilterTags     []string
	FilterPages    []string
	Scope          string
	FusionMethod   FusionMethod
	SemanticWeight float64
	KeywordWeight  float64
}

// DefaultOptions returns default search options.
func DefaultOptions() SearchOptions {
	return SearchOptions{
		Limit:          10,
		FusionMethod:   FusionRRF,
		SemanticWeight: 0.5,
		KeywordWeight:  0.5,
	}
}

// Search performs hybrid search combining keyword and semantic results.
func (h *HybridSearch) Search(ctx context.Context, query string, opts SearchOptions) ([]types.SearchResult, error) {
	if strings.TrimSpace(query) == "" {
		return nil, fmt.Errorf("query cannot be empty")
	}

	// Apply defaults
	if opts.Limit == 0 {
		opts.Limit = 10
	}
	if opts.FusionMethod == "" {
		opts.FusionMethod = FusionRRF
	}
	if opts.FusionMethod == FusionWeighted && opts.KeywordWeight == 0 && opts.SemanticWeight == 0 {
		opts.KeywordWeight = 0.5
		opts.SemanticWeight = 0.5
	}

	// Normalize weights for weighted fusion
	if opts.FusionMethod == FusionWeighted {
		total := opts.SemanticWeight + opts.KeywordWeight
		if total > 0 && math.Abs(total-1.0) > 0.01 {
			opts.SemanticWeight = opts.SemanticWeight / total
			opts.KeywordWeight = opts.KeywordWeight / total
		}
	}

	// Perform keyword search
	keywordResults, err := h.keywordSearch(ctx, query, opts)
	if err != nil {
		return nil, fmt.Errorf("keyword search: %w", err)
	}

	// Perform semantic search if embeddings enabled
	var semanticResults []scoredChunk
	if h.db.EnableEmbeddings() && h.embedding != nil {
		semanticResults, err = h.semanticSearch(ctx, query, opts)
		if err != nil {
			// Fall back to keyword-only
			semanticResults = nil
		}
	}

	// If only one type has results, return those
	if len(semanticResults) == 0 {
		return formatResults(keywordResults, true, false), nil
	}
	if len(keywordResults) == 0 {
		return formatResults(semanticResults, false, true), nil
	}

	// Fuse results
	var fused []types.SearchResult
	if opts.FusionMethod == FusionRRF {
		fused = h.reciprocalRankFusion(keywordResults, semanticResults, opts.Limit*2)
	} else {
		fused = h.weightedFusion(keywordResults, semanticResults, opts)
	}

	// Apply post-fusion filtering
	if len(opts.FilterTags) > 0 {
		fused = h.filterByTags(ctx, fused, opts.FilterTags)
	}
	if len(opts.FilterPages) > 0 {
		fused = filterByPages(fused, opts.FilterPages)
	}

	// Limit results
	if len(fused) > opts.Limit {
		fused = fused[:opts.Limit]
	}

	return fused, nil
}

type scoredChunk struct {
	chunk types.Chunk
	score float64
}

func (h *HybridSearch) keywordSearch(ctx context.Context, keyword string, opts SearchOptions) ([]scoredChunk, error) {
	// Get total document count for IDF
	var totalDocs int
	if opts.Scope != "" {
		records, err := h.db.Execute(ctx, `
			MATCH (c:Chunk)-[:IN_FOLDER]->(f:Folder)
			WHERE f.path = $scope OR f.path STARTS WITH $scope_prefix
			RETURN count(c) as total
		`, map[string]any{"scope": opts.Scope, "scope_prefix": opts.Scope + "/"})
		if err == nil && len(records) > 0 {
			if v, ok := records[0]["total"].(int64); ok {
				totalDocs = int(v)
			}
		}
	} else {
		records, err := h.db.Execute(ctx, "MATCH (c:Chunk) RETURN count(c) as total", nil)
		if err == nil && len(records) > 0 {
			if v, ok := records[0]["total"].(int64); ok {
				totalDocs = int(v)
			}
		}
	}

	if totalDocs == 0 {
		return nil, nil
	}

	// Tokenize query
	queryTerms := strings.Fields(strings.ToLower(keyword))

	// Build search query
	var scopeMatch, scopeWhere string
	params := make(map[string]any)

	if opts.Scope != "" {
		scopeMatch = "-[:IN_FOLDER]->(f:Folder)"
		scopeWhere = " AND (f.path = $scope OR f.path STARTS WITH $scope_prefix)"
		params["scope"] = opts.Scope
		params["scope_prefix"] = opts.Scope + "/"
	}

	// Build WHERE clause for terms
	var whereClauses []string
	for i, term := range queryTerms {
		paramName := fmt.Sprintf("term%d", i)
		clause := fmt.Sprintf("(toLower(c.content) CONTAINS $%s OR toLower(c.file_path) CONTAINS $%s OR toLower(c.header) CONTAINS $%s)", paramName, paramName, paramName)
		whereClauses = append(whereClauses, clause)
		params[paramName] = term
	}

	query := fmt.Sprintf("MATCH (c:Chunk)%s WHERE (%s)%s RETURN c", scopeMatch, strings.Join(whereClauses, " OR "), scopeWhere)
	records, err := h.db.Execute(ctx, query, params)
	if err != nil {
		return nil, err
	}

	// Calculate BM25 scores
	k1 := 1.5
	b := 0.75

	// Calculate average document length
	var totalLen int
	chunks := make([]types.Chunk, 0, len(records))
	for _, rec := range records {
		chunk := recordToChunk(rec)
		chunks = append(chunks, chunk)
		totalLen += len(chunk.Content)
	}
	avgDocLen := float64(totalLen) / float64(len(chunks))

	// Calculate document frequencies
	termDocFreqs := make(map[string]int)
	for _, term := range queryTerms {
		for _, chunk := range chunks {
			content := strings.ToLower(chunk.Content + " " + chunk.Header + " " + chunk.FilePath)
			if strings.Contains(content, term) {
				termDocFreqs[term]++
			}
		}
	}

	// Score chunks
	var results []scoredChunk
	for _, chunk := range chunks {
		content := strings.ToLower(chunk.Content)
		header := strings.ToLower(chunk.Header)
		filePath := strings.ToLower(chunk.FilePath)
		docLen := float64(len(chunk.Content))

		var bm25Score float64
		for _, term := range queryTerms {
			tf := float64(strings.Count(content, term))
			tf += float64(strings.Count(header, term)) * 2.0   // Header boost
			tf += float64(strings.Count(filePath, term)) * 1.5 // Path boost

			if tf == 0 {
				continue
			}

			df := float64(termDocFreqs[term])
			if df == 0 {
				df = 1
			}

			// IDF with smoothing
			idf := math.Log((float64(totalDocs)-df+0.5)/(df+0.5) + 1.0)

			// BM25 formula
			normalizedTF := (tf * (k1 + 1)) / (tf + k1*(1-b+b*docLen/avgDocLen))
			bm25Score += idf * normalizedTF
		}

		results = append(results, scoredChunk{chunk: chunk, score: bm25Score})
	}

	// Sort by score descending
	sort.Slice(results, func(i, j int) bool {
		return results[i].score > results[j].score
	})

	return results, nil
}

func (h *HybridSearch) semanticSearch(ctx context.Context, query string, opts SearchOptions) ([]scoredChunk, error) {
	if h.embedding == nil {
		return nil, fmt.Errorf("embeddings not enabled")
	}

	// Generate query embedding
	queryEmbedding, err := h.embedding.GenerateEmbedding(ctx, query, true)
	if err != nil {
		return nil, err
	}

	// Build filter conditions
	conditions := []string{"c.embedding IS NOT NULL"}
	params := map[string]any{"limit": opts.Limit * 2}

	if len(opts.FilterTags) > 0 {
		conditions = append(conditions, "EXISTS { MATCH (c)-[:TAGGED]->(t:Tag) WHERE t.name IN $tags }")
		params["tags"] = opts.FilterTags
	}

	if len(opts.FilterPages) > 0 {
		conditions = append(conditions, "c.file_path IN $pages")
		params["pages"] = opts.FilterPages
	}

	if opts.Scope != "" {
		conditions = append(conditions, "EXISTS { MATCH (c)-[:IN_FOLDER]->(f:Folder) WHERE f.path = $scope OR f.path STARTS WITH $scope_prefix }")
		params["scope"] = opts.Scope
		params["scope_prefix"] = opts.Scope + "/"
	}

	// Build embedding literal
	var embParts []string
	for _, v := range queryEmbedding {
		embParts = append(embParts, fmt.Sprintf("%f", v))
	}
	embeddingLiteral := "[" + strings.Join(embParts, ",") + "]"

	cypherQuery := fmt.Sprintf(`
		MATCH (c:Chunk)
		WHERE %s
		RETURN c, ARRAY_COSINE_SIMILARITY(c.embedding, %s) AS similarity
		ORDER BY similarity DESC
		LIMIT $limit
	`, strings.Join(conditions, " AND "), embeddingLiteral)

	records, err := h.db.Execute(ctx, cypherQuery, params)
	if err != nil {
		return nil, err
	}

	var results []scoredChunk
	for _, rec := range records {
		chunk := recordToChunk(rec)
		similarity := 0.0
		if v, ok := rec["similarity"].(float64); ok {
			similarity = v
		}
		results = append(results, scoredChunk{chunk: chunk, score: similarity})
	}

	return results, nil
}

func (h *HybridSearch) reciprocalRankFusion(keyword, semantic []scoredChunk, limit int) []types.SearchResult {
	const k = 60.0

	rrfScores := make(map[string]float64)
	chunkData := make(map[string]types.Chunk)

	// Process keyword results
	for rank, sc := range keyword {
		rrfScores[sc.chunk.ID] += 1.0 / (k + float64(rank+1))
		chunkData[sc.chunk.ID] = sc.chunk
	}

	// Process semantic results
	for rank, sc := range semantic {
		rrfScores[sc.chunk.ID] += 1.0 / (k + float64(rank+1))
		if _, exists := chunkData[sc.chunk.ID]; !exists {
			chunkData[sc.chunk.ID] = sc.chunk
		}
	}

	// Normalize scores
	if len(rrfScores) > 0 {
		var maxScore, minScore float64 = 0, math.MaxFloat64
		for _, s := range rrfScores {
			if s > maxScore {
				maxScore = s
			}
			if s < minScore {
				minScore = s
			}
		}
		scoreRange := maxScore - minScore
		if scoreRange == 0 {
			scoreRange = 1
		}
		for id := range rrfScores {
			rrfScores[id] = (rrfScores[id] - minScore) / scoreRange
		}
	}

	// Build results
	var results []types.SearchResult
	for id, score := range rrfScores {
		results = append(results, types.SearchResult{
			Chunk:       chunkData[id],
			HybridScore: score,
		})
	}

	sort.Slice(results, func(i, j int) bool {
		return results[i].HybridScore > results[j].HybridScore
	})

	if len(results) > limit {
		results = results[:limit]
	}

	return results
}

func (h *HybridSearch) weightedFusion(keyword, semantic []scoredChunk, opts SearchOptions) []types.SearchResult {
	// Normalize keyword scores
	keywordScores := make(map[string]float64)
	if len(keyword) > 0 {
		var maxScore, minScore float64 = 0, math.MaxFloat64
		for _, sc := range keyword {
			if sc.score > maxScore {
				maxScore = sc.score
			}
			if sc.score < minScore {
				minScore = sc.score
			}
		}
		scoreRange := maxScore - minScore
		if scoreRange == 0 {
			scoreRange = 1
		}
		for _, sc := range keyword {
			keywordScores[sc.chunk.ID] = (sc.score - minScore) / scoreRange
		}
	}

	// Normalize semantic scores (use rank-based)
	semanticScores := make(map[string]float64)
	for rank, sc := range semantic {
		semanticScores[sc.chunk.ID] = math.Exp(-0.1 * float64(rank+1))
	}

	// Collect all chunks
	chunkData := make(map[string]types.Chunk)
	for _, sc := range keyword {
		chunkData[sc.chunk.ID] = sc.chunk
	}
	for _, sc := range semantic {
		if _, exists := chunkData[sc.chunk.ID]; !exists {
			chunkData[sc.chunk.ID] = sc.chunk
		}
	}

	// Calculate weighted scores
	var results []types.SearchResult
	for id, chunk := range chunkData {
		kwScore := keywordScores[id]
		semScore := semanticScores[id]
		hybridScore := opts.KeywordWeight*kwScore + opts.SemanticWeight*semScore

		results = append(results, types.SearchResult{
			Chunk:         chunk,
			HybridScore:   hybridScore,
			KeywordScore:  kwScore,
			SemanticScore: semScore,
		})
	}

	sort.Slice(results, func(i, j int) bool {
		return results[i].HybridScore > results[j].HybridScore
	})

	return results
}

func (h *HybridSearch) filterByTags(ctx context.Context, results []types.SearchResult, tags []string) []types.SearchResult {
	var filtered []types.SearchResult
	for _, r := range results {
		records, err := h.db.Execute(ctx, `
			MATCH (c:Chunk {id: $chunk_id})-[:TAGGED]->(t:Tag)
			RETURN t.name as tag
		`, map[string]any{"chunk_id": r.Chunk.ID})
		if err != nil {
			continue
		}

		chunkTags := make(map[string]struct{})
		for _, rec := range records {
			if tag, ok := rec["tag"].(string); ok {
				chunkTags[tag] = struct{}{}
			}
		}

		for _, tag := range tags {
			if _, exists := chunkTags[tag]; exists {
				filtered = append(filtered, r)
				break
			}
		}
	}
	return filtered
}

func filterByPages(results []types.SearchResult, pages []string) []types.SearchResult {
	pageSet := make(map[string]struct{})
	for _, p := range pages {
		pageSet[p] = struct{}{}
	}

	var filtered []types.SearchResult
	for _, r := range results {
		if _, exists := pageSet[r.Chunk.FilePath]; exists {
			filtered = append(filtered, r)
		}
	}
	return filtered
}

func formatResults(chunks []scoredChunk, keywordOnly, semanticOnly bool) []types.SearchResult {
	var results []types.SearchResult
	for i, sc := range chunks {
		r := types.SearchResult{Chunk: sc.chunk}
		if keywordOnly {
			r.HybridScore = sc.score
			r.KeywordScore = sc.score
		} else if semanticOnly {
			rankScore := math.Exp(-0.1 * float64(i+1))
			r.HybridScore = rankScore
			r.SemanticScore = rankScore
		}
		results = append(results, r)
	}
	return results
}

func recordToChunk(rec db.Record) types.Chunk {
	chunk := types.Chunk{}

	// The db package converts lbug.Node to map[string]any
	if c, ok := rec["c"].(map[string]any); ok {
		if v, ok := c["id"].(string); ok {
			chunk.ID = v
		}
		if v, ok := c["file_path"].(string); ok {
			chunk.FilePath = v
		}
		if v, ok := c["header"].(string); ok {
			chunk.Header = v
		}
		if v, ok := c["content"].(string); ok {
			chunk.Content = v
		}
		if v, ok := c["folder_path"].(string); ok {
			chunk.FolderPath = v
		}
	}

	return chunk
}
