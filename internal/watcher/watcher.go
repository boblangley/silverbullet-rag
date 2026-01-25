// Package watcher provides file system watching for SilverBullet spaces.
package watcher

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/fsnotify/fsnotify"

	"github.com/boblangley/silverbullet-rag/internal/config"
	"github.com/boblangley/silverbullet-rag/internal/db"
	"github.com/boblangley/silverbullet-rag/internal/embeddings"
	"github.com/boblangley/silverbullet-rag/internal/parser"
	"github.com/boblangley/silverbullet-rag/internal/types"
)

// Watcher watches a SilverBullet space for file changes.
type Watcher struct {
	spacePath  string
	db         *db.GraphDB
	parser     *parser.SpaceParser
	embedding  *embeddings.Service
	denoRunner *config.DenoRunner
	dbPath     string
	logger     *slog.Logger

	watcher  *fsnotify.Watcher
	debounce time.Duration
	pending  map[string]time.Time
	mu       sync.Mutex

	// Hash tracking to avoid reprocessing unchanged files
	fileHashes map[string]string
	hashMu     sync.RWMutex

	// Concurrent processing tracking
	currentlyProcessing map[string]bool
	processingMu        sync.Mutex
}

// Config holds watcher configuration.
type Config struct {
	SpacePath  string
	DB         *db.GraphDB
	Embedding  *embeddings.Service
	DenoRunner *config.DenoRunner
	DBPath     string
	Debounce   time.Duration
	Logger     *slog.Logger
}

// New creates a new file watcher.
func New(cfg Config) (*Watcher, error) {
	fsWatcher, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, err
	}

	debounce := cfg.Debounce
	if debounce == 0 {
		debounce = 500 * time.Millisecond
	}

	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	return &Watcher{
		spacePath:           cfg.SpacePath,
		db:                  cfg.DB,
		parser:              parser.NewSpaceParser(cfg.SpacePath),
		embedding:           cfg.Embedding,
		denoRunner:          cfg.DenoRunner,
		dbPath:              cfg.DBPath,
		logger:              logger,
		watcher:             fsWatcher,
		debounce:            debounce,
		pending:             make(map[string]time.Time),
		fileHashes:          make(map[string]string),
		currentlyProcessing: make(map[string]bool),
	}, nil
}

// Start begins watching the space directory.
func (w *Watcher) Start(ctx context.Context) error {
	// Add all directories recursively
	err := filepath.WalkDir(w.spacePath, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}

		if d.IsDir() {
			// Skip hidden directories
			if strings.HasPrefix(d.Name(), ".") {
				return filepath.SkipDir
			}
			return w.watcher.Add(path)
		}
		return nil
	})
	if err != nil {
		return err
	}

	w.logger.Info("started watching space", "path", w.spacePath)

	// Start event processing
	go w.processEvents(ctx)

	// Start debounce processor
	go w.processDebounced(ctx)

	return nil
}

// Stop stops the watcher.
func (w *Watcher) Stop() error {
	return w.watcher.Close()
}

func (w *Watcher) processEvents(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return

		case event, ok := <-w.watcher.Events:
			if !ok {
				return
			}

			// Only handle markdown files
			if !strings.HasSuffix(event.Name, ".md") {
				// Handle new directories
				if event.Op&fsnotify.Create != 0 {
					if info, err := os.Stat(event.Name); err == nil && info.IsDir() {
						_ = w.watcher.Add(event.Name)
					}
				}
				continue
			}

			// Skip proposal files
			if strings.HasSuffix(event.Name, ".proposal") ||
				strings.Contains(event.Name, "_Proposals") ||
				strings.HasSuffix(event.Name, ".rejected.md") {
				continue
			}

			// Queue for debounced processing
			w.mu.Lock()
			w.pending[event.Name] = time.Now()
			w.mu.Unlock()

		case err, ok := <-w.watcher.Errors:
			if !ok {
				return
			}
			w.logger.Error("watcher error", "error", err)
		}
	}
}

