// Package parser provides markdown parsing for SilverBullet spaces.
package parser

import (
	"os"
	"path/filepath"
	"testing"
)

// Helper function to create a temp space directory
func createTempSpace(t *testing.T) string {
	t.Helper()
	dir, err := os.MkdirTemp("", "test_space_")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	t.Cleanup(func() { os.RemoveAll(dir) })
	return dir
}

// Helper function to write a markdown file
func writeMarkdownFile(t *testing.T, dir, name, content string) string {
	t.Helper()
	filePath := filepath.Join(dir, name)
	if err := os.MkdirAll(filepath.Dir(filePath), 0755); err != nil {
		t.Fatalf("Failed to create directory: %v", err)
	}
	if err := os.WriteFile(filePath, []byte(content), 0644); err != nil {
		t.Fatalf("Failed to write file: %v", err)
	}
	return filePath
}

// ==================== Transclusion Tests ====================

func TestExtractSimpleTransclusion(t *testing.T) {
	parser := NewSpaceParser("")
	content := "Some text before ![[MyPage]] and after."
	transclusions := parser.extractTransclusions(content)

	if len(transclusions) != 1 {
		t.Fatalf("Expected 1 transclusion, got %d", len(transclusions))
	}
	if transclusions[0].TargetPage != "MyPage" {
		t.Errorf("Expected target page 'MyPage', got '%s'", transclusions[0].TargetPage)
	}
	if transclusions[0].TargetHeader != "" {
		t.Errorf("Expected empty target header, got '%s'", transclusions[0].TargetHeader)
	}
}

func TestExtractTransclusionWithHeader(t *testing.T) {
	parser := NewSpaceParser("")
	content := "Include this section ![[Documentation#Installation]] here."
	transclusions := parser.extractTransclusions(content)

	if len(transclusions) != 1 {
		t.Fatalf("Expected 1 transclusion, got %d", len(transclusions))
	}
	if transclusions[0].TargetPage != "Documentation" {
		t.Errorf("Expected target page 'Documentation', got '%s'", transclusions[0].TargetPage)
	}
	if transclusions[0].TargetHeader != "Installation" {
		t.Errorf("Expected target header 'Installation', got '%s'", transclusions[0].TargetHeader)
	}
}

func TestExtractMultipleTransclusions(t *testing.T) {
	parser := NewSpaceParser("")
	content := `
		![[PageOne]]
		Some text
		![[PageTwo#Section]]
		More text
		![[Folder/PageThree]]
	`
	transclusions := parser.extractTransclusions(content)

	if len(transclusions) != 3 {
		t.Fatalf("Expected 3 transclusions, got %d", len(transclusions))
	}
	if transclusions[0].TargetPage != "PageOne" {
		t.Errorf("Expected target page 'PageOne', got '%s'", transclusions[0].TargetPage)
	}
	if transclusions[1].TargetPage != "PageTwo" {
		t.Errorf("Expected target page 'PageTwo', got '%s'", transclusions[1].TargetPage)
	}
	if transclusions[1].TargetHeader != "Section" {
		t.Errorf("Expected target header 'Section', got '%s'", transclusions[1].TargetHeader)
	}
	if transclusions[2].TargetPage != "Folder/PageThree" {
		t.Errorf("Expected target page 'Folder/PageThree', got '%s'", transclusions[2].TargetPage)
	}
}

func TestTransclusionExpansion(t *testing.T) {
	tmpDir := createTempSpace(t)

	// Create two pages - one transcluding the other
	writeMarkdownFile(t, tmpDir, "PageB.md", "This is content from PageB.")
	writeMarkdownFile(t, tmpDir, "PageA.md", "Before ![[PageB]] After")

	parser := NewSpaceParser(tmpDir)
	chunks, err := parser.ParseSpace(tmpDir)
	if err != nil {
		t.Fatalf("ParseSpace failed: %v", err)
	}

	// Find PageA chunk
	var pageAContent string
	for _, c := range chunks {
		if filepath.Base(c.FilePath) == "PageA.md" {
			pageAContent = c.Content
			break
		}
	}

	if pageAContent == "" {
		t.Fatal("Could not find PageA chunk")
	}

	// The content should include expanded transclusion
	if !contains(pageAContent, "This is content from PageB") {
		t.Errorf("Expected PageA content to include transclusion content, got: %s", pageAContent)
	}
}

