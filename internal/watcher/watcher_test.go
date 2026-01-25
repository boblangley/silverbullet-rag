package watcher

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/boblangley/silverbullet-rag/internal/db"
)

func createTempDB(t *testing.T) (*db.GraphDB, string) {
	t.Helper()
	tmpDir, err := os.MkdirTemp("", "watcher-test-db-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	t.Cleanup(func() { os.RemoveAll(tmpDir) })

	dbPath := filepath.Join(tmpDir, "test.db")
	graphDB, err := db.Open(db.Config{
		Path:             dbPath,
		EnableEmbeddings: false,
		AutoRecover:      true,
	})
	if err != nil {
		t.Fatalf("failed to open database: %v", err)
	}
	t.Cleanup(func() { graphDB.Close() })

	return graphDB, tmpDir
}

func createTempSpace(t *testing.T) string {
	t.Helper()
	tmpDir, err := os.MkdirTemp("", "watcher-test-space-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	t.Cleanup(func() { os.RemoveAll(tmpDir) })

	// Create some test markdown files
	testFile := filepath.Join(tmpDir, "test.md")
	content := `---
tags:
- test
---
# Test Page

This is test content.
`
	if err := os.WriteFile(testFile, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	return tmpDir
}

func TestNewWatcher(t *testing.T) {
	graphDB, dbPath := createTempDB(t)
	spacePath := createTempSpace(t)

	w, err := New(Config{
		SpacePath: spacePath,
		DB:        graphDB,
		DBPath:    dbPath,
	})
	if err != nil {
		t.Fatalf("New() failed: %v", err)
	}
	defer w.Stop()

	if w.spacePath != spacePath {
		t.Errorf("spacePath = %s, want %s", w.spacePath, spacePath)
	}
	if w.debounce != 500*time.Millisecond {
		t.Errorf("debounce = %v, want 500ms", w.debounce)
	}
}

func TestNewWatcherCustomDebounce(t *testing.T) {
	graphDB, dbPath := createTempDB(t)
	spacePath := createTempSpace(t)

	customDebounce := 100 * time.Millisecond
	w, err := New(Config{
		SpacePath: spacePath,
		DB:        graphDB,
		DBPath:    dbPath,
		Debounce:  customDebounce,
	})
	if err != nil {
		t.Fatalf("New() failed: %v", err)
	}
	defer w.Stop()

	if w.debounce != customDebounce {
		t.Errorf("debounce = %v, want %v", w.debounce, customDebounce)
	}
}

func TestWatcherStartStop(t *testing.T) {
	graphDB, dbPath := createTempDB(t)
	spacePath := createTempSpace(t)

	w, err := New(Config{
		SpacePath: spacePath,
		DB:        graphDB,
		DBPath:    dbPath,
	})
	if err != nil {
		t.Fatalf("New() failed: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	if err := w.Start(ctx); err != nil {
		t.Fatalf("Start() failed: %v", err)
	}

	// Give it a moment to start
	time.Sleep(50 * time.Millisecond)

	if err := w.Stop(); err != nil {
		t.Errorf("Stop() failed: %v", err)
	}
}

func TestInitialIndex(t *testing.T) {
	graphDB, dbPath := createTempDB(t)
	spacePath := createTempSpace(t)

	w, err := New(Config{
		SpacePath: spacePath,
		DB:        graphDB,
		DBPath:    dbPath,
	})
	if err != nil {
		t.Fatalf("New() failed: %v", err)
	}
	defer w.Stop()

	ctx := context.Background()
	count, err := w.InitialIndex(ctx, false)
	if err != nil {
		t.Fatalf("InitialIndex() failed: %v", err)
	}

	if count == 0 {
		t.Error("InitialIndex() returned 0 chunks, expected at least 1")
	}
}

func TestInitialIndexWithRebuild(t *testing.T) {
	graphDB, dbPath := createTempDB(t)
	spacePath := createTempSpace(t)

	w, err := New(Config{
		SpacePath: spacePath,
		DB:        graphDB,
		DBPath:    dbPath,
	})
	if err != nil {
		t.Fatalf("New() failed: %v", err)
	}
	defer w.Stop()

	ctx := context.Background()

	// First index
	count1, err := w.InitialIndex(ctx, false)
	if err != nil {
		t.Fatalf("first InitialIndex() failed: %v", err)
	}

	// Second index with rebuild
	count2, err := w.InitialIndex(ctx, true)
	if err != nil {
		t.Fatalf("second InitialIndex() with rebuild failed: %v", err)
	}

	// Should have same number of chunks
	if count1 != count2 {
		t.Errorf("chunk counts differ: first=%d, rebuild=%d", count1, count2)
	}
}

func TestFileChangeDetection(t *testing.T) {
	// Skip this test as it requires concurrent database access which can cause
	// issues with the LadybugDB CGO library in test environments
	t.Skip("Skipping file change detection test due to CGO concurrency issues")
}

func TestSkipsProposalFiles(t *testing.T) {
	graphDB, dbPath := createTempDB(t)
	spacePath := createTempSpace(t)

	// Create a proposal file
	proposalDir := filepath.Join(spacePath, "_Proposals")
	if err := os.MkdirAll(proposalDir, 0755); err != nil {
		t.Fatalf("failed to create proposals dir: %v", err)
	}

	proposalFile := filepath.Join(proposalDir, "test.proposal")
	if err := os.WriteFile(proposalFile, []byte("proposal content"), 0644); err != nil {
		t.Fatalf("failed to write proposal file: %v", err)
	}

	w, err := New(Config{
		SpacePath: spacePath,
		DB:        graphDB,
		DBPath:    dbPath,
	})
	if err != nil {
		t.Fatalf("New() failed: %v", err)
	}
	defer w.Stop()

	ctx := context.Background()

	// Index should not include proposal files
	_, err = w.InitialIndex(ctx, false)
	if err != nil {
		t.Fatalf("InitialIndex() failed: %v", err)
	}

	// Check that proposal file is not indexed
	results, err := graphDB.Execute(ctx, `MATCH (c:Chunk) WHERE c.file_path CONTAINS ".proposal" RETURN c`, nil)
	if err != nil {
		t.Fatalf("query failed: %v", err)
	}

	if len(results) > 0 {
		t.Error("proposal files should not be indexed")
	}
}

func TestSkipsHiddenDirectories(t *testing.T) {
	graphDB, dbPath := createTempDB(t)
	spacePath := createTempSpace(t)

	// Create a hidden directory with a markdown file
	hiddenDir := filepath.Join(spacePath, ".hidden")
	if err := os.MkdirAll(hiddenDir, 0755); err != nil {
		t.Fatalf("failed to create hidden dir: %v", err)
	}

	hiddenFile := filepath.Join(hiddenDir, "secret.md")
	if err := os.WriteFile(hiddenFile, []byte("# Secret\nThis should not be indexed."), 0644); err != nil {
		t.Fatalf("failed to write hidden file: %v", err)
	}

	w, err := New(Config{
		SpacePath: spacePath,
		DB:        graphDB,
		DBPath:    dbPath,
	})
	if err != nil {
		t.Fatalf("New() failed: %v", err)
	}
	defer w.Stop()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	if err := w.Start(ctx); err != nil {
		t.Fatalf("Start() failed: %v", err)
	}

	// Check that the hidden directory is not watched
	// The watcher should have skipped it during Start()
	time.Sleep(50 * time.Millisecond)

	// This is a bit tricky to test directly, but we can verify
	// that the initial index doesn't include hidden files
	_, err = w.InitialIndex(ctx, false)
	if err != nil {
		t.Fatalf("InitialIndex() failed: %v", err)
	}

	results, err := graphDB.Execute(ctx, `MATCH (c:Chunk) WHERE c.file_path CONTAINS ".hidden" RETURN c`, nil)
	if err != nil {
		t.Fatalf("query failed: %v", err)
	}

	if len(results) > 0 {
		t.Error("hidden directory files should not be indexed")
	}
}

func TestConfigMDHandling(t *testing.T) {
	graphDB, dbPath := createTempDB(t)
	spacePath := createTempSpace(t)

	// Create CONFIG.md
	configContent := "# CONFIG\n\n```space-lua\nconfig.set(\"test_setting\", \"test_value\")\n```\n"
	configPath := filepath.Join(spacePath, "CONFIG.md")
	if err := os.WriteFile(configPath, []byte(configContent), 0644); err != nil {
		t.Fatalf("failed to write CONFIG.md: %v", err)
	}

	w, err := New(Config{
		SpacePath: spacePath,
		DB:        graphDB,
		DBPath:    dbPath,
	})
	if err != nil {
		t.Fatalf("New() failed: %v", err)
	}
	defer w.Stop()

	ctx := context.Background()

	// Initial index should process CONFIG.md
	_, err = w.InitialIndex(ctx, false)
	if err != nil {
		t.Fatalf("InitialIndex() failed: %v", err)
	}

	// Check if config.json was created (even with AST fallback)
	configJSONPath := filepath.Join(dbPath, "config.json")
	if _, err := os.Stat(configJSONPath); err == nil {
		// Config JSON was created
		content, _ := os.ReadFile(configJSONPath)
		if len(content) > 0 {
			t.Logf("Config JSON created: %s", string(content))
		}
	}
}

func TestFileDeletion(t *testing.T) {
	// Skip this test as it requires concurrent database access which can cause
	// issues with the LadybugDB CGO library in test environments
	t.Skip("Skipping file deletion test due to CGO concurrency issues")
}

func TestNestedDirectoryWatching(t *testing.T) {
	graphDB, dbPath := createTempDB(t)
	spacePath := createTempSpace(t)

	// Create nested directories
	nestedDir := filepath.Join(spacePath, "level1", "level2")
	if err := os.MkdirAll(nestedDir, 0755); err != nil {
		t.Fatalf("failed to create nested dirs: %v", err)
	}

	nestedFile := filepath.Join(nestedDir, "nested.md")
	if err := os.WriteFile(nestedFile, []byte("# Nested\nContent"), 0644); err != nil {
		t.Fatalf("failed to write nested file: %v", err)
	}

	w, err := New(Config{
		SpacePath: spacePath,
		DB:        graphDB,
		DBPath:    dbPath,
	})
	if err != nil {
		t.Fatalf("New() failed: %v", err)
	}
	defer w.Stop()

	ctx := context.Background()

	// Index should include nested files
	_, err = w.InitialIndex(ctx, false)
	if err != nil {
		t.Fatalf("InitialIndex() failed: %v", err)
	}

	results, err := graphDB.Execute(ctx, `MATCH (c:Chunk) WHERE c.file_path CONTAINS "nested.md" RETURN c`, nil)
	if err != nil {
		t.Fatalf("query failed: %v", err)
	}

	if len(results) == 0 {
		t.Error("nested directory files should be indexed")
	}
}
