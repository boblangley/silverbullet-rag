// Package parser provides markdown parsing for SilverBullet spaces.
package parser

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/yuin/goldmark"
	"github.com/yuin/goldmark/ast"
	"github.com/yuin/goldmark/text"
	"gopkg.in/yaml.v3"

	"github.com/boblangley/silverbullet-rag/internal/types"
)

var (
	// Regex patterns for SilverBullet syntax
	frontmatterPattern  = regexp.MustCompile(`(?s)^---\s*\n(.*?)\n---\s*\n`)
	linkPattern         = regexp.MustCompile(`\[\[([^\]]+)\]\]`)
	tagPattern          = regexp.MustCompile(`(?m)(?:^|[^` + "`" + `/])#(\w+)`)
	transclusionPattern = regexp.MustCompile(`!\[\[([^\]#]+)(?:#([^\]]+))?\]\]`)
	// Inline attributes: [name: value] - captures optional context char before [
	// We filter out matches preceded by ! in code
	inlineAttrPattern = regexp.MustCompile(`(^|[^!])\[([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([^\]]+)\]`)
	dataBlockPattern  = regexp.MustCompile("(?s)```#(\\w+)\\s*\\n(.*?)\\n```")
)

// SpaceParser parses SilverBullet markdown files.
type SpaceParser struct {
	md               goldmark.Markdown
	spaceRoot        string
	contentCache     map[string]string
	frontmatterCache map[string]map[string]any
}

// NewSpaceParser creates a new parser.
func NewSpaceParser(spaceRoot string) *SpaceParser {
	return &SpaceParser{
		md:               goldmark.New(),
		spaceRoot:        spaceRoot,
		contentCache:     make(map[string]string),
		frontmatterCache: make(map[string]map[string]any),
	}
}

// ParseSpace parses all markdown files in a directory.
func (p *SpaceParser) ParseSpace(dirPath string) ([]types.Chunk, error) {
	p.spaceRoot = dirPath
	var chunks []types.Chunk

	// First pass: cache all file contents
	err := filepath.WalkDir(dirPath, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}

		if d.IsDir() {
			if p.shouldSkipDirectory(path) {
				return filepath.SkipDir
			}
			return nil
		}

		if !strings.HasSuffix(path, ".md") || p.shouldSkipFile(path) {
			return nil
		}

		content, err := os.ReadFile(path)
		if err != nil {
			return nil // Skip files we can't read
		}

		relPath, _ := filepath.Rel(dirPath, path)
		pageName := strings.TrimSuffix(relPath, ".md")
		p.contentCache[pageName] = string(content)
		p.frontmatterCache[path] = p.extractFrontmatter(string(content))

		return nil
	})
	if err != nil {
		return nil, err
	}

	// Second pass: parse files
	err = filepath.WalkDir(dirPath, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}

		if d.IsDir() {
			if p.shouldSkipDirectory(path) {
				return filepath.SkipDir
			}
			return nil
		}

		if !strings.HasSuffix(path, ".md") || p.shouldSkipFile(path) {
			return nil
		}

		relPath, _ := filepath.Rel(dirPath, path)
		pageName := strings.TrimSuffix(relPath, ".md")
		content := p.contentCache[pageName]

		folderPath := ""
		if dir := filepath.Dir(relPath); dir != "." {
			folderPath = dir
		}

		frontmatter := p.frontmatterCache[path]
		fileChunks := p.parseFile(path, content, folderPath, frontmatter)
		chunks = append(chunks, fileChunks...)

		return nil
	})

	return chunks, err
}

// ParseFile parses a single markdown file.
func (p *SpaceParser) ParseFile(filePath string) ([]types.Chunk, error) {
	content, err := os.ReadFile(filePath)
	if err != nil {
		return nil, err
	}

	if p.shouldSkipFile(filePath) {
		return nil, nil
	}

	folderPath := ""
	if p.spaceRoot != "" {
		if relPath, err := filepath.Rel(p.spaceRoot, filePath); err == nil {
			if dir := filepath.Dir(relPath); dir != "." {
				folderPath = dir
			}
		}
	}

	frontmatter := p.extractFrontmatter(string(content))
	return p.parseFile(filePath, string(content), folderPath, frontmatter), nil
}

