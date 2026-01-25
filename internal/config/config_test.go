// Package config provides space-lua CONFIG.md parsing via Deno sidecar.
package config

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// ==================== parseValue Tests ====================

func TestParseValueString(t *testing.T) {
	tests := []struct {
		input    string
		expected any
	}{
		{`"hello"`, "hello"},
		{`'hello'`, "hello"},
		{`"_Proposals/"`, "_Proposals/"},
	}

	for _, tc := range tests {
		result := parseValue(tc.input)
		if result != tc.expected {
			t.Errorf("parseValue(%q) = %v, want %v", tc.input, result, tc.expected)
		}
	}
}

func TestParseValueNumber(t *testing.T) {
	tests := []struct {
		input    string
		expected any
	}{
		{"42", 42},
		{"0", 0},
		{"-5", -5},
		{"3.14", 3.14},
		{"0.75", 0.75},
	}

	for _, tc := range tests {
		result := parseValue(tc.input)
		if result != tc.expected {
			t.Errorf("parseValue(%q) = %v (%T), want %v (%T)", tc.input, result, result, tc.expected, tc.expected)
		}
	}
}

func TestParseValueBoolean(t *testing.T) {
	if parseValue("true") != true {
		t.Error("parseValue('true') should return true")
	}
	if parseValue("false") != false {
		t.Error("parseValue('false') should return false")
	}
}

func TestParseValueNil(t *testing.T) {
	if parseValue("nil") != nil {
		t.Error("parseValue('nil') should return nil")
	}
}

// ==================== parseConfigAST Tests ====================

func TestParseConfigASTSimpleString(t *testing.T) {
	luaCode := `config.set("mcp.proposals.path_prefix", "_Proposals/")`

	config, err := parseConfigAST(luaCode)
	if err != nil {
		t.Fatalf("parseConfigAST failed: %v", err)
	}

	if config["mcp.proposals.path_prefix"] != "_Proposals/" {
		t.Errorf("Expected '_Proposals/', got %v", config["mcp.proposals.path_prefix"])
	}
}

func TestParseConfigASTInteger(t *testing.T) {
	luaCode := `config.set("mcp.proposals.cleanup_after_days", 30)`

	config, err := parseConfigAST(luaCode)
	if err != nil {
		t.Fatalf("parseConfigAST failed: %v", err)
	}

	if config["mcp.proposals.cleanup_after_days"] != 30 {
		t.Errorf("Expected 30, got %v", config["mcp.proposals.cleanup_after_days"])
	}
}

func TestParseConfigASTBoolean(t *testing.T) {
	luaCode := `config.set("feature.enabled", true)
config.set("feature.disabled", false)`

	config, err := parseConfigAST(luaCode)
	if err != nil {
		t.Fatalf("parseConfigAST failed: %v", err)
	}

	if config["feature.enabled"] != true {
		t.Errorf("Expected true, got %v", config["feature.enabled"])
	}
	if config["feature.disabled"] != false {
		t.Errorf("Expected false, got %v", config["feature.disabled"])
	}
}

func TestParseConfigASTMultiple(t *testing.T) {
	luaCode := `config.set("mcp.proposals.path_prefix", "_Proposals/")
config.set("mcp.proposals.cleanup_after_days", 14)
config.set("editor.theme", "dark")`

	config, err := parseConfigAST(luaCode)
	if err != nil {
		t.Fatalf("parseConfigAST failed: %v", err)
	}

	if config["mcp.proposals.path_prefix"] != "_Proposals/" {
		t.Errorf("Expected '_Proposals/', got %v", config["mcp.proposals.path_prefix"])
	}
	if config["mcp.proposals.cleanup_after_days"] != 14 {
		t.Errorf("Expected 14, got %v", config["mcp.proposals.cleanup_after_days"])
	}
	if config["editor.theme"] != "dark" {
		t.Errorf("Expected 'dark', got %v", config["editor.theme"])
	}
}

