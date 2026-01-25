// Package embeddings provides embedding generation for semantic search.
package embeddings

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/knights-analytics/hugot"
	"github.com/knights-analytics/hugot/pipelines"
)

// Provider represents an embedding provider type.
type Provider string

const (
	ProviderOpenAI Provider = "openai"
	ProviderLocal  Provider = "local"
)

// Local model constants
const (
	DefaultLocalModel = "BAAI/bge-small-en-v1.5"
	LocalModelDim     = 384
)

// Config holds embedding service configuration.
type Config struct {
	Provider  Provider
	APIKey    string
	Model     string
	BaseURL   string
	CacheDir  string // Directory to cache local models
	MaxLength int    // Max sequence length for local models
}

// Service generates text embeddings.
type Service struct {
	config   Config
	client   *http.Client
	session  *hugot.Session
	pipeline *pipelines.FeatureExtractionPipeline
	mu       sync.Mutex
}

// NewService creates a new embedding service.
func NewService(cfg Config) (*Service, error) {
	if cfg.Provider == "" {
		cfg.Provider = Provider(os.Getenv("EMBEDDING_PROVIDER"))
		if cfg.Provider == "" {
			cfg.Provider = ProviderOpenAI
		}
	}

	svc := &Service{
		config: cfg,
		client: &http.Client{Timeout: 30 * time.Second},
	}

	switch cfg.Provider {
	case ProviderOpenAI:
		if err := svc.initOpenAI(); err != nil {
			return nil, err
		}
	case ProviderLocal:
		if err := svc.initLocal(); err != nil {
			return nil, err
		}
	default:
		return nil, fmt.Errorf("unknown embedding provider: %s", cfg.Provider)
	}

	return svc, nil
}

func (s *Service) initOpenAI() error {
	if s.config.APIKey == "" {
		s.config.APIKey = os.Getenv("OPENAI_API_KEY")
	}
	if s.config.APIKey == "" {
		return fmt.Errorf("OpenAI API key not provided")
	}
	if s.config.Model == "" {
		s.config.Model = os.Getenv("EMBEDDING_MODEL")
		if s.config.Model == "" {
			s.config.Model = "text-embedding-3-small"
		}
	}
	if s.config.BaseURL == "" {
		s.config.BaseURL = "https://api.openai.com/v1"
	}
	return nil
}

func (s *Service) initLocal() error {
	if s.config.Model == "" {
		s.config.Model = DefaultLocalModel
	}
	if s.config.CacheDir == "" {
		s.config.CacheDir = filepath.Join(os.TempDir(), "hugot-models")
	}
	if s.config.MaxLength == 0 {
		s.config.MaxLength = 512
	}

	// Create hugot session with native Go backend
	session, err := hugot.NewGoSession()
	if err != nil {
		return fmt.Errorf("create hugot session: %w", err)
	}
	s.session = session

	// Download model if needed
	modelPath, err := hugot.DownloadModel(s.config.Model, s.config.CacheDir, hugot.NewDownloadOptions())
	if err != nil {
		_ = s.session.Destroy()
		return fmt.Errorf("download model %s: %w", s.config.Model, err)
	}

	// Create feature extraction pipeline
	pipelineConfig := hugot.FeatureExtractionConfig{
		ModelPath: modelPath,
		Name:      "embeddings",
	}
	pipeline, err := hugot.NewPipeline(s.session, pipelineConfig)
	if err != nil {
		_ = s.session.Destroy()
		return fmt.Errorf("create pipeline: %w", err)
	}
	s.pipeline = pipeline

	return nil
}

// Close releases resources used by the service.
func (s *Service) Close() error {
	if s.session != nil {
		_ = s.session.Destroy()
		s.session = nil
	}
	return nil
}

// CleanContent removes SilverBullet syntax noise from text.
func CleanContent(text string) string {
	// Remove front matter delimiters
	text = regexp.MustCompile(`(?m)^---\s*$`).ReplaceAllString(text, "")

	// Convert wikilinks: [[page|alias]] -> alias, [[page]] -> page
	text = regexp.MustCompile(`\[\[([^\]|]+)\|([^\]]+)\]\]`).ReplaceAllString(text, "$2")
	text = regexp.MustCompile(`\[\[([^\]]+)\]\]`).ReplaceAllString(text, "$1")

	// Remove SilverBullet attributes
	text = regexp.MustCompile(`#(\w+)`).ReplaceAllString(text, "$1")
	text = regexp.MustCompile(`@(\w+)`).ReplaceAllString(text, "$1")

	// Normalize whitespace
	text = regexp.MustCompile(`\n\s*\n\s*\n+`).ReplaceAllString(text, "\n\n")
	text = regexp.MustCompile(` +`).ReplaceAllString(text, " ")

	return strings.TrimSpace(text)
}

