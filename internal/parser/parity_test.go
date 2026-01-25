// Package parser provides markdown parsing for SilverBullet spaces.
package parser

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

// normalizedChunk is a simplified chunk structure for comparison.
type normalizedChunk struct {
	Header     string   `json:"header"`
	Content    string   `json:"content"`
	Tags       []string `json:"tags"`
	Links      []string `json:"links"`
	FolderPath string   `json:"folder_path"`
	FilePath   string   `json:"file_path"`
}

// TestParserParityWithGolden compares Go parser output against Python golden file.
func TestParserParityWithGolden(t *testing.T) {
	// Find test space
	testSpace := filepath.Join("..", "..", "test-data", "e2e-space")
	if _, err := os.Stat(testSpace); os.IsNotExist(err) {
		t.Skip("Test space not found at", testSpace)
	}

	// Find golden file
	goldenFile := filepath.Join("..", "..", "tests", "golden", "e2e-space-chunks.json")
	if _, err := os.Stat(goldenFile); os.IsNotExist(err) {
		t.Skip("Golden file not found at", goldenFile)
	}

	// Parse with Go
	parser := NewSpaceParser(testSpace)
	goChunks, err := parser.ParseSpace(testSpace)
	if err != nil {
		t.Fatalf("Go parser failed: %v", err)
	}

	// Convert Go chunks to normalized form
	var goNormalized []normalizedChunk
	for _, chunk := range goChunks {
		nc := normalizedChunk{
			Header:     chunk.Header,
			Content:    strings.TrimSpace(chunk.Content),
			Tags:       chunk.Tags,
			Links:      chunk.Links,
			FolderPath: strings.ReplaceAll(chunk.FolderPath, "\\", "/"),
		}

		// Normalize file path
		fp := strings.ReplaceAll(chunk.FilePath, "\\", "/")
		if idx := strings.Index(fp, "e2e-space/"); idx >= 0 {
			fp = fp[idx+len("e2e-space/"):]
		} else if idx := strings.LastIndex(fp, "/"); idx >= 0 {
			// Just use relative path from space root
			relPath, _ := filepath.Rel(testSpace, chunk.FilePath)
			fp = strings.ReplaceAll(relPath, "\\", "/")
		}
		nc.FilePath = fp

		// Ensure sorted
		sort.Strings(nc.Tags)
		sort.Strings(nc.Links)

		goNormalized = append(goNormalized, nc)
	}

	// Sort by file path + header
	sort.Slice(goNormalized, func(i, j int) bool {
		if goNormalized[i].FilePath != goNormalized[j].FilePath {
			return goNormalized[i].FilePath < goNormalized[j].FilePath
		}
		return goNormalized[i].Header < goNormalized[j].Header
	})

	// Load golden file
	goldenData, err := os.ReadFile(goldenFile)
	if err != nil {
		t.Fatalf("Failed to read golden file: %v", err)
	}

	var pyNormalized []normalizedChunk
	if err := json.Unmarshal(goldenData, &pyNormalized); err != nil {
		t.Fatalf("Failed to parse golden file: %v", err)
	}

	// Sort golden data
	sort.Slice(pyNormalized, func(i, j int) bool {
		if pyNormalized[i].FilePath != pyNormalized[j].FilePath {
			return pyNormalized[i].FilePath < pyNormalized[j].FilePath
		}
		return pyNormalized[i].Header < pyNormalized[j].Header
	})

	// Compare chunk counts
	t.Run("ChunkCount", func(t *testing.T) {
		if len(goNormalized) != len(pyNormalized) {
			t.Errorf("Chunk count mismatch: Go=%d, Python=%d", len(goNormalized), len(pyNormalized))
		}
	})

	// Compare file paths
	t.Run("FilePaths", func(t *testing.T) {
		goFiles := make(map[string]bool)
		pyFiles := make(map[string]bool)

		for _, c := range goNormalized {
			goFiles[c.FilePath] = true
		}
		for _, c := range pyNormalized {
			pyFiles[c.FilePath] = true
		}

		for f := range pyFiles {
			if !goFiles[f] {
				t.Errorf("Python has file %q but Go doesn't", f)
			}
		}
		for f := range goFiles {
			if !pyFiles[f] {
				t.Errorf("Go has file %q but Python doesn't", f)
			}
		}
	})

	// Compare headers for each file
	t.Run("Headers", func(t *testing.T) {
		goHeaders := make(map[string][]string)
		pyHeaders := make(map[string][]string)

		for _, c := range goNormalized {
			goHeaders[c.FilePath] = append(goHeaders[c.FilePath], c.Header)
		}
		for _, c := range pyNormalized {
			pyHeaders[c.FilePath] = append(pyHeaders[c.FilePath], c.Header)
		}

		for file, pyH := range pyHeaders {
			goH := goHeaders[file]
			sort.Strings(pyH)
			sort.Strings(goH)

			if len(pyH) != len(goH) {
				t.Errorf("Header count mismatch for %s: Go=%d, Python=%d", file, len(goH), len(pyH))
				t.Logf("  Python headers: %v", pyH)
				t.Logf("  Go headers: %v", goH)
			}
		}
	})

	// Compare tags
	t.Run("Tags", func(t *testing.T) {
		// Build lookup by file+header
		pyLookup := make(map[string]normalizedChunk)
		for _, c := range pyNormalized {
			key := c.FilePath + "#" + c.Header
			pyLookup[key] = c
		}

		for _, goChunk := range goNormalized {
			key := goChunk.FilePath + "#" + goChunk.Header
			pyChunk, ok := pyLookup[key]
			if !ok {
				continue // Already reported in headers test
			}

			if len(goChunk.Tags) != len(pyChunk.Tags) {
				t.Errorf("Tag count mismatch for %s: Go=%v, Python=%v",
					key, goChunk.Tags, pyChunk.Tags)
				continue
			}

			for i := range goChunk.Tags {
				if goChunk.Tags[i] != pyChunk.Tags[i] {
					t.Errorf("Tag mismatch for %s: Go=%v, Python=%v",
						key, goChunk.Tags, pyChunk.Tags)
					break
				}
			}
		}
	})

	// Compare links
	t.Run("Links", func(t *testing.T) {
		pyLookup := make(map[string]normalizedChunk)
		for _, c := range pyNormalized {
			key := c.FilePath + "#" + c.Header
			pyLookup[key] = c
		}

		for _, goChunk := range goNormalized {
			key := goChunk.FilePath + "#" + goChunk.Header
			pyChunk, ok := pyLookup[key]
			if !ok {
				continue
			}

			if len(goChunk.Links) != len(pyChunk.Links) {
				t.Errorf("Link count mismatch for %s: Go=%v, Python=%v",
					key, goChunk.Links, pyChunk.Links)
				continue
			}

			for i := range goChunk.Links {
				if goChunk.Links[i] != pyChunk.Links[i] {
					t.Errorf("Link mismatch for %s: Go=%v, Python=%v",
						key, goChunk.Links, pyChunk.Links)
					break
				}
			}
		}
	})
}