func (p *SpaceParser) parseFile(filePath, content, folderPath string, frontmatter map[string]any) []types.Chunk {
	// Strip frontmatter
	rawContent := p.stripFrontmatter(content)

	// Extract data blocks before transclusion expansion
	dataBlocks := p.extractDataBlocks(rawContent, filePath)

	// Expand transclusions
	rawContent = p.expandTransclusions(rawContent, 0, 5)

	// Parse markdown
	reader := text.NewReader([]byte(rawContent))
	doc := p.md.Parser().Parse(reader)

	var chunks []types.Chunk
	currentHeader := filepath.Base(strings.TrimSuffix(filePath, ".md"))
	var currentContent []string

	// Walk the AST to find headings and content
	_ = ast.Walk(doc, func(n ast.Node, entering bool) (ast.WalkStatus, error) {
		if !entering {
			return ast.WalkContinue, nil
		}

		switch node := n.(type) {
		case *ast.Heading:
			if node.Level == 2 {
				// Save previous chunk
				if len(currentContent) > 0 {
					text := strings.TrimSpace(strings.Join(currentContent, "\n"))
					if text != "" {
						chunk := p.createChunk(filePath, currentHeader, text, folderPath, frontmatter, rawContent)
						chunks = append(chunks, chunk)
					}
					currentContent = nil
				}
				// Get heading text
				if node.Lines().Len() > 0 {
					line := node.Lines().At(0)
					currentHeader = string(line.Value(reader.Source()))
				}
			}
		case *ast.Text:
			currentContent = append(currentContent, string(node.Segment.Value(reader.Source())))
		case *ast.String:
			currentContent = append(currentContent, string(node.Value))
		case *ast.FencedCodeBlock:
			// Include fenced code block content (important for CONFIG.md and documentation)
			// Skip data blocks (```#tagname) as they are handled separately
			info := ""
			if node.Info != nil {
				info = string(node.Info.Segment.Value(reader.Source()))
			}
			if !strings.HasPrefix(info, "#") {
				var codeLines []string
				lines := node.Lines()
				for i := 0; i < lines.Len(); i++ {
					line := lines.At(i)
					codeLines = append(codeLines, string(line.Value(reader.Source())))
				}
				if len(codeLines) > 0 {
					currentContent = append(currentContent, strings.Join(codeLines, ""))
				}
			}
		case *ast.CodeBlock:
			// Include indented code blocks
			var codeLines []string
			lines := node.Lines()
			for i := 0; i < lines.Len(); i++ {
				line := lines.At(i)
				codeLines = append(codeLines, string(line.Value(reader.Source())))
			}
			if len(codeLines) > 0 {
				currentContent = append(currentContent, strings.Join(codeLines, ""))
			}
		}

		return ast.WalkContinue, nil
	})

	// Save last chunk
	if len(currentContent) > 0 {
		text := strings.TrimSpace(strings.Join(currentContent, "\n"))
		if text != "" {
			chunk := p.createChunk(filePath, currentHeader, text, folderPath, frontmatter, rawContent)
			chunks = append(chunks, chunk)
		}
	}

	// If no chunks but we have data blocks, create an empty chunk
	if len(chunks) == 0 && len(dataBlocks) > 0 {
		chunk := types.Chunk{
			ID:          filePath + "#" + currentHeader,
			FilePath:    filePath,
			Header:      currentHeader,
			Content:     "",
			Links:       nil,
			Tags:        p.getFrontmatterTags(frontmatter),
			FolderPath:  folderPath,
			Frontmatter: frontmatter,
			DataBlocks:  dataBlocks,
		}
		chunks = append(chunks, chunk)
	} else if len(chunks) > 0 {
		// Associate data blocks with first chunk
		chunks[0].DataBlocks = append(chunks[0].DataBlocks, dataBlocks...)
	}

	return chunks
}

func (p *SpaceParser) createChunk(filePath, header, content, folderPath string, frontmatter map[string]any, rawContent string) types.Chunk {
	links := p.extractLinks(content)
	tags := p.extractTags(content, frontmatter)
	transclusions := p.extractTransclusions(rawContent)
	inlineAttrs := p.extractInlineAttributes(content)

	return types.Chunk{
		ID:               filePath + "#" + header,
		FilePath:         filePath,
		Header:           header,
		Content:          content,
		Links:            links,
		Tags:             tags,
		FolderPath:       folderPath,
		Frontmatter:      frontmatter,
		Transclusions:    transclusions,
		InlineAttributes: inlineAttrs,
	}
}