func TestParseConfigASTFloat(t *testing.T) {
	luaCode := `config.set("threshold", 0.75)`

	config, err := parseConfigAST(luaCode)
	if err != nil {
		t.Fatalf("parseConfigAST failed: %v", err)
	}

	if config["threshold"] != 0.75 {
		t.Errorf("Expected 0.75, got %v", config["threshold"])
	}
}

func TestParseConfigASTVariableReference(t *testing.T) {
	// AST parser can't resolve variable references - should return nil
	luaCode := `local x = 10
config.set("computed", x)`

	config, err := parseConfigAST(luaCode)
	if err != nil {
		t.Fatalf("parseConfigAST failed: %v", err)
	}

	// AST parser sees config.set("computed", x) but x is a variable, not literal
	if config["computed"] != nil {
		t.Errorf("Variable reference should return nil, got %v", config["computed"])
	}
}

// ==================== extractSpaceLuaBlocks Tests ====================

func TestExtractSpaceLuaBlocks(t *testing.T) {
	content := "# Configuration\n\n```space-lua\nconfig.set(\"key\", \"value\")\n```\n"

	blocks := extractSpaceLuaBlocks(content)

	if len(blocks) != 1 {
		t.Fatalf("Expected 1 block, got %d", len(blocks))
	}
	if blocks[0] != `config.set("key", "value")` {
		t.Errorf("Unexpected block content: %q", blocks[0])
	}
}

func TestExtractMultipleSpaceLuaBlocks(t *testing.T) {
	content := `# Config Part 1

` + "```space-lua\n" + `config.set("section1.key", "value1")
` + "```\n\n# Config Part 2\n\n```space-lua\n" + `config.set("section2.key", "value2")
` + "```"

	blocks := extractSpaceLuaBlocks(content)

	if len(blocks) != 2 {
		t.Fatalf("Expected 2 blocks, got %d", len(blocks))
	}
}

func TestExtractSpaceLuaBlocksNoBlocks(t *testing.T) {
	content := "# Just Markdown\n\nNo lua blocks here."

	blocks := extractSpaceLuaBlocks(content)

	if len(blocks) != 0 {
		t.Errorf("Expected 0 blocks, got %d", len(blocks))
	}
}

// ==================== ParseConfigPage Tests ====================

func TestParseConfigPageSimple(t *testing.T) {
	content := `# Configuration

` + "```space-lua\n" + `config.set("mcp.proposals.path_prefix", "_Proposals/")
` + "```\n"

	config, err := ParseConfigPage(content, false, nil)
	if err != nil {
		t.Fatalf("ParseConfigPage failed: %v", err)
	}

	if config == nil {
		t.Fatal("Config should not be nil")
	}
	if config["mcp.proposals.path_prefix"] != "_Proposals/" {
		t.Errorf("Expected '_Proposals/', got %v", config["mcp.proposals.path_prefix"])
	}
}

func TestParseConfigPageEmpty(t *testing.T) {
	config, err := ParseConfigPage("", false, nil)
	if err != nil {
		t.Fatalf("ParseConfigPage failed: %v", err)
	}

	if config != nil {
		t.Errorf("Empty content should return nil config, got %v", config)
	}
}

func TestParseConfigPageNoLuaBlocks(t *testing.T) {
	content := "# Just Markdown\n\nNo lua blocks here."

	config, err := ParseConfigPage(content, false, nil)
	if err != nil {
		t.Fatalf("ParseConfigPage failed: %v", err)
	}

	if config != nil {
		t.Errorf("No lua blocks should return nil config, got %v", config)
	}
}

func TestParseConfigPageWithComments(t *testing.T) {
	content := "```space-lua\n-- This is a comment\nconfig.set(\"key\", \"value\")\n-- Another comment\n```"

	config, err := ParseConfigPage(content, false, nil)
	if err != nil {
		t.Fatalf("ParseConfigPage failed: %v", err)
	}

	if config["key"] != "value" {
		t.Errorf("Expected 'value', got %v", config["key"])
	}
}

