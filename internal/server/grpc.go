// Package server provides MCP and gRPC server implementations.
package server

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net"
	"os"
	"path/filepath"
	"strings"
	"time"

	"google.golang.org/grpc"

	"github.com/boblangley/silverbullet-rag/internal/db"
	"github.com/boblangley/silverbullet-rag/internal/parser"
	pb "github.com/boblangley/silverbullet-rag/internal/proto"
	"github.com/boblangley/silverbullet-rag/internal/search"
)

// GRPCServer provides the gRPC interface to silverbullet-rag.
type GRPCServer struct {
	pb.UnimplementedRAGServiceServer
	server    *grpc.Server
	db        *db.GraphDB
	search    *search.HybridSearch
	parser    *parser.SpaceParser
	spacePath string
	dbPath    string
	logger    *slog.Logger
}

// GRPCConfig holds gRPC server configuration.
type GRPCConfig struct {
	DB        *db.GraphDB
	Search    *search.HybridSearch
	Parser    *parser.SpaceParser
	SpacePath string
	DBPath    string
	Logger    *slog.Logger
}

// NewGRPCServer creates a new gRPC server instance.
func NewGRPCServer(cfg GRPCConfig) *GRPCServer {
	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	s := &GRPCServer{
		server:    grpc.NewServer(),
		db:        cfg.DB,
		search:    cfg.Search,
		parser:    cfg.Parser,
		spacePath: cfg.SpacePath,
		dbPath:    cfg.DBPath,
		logger:    logger,
	}

	pb.RegisterRAGServiceServer(s.server, s)
	return s
}

// Serve starts the gRPC server on the given address.
func (s *GRPCServer) Serve(addr string) error {
	lis, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("failed to listen: %w", err)
	}
	s.logger.Info("gRPC server listening", "addr", addr)
	return s.server.Serve(lis)
}

// Stop gracefully stops the gRPC server.
func (s *GRPCServer) Stop() {
	s.server.GracefulStop()
}

// Query executes a Cypher query against the knowledge graph.
func (s *GRPCServer) Query(ctx context.Context, req *pb.QueryRequest) (*pb.QueryResponse, error) {
	results, err := s.db.Execute(ctx, req.CypherQuery, nil)
	if err != nil {
		s.logger.Error("Query error", "error", err)
		return &pb.QueryResponse{Success: false, Error: err.Error()}, nil
	}

	jsonBytes, err := json.Marshal(results)
	if err != nil {
		return &pb.QueryResponse{Success: false, Error: err.Error()}, nil
	}

	return &pb.QueryResponse{
		ResultsJson: string(jsonBytes),
		Success:     true,
	}, nil
}

// Search performs keyword search using BM25 ranking.
func (s *GRPCServer) Search(ctx context.Context, req *pb.SearchRequest) (*pb.SearchResponse, error) {
	limit := int(req.Limit)
	if limit <= 0 {
		limit = 10
	}

	opts := search.SearchOptions{
		Limit:          limit,
		SemanticWeight: 0,
		KeywordWeight:  1,
	}

	results, err := s.search.Search(ctx, req.Keyword, opts)
	if err != nil {
		s.logger.Error("Search error", "error", err)
		return &pb.SearchResponse{Success: false, Error: err.Error()}, nil
	}

	jsonBytes, err := json.Marshal(results)
	if err != nil {
		return &pb.SearchResponse{Success: false, Error: err.Error()}, nil
	}

	return &pb.SearchResponse{
		ResultsJson: string(jsonBytes),
		Success:     true,
	}, nil
}

// SemanticSearch performs semantic search using vector embeddings.
func (s *GRPCServer) SemanticSearch(ctx context.Context, req *pb.SemanticSearchRequest) (*pb.SemanticSearchResponse, error) {
	limit := int(req.Limit)
	if limit <= 0 {
		limit = 10
	}

	opts := search.SearchOptions{
		Limit:          limit,
		FilterTags:     req.FilterTags,
		FilterPages:    req.FilterPages,
		SemanticWeight: 1,
		KeywordWeight:  0,
	}

	results, err := s.search.Search(ctx, req.Query, opts)
	if err != nil {
		s.logger.Error("SemanticSearch error", "error", err)
		return &pb.SemanticSearchResponse{Success: false, Error: err.Error()}, nil
	}

	jsonBytes, err := json.Marshal(results)
	if err != nil {
		return &pb.SemanticSearchResponse{Success: false, Error: err.Error()}, nil
	}

	return &pb.SemanticSearchResponse{
		ResultsJson: string(jsonBytes),
		Success:     true,
	}, nil
}