func (p *SpaceParser) extractFrontmatter(content string) map[string]any {
	match := frontmatterPattern.FindStringSubmatch(content)
	if match == nil {
		return nil
	}

	var fm map[string]any
	if err := yaml.Unmarshal([]byte(match[1]), &fm); err != nil {
		return nil
	}
	return fm
}

func (p *SpaceParser) stripFrontmatter(content string) string {
	return frontmatterPattern.ReplaceAllString(content, "")
}

func (p *SpaceParser) extractLinks(content string) []string {
	matches := linkPattern.FindAllStringSubmatch(content, -1)
	var links []string
	for _, m := range matches {
		// Remove header part if present (e.g., "page#header" -> "page")
		link := strings.Split(m[1], "|")[0]
		link = strings.Split(link, "#")[0]
		links = append(links, link)
	}
	return links
}

func (p *SpaceParser) extractTags(content string, frontmatter map[string]any) []string {
	// Extract from content
	matches := tagPattern.FindAllStringSubmatch(content, -1)
	tagSet := make(map[string]struct{})
	var tags []string

	for _, m := range matches {
		if _, exists := tagSet[m[1]]; !exists {
			tagSet[m[1]] = struct{}{}
			tags = append(tags, m[1])
		}
	}

	// Add frontmatter tags
	for _, t := range p.getFrontmatterTags(frontmatter) {
		if _, exists := tagSet[t]; !exists {
			tagSet[t] = struct{}{}
			tags = append(tags, t)
		}
	}

	return tags
}

func (p *SpaceParser) getFrontmatterTags(frontmatter map[string]any) []string {
	if frontmatter == nil {
		return nil
	}

	tagsRaw, ok := frontmatter["tags"]
	if !ok {
		return nil
	}

	switch v := tagsRaw.(type) {
	case string:
		return []string{v}
	case []interface{}:
		var tags []string
		for _, t := range v {
			if s, ok := t.(string); ok {
				tags = append(tags, s)
			}
		}
		return tags
	case []string:
		return v
	}
	return nil
}

func (p *SpaceParser) extractTransclusions(content string) []types.Transclusion {
	matches := transclusionPattern.FindAllStringSubmatch(content, -1)
	var trans []types.Transclusion
	for _, m := range matches {
		t := types.Transclusion{
			TargetPage: strings.TrimSpace(m[1]),
		}
		if len(m) > 2 && m[2] != "" {
			t.TargetHeader = strings.TrimSpace(m[2])
		}
		trans = append(trans, t)
	}
	return trans
}

func (p *SpaceParser) extractInlineAttributes(content string) []types.InlineAttribute {
	matches := inlineAttrPattern.FindAllStringSubmatch(content, -1)
	var attrs []types.InlineAttribute
	for _, m := range matches {
		// m[1] is prefix (empty or non-! char), m[2] is name, m[3] is value
		attrs = append(attrs, types.InlineAttribute{
			Name:  strings.TrimSpace(m[2]),
			Value: strings.TrimSpace(m[3]),
		})
	}
	return attrs
}

func (p *SpaceParser) extractDataBlocks(content, filePath string) []types.DataBlock {
	matches := dataBlockPattern.FindAllStringSubmatch(content, -1)
	var blocks []types.DataBlock
	for _, m := range matches {
		var data map[string]any
		if err := yaml.Unmarshal([]byte(m[2]), &data); err == nil && data != nil {
			blocks = append(blocks, types.DataBlock{
				Tag:      m[1],
				Data:     data,
				FilePath: filePath,
			})
		}
	}
	return blocks
}