func TestParseConfigPageRealWorld(t *testing.T) {
	content := `---
displayName: Configuration
---

# Space Configuration

This page configures your Silverbullet space.

## AI Proposals

` + "```space-lua\n" + `-- Configure where proposals are stored
config.set("mcp.proposals.path_prefix", "_Proposals/")

-- Auto-cleanup rejected proposals after this many days
config.set("mcp.proposals.cleanup_after_days", 30)
` + "```\n\n## Editor Settings\n\n```space-lua\n" + `config.set("editor.vim_mode", true)
config.set("editor.line_numbers", true)
` + "```"

	config, err := ParseConfigPage(content, false, nil)
	if err != nil {
		t.Fatalf("ParseConfigPage failed: %v", err)
	}

	if config["mcp.proposals.path_prefix"] != "_Proposals/" {
		t.Errorf("path_prefix wrong: %v", config["mcp.proposals.path_prefix"])
	}
	if config["mcp.proposals.cleanup_after_days"] != 30 {
		t.Errorf("cleanup_after_days wrong: %v", config["mcp.proposals.cleanup_after_days"])
	}
	if config["editor.vim_mode"] != true {
		t.Errorf("vim_mode wrong: %v", config["editor.vim_mode"])
	}
	if config["editor.line_numbers"] != true {
		t.Errorf("line_numbers wrong: %v", config["editor.line_numbers"])
	}
}

// ==================== WriteConfigJSON / LoadConfigJSON Tests ====================

func TestWriteAndLoadConfigJSON(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "test_config_")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	config := map[string]any{
		"mcp.proposals.path_prefix": "_Proposals/",
		"editor.theme":              "dark",
	}

	err = WriteConfigJSON(config, tmpDir)
	if err != nil {
		t.Fatalf("WriteConfigJSON failed: %v", err)
	}

	loaded, err := LoadConfigJSON(tmpDir)
	if err != nil {
		t.Fatalf("LoadConfigJSON failed: %v", err)
	}

	if loaded["mcp.proposals.path_prefix"] != "_Proposals/" {
		t.Errorf("Loaded config wrong: %v", loaded)
	}
}

func TestLoadConfigJSONNonexistent(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "test_config_")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	_, err = LoadConfigJSON(tmpDir)
	if err == nil {
		t.Error("Expected error for nonexistent file")
	}
}

func TestWriteConfigJSONCreatesParentDirs(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "test_config_")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	dbPath := filepath.Join(tmpDir, "deeply", "nested", "path")

	config := map[string]any{"key": "value"}
	err = WriteConfigJSON(config, dbPath)
	if err != nil {
		t.Fatalf("WriteConfigJSON failed: %v", err)
	}

	configPath := filepath.Join(dbPath, "space_config.json")
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		t.Error("Config file should exist")
	}

	data, _ := os.ReadFile(configPath)
	var loaded map[string]any
	json.Unmarshal(data, &loaded)
	if loaded["key"] != "value" {
		t.Errorf("Loaded config wrong: %v", loaded)
	}
}

// ==================== parseTable Tests ====================

func TestParseTableSimple(t *testing.T) {
	result := parseTable(`{ theme = "dark" }`)

	if result["theme"] != "dark" {
		t.Errorf("Expected 'dark', got %v", result["theme"])
	}
}

func TestParseTableMultipleKeys(t *testing.T) {
	result := parseTable(`{ theme = "dark", enabled = true }`)

	if result["theme"] != "dark" {
		t.Errorf("Expected 'dark', got %v", result["theme"])
	}
	if result["enabled"] != true {
		t.Errorf("Expected true, got %v", result["enabled"])
	}
}

func TestParseTableEmpty(t *testing.T) {
	result := parseTable(`{}`)

	if len(result) != 0 {
		t.Errorf("Expected empty table, got %v", result)
	}
}

func TestParseTableNumbers(t *testing.T) {
	result := parseTable(`{ max_items = 100, threshold = 0.5 }`)

	if result["max_items"] != 100 {
		t.Errorf("Expected 100, got %v", result["max_items"])
	}
	if result["threshold"] != 0.5 {
		t.Errorf("Expected 0.5, got %v", result["threshold"])
	}
}

// ==================== Deno Tests ====================

