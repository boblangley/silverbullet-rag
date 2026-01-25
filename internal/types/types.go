// Package types defines the core data structures for silverbullet-rag.
package types

// InlineAttribute represents an inline attribute [name: value] in markdown.
type InlineAttribute struct {
	Name  string `json:"name"`
	Value string `json:"value"`
}

// DataBlock represents a tagged data block (```#tagname YAML content).
type DataBlock struct {
	Tag      string         `json:"tag"`
	Data     map[string]any `json:"data"`
	FilePath string         `json:"file_path"`
}

// Transclusion represents a transclusion reference ![[page]] or ![[page#header]].
type Transclusion struct {
	TargetPage   string `json:"target_page"`
	TargetHeader string `json:"target_header,omitempty"`
}

// Chunk represents a chunk of content from a markdown file.
type Chunk struct {
	// ID is a unique identifier for the chunk (file_path#header).
	ID string `json:"id"`

	// FilePath is the absolute path to the source file.
	FilePath string `json:"file_path"`

	// Header is the section header or filename.
	Header string `json:"header"`

	// Content is the text content of the chunk.
	Content string `json:"content"`

	// Links are wikilinks found in the content.
	Links []string `json:"links"`

	// Tags are hashtags found in the content or frontmatter.
	Tags []string `json:"tags"`

	// FolderPath is the path relative to the space root.
	FolderPath string `json:"folder_path"`

	// Frontmatter is parsed YAML frontmatter.
	Frontmatter map[string]any `json:"frontmatter"`

	// Transclusions are ![[page]] references.
	Transclusions []Transclusion `json:"transclusions,omitempty"`

	// InlineAttributes are [name: value] attributes.
	InlineAttributes []InlineAttribute `json:"inline_attributes,omitempty"`

	// DataBlocks are ```#tagname YAML blocks.
	DataBlocks []DataBlock `json:"data_blocks,omitempty"`

	// Embedding is the vector embedding for semantic search.
	Embedding []float32 `json:"embedding,omitempty"`
}

// Page represents a markdown page in the space.
type Page struct {
	Name string `json:"name"`
}

// Tag represents a hashtag.
type Tag struct {
	Name string `json:"name"`
}

// Folder represents a folder in the space hierarchy.
type Folder struct {
	Name         string `json:"name"`
	Path         string `json:"path"`
	HasIndexPage bool   `json:"has_index_page"`
}

// SearchResult represents a single search result.
type SearchResult struct {
	Chunk         Chunk   `json:"chunk"`
	HybridScore   float64 `json:"hybrid_score"`
	KeywordScore  float64 `json:"keyword_score"`
	SemanticScore float64 `json:"semantic_score"`
}
