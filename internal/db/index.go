package db

import (
	"context"
	"encoding/json"
	"fmt"
	"path/filepath"
	"strings"

	"github.com/boblangley/silverbullet-rag/internal/types"
)

// IndexChunks indexes chunks into the graph database.
func (g *GraphDB) IndexChunks(ctx context.Context, chunks []types.Chunk) error {
	// Group chunks by file to create Page nodes
	chunksByFile := make(map[string][]types.Chunk)
	for _, chunk := range chunks {
		chunksByFile[chunk.FilePath] = append(chunksByFile[chunk.FilePath], chunk)
	}

	// Track page links for PAGE_LINKS_TO relationships
	pageLinks := make(map[string]map[string]struct{})

	// Create Page nodes for each file
	for filePath := range chunksByFile {
		pageName := filePathToPageName(filePath)
		if err := g.ExecuteWrite(ctx, `MERGE (p:Page {name: $name})`, map[string]any{"name": pageName}); err != nil {
			return fmt.Errorf("create page %s: %w", pageName, err)
		}
		pageLinks[pageName] = make(map[string]struct{})
	}

	// Index each chunk
	for filePath, fileChunks := range chunksByFile {
		pageName := filePathToPageName(filePath)

		for order, chunk := range fileChunks {
			chunkID := fmt.Sprintf("%s#%s", chunk.FilePath, chunk.Header)

			// Serialize frontmatter to JSON
			frontmatterJSON := "{}"
			if chunk.Frontmatter != nil {
				if data, err := json.Marshal(chunk.Frontmatter); err == nil {
					frontmatterJSON = string(data)
				}
			}

			// Create/update Chunk node
			var chunkQuery string
			params := map[string]any{
				"id":          chunkID,
				"file_path":   chunk.FilePath,
				"folder_path": chunk.FolderPath,
				"header":      chunk.Header,
				"content":     chunk.Content,
				"frontmatter": frontmatterJSON,
			}

			if g.enableEmbeddings && len(chunk.Embedding) > 0 {
				chunkQuery = `
					MERGE (c:Chunk {id: $id})
					SET c.file_path = $file_path,
					    c.folder_path = $folder_path,
					    c.header = $header,
					    c.content = $content,
					    c.frontmatter = $frontmatter,
					    c.embedding = $embedding
				`
				params["embedding"] = chunk.Embedding
			} else {
				chunkQuery = `
					MERGE (c:Chunk {id: $id})
					SET c.file_path = $file_path,
					    c.folder_path = $folder_path,
					    c.header = $header,
					    c.content = $content,
					    c.frontmatter = $frontmatter
				`
			}

			if err := g.ExecuteWrite(ctx, chunkQuery, params); err != nil {
				return fmt.Errorf("create chunk %s: %w", chunkID, err)
			}

			// Create HAS_CHUNK relationship
			hasChunkQuery := fmt.Sprintf(`
				MATCH (p:Page {name: $page_name})
				MATCH (c:Chunk {id: $chunk_id})
				MERGE (p)-[:HAS_CHUNK {chunk_order: %d}]->(c)
			`, order)
			if err := g.ExecuteWrite(ctx, hasChunkQuery, map[string]any{
				"page_name": pageName,
				"chunk_id":  chunkID,
			}); err != nil {
				return fmt.Errorf("create HAS_CHUNK for %s: %w", chunkID, err)
			}

			// Create LINKS_TO relationships
			for _, link := range chunk.Links {
				if err := g.ExecuteWrite(ctx, `
					MATCH (c:Chunk {id: $chunk_id})
					MERGE (t:Page {name: $link_name})
					MERGE (c)-[:LINKS_TO]->(t)
				`, map[string]any{
					"chunk_id":  chunkID,
					"link_name": link,
				}); err != nil {
					g.logger.Debug("create LINKS_TO", "chunk", chunkID, "link", link, "error", err)
				}
				pageLinks[pageName][link] = struct{}{}
			}

			// Create TAGGED relationships
			for _, tag := range chunk.Tags {
				if err := g.ExecuteWrite(ctx, `
					MATCH (c:Chunk {id: $chunk_id})
					MERGE (t:Tag {name: $tag_name})
					MERGE (c)-[:TAGGED]->(t)
				`, map[string]any{
					"chunk_id": chunkID,
					"tag_name": tag,
				}); err != nil {
					g.logger.Debug("create TAGGED", "chunk", chunkID, "tag", tag, "error", err)
				}
			}

			// Create IN_FOLDER relationship
			if chunk.FolderPath != "" {
				if err := g.ExecuteWrite(ctx, `
					MATCH (c:Chunk {id: $chunk_id})
					MATCH (f:Folder {path: $folder_path})
					MERGE (c)-[:IN_FOLDER]->(f)
				`, map[string]any{
					"chunk_id":    chunkID,
					"folder_path": chunk.FolderPath,
				}); err != nil {
					g.logger.Debug("create IN_FOLDER", "chunk", chunkID, "folder", chunk.FolderPath, "error", err)
				}
			}

			// Create EMBEDS relationships for transclusions
			for _, trans := range chunk.Transclusions {
				if err := g.ExecuteWrite(ctx, `
					MATCH (c:Chunk {id: $chunk_id})
					MERGE (p:Page {name: $target_page})
					MERGE (c)-[:EMBEDS {header: $header}]->(p)
				`, map[string]any{
					"chunk_id":    chunkID,
					"target_page": trans.TargetPage,
					"header":      trans.TargetHeader,
				}); err != nil {
					g.logger.Debug("create EMBEDS", "chunk", chunkID, "target", trans.TargetPage, "error", err)
				}
			}

			// Create HAS_ATTRIBUTE relationships
			for _, attr := range chunk.InlineAttributes {
				attrID := fmt.Sprintf("%s#%s", chunkID, attr.Name)
				if err := g.ExecuteWrite(ctx, `
					MATCH (c:Chunk {id: $chunk_id})
					MERGE (a:Attribute {id: $attr_id})
					SET a.name = $name, a.value = $value
					MERGE (c)-[:HAS_ATTRIBUTE]->(a)
				`, map[string]any{
					"chunk_id": chunkID,
					"attr_id":  attrID,
					"name":     attr.Name,
					"value":    attr.Value,
				}); err != nil {
					g.logger.Debug("create HAS_ATTRIBUTE", "chunk", chunkID, "attr", attr.Name, "error", err)
				}
			}

			// Create HAS_DATA_BLOCK relationships
			for idx, block := range chunk.DataBlocks {
				blockID := fmt.Sprintf("%s#datablock#%d", chunkID, idx)
				dataJSON, _ := json.Marshal(block.Data)
				if err := g.ExecuteWrite(ctx, `
					MATCH (c:Chunk {id: $chunk_id})
					MERGE (d:DataBlock {id: $block_id})
					SET d.tag = $tag, d.data = $data, d.file_path = $file_path
					MERGE (c)-[:HAS_DATA_BLOCK]->(d)
				`, map[string]any{
					"chunk_id":  chunkID,
					"block_id":  blockID,
					"tag":       block.Tag,
					"data":      string(dataJSON),
					"file_path": block.FilePath,
				}); err != nil {
					g.logger.Debug("create HAS_DATA_BLOCK", "chunk", chunkID, "block", blockID, "error", err)
				}

				// Create DATA_TAGGED relationship
				if err := g.ExecuteWrite(ctx, `
					MATCH (d:DataBlock {id: $block_id})
					MERGE (t:Tag {name: $tag_name})
					MERGE (d)-[:DATA_TAGGED]->(t)
				`, map[string]any{
					"block_id": blockID,
					"tag_name": block.Tag,
				}); err != nil {
					g.logger.Debug("create DATA_TAGGED", "block", blockID, "tag", block.Tag, "error", err)
				}
			}
		}
	}

	// Create PAGE_LINKS_TO relationships
	for sourcePage, targets := range pageLinks {
		for targetPage := range targets {
			if err := g.ExecuteWrite(ctx, `
				MATCH (source:Page {name: $source})
				MATCH (target:Page {name: $target})
				MERGE (source)-[:PAGE_LINKS_TO]->(target)
			`, map[string]any{
				"source": sourcePage,
				"target": targetPage,
			}); err != nil {
				g.logger.Debug("create PAGE_LINKS_TO", "source", sourcePage, "target", targetPage, "error", err)
			}
		}
	}

	return nil
}