// HybridSearch performs combined keyword and semantic search.
func (s *GRPCServer) HybridSearch(ctx context.Context, req *pb.HybridSearchRequest) (*pb.HybridSearchResponse, error) {
	limit := int(req.Limit)
	if limit <= 0 {
		limit = 10
	}

	fusionMethod := search.FusionRRF
	if req.FusionMethod == "weighted" {
		fusionMethod = search.FusionWeighted
	}

	semanticWeight := float64(req.SemanticWeight)
	if semanticWeight <= 0 {
		semanticWeight = 0.5
	}

	keywordWeight := float64(req.KeywordWeight)
	if keywordWeight <= 0 {
		keywordWeight = 0.5
	}

	opts := search.SearchOptions{
		Limit:          limit,
		FilterTags:     req.FilterTags,
		FilterPages:    req.FilterPages,
		FusionMethod:   fusionMethod,
		SemanticWeight: semanticWeight,
		KeywordWeight:  keywordWeight,
	}

	results, err := s.search.Search(ctx, req.Query, opts)
	if err != nil {
		s.logger.Error("HybridSearch error", "error", err)
		return &pb.HybridSearchResponse{Success: false, Error: err.Error()}, nil
	}

	jsonBytes, err := json.Marshal(results)
	if err != nil {
		return &pb.HybridSearchResponse{Success: false, Error: err.Error()}, nil
	}

	return &pb.HybridSearchResponse{
		ResultsJson: string(jsonBytes),
		Success:     true,
	}, nil
}

// ReadPage reads the content of a page from the space.
func (s *GRPCServer) ReadPage(ctx context.Context, req *pb.ReadPageRequest) (*pb.ReadPageResponse, error) {
	pagePath := filepath.Join(s.spacePath, req.PageName)

	// Security check - prevent path traversal
	absPath, err := filepath.Abs(pagePath)
	if err != nil {
		return &pb.ReadPageResponse{Success: false, Error: "Invalid page name"}, nil
	}
	absSpace, _ := filepath.Abs(s.spacePath)
	if !strings.HasPrefix(absPath, absSpace) {
		return &pb.ReadPageResponse{Success: false, Error: "Invalid page name"}, nil
	}

	content, err := os.ReadFile(pagePath)
	if err != nil {
		if os.IsNotExist(err) {
			return &pb.ReadPageResponse{
				Success: false,
				Error:   fmt.Sprintf("Page '%s' not found", req.PageName),
			}, nil
		}
		return &pb.ReadPageResponse{Success: false, Error: err.Error()}, nil
	}

	return &pb.ReadPageResponse{
		Success: true,
		Content: string(content),
	}, nil
}