// TestParserParityContentComparison compares content between Go and Python.
func TestParserParityContentComparison(t *testing.T) {
	testSpace := filepath.Join("..", "..", "test-data", "e2e-space")
	if _, err := os.Stat(testSpace); os.IsNotExist(err) {
		t.Skip("Test space not found")
	}

	goldenFile := filepath.Join("..", "..", "tests", "golden", "e2e-space-chunks.json")
	if _, err := os.Stat(goldenFile); os.IsNotExist(err) {
		t.Skip("Golden file not found")
	}

	// Parse with Go
	parser := NewSpaceParser(testSpace)
	goChunks, err := parser.ParseSpace(testSpace)
	if err != nil {
		t.Fatalf("Go parser failed: %v", err)
	}

	// Load golden
	goldenData, err := os.ReadFile(goldenFile)
	if err != nil {
		t.Fatalf("Failed to read golden file: %v", err)
	}

	var pyChunks []normalizedChunk
	if err := json.Unmarshal(goldenData, &pyChunks); err != nil {
		t.Fatalf("Failed to parse golden file: %v", err)
	}

	// Build Python lookup
	pyLookup := make(map[string]normalizedChunk)
	for _, c := range pyChunks {
		key := c.FilePath + "#" + c.Header
		pyLookup[key] = c
	}

	// Compare content
	for _, goChunk := range goChunks {
		// Normalize Go file path
		fp := strings.ReplaceAll(goChunk.FilePath, "\\", "/")
		if idx := strings.Index(fp, "e2e-space/"); idx >= 0 {
			fp = fp[idx+len("e2e-space/"):]
		} else {
			relPath, _ := filepath.Rel(testSpace, goChunk.FilePath)
			fp = strings.ReplaceAll(relPath, "\\", "/")
		}

		key := fp + "#" + goChunk.Header
		pyChunk, ok := pyLookup[key]
		if !ok {
			continue // Missing chunk already caught
		}

		// Normalize content for comparison
		goContent := strings.Join(strings.Fields(strings.TrimSpace(goChunk.Content)), " ")
		pyContent := strings.Join(strings.Fields(strings.TrimSpace(pyChunk.Content)), " ")

		if goContent != pyContent {
			t.Errorf("Content mismatch for %s:\n  Go: %s\n  Py: %s",
				key, truncate(goContent, 100), truncate(pyContent, 100))
		}
	}
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