func TestTransclusionExpansionWithHeader(t *testing.T) {
	tmpDir := createTempSpace(t)

	writeMarkdownFile(t, tmpDir, "PageB.md", `# PageB

## Section One
Content of section one.

## Section Two
Content of section two.

## Section Three
Content of section three.
`)
	writeMarkdownFile(t, tmpDir, "PageA.md", "Include: ![[PageB#Section Two]]")

	parser := NewSpaceParser(tmpDir)
	chunks, err := parser.ParseSpace(tmpDir)
	if err != nil {
		t.Fatalf("ParseSpace failed: %v", err)
	}

	// Find PageA chunk
	var pageAContent string
	for _, c := range chunks {
		if filepath.Base(c.FilePath) == "PageA.md" {
			pageAContent = c.Content
			break
		}
	}

	if pageAContent == "" {
		t.Fatal("Could not find PageA chunk")
	}

	// Should include section two content
	if !contains(pageAContent, "Content of section two") {
		t.Errorf("Expected PageA content to include section two, got: %s", pageAContent)
	}

	// Should NOT include other sections
	if contains(pageAContent, "Content of section one") {
		t.Errorf("PageA content should not include section one")
	}
	if contains(pageAContent, "Content of section three") {
		t.Errorf("PageA content should not include section three")
	}
}

func TestTransclusionMaxDepth(t *testing.T) {
	tmpDir := createTempSpace(t)

	// Create circular/deep transclusion
	writeMarkdownFile(t, tmpDir, "PageA.md", "A includes ![[PageB]]")
	writeMarkdownFile(t, tmpDir, "PageB.md", "B includes ![[PageA]]")

	parser := NewSpaceParser(tmpDir)
	// Should not hang due to max_depth limit
	chunks, err := parser.ParseSpace(tmpDir)
	if err != nil {
		t.Fatalf("ParseSpace failed: %v", err)
	}

	if len(chunks) < 2 {
		t.Errorf("Expected at least 2 chunks, got %d", len(chunks))
	}
}

// ==================== Inline Attribute Tests ====================

func TestExtractSimpleAttribute(t *testing.T) {
	parser := NewSpaceParser("")
	content := "Task item [status: done]"
	attributes := parser.extractInlineAttributes(content)

	if len(attributes) != 1 {
		t.Fatalf("Expected 1 attribute, got %d", len(attributes))
	}
	if attributes[0].Name != "status" {
		t.Errorf("Expected name 'status', got '%s'", attributes[0].Name)
	}
	if attributes[0].Value != "done" {
		t.Errorf("Expected value 'done', got '%s'", attributes[0].Value)
	}
}

func TestExtractMultipleAttributes(t *testing.T) {
	parser := NewSpaceParser("")
	content := "Item [priority: high] [assignee: John] [due: 2024-01-15]"
	attributes := parser.extractInlineAttributes(content)

	if len(attributes) != 3 {
		t.Fatalf("Expected 3 attributes, got %d", len(attributes))
	}
	if attributes[0].Name != "priority" || attributes[0].Value != "high" {
		t.Errorf("First attribute wrong: %v", attributes[0])
	}
	if attributes[1].Name != "assignee" || attributes[1].Value != "John" {
		t.Errorf("Second attribute wrong: %v", attributes[1])
	}
	if attributes[2].Name != "due" || attributes[2].Value != "2024-01-15" {
		t.Errorf("Third attribute wrong: %v", attributes[2])
	}
}

