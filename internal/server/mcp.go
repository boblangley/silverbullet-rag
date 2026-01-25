// Package server provides MCP and gRPC server implementations.
package server

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/boblangley/silverbullet-rag/internal/db"
	"github.com/boblangley/silverbullet-rag/internal/parser"
	"github.com/boblangley/silverbullet-rag/internal/search"
	"github.com/boblangley/silverbullet-rag/internal/types"
	"github.com/boblangley/silverbullet-rag/internal/version"
)

// MCPServer provides the MCP interface to silverbullet-rag.
type MCPServer struct {
	server           *mcp.Server
	db               *db.GraphDB
	search           *search.HybridSearch
	parser           *parser.SpaceParser
	spacePath        string
	dbPath           string
	libraryPath      string
	allowLibMgmt     bool
	proposalsEnabled bool
	logger           *slog.Logger
}

// MCPConfig holds MCP server configuration.
type MCPConfig struct {
	DB                     *db.GraphDB
	Search                 *search.HybridSearch
	Parser                 *parser.SpaceParser
	SpacePath              string
	DBPath                 string
	LibraryPath            string
	AllowLibraryManagement bool
	Logger                 *slog.Logger
}

// NewMCPServer creates a new MCP server instance.
func NewMCPServer(cfg MCPConfig) *MCPServer {
	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	server := mcp.NewServer(
		&mcp.Implementation{Name: version.Name, Version: version.Version},
		nil,
	)

	m := &MCPServer{
		server:       server,
		db:           cfg.DB,
		search:       cfg.Search,
		parser:       cfg.Parser,
		spacePath:    cfg.SpacePath,
		dbPath:       cfg.DBPath,
		libraryPath:  cfg.LibraryPath,
		allowLibMgmt: cfg.AllowLibraryManagement,
		logger:       logger,
	}

	// Check if Proposals library is installed
	m.proposalsEnabled = m.libraryInstalled()
	if m.proposalsEnabled {
		logger.Info("Proposals library found, proposal tools enabled")
	} else {
		logger.Info("Proposals library not installed, proposal tools disabled")
	}

	m.registerTools()
	return m
}

// libraryInstalled checks if the Proposals library is installed in the space.
func (m *MCPServer) libraryInstalled() bool {
	markerFile := filepath.Join(m.spacePath, "Library", "Proposals.md")
	_, err := os.Stat(markerFile)
	return err == nil
}

// refreshProposalsStatus refreshes the proposalsEnabled status after library install/update.
func (m *MCPServer) refreshProposalsStatus() {
	m.proposalsEnabled = m.libraryInstalled()
	if m.proposalsEnabled {
		m.logger.Info("Proposals library detected, proposal tools enabled")
	} else {
		m.logger.Info("Proposals library not detected, proposal tools disabled")
	}
}

// HTTPHandler returns an http.Handler that serves the MCP protocol over HTTP
// using the streamable HTTP transport.
func (m *MCPServer) HTTPHandler() http.Handler {
	return mcp.NewStreamableHTTPHandler(
		func(_ *http.Request) *mcp.Server {
			return m.server
		},
		&mcp.StreamableHTTPOptions{
			JSONResponse: true, // Match Python FastMCP json_response=True
			Logger:       m.logger,
		},
	)
}

func (m *MCPServer) registerTools() {
	// Search tools
	m.registerCypherQuery()
	m.registerKeywordSearch()
	m.registerSemanticSearch()
	m.registerHybridSearch()
	m.registerGetGraphSchema()

	// Page tools
	m.registerReadPage()
	m.registerGetProjectContext()

	// Proposal tools
	m.registerProposeChange()
	m.registerListProposals()
	m.registerWithdrawProposal()

	// Library tools (conditional)
	if m.allowLibMgmt {
		m.registerInstallLibrary()
		m.registerUpdateLibrary()
		m.logger.Info("library management tools enabled")
	}
}

// Tool result helper
func toolResult(data any) (*mcp.CallToolResult, error) {
	jsonBytes, err := json.Marshal(data)
	if err != nil {
		return nil, err
	}
	return &mcp.CallToolResult{
		Content: []mcp.Content{
			&mcp.TextContent{Text: string(jsonBytes)},
		},
	}, nil
}

// Error result helper
func errorResult(err error) (*mcp.CallToolResult, error) {
	return toolResult(map[string]any{
		"success": false,
		"error":   err.Error(),
	})
}

// ============ Search Tools ============

type cypherQueryInput struct {
	Query string `json:"query" jsonschema:"Cypher query string"`
}

func (m *MCPServer) registerCypherQuery() {
	mcp.AddTool(m.server, &mcp.Tool{
		Name:        "cypher_query",
		Description: "Execute a Cypher query against the knowledge graph",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input cypherQueryInput) (*mcp.CallToolResult, any, error) {
		results, err := m.db.Execute(ctx, input.Query, nil)
		if err != nil {
			m.logger.Error("cypher query failed", "error", err)
			res, _ := errorResult(err)
			return res, nil, nil
		}
		res, _ := toolResult(map[string]any{
			"success": true,
			"results": results,
		})
		return res, nil, nil
	})
}

