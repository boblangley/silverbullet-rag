// Package db provides the database interface and implementations for silverbullet-rag.
package db

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"

	lbug "github.com/LadybugDB/go-ladybug"
)

// Record represents a single result row from a query.
type Record map[string]any

// GraphDB wraps LadybugDB for graph operations.
type GraphDB struct {
	db               *lbug.Database
	conn             *lbug.Connection
	path             string
	readOnly         bool
	enableEmbeddings bool
	logger           *slog.Logger
}

// Config holds database configuration options.
type Config struct {
	// Path is the filesystem path to the database.
	Path string

	// ReadOnly opens the database in read-only mode.
	ReadOnly bool

	// EnableEmbeddings enables vector embedding storage and search.
	EnableEmbeddings bool

	// AutoRecover attempts to recover from WAL corruption.
	AutoRecover bool

	// Logger for database operations.
	Logger *slog.Logger
}

// Open opens or creates a LadybugDB database.
func Open(cfg Config) (*GraphDB, error) {
	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}

	// Ensure parent directory exists
	dir := filepath.Dir(cfg.Path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, fmt.Errorf("create database directory: %w", err)
	}

	sysCfg := lbug.DefaultSystemConfig()
	sysCfg.ReadOnly = cfg.ReadOnly

	db, err := lbug.OpenDatabase(cfg.Path, sysCfg)
	if err != nil {
		if cfg.AutoRecover {
			logger.Warn("database open failed, attempting recovery", "error", err)
			if recoverErr := removeWALFiles(cfg.Path); recoverErr != nil {
				logger.Warn("WAL removal failed", "error", recoverErr)
			}
			db, err = lbug.OpenDatabase(cfg.Path, sysCfg)
			if err != nil {
				return nil, fmt.Errorf("open database after recovery: %w", err)
			}
			logger.Info("database recovery successful")
		} else {
			return nil, fmt.Errorf("open database: %w", err)
		}
	}

	conn, err := lbug.OpenConnection(db)
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("open connection: %w", err)
	}

	gdb := &GraphDB{
		db:               db,
		conn:             conn,
		path:             cfg.Path,
		readOnly:         cfg.ReadOnly,
		enableEmbeddings: cfg.EnableEmbeddings,
		logger:           logger,
	}

	if !cfg.ReadOnly {
		if err := gdb.initSchema(); err != nil {
			gdb.Close()
			return nil, fmt.Errorf("init schema: %w", err)
		}
	}

	return gdb, nil
}

// removeWALFiles removes WAL files for recovery.
func removeWALFiles(dbPath string) error {
	walPath := dbPath + ".wal"
	if _, err := os.Stat(walPath); err == nil {
		if err := os.Remove(walPath); err != nil {
			return fmt.Errorf("remove WAL file: %w", err)
		}
	}
	return nil
}

// initSchema creates the database schema.
func (g *GraphDB) initSchema() error {
	schemas := []string{
		// Chunk table - main content storage
		`CREATE NODE TABLE IF NOT EXISTS Chunk(
			id STRING,
			file_path STRING,
			folder_path STRING,
			header STRING,
			content STRING,
			frontmatter STRING,
			PRIMARY KEY(id)
		)`,

		// Page table
		`CREATE NODE TABLE IF NOT EXISTS Page(name STRING, PRIMARY KEY(name))`,

		// Tag table
		`CREATE NODE TABLE IF NOT EXISTS Tag(name STRING, PRIMARY KEY(name))`,

		// Folder table
		`CREATE NODE TABLE IF NOT EXISTS Folder(
			name STRING,
			path STRING,
			has_index_page BOOL,
			PRIMARY KEY(path)
		)`,

		// Attribute table for inline attributes
		`CREATE NODE TABLE IF NOT EXISTS Attribute(
			id STRING,
			name STRING,
			value STRING,
			PRIMARY KEY(id)
		)`,

		// DataBlock table for tagged YAML blocks
		`CREATE NODE TABLE IF NOT EXISTS DataBlock(
			id STRING,
			tag STRING,
			data STRING,
			file_path STRING,
			PRIMARY KEY(id)
		)`,

		// Relationships
		`CREATE REL TABLE IF NOT EXISTS LINKS_TO(FROM Chunk TO Page)`,
		`CREATE REL TABLE IF NOT EXISTS TAGGED(FROM Chunk TO Tag)`,
		`CREATE REL TABLE IF NOT EXISTS CONTAINS(FROM Folder TO Folder)`,
		`CREATE REL TABLE IF NOT EXISTS FOLDER_CONTAINS_PAGE(FROM Folder TO Page)`,
		`CREATE REL TABLE IF NOT EXISTS IN_FOLDER(FROM Chunk TO Folder)`,
		`CREATE REL TABLE IF NOT EXISTS HAS_CHUNK(FROM Page TO Chunk, chunk_order INT64)`,
		`CREATE REL TABLE IF NOT EXISTS PAGE_LINKS_TO(FROM Page TO Page)`,
		`CREATE REL TABLE IF NOT EXISTS EMBEDS(FROM Chunk TO Page, header STRING)`,
		`CREATE REL TABLE IF NOT EXISTS HAS_ATTRIBUTE(FROM Chunk TO Attribute)`,
		`CREATE REL TABLE IF NOT EXISTS HAS_DATA_BLOCK(FROM Chunk TO DataBlock)`,
		`CREATE REL TABLE IF NOT EXISTS DATA_TAGGED(FROM DataBlock TO Tag)`,
	}

	// Add embedding column if enabled
	if g.enableEmbeddings {
		schemas = append([]string{
			`CREATE NODE TABLE IF NOT EXISTS Chunk(
				id STRING,
				file_path STRING,
				folder_path STRING,
				header STRING,
				content STRING,
				frontmatter STRING,
				embedding FLOAT[],
				PRIMARY KEY(id)
			)`,
		}, schemas[1:]...)
	}

	for _, schema := range schemas {
		if _, err := g.conn.Query(schema); err != nil {
			// Ignore "already exists" errors
			g.logger.Debug("schema statement", "query", schema, "error", err)
		}
	}

	return nil
}