func TestAttributeWithSpacesInValue(t *testing.T) {
	parser := NewSpaceParser("")
	content := "[description: A longer description with spaces]"
	attributes := parser.extractInlineAttributes(content)

	if len(attributes) != 1 {
		t.Fatalf("Expected 1 attribute, got %d", len(attributes))
	}
	if attributes[0].Value != "A longer description with spaces" {
		t.Errorf("Expected value with spaces, got '%s'", attributes[0].Value)
	}
}

func TestAttributeUnderscoreInName(t *testing.T) {
	parser := NewSpaceParser("")
	content := "[due_date: 2024-12-31]"
	attributes := parser.extractInlineAttributes(content)

	if len(attributes) != 1 {
		t.Fatalf("Expected 1 attribute, got %d", len(attributes))
	}
	if attributes[0].Name != "due_date" {
		t.Errorf("Expected name 'due_date', got '%s'", attributes[0].Name)
	}
}

// ==================== Data Block Tests ====================

func TestExtractSimpleDataBlock(t *testing.T) {
	parser := NewSpaceParser("")
	content := `Some text

` + "```#person\nname: John Doe\nage: 30\n```" + `

More text`

	dataBlocks := parser.extractDataBlocks(content, "/test/file.md")

	if len(dataBlocks) != 1 {
		t.Fatalf("Expected 1 data block, got %d", len(dataBlocks))
	}
	if dataBlocks[0].Tag != "person" {
		t.Errorf("Expected tag 'person', got '%s'", dataBlocks[0].Tag)
	}
	if dataBlocks[0].Data["name"] != "John Doe" {
		t.Errorf("Expected name 'John Doe', got '%v'", dataBlocks[0].Data["name"])
	}
	if dataBlocks[0].Data["age"] != 30 {
		t.Errorf("Expected age 30, got '%v'", dataBlocks[0].Data["age"])
	}
	if dataBlocks[0].FilePath != "/test/file.md" {
		t.Errorf("Expected file_path '/test/file.md', got '%s'", dataBlocks[0].FilePath)
	}
}

func TestExtractMultipleDataBlocks(t *testing.T) {
	parser := NewSpaceParser("")
	content := "```#contact\nname: Alice\nemail: alice@example.com\n```\n\nSome text between\n\n```#contact\nname: Bob\nemail: bob@example.com\n```"

	dataBlocks := parser.extractDataBlocks(content, "/test/file.md")

	if len(dataBlocks) != 2 {
		t.Fatalf("Expected 2 data blocks, got %d", len(dataBlocks))
	}
	if dataBlocks[0].Data["name"] != "Alice" {
		t.Errorf("Expected first name 'Alice', got '%v'", dataBlocks[0].Data["name"])
	}
	if dataBlocks[1].Data["name"] != "Bob" {
		t.Errorf("Expected second name 'Bob', got '%v'", dataBlocks[1].Data["name"])
	}
}

func TestRegularCodeBlockNotParsed(t *testing.T) {
	parser := NewSpaceParser("")
	content := "```python\ndef hello():\n    print(\"Hello\")\n```"

	dataBlocks := parser.extractDataBlocks(content, "/test/file.md")

	if len(dataBlocks) != 0 {
		t.Errorf("Expected 0 data blocks for regular code block, got %d", len(dataBlocks))
	}
}

// ==================== Section Extraction Tests ====================

func TestExtractSectionByHeader(t *testing.T) {
	parser := NewSpaceParser("")
	content := `# Main Title

## First Section
Content of first section.

## Second Section
Content of second section.
More content here.

## Third Section
Content of third section.
`

	section := parser.extractSection(content, "Second Section")

	if !contains(section, "## Second Section") {
		t.Errorf("Section should contain '## Second Section'")
	}
	if !contains(section, "Content of second section") {
		t.Errorf("Section should contain 'Content of second section'")
	}
	if !contains(section, "More content here") {
		t.Errorf("Section should contain 'More content here'")
	}
	if contains(section, "First Section") {
		t.Errorf("Section should not contain 'First Section'")
	}
	if contains(section, "Third Section") {
		t.Errorf("Section should not contain 'Third Section'")
	}
}