type keywordSearchInput struct {
	Query string `json:"query" jsonschema:"Search keyword or phrase"`
	Limit int    `json:"limit,omitempty" jsonschema:"Maximum results to return (default 10)"`
}

func (m *MCPServer) registerKeywordSearch() {
	mcp.AddTool(m.server, &mcp.Tool{
		Name:        "keyword_search",
		Description: "BM25-ranked keyword search across chunks, tags, and pages",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input keywordSearchInput) (*mcp.CallToolResult, any, error) {
		limit := input.Limit
		if limit == 0 {
			limit = 10
		}

		opts := search.SearchOptions{
			Limit:          limit,
			SemanticWeight: 0,
			KeywordWeight:  1,
		}

		results, err := m.search.Search(ctx, input.Query, opts)
		if err != nil {
			m.logger.Error("keyword search failed", "error", err)
			res, _ := errorResult(err)
			return res, nil, nil
		}

		res, _ := toolResult(map[string]any{
			"success": true,
			"results": formatSearchResults(results),
		})
		return res, nil, nil
	})
}

type semanticSearchInput struct {
	Query       string   `json:"query" jsonschema:"Natural language search query"`
	Limit       int      `json:"limit,omitempty" jsonschema:"Maximum results to return (default 10)"`
	FilterTags  []string `json:"filter_tags,omitempty" jsonschema:"Optional tag filter"`
	FilterPages []string `json:"filter_pages,omitempty" jsonschema:"Optional page name filter"`
}

func (m *MCPServer) registerSemanticSearch() {
	mcp.AddTool(m.server, &mcp.Tool{
		Name:        "semantic_search",
		Description: "AI-powered semantic search using vector embeddings",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input semanticSearchInput) (*mcp.CallToolResult, any, error) {
		limit := input.Limit
		if limit == 0 {
			limit = 10
		}

		opts := search.SearchOptions{
			Limit:          limit,
			FilterTags:     input.FilterTags,
			FilterPages:    input.FilterPages,
			SemanticWeight: 1,
			KeywordWeight:  0,
		}

		results, err := m.search.Search(ctx, input.Query, opts)
		if err != nil {
			m.logger.Error("semantic search failed", "error", err)
			res, _ := errorResult(err)
			return res, nil, nil
		}

		res, _ := toolResult(map[string]any{
			"success": true,
			"results": formatSearchResults(results),
		})
		return res, nil, nil
	})
}

type hybridSearchInput struct {
	Query          string   `json:"query" jsonschema:"Search query"`
	Limit          int      `json:"limit,omitempty" jsonschema:"Maximum results (default 10)"`
	FilterTags     []string `json:"filter_tags,omitempty" jsonschema:"Optional tag filter"`
	FilterPages    []string `json:"filter_pages,omitempty" jsonschema:"Optional page filter"`
	FusionMethod   string   `json:"fusion_method,omitempty" jsonschema:"Fusion method: rrf or weighted (default rrf)"`
	SemanticWeight float64  `json:"semantic_weight,omitempty" jsonschema:"Weight for semantic results 0-1 (default 0.5)"`
	KeywordWeight  float64  `json:"keyword_weight,omitempty" jsonschema:"Weight for keyword results 0-1 (default 0.5)"`
	Scope          string   `json:"scope,omitempty" jsonschema:"Optional folder path to scope results to"`
}

func (m *MCPServer) registerHybridSearch() {
	mcp.AddTool(m.server, &mcp.Tool{
		Name:        "hybrid_search_tool",
		Description: "Combined keyword + semantic search with result fusion",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input hybridSearchInput) (*mcp.CallToolResult, any, error) {
		limit := input.Limit
		if limit == 0 {
			limit = 10
		}

		fusionMethod := search.FusionRRF
		if input.FusionMethod == "weighted" {
			fusionMethod = search.FusionWeighted
		}

		semanticWeight := input.SemanticWeight
		if semanticWeight == 0 {
			semanticWeight = 0.5
		}
		keywordWeight := input.KeywordWeight
		if keywordWeight == 0 {
			keywordWeight = 0.5
		}

		opts := search.SearchOptions{
			Limit:          limit,
			FilterTags:     input.FilterTags,
			FilterPages:    input.FilterPages,
			Scope:          input.Scope,
			FusionMethod:   fusionMethod,
			SemanticWeight: semanticWeight,
			KeywordWeight:  keywordWeight,
		}

		results, err := m.search.Search(ctx, input.Query, opts)
		if err != nil {
			m.logger.Error("hybrid search failed", "error", err)
			res, _ := errorResult(err)
			return res, nil, nil
		}

		res, _ := toolResult(map[string]any{
			"success": true,
			"results": formatSearchResults(results),
		})
		return res, nil, nil
	})
}