// IndexFolders creates folder nodes and hierarchy relationships.
func (g *GraphDB) IndexFolders(ctx context.Context, folderPaths []string, indexPages map[string]string) error {
	// Collect all folders including parent paths
	allFolders := make(map[string]struct{})
	for _, path := range folderPaths {
		parts := strings.Split(path, "/")
		for i := 1; i <= len(parts); i++ {
			folderPath := strings.Join(parts[:i], "/")
			allFolders[folderPath] = struct{}{}
		}
	}

	// Create folder nodes
	for folderPath := range allFolders {
		name := filepath.Base(folderPath)
		_, hasIndex := indexPages[folderPath]

		if err := g.ExecuteWrite(ctx, `
			MERGE (f:Folder {path: $path})
			SET f.name = $name, f.has_index_page = $has_index
		`, map[string]any{
			"path":      folderPath,
			"name":      name,
			"has_index": hasIndex,
		}); err != nil {
			return fmt.Errorf("create folder %s: %w", folderPath, err)
		}
	}

	// Create CONTAINS relationships for parent-child folders
	for folderPath := range allFolders {
		if strings.Contains(folderPath, "/") {
			parentPath := filepath.Dir(folderPath)
			if _, exists := allFolders[parentPath]; exists {
				if err := g.ExecuteWrite(ctx, `
					MATCH (parent:Folder {path: $parent_path})
					MATCH (child:Folder {path: $child_path})
					MERGE (parent)-[:CONTAINS]->(child)
				`, map[string]any{
					"parent_path": parentPath,
					"child_path":  folderPath,
				}); err != nil {
					g.logger.Debug("create CONTAINS", "parent", parentPath, "child", folderPath, "error", err)
				}
			}
		}
	}

	return nil
}