func TestExtractSectionCaseInsensitive(t *testing.T) {
	parser := NewSpaceParser("")
	content := `## My Section
Some content here.

## Another Section
Other content.
`

	section := parser.extractSection(content, "my section")
	if !contains(section, "Some content here") {
		t.Errorf("Case insensitive section extraction failed")
	}
}

func TestExtractNestedSection(t *testing.T) {
	parser := NewSpaceParser("")
	content := `## Parent Section
Parent content.

### Child Section
Child content.

## Next Section
Next content.
`

	section := parser.extractSection(content, "Parent Section")

	if !contains(section, "Parent content") {
		t.Errorf("Section should contain 'Parent content'")
	}
	if !contains(section, "Child Section") {
		t.Errorf("Section should contain nested 'Child Section'")
	}
	if !contains(section, "Child content") {
		t.Errorf("Section should contain 'Child content'")
	}
	if contains(section, "Next Section") {
		t.Errorf("Section should not contain 'Next Section'")
	}
}

// ==================== Link and Tag Extraction Tests ====================

func TestExtractLinks(t *testing.T) {
	parser := NewSpaceParser("")
	content := "This links to [[page1]] and [[page2|alias]] and [[page3#header]]."

	links := parser.extractLinks(content)

	if len(links) != 3 {
		t.Fatalf("Expected 3 links, got %d", len(links))
	}
	if links[0] != "page1" {
		t.Errorf("Expected 'page1', got '%s'", links[0])
	}
	if links[1] != "page2" {
		t.Errorf("Expected 'page2', got '%s'", links[1])
	}
	if links[2] != "page3" {
		t.Errorf("Expected 'page3', got '%s'", links[2])
	}
}

func TestExtractTags(t *testing.T) {
	parser := NewSpaceParser("")
	content := "Content with #tag1 and #tag2 and another #tag1"

	tags := parser.extractTags(content, nil)

	// Should deduplicate
	if len(tags) != 2 {
		t.Fatalf("Expected 2 unique tags, got %d: %v", len(tags), tags)
	}
	if !containsString(tags, "tag1") || !containsString(tags, "tag2") {
		t.Errorf("Missing expected tags: %v", tags)
	}
}

func TestExtractTagsWithFrontmatter(t *testing.T) {
	parser := NewSpaceParser("")
	content := "Content with #hashtag"
	frontmatter := map[string]any{
		"tags": []interface{}{"frontmatter_tag"},
	}

	tags := parser.extractTags(content, frontmatter)

	if len(tags) != 2 {
		t.Fatalf("Expected 2 tags, got %d: %v", len(tags), tags)
	}
	if !containsString(tags, "hashtag") {
		t.Errorf("Missing 'hashtag'")
	}
	if !containsString(tags, "frontmatter_tag") {
		t.Errorf("Missing 'frontmatter_tag'")
	}
}

// ==================== Frontmatter Tests ====================

func TestExtractFrontmatter(t *testing.T) {
	parser := NewSpaceParser("")
	content := `---
github: owner/repo
tags:
  - python
  - rag
---
# Project Page

Content here.
`

	frontmatter := parser.extractFrontmatter(content)

	if frontmatter == nil {
		t.Fatal("Frontmatter should not be nil")
	}
	if frontmatter["github"] != "owner/repo" {
		t.Errorf("Expected github 'owner/repo', got '%v'", frontmatter["github"])
	}
	tags, ok := frontmatter["tags"].([]interface{})
	if !ok {
		t.Fatalf("tags should be a slice, got %T", frontmatter["tags"])
	}
	if len(tags) != 2 {
		t.Errorf("Expected 2 tags, got %d", len(tags))
	}
}