func (m *MCPServer) registerGetGraphSchema() {
	mcp.AddTool(m.server, &mcp.Tool{
		Name:        "get_graph_schema",
		Description: "Get the knowledge graph schema for constructing Cypher queries",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input struct{}) (*mcp.CallToolResult, any, error) {
		res, _ := toolResult(map[string]any{
			"success": true,
			"schema":  graphSchema,
		})
		return res, nil, nil
	})
}

// ============ Page Tools ============

type readPageInput struct {
	PageName string `json:"page_name" jsonschema:"Name of the page (e.g. MyPage.md)"`
}

func (m *MCPServer) registerReadPage() {
	mcp.AddTool(m.server, &mcp.Tool{
		Name:        "read_page",
		Description: "Read the contents of a Silverbullet page",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input readPageInput) (*mcp.CallToolResult, any, error) {
		filePath := filepath.Join(m.spacePath, input.PageName)

		// Security check - prevent path traversal
		absFilePath, err := filepath.Abs(filePath)
		if err != nil {
			res, _ := errorResult(err)
			return res, nil, nil
		}
		absSpacePath, _ := filepath.Abs(m.spacePath)
		if !strings.HasPrefix(absFilePath, absSpacePath) {
			res, _ := errorResult(fmt.Errorf("invalid page name: %s", input.PageName))
			return res, nil, nil
		}

		content, err := os.ReadFile(filePath)
		if err != nil {
			if os.IsNotExist(err) {
				res, _ := errorResult(fmt.Errorf("page '%s' not found", input.PageName))
				return res, nil, nil
			}
			res, _ := errorResult(err)
			return res, nil, nil
		}

		res, _ := toolResult(map[string]any{
			"success": true,
			"content": string(content),
		})
		return res, nil, nil
	})
}

type getProjectContextInput struct {
	GithubRemote string `json:"github_remote,omitempty" jsonschema:"GitHub repository in owner/repo format"`
	FolderPath   string `json:"folder_path,omitempty" jsonschema:"Folder path in Silverbullet space"`
}

func (m *MCPServer) registerGetProjectContext() {
	mcp.AddTool(m.server, &mcp.Tool{
		Name:        "get_project_context",
		Description: "Get project context from Silverbullet space by GitHub remote or folder path",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input getProjectContextInput) (*mcp.CallToolResult, any, error) {
		if input.GithubRemote == "" && input.FolderPath == "" {
			res, _ := errorResult(fmt.Errorf("must provide either github_remote or folder_path"))
			return res, nil, nil
		}

		var projectFile string
		var frontmatter map[string]any

		// Search by GitHub remote
		if input.GithubRemote != "" {
			err := filepath.Walk(m.spacePath, func(path string, info os.FileInfo, err error) error {
				if err != nil || info.IsDir() || !strings.HasSuffix(path, ".md") {
					return nil
				}
				fm, _ := m.parser.GetFrontmatter(path)
				if gh, ok := fm["github"].(string); ok && gh == input.GithubRemote {
					projectFile = path
					frontmatter = fm
					return io.EOF // Stop walking
				}
				return nil
			})
			if err != nil && err != io.EOF {
				res, _ := errorResult(err)
				return res, nil, nil
			}
		} else if input.FolderPath != "" {
			// Search by folder path
			parts := strings.Split(input.FolderPath, "/")
			var indexFile string
			if len(parts) > 1 {
				parent := strings.Join(parts[:len(parts)-1], "/")
				indexFile = filepath.Join(m.spacePath, parent, parts[len(parts)-1]+".md")
			} else {
				indexFile = filepath.Join(m.spacePath, input.FolderPath+".md")
			}

			if info, err := os.Stat(indexFile); err == nil && !info.IsDir() {
				projectFile = indexFile
				frontmatter, _ = m.parser.GetFrontmatter(indexFile)
			} else {
				// Try folder contents
				folderDir := filepath.Join(m.spacePath, input.FolderPath)
				entries, _ := os.ReadDir(folderDir)
				for _, e := range entries {
					if !e.IsDir() && strings.HasSuffix(e.Name(), ".md") {
						mdPath := filepath.Join(folderDir, e.Name())
						fm, _ := m.parser.GetFrontmatter(mdPath)
						if len(fm) > 0 {
							projectFile = mdPath
							frontmatter = fm
							break
						}
					}
				}
			}
		}

		if projectFile == "" {
			res, _ := errorResult(fmt.Errorf("no project found for github_remote=%s, folder_path=%s",
				input.GithubRemote, input.FolderPath))
			return res, nil, nil
		}

		// Read content
		content, err := os.ReadFile(projectFile)
		if err != nil {
			res, _ := errorResult(err)
			return res, nil, nil
		}

		// Get relative path
		relPath, _ := filepath.Rel(m.spacePath, projectFile)
		folder := filepath.Dir(relPath)

		// Find related pages
		var relatedPages []map[string]string
		if folder != "." {
			folderDir := filepath.Join(m.spacePath, folder)
			entries, _ := os.ReadDir(folderDir)
			for _, e := range entries {
				if !e.IsDir() && strings.HasSuffix(e.Name(), ".md") {
					mdPath := filepath.Join(folderDir, e.Name())
					if mdPath != projectFile {
						relatedPages = append(relatedPages, map[string]string{
							"name": strings.TrimSuffix(e.Name(), ".md"),
							"path": filepath.Join(folder, e.Name()),
						})
					}
				}
			}
		}

		// Check for subdirectory
		projectName := strings.TrimSuffix(filepath.Base(projectFile), ".md")
		subDir := filepath.Join(filepath.Dir(projectFile), projectName)
		if info, err := os.Stat(subDir); err == nil && info.IsDir() {
			_ = filepath.Walk(subDir, func(path string, info os.FileInfo, err error) error {
				if err == nil && !info.IsDir() && strings.HasSuffix(path, ".md") {
					rel, _ := filepath.Rel(m.spacePath, path)
					relatedPages = append(relatedPages, map[string]string{
						"name": strings.TrimSuffix(info.Name(), ".md"),
						"path": rel,
					})
				}
				return nil
			})
		}

		// Limit related pages
		if len(relatedPages) > 20 {
			relatedPages = relatedPages[:20]
		}

		// Get tags and concerns from frontmatter
		var tags, concerns []string
		if t, ok := frontmatter["tags"].([]any); ok {
			for _, v := range t {
				if s, ok := v.(string); ok {
					tags = append(tags, s)
				}
			}
		}
		if c, ok := frontmatter["concerns"].([]any); ok {
			for _, v := range c {
				if s, ok := v.(string); ok {
					concerns = append(concerns, s)
				}
			}
		}

		res, _ := toolResult(map[string]any{
			"success": true,
			"project": map[string]any{
				"file":     relPath,
				"github":   frontmatter["github"],
				"tags":     tags,
				"concerns": concerns,
				"content":  string(content),
			},
			"related_pages": relatedPages,
		})
		return res, nil, nil
	})
}