// ProposeChange creates a proposal for a page change.
func (s *GRPCServer) ProposeChange(ctx context.Context, req *pb.ProposeChangeRequest) (*pb.ProposeChangeResponse, error) {
	// Check if proposals library is installed
	libraryPath := filepath.Join(s.spacePath, "Library", "Proposals")
	if _, err := os.Stat(libraryPath); os.IsNotExist(err) {
		return &pb.ProposeChangeResponse{
			Success: false,
			Error:   "Proposals library not installed",
			Message: "Install the Proposals library from Library Manager",
		}, nil
	}

	// Security check - prevent path traversal
	targetPath := filepath.Join(s.spacePath, req.TargetPage)
	absPath, err := filepath.Abs(targetPath)
	if err != nil {
		return &pb.ProposeChangeResponse{
			Success: false,
			Error:   fmt.Sprintf("Invalid page name: %s", req.TargetPage),
		}, nil
	}
	absSpace, _ := filepath.Abs(s.spacePath)
	if !strings.HasPrefix(absPath, absSpace) {
		return &pb.ProposeChangeResponse{
			Success: false,
			Error:   fmt.Sprintf("Invalid page name: %s", req.TargetPage),
		}, nil
	}

	// Check if page exists
	isNewPage := false
	if _, err := os.Stat(targetPath); os.IsNotExist(err) {
		isNewPage = true
	}

	// Get proposals config prefix
	prefix := "_Proposals/"
	configPath := filepath.Join(s.dbPath, "config.json")
	if configData, err := os.ReadFile(configPath); err == nil {
		var config map[string]interface{}
		if json.Unmarshal(configData, &config) == nil {
			if proposals, ok := config["proposals"].(map[string]interface{}); ok {
				if p, ok := proposals["path_prefix"].(string); ok {
					prefix = p
				}
			}
		}
	}

	// Generate proposal path
	proposalPath := prefix + strings.TrimSuffix(req.TargetPage, ".md") + ".proposal"

	// Set default proposed_by if not provided
	proposedBy := req.ProposedBy
	if proposedBy == "" {
		proposedBy = "claude-code"
	}

	// Generate proposal content with proper metadata
	createdAt := time.Now().Format(time.RFC3339)
	proposalContent := fmt.Sprintf(`---
type: proposal
tags:
- proposal
target_page: %s
title: %s
description: %s
proposed_by: %s
created_at: %s
status: pending
is_new_page: %t
---

%s
`, req.TargetPage, req.Title, req.Description, proposedBy, createdAt, isNewPage, req.Content)

	// Write proposal file
	fullPath := filepath.Join(s.spacePath, proposalPath)
	if err := os.MkdirAll(filepath.Dir(fullPath), 0755); err != nil {
		return &pb.ProposeChangeResponse{Success: false, Error: err.Error()}, nil
	}

	if err := os.WriteFile(fullPath, []byte(proposalContent), 0644); err != nil {
		return &pb.ProposeChangeResponse{Success: false, Error: err.Error()}, nil
	}

	s.logger.Info("Created proposal", "path", proposalPath)

	return &pb.ProposeChangeResponse{
		Success:      true,
		ProposalPath: proposalPath,
		IsNewPage:    isNewPage,
		Message:      fmt.Sprintf("Proposal created. User can review at %s", proposalPath),
	}, nil
}

// ListProposals lists change proposals by status.
func (s *GRPCServer) ListProposals(ctx context.Context, req *pb.ListProposalsRequest) (*pb.ListProposalsResponse, error) {
	// Check if proposals library is installed
	libraryPath := filepath.Join(s.spacePath, "Library", "Proposals")
	if _, err := os.Stat(libraryPath); os.IsNotExist(err) {
		return &pb.ListProposalsResponse{
			Success: false,
			Error:   "Proposals library not installed",
		}, nil
	}

	// Get proposals config prefix
	prefix := "_Proposals/"
	configPath := filepath.Join(s.dbPath, "config.json")
	if configData, err := os.ReadFile(configPath); err == nil {
		var config map[string]interface{}
		if json.Unmarshal(configData, &config) == nil {
			if proposals, ok := config["proposals"].(map[string]interface{}); ok {
				if p, ok := proposals["path_prefix"].(string); ok {
					prefix = p
				}
			}
		}
	}

	status := req.Status
	if status == "" {
		status = "pending"
	}

	proposalsDir := filepath.Join(s.spacePath, prefix)
	var proposals []*pb.ProposalInfo

	err := filepath.Walk(proposalsDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return nil // Ignore errors
		}
		if info.IsDir() || !strings.HasSuffix(path, ".proposal") {
			return nil
		}

		content, err := os.ReadFile(path)
		if err != nil {
			return nil
		}

		// Parse frontmatter
		proposal := parseProposalFrontmatter(string(content))
		if proposal == nil {
			return nil
		}

		// Filter by status
		if status != "all" && proposal.Status != status {
			return nil
		}

		relPath, _ := filepath.Rel(s.spacePath, path)
		proposal.Path = relPath
		proposals = append(proposals, proposal)
		return nil
	})

	if err != nil && !os.IsNotExist(err) {
		return &pb.ListProposalsResponse{Success: false, Error: err.Error()}, nil
	}

	return &pb.ListProposalsResponse{
		Success:   true,
		Count:     int32(len(proposals)),
		Proposals: proposals,
	}, nil
}