func TestFindDeno(t *testing.T) {
	// This test just verifies FindDeno doesn't crash
	// It may or may not find deno depending on the environment
	path := FindDeno()
	t.Logf("FindDeno returned: %q", path)
}

func TestDenoRunnerWithoutDeno(t *testing.T) {
	runner := NewDenoRunner("", "", "")

	_, err := runner.Execute(context.TODO(), `config.set("key", "value")`)
	if err == nil {
		t.Error("Should fail without deno")
	}
}

// Helper to get a Deno runner for tests, skips if Deno not available
func getTestDenoRunner(t *testing.T) *DenoRunner {
	t.Helper()

	denoPath := FindDeno()
	if denoPath == "" {
		t.Skip("Deno not available, skipping Deno execution test")
	}

	// Find project root from test execution directory
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("Failed to get working directory: %v", err)
	}

	// Navigate up to project root (from internal/config to root)
	projectRoot := filepath.Join(cwd, "..", "..")
	runnerPath := filepath.Join(projectRoot, "deno", "space_lua_runner.ts")
	denoDir := filepath.Join(projectRoot, "deno")

	if _, err := os.Stat(runnerPath); os.IsNotExist(err) {
		t.Skipf("Deno runner not found at %s", runnerPath)
	}

	return NewDenoRunner(denoPath, runnerPath, denoDir)
}

// ==================== Deno Execution Tests ====================
// These tests verify features that only work with actual Lua execution
// via Deno, matching Python's TestDenoExecution class.

func TestDenoComputedValue(t *testing.T) {
	runner := getTestDenoRunner(t)

	config, err := runner.Execute(context.Background(), `
local x = 10 + 5
config.set("computed", x * 2)
`)
	if err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	// With Deno: computed = 30
	val, ok := config["computed"].(float64)
	if !ok || val != 30 {
		t.Errorf("Expected computed=30, got %v (%T)", config["computed"], config["computed"])
	}
}

func TestDenoLocalVariable(t *testing.T) {
	runner := getTestDenoRunner(t)

	config, err := runner.Execute(context.Background(), `
local prefix = "_Proposals/"
config.set("mcp.proposals.path_prefix", prefix)
`)
	if err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	// Deno returns nested structure: {"mcp": {"proposals": {"path_prefix": "_Proposals/"}}}
	mcp, ok := config["mcp"].(map[string]any)
	if !ok {
		t.Fatalf("Expected mcp to be map, got %T", config["mcp"])
	}
	proposals, ok := mcp["proposals"].(map[string]any)
	if !ok {
		t.Fatalf("Expected proposals to be map, got %T", mcp["proposals"])
	}
	if proposals["path_prefix"] != "_Proposals/" {
		t.Errorf("Expected '_Proposals/', got %v", proposals["path_prefix"])
	}
}

func TestDenoStringConcatenation(t *testing.T) {
	runner := getTestDenoRunner(t)

	config, err := runner.Execute(context.Background(), `
local base = "proposals"
local suffix = "_v2"
config.set("feature", base .. suffix)
`)
	if err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	if config["feature"] != "proposals_v2" {
		t.Errorf("Expected 'proposals_v2', got %v", config["feature"])
	}
}

func TestDenoArithmeticOperations(t *testing.T) {
	runner := getTestDenoRunner(t)

	config, err := runner.Execute(context.Background(), `
config.set("sum", 10 + 5)
config.set("product", 3 * 4)
config.set("division", 20 / 4)
config.set("subtraction", 100 - 42)
`)
	if err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	tests := map[string]float64{
		"sum":         15,
		"product":     12,
		"division":    5,
		"subtraction": 58,
	}

	for key, expected := range tests {
		val, ok := config[key].(float64)
		if !ok || val != expected {
			t.Errorf("%s: expected %v, got %v (%T)", key, expected, config[key], config[key])
		}
	}
}

func TestDenoConditionalConfig(t *testing.T) {
	runner := getTestDenoRunner(t)

	config, err := runner.Execute(context.Background(), `
local debug = true
if debug then
    config.set("log_level", "debug")
else
    config.set("log_level", "info")
end
`)
	if err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	if config["log_level"] != "debug" {
		t.Errorf("Expected 'debug', got %v", config["log_level"])
	}
}