// ============ Proposal Tools ============

type proposeChangeInput struct {
	TargetPage  string `json:"target_page" jsonschema:"Page path (e.g. Projects/MyProject.md)"`
	Content     string `json:"content" jsonschema:"Proposed page content"`
	Title       string `json:"title" jsonschema:"Short title for the proposal"`
	Description string `json:"description" jsonschema:"Explanation of why this change is proposed"`
}

func (m *MCPServer) registerProposeChange() {
	mcp.AddTool(m.server, &mcp.Tool{
		Name:        "propose_change",
		Description: "Propose a change to a page. Requires Proposals library installed.",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input proposeChangeInput) (*mcp.CallToolResult, any, error) {
		// Check if proposals are enabled
		if !m.proposalsEnabled {
			res, _ := toolResult(map[string]any{
				"success":      false,
				"error":        "Proposals library not installed",
				"instructions": "Install the Proposals library from Library Manager",
			})
			return res, nil, nil
		}

		// Security check
		filePath := filepath.Join(m.spacePath, input.TargetPage)
		absFilePath, _ := filepath.Abs(filePath)
		absSpacePath, _ := filepath.Abs(m.spacePath)
		if !strings.HasPrefix(absFilePath, absSpacePath) {
			res, _ := errorResult(fmt.Errorf("invalid page name: %s", input.TargetPage))
			return res, nil, nil
		}

		// Check if target exists
		_, err := os.Stat(filePath)
		isNewPage := os.IsNotExist(err)

		// Get prefix from config (default _Proposals/)
		prefix := "_Proposals/"
		configPath := filepath.Join(m.dbPath, "space_config.json")
		if data, err := os.ReadFile(configPath); err == nil {
			var cfg map[string]any
			if json.Unmarshal(data, &cfg) == nil {
				if p, ok := cfg["proposals.pathPrefix"].(string); ok {
					prefix = p
				}
			}
		}

		// Create proposal path
		proposalPath := prefix + strings.TrimSuffix(input.TargetPage, ".md") + ".proposal"

		// Create proposal content
		proposalContent := fmt.Sprintf(`---
title: %s
target_page: %s
status: pending
is_new_page: %v
---
## Description
%s

## Proposed Content
%s
`, input.Title, input.TargetPage, isNewPage, input.Description, input.Content)

		// Write proposal file
		fullPath := filepath.Join(m.spacePath, proposalPath)
		if err := os.MkdirAll(filepath.Dir(fullPath), 0755); err != nil {
			res, _ := errorResult(err)
			return res, nil, nil
		}
		if err := os.WriteFile(fullPath, []byte(proposalContent), 0644); err != nil {
			res, _ := errorResult(err)
			return res, nil, nil
		}

		m.logger.Info("created proposal", "path", proposalPath)

		res, _ := toolResult(map[string]any{
			"success":       true,
			"proposal_path": proposalPath,
			"is_new_page":   isNewPage,
			"message":       fmt.Sprintf("Proposal created. User can review at %s", proposalPath),
		})
		return res, nil, nil
	})
}