// parseProposalFrontmatter extracts proposal metadata from frontmatter.
func parseProposalFrontmatter(content string) *pb.ProposalInfo {
	if !strings.HasPrefix(content, "---") {
		return nil
	}

	endIdx := strings.Index(content[3:], "---")
	if endIdx == -1 {
		return nil
	}

	frontmatter := content[3 : endIdx+3]
	proposal := &pb.ProposalInfo{}

	for _, line := range strings.Split(frontmatter, "\n") {
		line = strings.TrimSpace(line)
		if idx := strings.Index(line, ":"); idx > 0 {
			key := strings.TrimSpace(line[:idx])
			value := strings.TrimSpace(line[idx+1:])
			switch key {
			case "target_page":
				proposal.TargetPage = value
			case "title":
				proposal.Title = value
			case "description":
				proposal.Description = value
			case "status":
				proposal.Status = value
			case "is_new_page":
				proposal.IsNewPage = value == "true"
			case "proposed_by":
				proposal.ProposedBy = value
			case "created_at":
				proposal.CreatedAt = value
			}
		}
	}

	return proposal
}

// WithdrawProposal deletes a pending proposal.
func (s *GRPCServer) WithdrawProposal(ctx context.Context, req *pb.WithdrawProposalRequest) (*pb.WithdrawProposalResponse, error) {
	// Check if proposals library is installed
	libraryPath := filepath.Join(s.spacePath, "Library", "Proposals")
	if _, err := os.Stat(libraryPath); os.IsNotExist(err) {
		return &pb.WithdrawProposalResponse{
			Success: false,
			Error:   "Proposals library not installed",
		}, nil
	}

	fullPath := filepath.Join(s.spacePath, req.ProposalPath)

	// Security check - prevent path traversal
	absPath, err := filepath.Abs(fullPath)
	if err != nil {
		return &pb.WithdrawProposalResponse{
			Success: false,
			Error:   fmt.Sprintf("Invalid proposal path: %s", req.ProposalPath),
		}, nil
	}
	absSpace, _ := filepath.Abs(s.spacePath)
	if !strings.HasPrefix(absPath, absSpace) {
		return &pb.WithdrawProposalResponse{
			Success: false,
			Error:   fmt.Sprintf("Invalid proposal path: %s", req.ProposalPath),
		}, nil
	}

	if _, err := os.Stat(fullPath); os.IsNotExist(err) {
		return &pb.WithdrawProposalResponse{
			Success: false,
			Error:   "Proposal not found",
		}, nil
	}

	if !strings.HasSuffix(req.ProposalPath, ".proposal") {
		return &pb.WithdrawProposalResponse{
			Success: false,
			Error:   "Not a proposal file",
		}, nil
	}

	if err := os.Remove(fullPath); err != nil {
		return &pb.WithdrawProposalResponse{Success: false, Error: err.Error()}, nil
	}

	s.logger.Info("Withdrew proposal", "path", req.ProposalPath)

	return &pb.WithdrawProposalResponse{
		Success: true,
		Message: "Proposal withdrawn",
	}, nil
}