func TestStripFrontmatter(t *testing.T) {
	parser := NewSpaceParser("")
	content := `---
github: owner/repo
---
# Title

Body content.
`

	stripped := parser.stripFrontmatter(content)

	if contains(stripped, "---") {
		t.Errorf("Frontmatter delimiter should be stripped")
	}
	if contains(stripped, "github:") {
		t.Errorf("Frontmatter content should be stripped")
	}
	if !contains(stripped, "# Title") {
		t.Errorf("Body content should be preserved")
	}
}

// ==================== Folder Path Tests ====================

func TestParserExtractsFolderPaths(t *testing.T) {
	tmpDir := createTempSpace(t)

	// Create nested folder structure
	os.MkdirAll(filepath.Join(tmpDir, "Projects", "Project1"), 0755)
	os.MkdirAll(filepath.Join(tmpDir, "Area"), 0755)
	writeMarkdownFile(t, tmpDir, "Projects/Project1/test.md", "# Test")
	writeMarkdownFile(t, tmpDir, "Area/Health.md", "# Health")

	parser := NewSpaceParser(tmpDir)
	folders, err := parser.GetFolderPaths(tmpDir)
	if err != nil {
		t.Fatalf("GetFolderPaths failed: %v", err)
	}

	if !containsString(folders, "Projects") {
		t.Errorf("Expected 'Projects' in folders")
	}
	if !containsString(folders, "Projects/Project1") {
		t.Errorf("Expected 'Projects/Project1' in folders")
	}
	if !containsString(folders, "Area") {
		t.Errorf("Expected 'Area' in folders")
	}
}

func TestParserExcludesHiddenDirectories(t *testing.T) {
	tmpDir := createTempSpace(t)

	// Create normal folder
	os.MkdirAll(filepath.Join(tmpDir, "Projects"), 0755)
	writeMarkdownFile(t, tmpDir, "Projects/test.md", "# Test")

	// Create hidden directories
	os.MkdirAll(filepath.Join(tmpDir, ".git", "objects"), 0755)
	os.MkdirAll(filepath.Join(tmpDir, ".hidden"), 0755)
	os.MkdirAll(filepath.Join(tmpDir, "_Proposals"), 0755)

	parser := NewSpaceParser(tmpDir)
	folders, err := parser.GetFolderPaths(tmpDir)
	if err != nil {
		t.Fatalf("GetFolderPaths failed: %v", err)
	}

	// Normal folders should be included
	if !containsString(folders, "Projects") {
		t.Errorf("Expected 'Projects' in folders")
	}

	// Hidden directories should be excluded
	if containsString(folders, ".git") || containsString(folders, ".git/objects") {
		t.Errorf(".git should be excluded")
	}
	if containsString(folders, ".hidden") {
		t.Errorf(".hidden should be excluded")
	}
	if containsString(folders, "_Proposals") {
		t.Errorf("_Proposals should be excluded")
	}
}

func TestParserChunksHaveFolderPath(t *testing.T) {
	tmpDir := createTempSpace(t)

	// Create nested file
	os.MkdirAll(filepath.Join(tmpDir, "Projects"), 0755)
	writeMarkdownFile(t, tmpDir, "Projects/MyProject.md", "# My Project\n\nContent here")

	parser := NewSpaceParser(tmpDir)
	chunks, err := parser.ParseSpace(tmpDir)
	if err != nil {
		t.Fatalf("ParseSpace failed: %v", err)
	}

	if len(chunks) == 0 {
		t.Fatal("Expected at least one chunk")
	}

	// Find the MyProject chunk
	found := false
	for _, chunk := range chunks {
		if filepath.Base(chunk.FilePath) == "MyProject.md" {
			found = true
			if chunk.FolderPath != "Projects" {
				t.Errorf("Expected folder_path 'Projects', got '%s'", chunk.FolderPath)
			}
			break
		}
	}
	if !found {
		t.Errorf("Did not find MyProject.md chunk")
	}
}