type listProposalsInput struct {
	Status string `json:"status,omitempty" jsonschema:"Filter by status: pending, accepted, rejected, or all (default: pending)"`
}

func (m *MCPServer) registerListProposals() {
	mcp.AddTool(m.server, &mcp.Tool{
		Name:        "list_proposals",
		Description: "List change proposals by status",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input listProposalsInput) (*mcp.CallToolResult, any, error) {
		// Check if proposals are enabled
		if !m.proposalsEnabled {
			res, _ := toolResult(map[string]any{
				"success": false,
				"error":   "Proposals library not installed",
			})
			return res, nil, nil
		}

		status := input.Status
		if status == "" {
			status = "pending"
		}

		// Get prefix
		prefix := "_Proposals/"
		configPath := filepath.Join(m.dbPath, "space_config.json")
		if data, err := os.ReadFile(configPath); err == nil {
			var cfg map[string]any
			if json.Unmarshal(data, &cfg) == nil {
				if p, ok := cfg["proposals.pathPrefix"].(string); ok {
					prefix = p
				}
			}
		}

		proposalsDir := filepath.Join(m.spacePath, prefix)
		var proposals []map[string]any

		_ = filepath.Walk(proposalsDir, func(path string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() || !strings.HasSuffix(path, ".proposal") {
				return nil
			}

			content, err := os.ReadFile(path)
			if err != nil {
				return nil
			}

			// Parse frontmatter
			fm := m.parseProposalFrontmatter(string(content))
			proposalStatus, _ := fm["status"].(string)

			if status == "all" || status == proposalStatus {
				relPath, _ := filepath.Rel(m.spacePath, path)
				proposals = append(proposals, map[string]any{
					"path":        relPath,
					"title":       fm["title"],
					"target_page": fm["target_page"],
					"status":      proposalStatus,
					"is_new_page": fm["is_new_page"],
				})
			}
			return nil
		})

		res, _ := toolResult(map[string]any{
			"success":   true,
			"count":     len(proposals),
			"proposals": proposals,
		})
		return res, nil, nil
	})
}

type withdrawProposalInput struct {
	ProposalPath string `json:"proposal_path" jsonschema:"Path to the .proposal file"`
}

func (m *MCPServer) registerWithdrawProposal() {
	mcp.AddTool(m.server, &mcp.Tool{
		Name:        "withdraw_proposal",
		Description: "Withdraw a pending proposal",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input withdrawProposalInput) (*mcp.CallToolResult, any, error) {
		// Check if proposals are enabled
		if !m.proposalsEnabled {
			res, _ := toolResult(map[string]any{
				"success": false,
				"error":   "Proposals library not installed",
			})
			return res, nil, nil
		}

		fullPath := filepath.Join(m.spacePath, input.ProposalPath)

		// Security check
		absPath, _ := filepath.Abs(fullPath)
		absSpacePath, _ := filepath.Abs(m.spacePath)
		if !strings.HasPrefix(absPath, absSpacePath) {
			res, _ := errorResult(fmt.Errorf("invalid proposal path: %s", input.ProposalPath))
			return res, nil, nil
		}

		if !strings.HasSuffix(input.ProposalPath, ".proposal") {
			res, _ := errorResult(fmt.Errorf("not a proposal file"))
			return res, nil, nil
		}

		if _, err := os.Stat(fullPath); os.IsNotExist(err) {
			res, _ := errorResult(fmt.Errorf("proposal not found"))
			return res, nil, nil
		}

		if err := os.Remove(fullPath); err != nil {
			res, _ := errorResult(err)
			return res, nil, nil
		}

		m.logger.Info("withdrew proposal", "path", input.ProposalPath)

		res, _ := toolResult(map[string]any{
			"success": true,
			"message": "Proposal withdrawn",
		})
		return res, nil, nil
	})
}

func (m *MCPServer) parseProposalFrontmatter(content string) map[string]any {
	result := make(map[string]any)
	if !strings.HasPrefix(content, "---") {
		return result
	}

	endIdx := strings.Index(content[3:], "\n---")
	if endIdx < 0 {
		return result
	}

	fm := content[4 : endIdx+3]
	for _, line := range strings.Split(fm, "\n") {
		parts := strings.SplitN(line, ":", 2)
		if len(parts) == 2 {
			key := strings.TrimSpace(parts[0])
			value := strings.TrimSpace(parts[1])
			if value == "true" {
				result[key] = true
			} else if value == "false" {
				result[key] = false
			} else {
				result[key] = value
			}
		}
	}
	return result
}

// ============ Library Tools ============