func (w *Watcher) processDebounced(ctx context.Context) {
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return

		case <-ticker.C:
			w.mu.Lock()
			now := time.Now()
			var ready []string

			for path, queueTime := range w.pending {
				if now.Sub(queueTime) >= w.debounce {
					ready = append(ready, path)
				}
			}

			for _, path := range ready {
				delete(w.pending, path)
			}
			w.mu.Unlock()

			// Process ready files
			for _, path := range ready {
				w.handleFileChange(ctx, path)
			}
		}
	}
}

// computeFileHash computes MD5 hash of file contents.
func (w *Watcher) computeFileHash(filePath string) (string, error) {
	f, err := os.Open(filePath)
	if err != nil {
		return "", err
	}
	defer f.Close()

	h := md5.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}

	return hex.EncodeToString(h.Sum(nil)), nil
}

// hasContentChanged checks if file content has changed since last index.
func (w *Watcher) hasContentChanged(filePath string) bool {
	currentHash, err := w.computeFileHash(filePath)
	if err != nil {
		// If we can't compute hash, assume changed
		return true
	}

	w.hashMu.RLock()
	storedHash, exists := w.fileHashes[filePath]
	w.hashMu.RUnlock()

	if !exists {
		return true
	}

	return currentHash != storedHash
}

// updateFileHash stores the current hash for a file.
func (w *Watcher) updateFileHash(filePath string) {
	hash, err := w.computeFileHash(filePath)
	if err != nil {
		return
	}

	w.hashMu.Lock()
	w.fileHashes[filePath] = hash
	w.hashMu.Unlock()
}

// clearFileHash removes the stored hash for a file.
func (w *Watcher) clearFileHash(filePath string) {
	w.hashMu.Lock()
	delete(w.fileHashes, filePath)
	w.hashMu.Unlock()
}

// markProcessing marks a file as currently being processed.
// Returns false if already being processed.
func (w *Watcher) markProcessing(filePath string) bool {
	w.processingMu.Lock()
	defer w.processingMu.Unlock()

	if w.currentlyProcessing[filePath] {
		return false
	}

	w.currentlyProcessing[filePath] = true
	return true
}

// unmarkProcessing removes a file from the processing set.
func (w *Watcher) unmarkProcessing(filePath string) {
	w.processingMu.Lock()
	delete(w.currentlyProcessing, filePath)
	w.processingMu.Unlock()
}

func (w *Watcher) handleFileChange(ctx context.Context, filePath string) {
	// Check if already being processed (prevent concurrent processing of same file)
	if !w.markProcessing(filePath) {
		w.logger.Debug("file already being processed, skipping", "path", filePath)
		return
	}
	defer w.unmarkProcessing(filePath)

	w.logger.Info("processing file change", "path", filePath)

	// Check if file still exists
	_, err := os.Stat(filePath)
	fileExists := err == nil

	// Handle CONFIG.md specially
	if filepath.Base(filePath) == "CONFIG.md" {
		if fileExists {
			w.handleConfigChange(ctx, filePath)
		}
		return
	}

	// If file was deleted, remove chunks and hash
	if !fileExists {
		if err := w.db.DeleteChunksByFile(ctx, filePath); err != nil {
			w.logger.Error("failed to delete chunks", "path", filePath, "error", err)
		}
		w.clearFileHash(filePath)
		w.logger.Info("file deleted, chunks removed", "path", filePath)
		return
	}

	// Check if content has actually changed
	if !w.hasContentChanged(filePath) {
		w.logger.Debug("file content unchanged, skipping", "path", filePath)
		return
	}

	// Delete existing chunks for this file
	if err := w.db.DeleteChunksByFile(ctx, filePath); err != nil {
		w.logger.Error("failed to delete chunks", "path", filePath, "error", err)
	}

	// Parse the file
	chunks, err := w.parser.ParseFile(filePath)
	if err != nil {
		w.logger.Error("failed to parse file", "path", filePath, "error", err)
		return
	}

	if len(chunks) == 0 {
		// Update hash even if no chunks (file may be empty or non-indexable)
		w.updateFileHash(filePath)
		return
	}

	// Generate embeddings if enabled
	if w.db.EnableEmbeddings() && w.embedding != nil {
		contents := make([]string, len(chunks))
		for i, c := range chunks {
			contents[i] = c.Content
		}

		embeds, err := w.embedding.GenerateEmbeddingsBatch(ctx, contents, true)
		if err != nil {
			w.logger.Error("failed to generate embeddings", "path", filePath, "error", err)
		} else {
			for i := range chunks {
				chunks[i].Embedding = embeds[i]
			}
		}
	}

	// Index chunks
	if err := w.db.IndexChunks(ctx, chunks); err != nil {
		w.logger.Error("failed to index chunks", "path", filePath, "error", err)
		return
	}

	// Update file hash after successful indexing
	w.updateFileHash(filePath)

	w.logger.Info("reindexed file", "path", filePath, "chunks", len(chunks))
}