func TestChunksIncludeFrontmatterMetadata(t *testing.T) {
	tmpDir := createTempSpace(t)

	writeMarkdownFile(t, tmpDir, "test.md", `---
github: owner/repo
---
# Section 1

Content for section 1.
`)

	parser := NewSpaceParser(tmpDir)
	chunks, err := parser.ParseSpace(tmpDir)
	if err != nil {
		t.Fatalf("ParseSpace failed: %v", err)
	}

	if len(chunks) == 0 {
		t.Fatal("Expected at least one chunk")
	}

	chunk := chunks[0]
	if chunk.Frontmatter == nil {
		t.Fatal("Frontmatter should not be nil")
	}
	if chunk.Frontmatter["github"] != "owner/repo" {
		t.Errorf("Expected github 'owner/repo', got '%v'", chunk.Frontmatter["github"])
	}
}

func TestFrontmatterNotIncludedInChunkContent(t *testing.T) {
	tmpDir := createTempSpace(t)

	writeMarkdownFile(t, tmpDir, "test.md", `---
github: owner/repo
---
# Title

Body content.
`)

	parser := NewSpaceParser(tmpDir)
	chunks, err := parser.ParseSpace(tmpDir)
	if err != nil {
		t.Fatalf("ParseSpace failed: %v", err)
	}

	if len(chunks) == 0 {
		t.Fatal("Expected at least one chunk")
	}

	chunk := chunks[0]
	if contains(chunk.Content, "---") {
		t.Errorf("Frontmatter delimiter should not be in content")
	}
	if contains(chunk.Content, "github:") {
		t.Errorf("Frontmatter content should not be in content")
	}
}

func TestFrontmatterTagsMergedIntoChunkTags(t *testing.T) {
	tmpDir := createTempSpace(t)

	writeMarkdownFile(t, tmpDir, "test.md", `---
tags:
  - project
  - active
---
# Title

Body content with #hashtag and #another.
`)

	parser := NewSpaceParser(tmpDir)
	chunks, err := parser.ParseSpace(tmpDir)
	if err != nil {
		t.Fatalf("ParseSpace failed: %v", err)
	}

	if len(chunks) == 0 {
		t.Fatal("Expected at least one chunk")
	}

	chunk := chunks[0]
	if !containsString(chunk.Tags, "hashtag") {
		t.Errorf("Missing 'hashtag' in tags")
	}
	if !containsString(chunk.Tags, "another") {
		t.Errorf("Missing 'another' in tags")
	}
	if !containsString(chunk.Tags, "project") {
		t.Errorf("Missing 'project' from frontmatter in tags")
	}
	if !containsString(chunk.Tags, "active") {
		t.Errorf("Missing 'active' from frontmatter in tags")
	}
}

// ==================== Skip File Tests ====================

func TestSkipProposalFiles(t *testing.T) {
	tmpDir := createTempSpace(t)

	// Create normal file and proposal file
	writeMarkdownFile(t, tmpDir, "normal.md", "# Normal\n\nContent")
	writeMarkdownFile(t, tmpDir, "change.proposal", "# Proposal\n\nContent")
	writeMarkdownFile(t, tmpDir, "rejected.rejected.md", "# Rejected\n\nContent")
	os.MkdirAll(filepath.Join(tmpDir, "_Proposals"), 0755)
	writeMarkdownFile(t, tmpDir, "_Proposals/pending.md", "# Pending\n\nContent")

	parser := NewSpaceParser(tmpDir)
	chunks, err := parser.ParseSpace(tmpDir)
	if err != nil {
		t.Fatalf("ParseSpace failed: %v", err)
	}

	// Should only have the normal file
	if len(chunks) != 1 {
		t.Errorf("Expected 1 chunk, got %d", len(chunks))
	}
	if filepath.Base(chunks[0].FilePath) != "normal.md" {
		t.Errorf("Expected normal.md, got %s", chunks[0].FilePath)
	}
}

// ==================== Helpers ====================

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsHelper(s, substr))
}

func containsHelper(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

func containsString(slice []string, s string) bool {
	for _, item := range slice {
		if item == s {
			return true
		}
	}
	return false
}