type installLibraryInput struct {
	LibraryName string `json:"library_name,omitempty" jsonschema:"Name of the library to install (default: Proposals)"`
}

func (m *MCPServer) registerInstallLibrary() {
	mcp.AddTool(m.server, &mcp.Tool{
		Name:        "install_library",
		Description: "Install a library into the SilverBullet space",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input installLibraryInput) (*mcp.CallToolResult, any, error) {
		libraryName := input.LibraryName
		if libraryName == "" {
			libraryName = "Proposals"
		}

		if libraryName != "Proposals" {
			res, _ := errorResult(fmt.Errorf("unknown library: %s. Available: [Proposals]", libraryName))
			return res, nil, nil
		}

		sourcePath := filepath.Join(m.libraryPath, libraryName+".md")
		if _, err := os.Stat(sourcePath); os.IsNotExist(err) {
			res, _ := errorResult(fmt.Errorf("library source not found at %s", m.libraryPath))
			return res, nil, nil
		}

		destPath := filepath.Join(m.spacePath, "Library")
		markerFile := filepath.Join(destPath, libraryName+".md")

		if _, err := os.Stat(markerFile); err == nil {
			res, _ := toolResult(map[string]any{
				"success":           false,
				"error":             fmt.Sprintf("Library '%s' is already installed. Use update_library to update.", libraryName),
				"already_installed": true,
			})
			return res, nil, nil
		}

		// Copy files
		if err := os.MkdirAll(destPath, 0755); err != nil {
			res, _ := errorResult(err)
			return res, nil, nil
		}

		// Get version from source
		srcRoot := filepath.Join(m.libraryPath, libraryName+".md")
		libraryVersion := m.getLibraryVersion(srcRoot)
		if libraryVersion == "" {
			libraryVersion = "unknown"
		}

		installedFiles, err := m.copyLibraryFiles(libraryName, false)
		if err != nil {
			res, _ := errorResult(err)
			return res, nil, nil
		}

		m.logger.Info("installed library", "name", libraryName, "version", libraryVersion, "files", len(installedFiles))

		// Refresh proposals status after install
		m.refreshProposalsStatus()

		res, _ := toolResult(map[string]any{
			"success":         true,
			"library":         libraryName,
			"version":         libraryVersion,
			"installed_files": installedFiles,
			"message":         fmt.Sprintf("Library '%s' v%s installed successfully.", libraryName, libraryVersion),
		})
		return res, nil, nil
	})
}

type updateLibraryInput struct {
	LibraryName string `json:"library_name,omitempty" jsonschema:"Name of the library to update (default: Proposals)"`
}

func (m *MCPServer) registerUpdateLibrary() {
	mcp.AddTool(m.server, &mcp.Tool{
		Name:        "update_library",
		Description: "Update an existing library installation",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input updateLibraryInput) (*mcp.CallToolResult, any, error) {
		libraryName := input.LibraryName
		if libraryName == "" {
			libraryName = "Proposals"
		}

		if libraryName != "Proposals" {
			res, _ := errorResult(fmt.Errorf("unknown library: %s. Available: [Proposals]", libraryName))
			return res, nil, nil
		}

		destPath := filepath.Join(m.spacePath, "Library")
		markerFile := filepath.Join(destPath, libraryName+".md")

		if _, err := os.Stat(markerFile); os.IsNotExist(err) {
			res, _ := toolResult(map[string]any{
				"success":       false,
				"error":         fmt.Sprintf("Library '%s' is not installed. Use install_library first.", libraryName),
				"not_installed": true,
			})
			return res, nil, nil
		}

		// Get current installed version
		currentVersion := m.getLibraryVersion(markerFile)

		// Get new version from source
		srcRoot := filepath.Join(m.libraryPath, libraryName+".md")
		newVersion := m.getLibraryVersion(srcRoot)
		if newVersion == "" {
			newVersion = "unknown"
		}

		installedFiles, err := m.copyLibraryFiles(libraryName, true)
		if err != nil {
			res, _ := errorResult(err)
			return res, nil, nil
		}

		m.logger.Info("updated library", "name", libraryName, "from", currentVersion, "to", newVersion, "files", len(installedFiles))

		// Refresh proposals status after update
		m.refreshProposalsStatus()

		res, _ := toolResult(map[string]any{
			"success":          true,
			"library":          libraryName,
			"previous_version": currentVersion,
			"version":          newVersion,
			"installed_files":  installedFiles,
			"message":          fmt.Sprintf("Library '%s' updated from v%s to v%s.", libraryName, currentVersion, newVersion),
		})
		return res, nil, nil
	})
}

// getLibraryVersion extracts version from library frontmatter.
func (m *MCPServer) getLibraryVersion(libraryPath string) string {
	content, err := os.ReadFile(libraryPath)
	if err != nil {
		return ""
	}
	re := regexp.MustCompile(`(?m)^version:\s*(.+)$`)
	match := re.FindSubmatch(content)
	if match != nil {
		return strings.TrimSpace(string(match[1]))
	}
	return ""
}