func (w *Watcher) handleConfigChange(ctx context.Context, filePath string) {
	content, err := os.ReadFile(filePath)
	if err != nil {
		w.logger.Error("failed to read CONFIG.md", "error", err)
		return
	}

	cfg, err := config.ParseConfigPage(string(content), true, w.denoRunner)
	if err != nil {
		w.logger.Error("failed to parse CONFIG.md", "error", err)
		return
	}

	if err := config.WriteConfigJSON(cfg, w.dbPath); err != nil {
		w.logger.Error("failed to write config JSON", "error", err)
		return
	}

	w.logger.Info("updated space config", "keys", len(cfg))
}

// InitialIndex performs a full index of the space.
func (w *Watcher) InitialIndex(ctx context.Context, rebuild bool) (int, error) {
	w.logger.Info("starting initial index", "rebuild", rebuild)

	if rebuild {
		if err := w.db.ClearDatabase(ctx); err != nil {
			return 0, err
		}
	}

	// Parse the space
	chunks, err := w.parser.ParseSpace(w.spacePath)
	if err != nil {
		return 0, err
	}

	w.logger.Info("parsed space", "chunks", len(chunks))

	// Index folders
	folderPaths, err := w.parser.GetFolderPaths(w.spacePath)
	if err != nil {
		return 0, err
	}

	indexPages, err := w.parser.GetFolderIndexPages(w.spacePath)
	if err != nil {
		return 0, err
	}

	if err := w.db.IndexFolders(ctx, folderPaths, indexPages); err != nil {
		return 0, err
	}

	w.logger.Info("indexed folders", "count", len(folderPaths))

	// Generate embeddings
	if w.db.EnableEmbeddings() && w.embedding != nil {
		contents := make([]string, len(chunks))
		for i, c := range chunks {
			contents[i] = c.Content
		}

		embeds, err := w.embedding.GenerateEmbeddingsBatch(ctx, contents, true)
		if err != nil {
			w.logger.Error("failed to generate embeddings", "error", err)
		} else {
			for i := range chunks {
				chunks[i].Embedding = embeds[i]
			}
		}
	}

	// Index chunks
	if err := w.db.IndexChunks(ctx, convertChunks(chunks)); err != nil {
		return 0, err
	}

	// Populate file hash cache for all indexed files
	w.hashMu.Lock()
	seenFiles := make(map[string]bool)
	for _, chunk := range chunks {
		if !seenFiles[chunk.FilePath] {
			seenFiles[chunk.FilePath] = true
			if hash, err := w.computeFileHash(chunk.FilePath); err == nil {
				w.fileHashes[chunk.FilePath] = hash
			}
		}
	}
	w.hashMu.Unlock()

	w.logger.Info("cached file hashes", "count", len(seenFiles))

	// Handle CONFIG.md
	configPath := filepath.Join(w.spacePath, "CONFIG.md")
	if content, err := os.ReadFile(configPath); err == nil {
		cfg, err := config.ParseConfigPage(string(content), true, w.denoRunner)
		if err == nil {
			_ = config.WriteConfigJSON(cfg, w.dbPath)
			w.logger.Info("wrote space config", "keys", len(cfg))
		}
	}

	w.logger.Info("initial index complete", "chunks", len(chunks))
	return len(chunks), nil
}

func convertChunks(parsed []types.Chunk) []types.Chunk {
	// Already the right type
	return parsed
}