// GetFolderContext finds pages with matching openwebui-folder frontmatter.
func (s *GRPCServer) GetFolderContext(ctx context.Context, req *pb.GetFolderContextRequest) (*pb.GetFolderContextResponse, error) {
	if req.FolderPath == "" {
		return &pb.GetFolderContextResponse{
			Success: false,
			Error:   "folder_path is required",
		}, nil
	}

	// Query for chunks with openwebui-folder in frontmatter
	results, err := s.db.Execute(ctx,
		`MATCH (c:Chunk)
		WHERE c.frontmatter CONTAINS '"openwebui-folder"'
		RETURN c.file_path AS file_path, c.frontmatter AS frontmatter`,
		nil,
	)
	if err != nil {
		return &pb.GetFolderContextResponse{Success: false, Error: err.Error()}, nil
	}

	// Find matching page
	var matchingPage string
	normalizedFolder := strings.ToLower(strings.Trim(req.FolderPath, "/"))

	for _, result := range results {
		frontmatterStr, ok := result["col1"].(string)
		if !ok {
			continue
		}

		var frontmatter map[string]interface{}
		if err := json.Unmarshal([]byte(frontmatterStr), &frontmatter); err != nil {
			continue
		}

		owuiFolder, ok := frontmatter["openwebui-folder"].(string)
		if !ok {
			continue
		}

		if strings.ToLower(strings.Trim(owuiFolder, "/")) == normalizedFolder {
			filePath, ok := result["col0"].(string)
			if !ok {
				continue
			}

			// Convert file path to page name
			if idx := strings.Index(filePath, "/space/"); idx != -1 {
				matchingPage = filePath[idx+7:]
			} else {
				matchingPage = filePath
			}
			matchingPage = strings.TrimSuffix(matchingPage, ".md")
			break
		}
	}

	if matchingPage == "" {
		return &pb.GetFolderContextResponse{
			Success: true,
			Found:   false,
		}, nil
	}

	// Read the full page content
	pagePath := filepath.Join(s.spacePath, matchingPage+".md")
	content, err := os.ReadFile(pagePath)
	if err != nil {
		if os.IsNotExist(err) {
			pagePath = filepath.Join(s.spacePath, matchingPage)
			content, err = os.ReadFile(pagePath)
		}
		if err != nil {
			return &pb.GetFolderContextResponse{
				Success:  true,
				Found:    false,
				PageName: matchingPage,
			}, nil
		}
	}

	// Determine folder scope
	var folderScope string
	if idx := strings.LastIndex(matchingPage, "/"); idx != -1 {
		folderScope = matchingPage[:idx]
	}

	s.logger.Info("Found folder context", "folder", req.FolderPath, "page", matchingPage, "scope", folderScope)

	return &pb.GetFolderContextResponse{
		Success:     true,
		Found:       true,
		PageName:    matchingPage,
		PageContent: string(content),
		FolderScope: folderScope,
	}, nil
}