// Execute runs a Cypher query and returns all results.
func (g *GraphDB) Execute(ctx context.Context, query string, params map[string]any) ([]Record, error) {
	var result *lbug.QueryResult
	var err error

	if len(params) > 0 {
		stmt, prepErr := g.conn.Prepare(query)
		if prepErr != nil {
			return nil, fmt.Errorf("prepare query: %w", prepErr)
		}
		defer stmt.Close()

		result, err = g.conn.Execute(stmt, params)
	} else {
		result, err = g.conn.Query(query)
	}

	if err != nil {
		return nil, fmt.Errorf("execute query: %w", err)
	}
	defer result.Close()

	// Initialize to empty slice (not nil) to distinguish "no results" from error
	records := make([]Record, 0)
	for result.HasNext() {
		tuple, err := result.Next()
		if err != nil {
			return nil, fmt.Errorf("fetch row: %w", err)
		}

		row, err := tuple.GetAsMap()
		if err != nil {
			return nil, fmt.Errorf("convert row: %w", err)
		}

		// Convert lbug.Node and lbug.Relationship to maps for easier handling
		convertedRow := make(Record)
		for k, v := range row {
			convertedRow[k] = convertLbugValue(v)
		}

		records = append(records, convertedRow)
	}

	return records, nil
}

// convertLbugValue converts LadybugDB-specific types to standard Go types.
func convertLbugValue(v any) any {
	switch val := v.(type) {
	case lbug.Node:
		// Convert Node to map with properties + label
		m := make(map[string]any)
		for k, propVal := range val.Properties {
			m[k] = convertLbugValue(propVal)
		}
		m["_label"] = val.Label
		return m
	case lbug.Relationship:
		// Convert Relationship to map with properties + label
		m := make(map[string]any)
		for k, propVal := range val.Properties {
			m[k] = convertLbugValue(propVal)
		}
		m["_label"] = val.Label
		return m
	case []any:
		// Convert slices recursively
		result := make([]any, len(val))
		for i, item := range val {
			result[i] = convertLbugValue(item)
		}
		return result
	default:
		return v
	}
}

// ExecuteWrite runs a Cypher query that modifies data.
func (g *GraphDB) ExecuteWrite(ctx context.Context, query string, params map[string]any) error {
	_, err := g.Execute(ctx, query, params)
	return err
}

// Close closes the database connection.
func (g *GraphDB) Close() error {
	if g.conn != nil {
		g.conn.Close()
	}
	if g.db != nil {
		g.db.Close()
	}
	return nil
}

// EnableEmbeddings returns whether embeddings are enabled.
func (g *GraphDB) EnableEmbeddings() bool {
	return g.enableEmbeddings
}

// ClearDatabase removes all data from the database.
func (g *GraphDB) ClearDatabase(ctx context.Context) error {
	tables := []string{"Chunk", "Page", "Tag", "Folder", "Attribute", "DataBlock"}
	for _, table := range tables {
		query := fmt.Sprintf("MATCH (n:%s) DETACH DELETE n", table)
		if err := g.ExecuteWrite(ctx, query, nil); err != nil {
			g.logger.Debug("clear table", "table", table, "error", err)
		}
	}
	g.logger.Info("database cleared")
	return nil
}