func TestDenoConditionalFalseBranch(t *testing.T) {
	runner := getTestDenoRunner(t)

	config, err := runner.Execute(context.Background(), `
local debug = false
if debug then
    config.set("log_level", "debug")
else
    config.set("log_level", "info")
end
`)
	if err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	if config["log_level"] != "info" {
		t.Errorf("Expected 'info', got %v", config["log_level"])
	}
}

func TestDenoFunctionDefinitionAndCall(t *testing.T) {
	runner := getTestDenoRunner(t)

	config, err := runner.Execute(context.Background(), `
local function make_path(name)
    return "_Storage/" .. name .. "/"
end

config.set("cache.path", make_path("cache"))
config.set("logs.path", make_path("logs"))
`)
	if err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	// Deno returns nested structure: {"cache": {"path": "..."}, "logs": {"path": "..."}}
	cache, ok := config["cache"].(map[string]any)
	if !ok {
		t.Fatalf("Expected cache to be map, got %T", config["cache"])
	}
	if cache["path"] != "_Storage/cache/" {
		t.Errorf("Expected '_Storage/cache/', got %v", cache["path"])
	}

	logs, ok := config["logs"].(map[string]any)
	if !ok {
		t.Fatalf("Expected logs to be map, got %T", config["logs"])
	}
	if logs["path"] != "_Storage/logs/" {
		t.Errorf("Expected '_Storage/logs/', got %v", logs["path"])
	}
}

func TestDenoTableConstruction(t *testing.T) {
	runner := getTestDenoRunner(t)

	config, err := runner.Execute(context.Background(), `
local settings = {
    enabled = true,
    max_items = 50 + 50
}
config.set("feature", settings)
`)
	if err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	feature, ok := config["feature"].(map[string]any)
	if !ok {
		t.Fatalf("Expected feature to be map, got %T", config["feature"])
	}

	if feature["enabled"] != true {
		t.Errorf("Expected enabled=true, got %v", feature["enabled"])
	}

	maxItems, ok := feature["max_items"].(float64)
	if !ok || maxItems != 100 {
		t.Errorf("Expected max_items=100, got %v", feature["max_items"])
	}
}

func TestDenoParseConfigPageWithComputation(t *testing.T) {
	runner := getTestDenoRunner(t)

	content := "```space-lua\n" + `
local x = 10 + 5
config.set("computed", x * 2)
` + "\n```"

	config, err := ParseConfigPage(content, true, runner)
	if err != nil {
		t.Fatalf("ParseConfigPage failed: %v", err)
	}

	val, ok := config["computed"].(float64)
	if !ok || val != 30 {
		t.Errorf("Expected computed=30, got %v (%T)", config["computed"], config["computed"])
	}
}

func TestDenoParseConfigPageCrossBlockReferences(t *testing.T) {
	runner := getTestDenoRunner(t)

	content := "```space-lua\n" + `
local base_path = "_AI/"
` + "\n```\n\nSome markdown in between.\n\n```space-lua\n" + `
config.set("proposals.path", base_path .. "Proposals/")
config.set("drafts.path", base_path .. "Drafts/")
` + "\n```"

	config, err := ParseConfigPage(content, true, runner)
	if err != nil {
		t.Fatalf("ParseConfigPage failed: %v", err)
	}

	// Deno returns nested structure: {"proposals": {"path": "..."}, "drafts": {"path": "..."}}
	proposals, ok := config["proposals"].(map[string]any)
	if !ok {
		t.Fatalf("Expected proposals to be map, got %T", config["proposals"])
	}
	if proposals["path"] != "_AI/Proposals/" {
		t.Errorf("Expected '_AI/Proposals/', got %v", proposals["path"])
	}

	drafts, ok := config["drafts"].(map[string]any)
	if !ok {
		t.Fatalf("Expected drafts to be map, got %T", config["drafts"])
	}
	if drafts["path"] != "_AI/Drafts/" {
		t.Errorf("Expected '_AI/Drafts/', got %v", drafts["path"])
	}
}
