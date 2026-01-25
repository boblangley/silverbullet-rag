// Package config provides space-lua CONFIG.md parsing via Deno sidecar.
package config

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

// DenoRunner executes space-lua code using the Deno runtime.
type DenoRunner struct {
	denoPath   string
	runnerPath string
	denoDir    string
}

// NewDenoRunner creates a new Deno runner.
func NewDenoRunner(denoPath, runnerPath, denoDir string) *DenoRunner {
	return &DenoRunner{
		denoPath:   denoPath,
		runnerPath: runnerPath,
		denoDir:    denoDir,
	}
}

// FindDeno locates the deno executable.
func FindDeno() string {
	// Check common locations
	paths := []string{
		"deno",
		"/usr/local/bin/deno",
		"/usr/bin/deno",
		filepath.Join(os.Getenv("HOME"), ".deno", "bin", "deno"),
	}

	for _, p := range paths {
		if path, err := exec.LookPath(p); err == nil {
			return path
		}
	}

	return ""
}

// Execute runs space-lua code and returns the config values.
func (r *DenoRunner) Execute(ctx context.Context, luaCode string) (map[string]any, error) {
	if r.denoPath == "" {
		return nil, fmt.Errorf("deno not found")
	}

	input := map[string]string{"luaCode": luaCode}
	inputJSON, err := json.Marshal(input)
	if err != nil {
		return nil, fmt.Errorf("marshal input: %w", err)
	}

	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, r.denoPath, "run", "--allow-read", "--allow-env", r.runnerPath)
	cmd.Dir = r.denoDir
	cmd.Stdin = strings.NewReader(string(inputJSON))

	output, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("execute deno: %w", err)
	}

	var result struct {
		Success bool           `json:"success"`
		Config  map[string]any `json:"config"`
		Error   string         `json:"error"`
	}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, fmt.Errorf("unmarshal output: %w", err)
	}

	if !result.Success {
		return nil, fmt.Errorf("space-lua error: %s", result.Error)
	}

	return result.Config, nil
}

// ParseConfigPage parses a CONFIG.md file content.
func ParseConfigPage(content string, useDeno bool, runner *DenoRunner) (map[string]any, error) {
	// Extract all space-lua blocks
	luaBlocks := extractSpaceLuaBlocks(content)
	if len(luaBlocks) == 0 {
		return nil, nil
	}

	combinedLua := strings.Join(luaBlocks, "\n")

	// Try Deno execution first
	if useDeno && runner != nil {
		config, err := runner.Execute(context.Background(), combinedLua)
		if err == nil {
			return config, nil
		}
		// Fall through to AST parsing on error
	}

	// Fallback to AST parsing
	return parseConfigAST(combinedLua)
}

// extractSpaceLuaBlocks extracts space-lua code blocks from markdown.
func extractSpaceLuaBlocks(content string) []string {
	pattern := regexp.MustCompile("(?s)```space-lua\\s*\\n(.*?)\\n```")
	matches := pattern.FindAllStringSubmatch(content, -1)

	var blocks []string
	for _, m := range matches {
		blocks = append(blocks, m[1])
	}
	return blocks
}

// parseConfigAST provides basic static extraction of config.set() calls.
// This is a fallback when Deno is not available.
func parseConfigAST(luaCode string) (map[string]any, error) {
	config := make(map[string]any)

	// Simple regex-based extraction for config.set("key", value)
	// This handles basic cases but not computed values
	pattern := regexp.MustCompile(`config\.set\s*\(\s*["']([^"']+)["']\s*,\s*(.+?)\s*\)`)
	matches := pattern.FindAllStringSubmatch(luaCode, -1)

	for _, m := range matches {
		key := m[1]
		valueStr := strings.TrimSpace(m[2])

		// Try to parse the value
		value := parseValue(valueStr)
		if value != nil {
			config[key] = value
		}
	}

	return config, nil
}

// parseValue attempts to parse a Lua value literal.
func parseValue(s string) any {
	s = strings.TrimSpace(s)

	// Boolean
	if s == "true" {
		return true
	}
	if s == "false" {
		return false
	}

	// Nil
	if s == "nil" {
		return nil
	}

	// String
	if (strings.HasPrefix(s, `"`) && strings.HasSuffix(s, `"`)) ||
		(strings.HasPrefix(s, `'`) && strings.HasSuffix(s, `'`)) {
		return s[1 : len(s)-1]
	}

	// Number (try int then float)
	var intVal int
	if _, err := fmt.Sscanf(s, "%d", &intVal); err == nil {
		// Make sure it's actually just a number
		if fmt.Sprintf("%d", intVal) == s {
			return intVal
		}
	}

	var floatVal float64
	if _, err := fmt.Sscanf(s, "%f", &floatVal); err == nil {
		return floatVal
	}

	// Table (basic case: { key = value, ... })
	if strings.HasPrefix(s, "{") && strings.HasSuffix(s, "}") {
		return parseTable(s)
	}

	// Unknown or expression - return nil (can't evaluate)
	return nil
}

// parseTable attempts to parse a simple Lua table literal.
func parseTable(s string) map[string]any {
	s = strings.TrimPrefix(s, "{")
	s = strings.TrimSuffix(s, "}")
	s = strings.TrimSpace(s)

	if s == "" {
		return make(map[string]any)
	}

	result := make(map[string]any)

	// Simple key=value parsing (doesn't handle nested tables well)
	parts := strings.Split(s, ",")
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if idx := strings.Index(part, "="); idx > 0 {
			key := strings.TrimSpace(part[:idx])
			valueStr := strings.TrimSpace(part[idx+1:])
			if val := parseValue(valueStr); val != nil {
				result[key] = val
			}
		}
	}

	return result
}

// WriteConfigJSON writes the config to a JSON file.
func WriteConfigJSON(config map[string]any, dbPath string) error {
	if err := os.MkdirAll(dbPath, 0755); err != nil {
		return fmt.Errorf("create directory: %w", err)
	}

	configPath := filepath.Join(dbPath, "space_config.json")
	data, err := json.MarshalIndent(config, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal config: %w", err)
	}

	return os.WriteFile(configPath, data, 0644)
}

// LoadConfigJSON loads the config from a JSON file.
func LoadConfigJSON(dbPath string) (map[string]any, error) {
	configPath := filepath.Join(dbPath, "space_config.json")
	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, err
	}

	var config map[string]any
	if err := json.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("unmarshal config: %w", err)
	}

	return config, nil
}