// addInstallMetadata adds installed_version and installed_at to frontmatter.
func (m *MCPServer) addInstallMetadata(content string, version string) string {
	now := time.Now().UTC().Format("2006-01-02")

	// Check if frontmatter exists
	if !strings.HasPrefix(content, "---") {
		return content
	}

	// Find the end of frontmatter
	re := regexp.MustCompile(`\n---\s*\n`)
	loc := re.FindStringIndex(content)
	if loc == nil {
		return content
	}

	frontmatterEnd := loc[0]
	frontmatter := content[:frontmatterEnd+1]
	rest := content[loc[1]-1:]

	// Remove existing install metadata if present
	frontmatter = regexp.MustCompile(`(?m)^installed_version:.*\n`).ReplaceAllString(frontmatter, "")
	frontmatter = regexp.MustCompile(`(?m)^installed_at:.*\n`).ReplaceAllString(frontmatter, "")

	// Add new metadata before the closing ---
	newMetadata := fmt.Sprintf("installed_version: %s\ninstalled_at: %s\n", version, now)
	newFrontmatter := frontmatter + newMetadata

	return newFrontmatter + "---" + rest
}

func (m *MCPServer) copyLibraryFiles(libraryName string, overwrite bool) ([]string, error) {
	sourcePath := m.libraryPath
	destPath := filepath.Join(m.spacePath, "Library")

	var installedFiles []string

	// Get version from source library
	srcRoot := filepath.Join(sourcePath, libraryName+".md")
	version := m.getLibraryVersion(srcRoot)
	if version == "" {
		version = "unknown"
	}

	// Copy root .md file with install metadata
	dstRoot := filepath.Join(destPath, libraryName+".md")

	content, err := os.ReadFile(srcRoot)
	if err != nil {
		return nil, err
	}

	// Add install metadata to content
	contentWithMetadata := m.addInstallMetadata(string(content), version)

	if err := os.WriteFile(dstRoot, []byte(contentWithMetadata), 0644); err != nil {
		return nil, err
	}
	installedFiles = append(installedFiles, filepath.Join("Library", libraryName+".md"))

	// Copy subdirectory if exists
	srcSubdir := filepath.Join(sourcePath, libraryName)
	if info, err := os.Stat(srcSubdir); err == nil && info.IsDir() {
		dstSubdir := filepath.Join(destPath, libraryName)
		if overwrite {
			_ = os.RemoveAll(dstSubdir)
		}

		_ = filepath.Walk(srcSubdir, func(path string, info os.FileInfo, err error) error {
			if err != nil {
				return nil
			}

			relPath, _ := filepath.Rel(sourcePath, path)
			dstPath := filepath.Join(destPath, relPath)

			if info.IsDir() {
				_ = os.MkdirAll(dstPath, 0755)
			} else {
				content, err := os.ReadFile(path)
				if err != nil {
					return nil
				}
				_ = os.MkdirAll(filepath.Dir(dstPath), 0755)
				if err := os.WriteFile(dstPath, content, 0644); err != nil {
					return nil
				}
				installedFiles = append(installedFiles, filepath.Join("Library", relPath))
			}
			return nil
		})
	}

	return installedFiles, nil
}

// ============ Helpers ============

func formatSearchResults(results []types.SearchResult) []map[string]any {
	formatted := make([]map[string]any, len(results))
	for i, r := range results {
		formatted[i] = map[string]any{
			"chunk_id":       r.Chunk.ID,
			"file_path":      r.Chunk.FilePath,
			"header":         r.Chunk.Header,
			"content":        r.Chunk.Content,
			"hybrid_score":   r.HybridScore,
			"keyword_score":  r.KeywordScore,
			"semantic_score": r.SemanticScore,
		}
	}
	return formatted
}