// GenerateEmbedding generates an embedding for a single text.
func (s *Service) GenerateEmbedding(ctx context.Context, text string, clean bool) ([]float32, error) {
	if clean {
		text = CleanContent(text)
	}

	if strings.TrimSpace(text) == "" {
		return make([]float32, s.GetDimension()), nil
	}

	embeddings, err := s.generateEmbeddings(ctx, []string{text})
	if err != nil {
		return nil, err
	}

	return embeddings[0], nil
}

// GenerateEmbeddingsBatch generates embeddings for multiple texts.
func (s *Service) GenerateEmbeddingsBatch(ctx context.Context, texts []string, clean bool) ([][]float32, error) {
	if clean {
		cleaned := make([]string, len(texts))
		for i, t := range texts {
			cleaned[i] = CleanContent(t)
		}
		texts = cleaned
	}

	// Track which texts are valid
	validTexts := make([]string, 0, len(texts))
	validIndices := make([]int, 0, len(texts))
	for i, t := range texts {
		if strings.TrimSpace(t) != "" {
			validTexts = append(validTexts, t)
			validIndices = append(validIndices, i)
		}
	}

	if len(validTexts) == 0 {
		result := make([][]float32, len(texts))
		dim := s.GetDimension()
		for i := range result {
			result[i] = make([]float32, dim)
		}
		return result, nil
	}

	validEmbeddings, err := s.generateEmbeddings(ctx, validTexts)
	if err != nil {
		return nil, err
	}

	// Build result with zero vectors for empty texts
	result := make([][]float32, len(texts))
	dim := s.GetDimension()
	for i := range result {
		result[i] = make([]float32, dim)
	}
	for i, embedding := range validEmbeddings {
		result[validIndices[i]] = embedding
	}

	return result, nil
}

// GetDimension returns the embedding dimension for the current model.
func (s *Service) GetDimension() int {
	if s.config.Provider == ProviderLocal {
		switch s.config.Model {
		case "BAAI/bge-small-en-v1.5", "BAAI/bge-small-en":
			return 384
		case "BAAI/bge-base-en-v1.5", "BAAI/bge-base-en":
			return 768
		case "sentence-transformers/all-MiniLM-L6-v2":
			return 384
		default:
			return LocalModelDim
		}
	}

	// OpenAI models
	switch s.config.Model {
	case "text-embedding-3-small":
		return 1536
	case "text-embedding-3-large":
		return 3072
	case "text-embedding-ada-002":
		return 1536
	default:
		return 1536
	}
}

// GetProvider returns the configured provider.
func (s *Service) GetProvider() Provider {
	return s.config.Provider
}

// GetModel returns the configured model name.
func (s *Service) GetModel() string {
	return s.config.Model
}

func (s *Service) generateEmbeddings(ctx context.Context, texts []string) ([][]float32, error) {
	switch s.config.Provider {
	case ProviderOpenAI:
		return s.generateOpenAIEmbeddings(ctx, texts)
	case ProviderLocal:
		return s.generateLocalEmbeddings(ctx, texts)
	default:
		return nil, fmt.Errorf("unknown provider: %s", s.config.Provider)
	}
}

func (s *Service) generateLocalEmbeddings(ctx context.Context, texts []string) ([][]float32, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.pipeline == nil {
		return nil, fmt.Errorf("local embedding pipeline not initialized")
	}

	// Run the pipeline
	batchResult, err := s.pipeline.RunPipeline(texts)
	if err != nil {
		return nil, fmt.Errorf("run pipeline: %w", err)
	}

	// FeatureExtractionOutput has Embeddings [][]float32
	return batchResult.Embeddings, nil
}

func (s *Service) generateOpenAIEmbeddings(ctx context.Context, texts []string) ([][]float32, error) {
	reqBody := map[string]any{
		"model": s.config.Model,
		"input": texts,
	}
	reqJSON, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", s.config.BaseURL+"/embeddings", bytes.NewReader(reqJSON))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+s.config.APIKey)

	resp, err := s.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errResp struct {
			Error struct {
				Message string `json:"message"`
			} `json:"error"`
		}
		_ = json.NewDecoder(resp.Body).Decode(&errResp)
		return nil, fmt.Errorf("OpenAI API error (%d): %s", resp.StatusCode, errResp.Error.Message)
	}

	var result struct {
		Data []struct {
			Embedding []float32 `json:"embedding"`
			Index     int       `json:"index"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	// Sort by index to maintain order
	embeddings := make([][]float32, len(result.Data))
	for _, d := range result.Data {
		embeddings[d.Index] = d.Embedding
	}

	return embeddings, nil
}