// GetProjectContext finds project context by GitHub remote or folder path.
func (s *GRPCServer) GetProjectContext(ctx context.Context, req *pb.GetProjectContextRequest) (*pb.GetProjectContextResponse, error) {
	if req.GithubRemote == "" && req.FolderPath == "" {
		return &pb.GetProjectContextResponse{
			Success: false,
			Error:   "Must provide either github_remote or folder_path",
		}, nil
	}

	var projectFile string
	var frontmatter map[string]interface{}

	// Search by GitHub remote
	if req.GithubRemote != "" {
		err := filepath.Walk(s.spacePath, func(path string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() || !strings.HasSuffix(path, ".md") {
				return nil
			}

			fm, fmErr := s.parser.GetFrontmatter(path)
			if fmErr != nil {
				return nil
			}
			if github, ok := fm["github"].(string); ok && github == req.GithubRemote {
				projectFile = path
				frontmatter = fm
				return filepath.SkipAll
			}
			return nil
		})
		if err != nil && err != filepath.SkipAll {
			return &pb.GetProjectContextResponse{Success: false, Error: err.Error()}, nil
		}
	}

	// Search by folder path
	if projectFile == "" && req.FolderPath != "" {
		parts := strings.Split(req.FolderPath, "/")
		var indexFile string
		if len(parts) > 1 {
			parent := strings.Join(parts[:len(parts)-1], "/")
			indexFile = filepath.Join(s.spacePath, parent, parts[len(parts)-1]+".md")
		} else {
			indexFile = filepath.Join(s.spacePath, req.FolderPath+".md")
		}

		if _, err := os.Stat(indexFile); err == nil {
			projectFile = indexFile
			frontmatter, _ = s.parser.GetFrontmatter(indexFile)
		} else {
			// Try looking for any .md file in the folder with project metadata
			folderDir := filepath.Join(s.spacePath, req.FolderPath)
			if info, err := os.Stat(folderDir); err == nil && info.IsDir() {
				entries, _ := os.ReadDir(folderDir)
				for _, entry := range entries {
					if strings.HasSuffix(entry.Name(), ".md") {
						mdPath := filepath.Join(folderDir, entry.Name())
						fm, fmErr := s.parser.GetFrontmatter(mdPath)
						if fmErr == nil && len(fm) > 0 {
							projectFile = mdPath
							frontmatter = fm
							break
						}
					}
				}
			}
		}
	}

	if projectFile == "" {
		return &pb.GetProjectContextResponse{
			Success: false,
			Error:   fmt.Sprintf("No project found for github_remote=%s, folder_path=%s", req.GithubRemote, req.FolderPath),
		}, nil
	}

	// Read project content
	content, err := os.ReadFile(projectFile)
	if err != nil {
		return &pb.GetProjectContextResponse{Success: false, Error: err.Error()}, nil
	}

	// Strip frontmatter from content
	cleanContent := stripFrontmatter(string(content))

	// Get relative path
	relPath, _ := filepath.Rel(s.spacePath, projectFile)

	// Get related pages
	folder := filepath.Dir(projectFile)
	var relatedPages []*pb.RelatedPage

	if folder != s.spacePath {
		entries, _ := os.ReadDir(folder)
		for _, entry := range entries {
			if strings.HasSuffix(entry.Name(), ".md") {
				fullPath := filepath.Join(folder, entry.Name())
				if fullPath != projectFile {
					relPagePath, _ := filepath.Rel(s.spacePath, fullPath)
					relatedPages = append(relatedPages, &pb.RelatedPage{
						Name: strings.TrimSuffix(entry.Name(), ".md"),
						Path: relPagePath,
					})
				}
			}
		}

		// Check for subdirectory matching project name
		projectSubdir := filepath.Join(folder, strings.TrimSuffix(filepath.Base(projectFile), ".md"))
		if info, err := os.Stat(projectSubdir); err == nil && info.IsDir() {
			_ = filepath.Walk(projectSubdir, func(path string, info os.FileInfo, err error) error {
				if err == nil && !info.IsDir() && strings.HasSuffix(path, ".md") {
					relPagePath, _ := filepath.Rel(s.spacePath, path)
					relatedPages = append(relatedPages, &pb.RelatedPage{
						Name: strings.TrimSuffix(filepath.Base(path), ".md"),
						Path: relPagePath,
					})
				}
				return nil
			})
		}
	}

	// Build project info
	var tags, concerns []string
	if t, ok := frontmatter["tags"]; ok {
		switch v := t.(type) {
		case string:
			tags = []string{v}
		case []interface{}:
			for _, item := range v {
				if s, ok := item.(string); ok {
					tags = append(tags, s)
				}
			}
		}
	}
	if c, ok := frontmatter["concerns"]; ok {
		switch v := c.(type) {
		case string:
			concerns = []string{v}
		case []interface{}:
			for _, item := range v {
				if s, ok := item.(string); ok {
					concerns = append(concerns, s)
				}
			}
		}
	}

	github := ""
	if g, ok := frontmatter["github"].(string); ok {
		github = g
	}

	projectInfo := &pb.ProjectInfo{
		File:     relPath,
		Github:   github,
		Tags:     tags,
		Concerns: concerns,
		Content:  cleanContent,
	}

	// Limit related pages
	if len(relatedPages) > 20 {
		relatedPages = relatedPages[:20]
	}

	s.logger.Info("Found project context",
		"file", relPath,
		"github", github,
		"related_pages", len(relatedPages),
	)

	return &pb.GetProjectContextResponse{
		Success:      true,
		Project:      projectInfo,
		RelatedPages: relatedPages,
	}, nil
}

// stripFrontmatter removes YAML frontmatter from content.
func stripFrontmatter(content string) string {
	if !strings.HasPrefix(content, "---") {
		return content
	}

	endIdx := strings.Index(content[3:], "---")
	if endIdx == -1 {
		return content
	}

	return strings.TrimSpace(content[endIdx+6:])
}