// Graph schema definition
var graphSchema = map[string]any{
	"nodes": map[string]any{
		"Page": map[string]any{
			"description": "A markdown page in the Silverbullet space",
			"properties":  []string{"name"},
			"example":     "MATCH (p:Page {name: 'Projects/MyProject'}) RETURN p",
		},
		"Chunk": map[string]any{
			"description": "A section of a page (split by headers)",
			"properties":  []string{"id", "file_path", "header", "content", "frontmatter"},
			"example":     "MATCH (c:Chunk) WHERE c.content CONTAINS 'search term' RETURN c",
		},
		"Tag": map[string]any{
			"description": "A hashtag used in pages",
			"properties":  []string{"name"},
			"example":     "MATCH (t:Tag {name: 'project'}) RETURN t",
		},
		"Folder": map[string]any{
			"description": "A folder in the space hierarchy",
			"properties":  []string{"path", "name"},
			"example":     "MATCH (f:Folder {path: 'Projects'}) RETURN f",
		},
		"Attribute": map[string]any{
			"description": "An inline attribute [key:: value]",
			"properties":  []string{"id", "name", "value"},
			"example":     "MATCH (a:Attribute {name: 'status'}) RETURN a",
		},
		"DataBlock": map[string]any{
			"description": "A YAML data block with structured data",
			"properties":  []string{"id", "tag", "data", "file_path"},
			"example":     "MATCH (d:DataBlock {tag: 'task'}) RETURN d",
		},
	},
	"relationships": []map[string]any{
		{
			"type":        "HAS_CHUNK",
			"from":        "Page",
			"to":          "Chunk",
			"properties":  []string{"chunk_order"},
			"description": "Page contains chunks in order",
			"example":     "MATCH (p:Page)-[r:HAS_CHUNK]->(c:Chunk) RETURN c ORDER BY r.chunk_order",
		},
		{
			"type":        "PAGE_LINKS_TO",
			"from":        "Page",
			"to":          "Page",
			"properties":  []string{},
			"description": "Page links to another page (derived from wikilinks)",
			"example":     "MATCH (p:Page {name: 'Index'})-[:PAGE_LINKS_TO]->(linked:Page) RETURN linked",
		},
		{
			"type":        "LINKS_TO",
			"from":        "Chunk",
			"to":          "Page",
			"properties":  []string{},
			"description": "Chunk contains a wikilink to a page",
			"example":     "MATCH (c:Chunk)-[:LINKS_TO]->(p:Page) RETURN c, p",
		},
		{
			"type":        "TAGGED",
			"from":        "Chunk",
			"to":          "Tag",
			"properties":  []string{},
			"description": "Chunk has a hashtag",
			"example":     "MATCH (c:Chunk)-[:TAGGED]->(t:Tag {name: 'important'}) RETURN c",
		},
		{
			"type":        "EMBEDS",
			"from":        "Chunk",
			"to":          "Page",
			"properties":  []string{"header"},
			"description": "Chunk transcludes/embeds another page",
			"example":     "MATCH (c:Chunk)-[r:EMBEDS]->(p:Page) RETURN c, p, r.header",
		},
		{
			"type":        "HAS_ATTRIBUTE",
			"from":        "Chunk",
			"to":          "Attribute",
			"properties":  []string{},
			"description": "Chunk contains an inline attribute",
			"example":     "MATCH (c:Chunk)-[:HAS_ATTRIBUTE]->(a:Attribute {name: 'due'}) RETURN c, a.value",
		},
		{
			"type":        "HAS_DATA_BLOCK",
			"from":        "Chunk",
			"to":          "DataBlock",
			"properties":  []string{},
			"description": "Chunk contains a data block",
			"example":     "MATCH (c:Chunk)-[:HAS_DATA_BLOCK]->(d:DataBlock) RETURN d",
		},
		{
			"type":        "DATA_TAGGED",
			"from":        "DataBlock",
			"to":          "Tag",
			"properties":  []string{},
			"description": "DataBlock is tagged with its block type",
			"example":     "MATCH (d:DataBlock)-[:DATA_TAGGED]->(t:Tag {name: 'task'}) RETURN d",
		},
		{
			"type":        "IN_FOLDER",
			"from":        "Chunk",
			"to":          "Folder",
			"properties":  []string{},
			"description": "Chunk belongs to a folder",
			"example":     "MATCH (c:Chunk)-[:IN_FOLDER]->(f:Folder {path: 'Projects'}) RETURN c",
		},
		{
			"type":        "CONTAINS",
			"from":        "Folder",
			"to":          "Folder",
			"properties":  []string{},
			"description": "Folder contains a subfolder",
			"example":     "MATCH (f:Folder {path: 'Projects'})-[:CONTAINS]->(sub:Folder) RETURN sub",
		},
		{
			"type":        "FOLDER_CONTAINS_PAGE",
			"from":        "Folder",
			"to":          "Page",
			"properties":  []string{},
			"description": "Folder contains a page",
			"example":     "MATCH (f:Folder)-[:FOLDER_CONTAINS_PAGE]->(p:Page) RETURN p",
		},
	},
	"common_patterns": []map[string]any{
		{
			"name":        "Find backlinks",
			"description": "Find all pages that link to a specific page",
			"query":       "MATCH (source:Page)-[:PAGE_LINKS_TO]->(target:Page {name: $page_name}) RETURN source.name",
		},
		{
			"name":        "Get page content",
			"description": "Get all chunks of a page in order",
			"query":       "MATCH (p:Page {name: $page_name})-[r:HAS_CHUNK]->(c:Chunk) RETURN c.content ORDER BY r.chunk_order",
		},
		{
			"name":        "Find pages by tag",
			"description": "Find all pages containing a specific tag",
			"query":       "MATCH (p:Page)-[:HAS_CHUNK]->(c:Chunk)-[:TAGGED]->(t:Tag {name: $tag_name}) RETURN DISTINCT p.name",
		},
	},
}