// DeleteChunksByFile removes all chunks for a file and cleans up orphaned nodes.
func (g *GraphDB) DeleteChunksByFile(ctx context.Context, filePath string) error {
	// Delete chunks
	if err := g.ExecuteWrite(ctx, `
		MATCH (c:Chunk {file_path: $file_path})
		DETACH DELETE c
	`, map[string]any{"file_path": filePath}); err != nil {
		return fmt.Errorf("delete chunks: %w", err)
	}

	// Cleanup orphaned tags
	if err := g.ExecuteWrite(ctx, `
		MATCH (t:Tag)
		WHERE NOT (t)<-[:TAGGED]-() AND NOT (t)<-[:DATA_TAGGED]-()
		DETACH DELETE t
	`, nil); err != nil {
		g.logger.Debug("cleanup tags", "error", err)
	}

	// Cleanup orphaned pages
	if err := g.ExecuteWrite(ctx, `
		MATCH (p:Page)
		WHERE NOT (p)-[:HAS_CHUNK]->()
		  AND NOT (p)<-[:LINKS_TO]-()
		  AND NOT (p)<-[:EMBEDS]-()
		  AND NOT (p)<-[:PAGE_LINKS_TO]-()
		DETACH DELETE p
	`, nil); err != nil {
		g.logger.Debug("cleanup pages", "error", err)
	}

	// Cleanup orphaned attributes
	if err := g.ExecuteWrite(ctx, `
		MATCH (a:Attribute)
		WHERE NOT (a)<-[:HAS_ATTRIBUTE]-()
		DETACH DELETE a
	`, nil); err != nil {
		g.logger.Debug("cleanup attributes", "error", err)
	}

	// Cleanup orphaned data blocks
	if err := g.ExecuteWrite(ctx, `
		MATCH (d:DataBlock)
		WHERE NOT (d)<-[:HAS_DATA_BLOCK]-()
		DETACH DELETE d
	`, nil); err != nil {
		g.logger.Debug("cleanup data blocks", "error", err)
	}

	return nil
}

// filePathToPageName converts a file path to a page name.
func filePathToPageName(fp string) string {
	// Try to find /space/ in the path
	if idx := strings.Index(fp, "/space/"); idx != -1 {
		fp = fp[idx+7:]
	}

	// Remove .md suffix
	return strings.TrimSuffix(fp, ".md")
}