func (p *SpaceParser) expandTransclusions(content string, depth, maxDepth int) string {
	if depth >= maxDepth {
		return content
	}

	return transclusionPattern.ReplaceAllStringFunc(content, func(match string) string {
		m := transclusionPattern.FindStringSubmatch(match)
		if m == nil {
			return match
		}

		targetPage := strings.TrimSpace(m[1])
		targetHeader := ""
		if len(m) > 2 {
			targetHeader = strings.TrimSpace(m[2])
		}

		// Look up target content
		targetContent, ok := p.contentCache[targetPage]
		if !ok {
			// Try path variations
			for pageName, c := range p.contentCache {
				if strings.HasSuffix(pageName, "/"+targetPage) || pageName == targetPage {
					targetContent = c
					ok = true
					break
				}
			}
		}

		if !ok {
			return match // Return original if not found
		}

		// Strip frontmatter
		targetContent = p.stripFrontmatter(targetContent)

		// Extract section if header specified
		if targetHeader != "" {
			targetContent = p.extractSection(targetContent, targetHeader)
		}

		// Recursively expand
		return p.expandTransclusions(targetContent, depth+1, maxDepth)
	})
}

func (p *SpaceParser) extractSection(content, header string) string {
	lines := strings.Split(content, "\n")
	var sectionLines []string
	inSection := false
	sectionLevel := 0
	headerPattern := regexp.MustCompile(`^(#+)\s+(.+)$`)

	for _, line := range lines {
		m := headerPattern.FindStringSubmatch(line)
		if m != nil {
			level := len(m[1])
			headerText := strings.TrimSpace(m[2])

			if strings.EqualFold(headerText, header) {
				inSection = true
				sectionLevel = level
				sectionLines = append(sectionLines, line)
			} else if inSection && level <= sectionLevel {
				break
			} else if inSection {
				sectionLines = append(sectionLines, line)
			}
		} else if inSection {
			sectionLines = append(sectionLines, line)
		}
	}

	return strings.Join(sectionLines, "\n")
}

func (p *SpaceParser) shouldSkipFile(path string) bool {
	base := filepath.Base(path)

	// Skip .proposal files
	if strings.HasSuffix(base, ".proposal") {
		return true
	}

	// Skip .rejected.md files
	if strings.HasSuffix(base, ".rejected.md") {
		return true
	}

	// Skip files in _Proposals directory
	if strings.Contains(path, "_Proposals") {
		return true
	}

	return false
}

func (p *SpaceParser) shouldSkipDirectory(path string) bool {
	base := filepath.Base(path)

	// Skip hidden directories
	if strings.HasPrefix(base, ".") {
		return true
	}

	// Skip _Proposals
	if base == "_Proposals" {
		return true
	}

	return false
}

// GetFolderPaths returns all folder paths in the space.
func (p *SpaceParser) GetFolderPaths(dirPath string) ([]string, error) {
	folderSet := make(map[string]struct{})

	err := filepath.WalkDir(dirPath, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}

		if d.IsDir() {
			if p.shouldSkipDirectory(path) {
				return filepath.SkipDir
			}

			relPath, err := filepath.Rel(dirPath, path)
			if err != nil || relPath == "." {
				return nil
			}

			folderSet[relPath] = struct{}{}
			return nil
		}

		return nil
	})
	if err != nil {
		return nil, err
	}

	var folders []string
	for f := range folderSet {
		folders = append(folders, f)
	}
	return folders, nil
}

// GetFolderIndexPages returns a mapping of folder paths to their index pages.
func (p *SpaceParser) GetFolderIndexPages(dirPath string) (map[string]string, error) {
	indexMap := make(map[string]string)

	err := filepath.WalkDir(dirPath, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}

		if !d.IsDir() {
			return nil
		}

		if p.shouldSkipDirectory(path) {
			return filepath.SkipDir
		}

		relPath, err := filepath.Rel(dirPath, path)
		if err != nil || relPath == "." {
			return nil
		}

		// Check for sibling .md file
		parentDir := filepath.Dir(path)
		indexFile := filepath.Join(parentDir, filepath.Base(path)+".md")
		if _, err := os.Stat(indexFile); err == nil {
			relIndex, _ := filepath.Rel(dirPath, indexFile)
			indexMap[relPath] = relIndex
		}

		return nil
	})

	return indexMap, err
}

// GetFrontmatter returns the frontmatter for a file.
func (p *SpaceParser) GetFrontmatter(filePath string) (map[string]any, error) {
	// Check cache first
	if fm, ok := p.frontmatterCache[filePath]; ok {
		return fm, nil
	}

	// Read and parse
	content, err := os.ReadFile(filePath)
	if err != nil {
		return nil, err
	}

	fm := p.extractFrontmatter(string(content))
	p.frontmatterCache[filePath] = fm
	return fm, nil
}
