"""Graph database operations using LadybugDB."""

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import real_ladybug as lb

from ..embeddings import EmbeddingService
from ..parser import Chunk, DataBlock, InlineAttribute, Transclusion

logger = logging.getLogger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles date and datetime objects."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


class GraphDB:
    """LadybugDB graph database wrapper."""

    def __init__(self, db_path: str = "/db", enable_embeddings: bool = True):
        """Initialize database connection.

        Args:
            db_path: Path to the database directory
            enable_embeddings: Whether to enable embedding generation (default: True)
        """
        self.db = lb.Database(db_path)
        self.enable_embeddings = enable_embeddings
        self.embedding_service = EmbeddingService() if enable_embeddings else None
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize database schema with node and relationship types."""
        conn = lb.Connection(self.db)

        # Create node labels if they don't exist
        # LadybugDB requires node tables to be created before use
        try:
            # Create Chunk table with embedding field (FLOAT[] for vector storage)
            # frontmatter is stored as JSON string for flexible schema
            if self.enable_embeddings:
                conn.execute(
                    """
                    CREATE NODE TABLE IF NOT EXISTS Chunk(
                        id STRING,
                        file_path STRING,
                        header STRING,
                        content STRING,
                        frontmatter STRING,
                        embedding FLOAT[],
                        PRIMARY KEY(id)
                    )
                """
                )
            else:
                conn.execute(
                    """
                    CREATE NODE TABLE IF NOT EXISTS Chunk(
                        id STRING,
                        file_path STRING,
                        header STRING,
                        content STRING,
                        frontmatter STRING,
                        PRIMARY KEY(id)
                    )
                """
                )

            conn.execute(
                "CREATE NODE TABLE IF NOT EXISTS Page(name STRING, PRIMARY KEY(name))"
            )
            conn.execute(
                "CREATE NODE TABLE IF NOT EXISTS Tag(name STRING, PRIMARY KEY(name))"
            )
            conn.execute(
                """
                CREATE NODE TABLE IF NOT EXISTS Folder(
                    name STRING,
                    path STRING,
                    has_index_page BOOL,
                    PRIMARY KEY(path)
                )
            """
            )
            # Attribute node for inline attributes [name: value]
            conn.execute(
                """
                CREATE NODE TABLE IF NOT EXISTS Attribute(
                    id STRING,
                    name STRING,
                    value STRING,
                    PRIMARY KEY(id)
                )
            """
            )
            # DataBlock node for ```#tagname YAML blocks
            conn.execute(
                """
                CREATE NODE TABLE IF NOT EXISTS DataBlock(
                    id STRING,
                    tag STRING,
                    data STRING,
                    file_path STRING,
                    PRIMARY KEY(id)
                )
            """
            )
            # Relationships
            conn.execute("CREATE REL TABLE IF NOT EXISTS LINKS_TO(FROM Chunk TO Page)")
            conn.execute("CREATE REL TABLE IF NOT EXISTS TAGGED(FROM Chunk TO Tag)")
            conn.execute(
                "CREATE REL TABLE IF NOT EXISTS CONTAINS(FROM Folder TO Folder)"
            )
            conn.execute(
                "CREATE REL TABLE IF NOT EXISTS FOLDER_CONTAINS_PAGE(FROM Folder TO Page)"
            )
            conn.execute(
                "CREATE REL TABLE IF NOT EXISTS IN_FOLDER(FROM Chunk TO Folder)"
            )
            # New relationships for transclusions, attributes, and data blocks
            conn.execute(
                "CREATE REL TABLE IF NOT EXISTS EMBEDS(FROM Chunk TO Page, header STRING)"
            )
            conn.execute(
                "CREATE REL TABLE IF NOT EXISTS HAS_ATTRIBUTE(FROM Chunk TO Attribute)"
            )
            conn.execute(
                "CREATE REL TABLE IF NOT EXISTS HAS_DATA_BLOCK(FROM Chunk TO DataBlock)"
            )
            conn.execute(
                "CREATE REL TABLE IF NOT EXISTS DATA_TAGGED(FROM DataBlock TO Tag)"
            )

            # Create vector index for semantic search if embeddings are enabled
            if self.enable_embeddings:
                self._create_vector_index()

        except Exception as e:
            # Tables might already exist
            logger.debug(f"Schema initialization note: {e}")

    def _create_vector_index(self) -> None:
        """Create HNSW vector index for semantic search."""
        try:
            conn = lb.Connection(self.db)
            # Create HNSW vector index on Chunk.embedding with cosine similarity
            conn.execute(
                """
                CREATE VECTOR INDEX IF NOT EXISTS chunk_embedding_idx
                ON Chunk(embedding)
                WITH {metric: 'cosine', M: 16, efConstruction: 200}
            """
            )
            logger.info("Vector index created successfully")
        except Exception as e:
            logger.warning(f"Vector index may already exist: {e}")

    def index_chunks(self, chunks: List[Chunk]) -> None:
        """Index chunks into the graph database.

        Creates nodes for pages and chunks, with edges for links and tags.
        Generates embeddings if enabled.

        Args:
            chunks: List of chunks to index
        """
        conn = lb.Connection(self.db)

        # Generate embeddings for all chunks in batch if enabled
        embeddings = []
        if self.enable_embeddings and self.embedding_service:
            logger.info(f"Generating embeddings for {len(chunks)} chunks")
            contents = [chunk.content for chunk in chunks]
            embeddings = self.embedding_service.generate_embeddings_batch(contents)
            logger.info(f"Generated {len(embeddings)} embeddings")

        for i, chunk in enumerate(chunks):
            # Create chunk node
            chunk_id = f"{chunk.file_path}#{chunk.header}"

            # Serialize frontmatter to JSON string (with date handling)
            frontmatter_json = (
                json.dumps(chunk.frontmatter, cls=DateTimeEncoder)
                if chunk.frontmatter
                else "{}"
            )

            # Build query based on whether embeddings are enabled
            if self.enable_embeddings and embeddings:
                query = """
                MERGE (c:Chunk {id: $id})
                SET c.file_path = $file_path,
                    c.header = $header,
                    c.content = $content,
                    c.frontmatter = $frontmatter,
                    c.embedding = $embedding
                """
                params = {
                    "id": chunk_id,
                    "file_path": chunk.file_path,
                    "header": chunk.header,
                    "content": chunk.content,
                    "frontmatter": frontmatter_json,
                    "embedding": embeddings[i],
                }
            else:
                query = """
                MERGE (c:Chunk {id: $id})
                SET c.file_path = $file_path,
                    c.header = $header,
                    c.content = $content,
                    c.frontmatter = $frontmatter
                """
                params = {
                    "id": chunk_id,
                    "file_path": chunk.file_path,
                    "header": chunk.header,
                    "content": chunk.content,
                    "frontmatter": frontmatter_json,
                }

            conn.execute(query, params)

            # Create edges for wikilinks
            for link in chunk.links:
                link_query = """
                MATCH (c:Chunk {id: $chunk_id})
                MERGE (t:Page {name: $link_name})
                MERGE (c)-[:LINKS_TO]->(t)
                """
                conn.execute(link_query, {"chunk_id": chunk_id, "link_name": link})

            # Create edges for tags
            for tag in chunk.tags:
                tag_query = """
                MATCH (c:Chunk {id: $chunk_id})
                MERGE (t:Tag {name: $tag_name})
                MERGE (c)-[:TAGGED]->(t)
                """
                conn.execute(tag_query, {"chunk_id": chunk_id, "tag_name": tag})

            # Create folder relationship if chunk has folder_path
            if hasattr(chunk, "folder_path") and chunk.folder_path:
                folder_query = """
                MATCH (c:Chunk {id: $chunk_id})
                MATCH (f:Folder {path: $folder_path})
                MERGE (c)-[:IN_FOLDER]->(f)
                """
                conn.execute(
                    folder_query,
                    {"chunk_id": chunk_id, "folder_path": chunk.folder_path},
                )

            # Create edges for transclusions (EMBEDS relationship)
            if hasattr(chunk, "transclusions") and chunk.transclusions:
                for transclusion in chunk.transclusions:
                    embed_query = """
                    MATCH (c:Chunk {id: $chunk_id})
                    MERGE (p:Page {name: $target_page})
                    MERGE (c)-[:EMBEDS {header: $header}]->(p)
                    """
                    conn.execute(
                        embed_query,
                        {
                            "chunk_id": chunk_id,
                            "target_page": transclusion.target_page,
                            "header": transclusion.target_header or "",
                        },
                    )

            # Create nodes and edges for inline attributes
            if hasattr(chunk, "inline_attributes") and chunk.inline_attributes:
                for attr in chunk.inline_attributes:
                    attr_id = f"{chunk_id}#{attr.name}"
                    attr_query = """
                    MATCH (c:Chunk {id: $chunk_id})
                    MERGE (a:Attribute {id: $attr_id})
                    SET a.name = $name, a.value = $value
                    MERGE (c)-[:HAS_ATTRIBUTE]->(a)
                    """
                    conn.execute(
                        attr_query,
                        {
                            "chunk_id": chunk_id,
                            "attr_id": attr_id,
                            "name": attr.name,
                            "value": attr.value,
                        },
                    )

            # Create nodes and edges for data blocks
            if hasattr(chunk, "data_blocks") and chunk.data_blocks:
                for idx, data_block in enumerate(chunk.data_blocks):
                    block_id = f"{chunk_id}#datablock#{idx}"
                    data_json = json.dumps(data_block.data, cls=DateTimeEncoder)
                    block_query = """
                    MATCH (c:Chunk {id: $chunk_id})
                    MERGE (d:DataBlock {id: $block_id})
                    SET d.tag = $tag, d.data = $data, d.file_path = $file_path
                    MERGE (c)-[:HAS_DATA_BLOCK]->(d)
                    """
                    conn.execute(
                        block_query,
                        {
                            "chunk_id": chunk_id,
                            "block_id": block_id,
                            "tag": data_block.tag,
                            "data": data_json,
                            "file_path": data_block.file_path,
                        },
                    )
                    # Also create tag relationship for the data block
                    data_tag_query = """
                    MATCH (d:DataBlock {id: $block_id})
                    MERGE (t:Tag {name: $tag_name})
                    MERGE (d)-[:DATA_TAGGED]->(t)
                    """
                    conn.execute(
                        data_tag_query,
                        {"block_id": block_id, "tag_name": data_block.tag},
                    )

    def index_folders(
        self, folder_paths: List[str], index_pages: Optional[Dict[str, str]] = None
    ) -> None:
        """Create folder nodes and hierarchy relationships.

        Args:
            folder_paths: List of folder paths to index
            index_pages: Optional mapping of folder path to index page name
        """
        if index_pages is None:
            index_pages = {}

        conn = lb.Connection(self.db)

        # First, create all folder nodes
        all_folders = set()
        for path in folder_paths:
            # Add this folder and all parent folders
            parts = path.split("/")
            for i in range(1, len(parts) + 1):
                folder_path = "/".join(parts[:i])
                all_folders.add(folder_path)

        # Create folder nodes
        for folder_path in all_folders:
            name = folder_path.split("/")[-1]
            has_index = folder_path in index_pages

            folder_query = """
            MERGE (f:Folder {path: $path})
            SET f.name = $name,
                f.has_index_page = $has_index
            """
            conn.execute(
                folder_query,
                {"path": folder_path, "name": name, "has_index": has_index},
            )

        # Create CONTAINS relationships for parent-child folders
        for folder_path in all_folders:
            if "/" in folder_path:
                parent_path = "/".join(folder_path.split("/")[:-1])
                if parent_path in all_folders:
                    contains_query = """
                    MATCH (parent:Folder {path: $parent_path})
                    MATCH (child:Folder {path: $child_path})
                    MERGE (parent)-[:CONTAINS]->(child)
                    """
                    conn.execute(
                        contains_query,
                        {"parent_path": parent_path, "child_path": folder_path},
                    )

    def cypher_query(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query.

        Args:
            query: Cypher query string
            params: Optional query parameters

        Returns:
            List of result records as dictionaries
        """
        conn = lb.Connection(self.db)
        result = conn.execute(query, params)

        records = []
        while result.has_next():
            record = result.get_next()
            record_dict = {}
            for i, value in enumerate(record):
                record_dict[f"col{i}"] = self._convert_value(value)
            records.append(record_dict)

        return records

    def clear_database(self) -> None:
        """Clear all data from the database.

        Deletes all nodes and relationships, then recreates the schema.
        Use this for a clean rebuild of the index.
        """
        conn = lb.Connection(self.db)
        logger.info("Clearing database...")

        # Delete all nodes and relationships
        # Order matters: delete relationships first via DETACH DELETE
        tables = ["Chunk", "Page", "Tag", "Folder", "Attribute", "DataBlock"]
        for table in tables:
            try:
                conn.execute(f"MATCH (n:{table}) DETACH DELETE n")
                logger.info(f"Cleared {table} nodes")
            except Exception as e:
                logger.debug(f"Error clearing {table}: {e}")

        logger.info("Database cleared")

    def delete_chunks_by_file(self, file_path: str) -> None:
        """Delete all chunks associated with a file and cleanup orphaned nodes.

        Args:
            file_path: Path to the file whose chunks should be deleted
        """
        conn = lb.Connection(self.db)

        # Delete chunks and their relationships
        delete_query = """
        MATCH (c:Chunk {file_path: $file_path})
        DETACH DELETE c
        """
        conn.execute(delete_query, {"file_path": file_path})

        # Cleanup orphaned Tag nodes (tags with no incoming TAGGED or DATA_TAGGED relationships)
        cleanup_tags_query = """
        MATCH (t:Tag)
        WHERE NOT (t)<-[:TAGGED]-() AND NOT (t)<-[:DATA_TAGGED]-()
        DETACH DELETE t
        """
        conn.execute(cleanup_tags_query)

        # Cleanup orphaned Page nodes (pages with no incoming LINKS_TO or EMBEDS relationships)
        cleanup_pages_query = """
        MATCH (p:Page)
        WHERE NOT (p)<-[:LINKS_TO]-() AND NOT (p)<-[:EMBEDS]-()
        DETACH DELETE p
        """
        conn.execute(cleanup_pages_query)

        # Cleanup orphaned Attribute nodes
        cleanup_attrs_query = """
        MATCH (a:Attribute)
        WHERE NOT (a)<-[:HAS_ATTRIBUTE]-()
        DETACH DELETE a
        """
        conn.execute(cleanup_attrs_query)

        # Cleanup orphaned DataBlock nodes
        cleanup_data_query = """
        MATCH (d:DataBlock)
        WHERE NOT (d)<-[:HAS_DATA_BLOCK]-()
        DETACH DELETE d
        """
        conn.execute(cleanup_data_query)

    def keyword_search(
        self, keyword: str, scope: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for chunks by keyword with BM25 ranking.

        Implements BM25 scoring with:
        - Tag boosting (2x weight for tag matches)
        - Technical term detection and boosting
        - Multi-term query support

        Args:
            keyword: Keyword or keywords to search for
            scope: Optional folder path to scope results to (e.g., "Projects/ProjectA")

        Returns:
            List of matching chunks with BM25 scores, sorted by relevance
        """
        import math
        import re

        # Get all chunks for IDF calculation (scoped if specified)
        conn = lb.Connection(self.db)

        if scope:
            total_docs_query = """
            MATCH (c:Chunk)-[:IN_FOLDER]->(f:Folder)
            WHERE f.path = $scope OR f.path STARTS WITH $scope_prefix
            RETURN count(c) as total
            """
            total_result = conn.execute(
                total_docs_query, {"scope": scope, "scope_prefix": scope + "/"}
            )
        else:
            total_docs_query = "MATCH (c:Chunk) RETURN count(c) as total"
            total_result = conn.execute(total_docs_query)

        total_docs = 0
        if total_result.has_next():
            total_docs = total_result.get_next()[0]

        if total_docs == 0:
            return []

        # Tokenize query into terms (split on whitespace and lowercase)
        query_terms = keyword.lower().split()

        # Technical terms that get boosted (common in developer documentation)
        technical_terms = {
            "sql",
            "nosql",
            "api",
            "rest",
            "graphql",
            "json",
            "xml",
            "index",
            "indexes",
            "query",
            "queries",
            "schema",
            "migration",
            "optimization",
            "performance",
            "cache",
            "caching",
            "async",
            "database",
            "db",
            "repository",
            "orm",
            "transaction",
        }

        # Build scope filter clause if scope is specified
        scope_match = ""
        scope_where = ""
        scope_params = {}
        if scope:
            scope_match = "-[:IN_FOLDER]->(f:Folder)"
            scope_where = " AND (f.path = $scope OR f.path STARTS WITH $scope_prefix)"
            scope_params = {"scope": scope, "scope_prefix": scope + "/"}

        # Get matching chunks - for multi-term queries, match any term
        if len(query_terms) > 1:
            # Multi-term query: build OR condition for all terms
            where_clauses = []
            params = dict(scope_params)
            for i, term in enumerate(query_terms):
                param_name = "term" + str(i)
                # Build WHERE clause without f-strings (concatenate strings instead)
                where_clause = (
                    "(toLower(c.content) CONTAINS $"
                    + param_name
                    + " OR toLower(c.file_path) CONTAINS $"
                    + param_name
                    + " OR toLower(c.header) CONTAINS $"
                    + param_name
                    + ")"
                )
                where_clauses.append(where_clause)
                params[param_name] = term

            # Build query without f-strings (concatenate strings instead)
            search_query = (
                "MATCH (c:Chunk)"
                + scope_match
                + " "
                + "WHERE ("
                + " OR ".join(where_clauses)
                + ")"
                + scope_where
                + " "
                + "RETURN c"
            )
            result = conn.execute(search_query, params)
        else:
            # Single term query
            params = {"keyword": keyword}
            params.update(scope_params)
            search_query = (
                "MATCH (c:Chunk)"
                + scope_match
                + " "
                + "WHERE (c.content CONTAINS $keyword "
                + "   OR c.file_path CONTAINS $keyword "
                + "   OR c.header CONTAINS $keyword)"
                + scope_where
                + " "
                + "RETURN c"
            )
            result = conn.execute(search_query, params)

        # Collect all matching chunks
        chunks = []
        while result.has_next():
            record = result.get_next()
            chunk_node = self._convert_value(record[0])
            chunks.append(chunk_node)

        if not chunks:
            return []

        # Calculate document frequency for each query term
        term_doc_freqs = {}
        for term in query_terms:
            df_query = """
            MATCH (c:Chunk)
            WHERE toLower(c.content) CONTAINS $term
               OR toLower(c.file_path) CONTAINS $term
               OR toLower(c.header) CONTAINS $term
            RETURN count(c) as df
            """
            df_result = conn.execute(df_query, {"term": term.lower()})
            if df_result.has_next():
                term_doc_freqs[term] = df_result.get_next()[0]
            else:
                term_doc_freqs[term] = 0

        # BM25 parameters
        k1 = 1.5  # Term frequency saturation parameter
        b = 0.75  # Length normalization parameter

        # Calculate average document length
        avg_doc_length = sum(len(c.get("content", "")) for c in chunks) / len(chunks)

        # Score each chunk using BM25
        scored_chunks = []
        for chunk in chunks:
            content = chunk.get("content", "").lower()
            file_path = chunk.get("file_path", "").lower()
            header = chunk.get("header", "").lower()
            doc_length = len(chunk.get("content", ""))

            # Get tags for this chunk to apply tag boosting
            chunk_id = chunk.get("id", "")
            tags_query = """
            MATCH (c:Chunk {id: $chunk_id})-[:TAGGED]->(t:Tag)
            RETURN t.name as tag
            """
            tags_result = conn.execute(tags_query, {"chunk_id": chunk_id})
            chunk_tags = set()
            while tags_result.has_next():
                tag_record = tags_result.get_next()
                chunk_tags.add(tag_record[0].lower())

            bm25_score = 0.0

            for term in query_terms:
                # Calculate term frequency in document (with boosting)
                tf = content.count(term)
                tf += file_path.count(term) * 1.5  # Boost matches in file path
                tf += header.count(term) * 2.0  # Boost matches in headers

                # Tag boosting: 2x weight if term appears in tags
                if term in chunk_tags:
                    tf *= 2.0

                # Technical term boosting: 1.5x weight for technical terms
                if term in technical_terms:
                    tf *= 1.5

                if tf == 0:
                    continue

                # Get document frequency for this term
                df = term_doc_freqs.get(term, 1)

                # Calculate IDF (Inverse Document Frequency)
                # Using smoothed IDF to avoid division by zero and negative values
                idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)

                # Calculate BM25 component for this term
                # BM25 formula: IDF * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_length / avg_doc_length))
                normalized_tf = (tf * (k1 + 1)) / (
                    tf + k1 * (1 - b + b * doc_length / avg_doc_length)
                )

                bm25_score += idf * normalized_tf

            scored_chunks.append({"col0": chunk, "bm25_score": round(bm25_score, 4)})

        # Sort by BM25 score (descending)
        scored_chunks.sort(key=lambda x: x["bm25_score"], reverse=True)

        # Limit to top 50 results
        return scored_chunks[:50]

    def semantic_search(
        self,
        query: str,
        limit: int = 10,
        filter_tags: Optional[List[str]] = None,
        filter_pages: Optional[List[str]] = None,
        scope: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Perform semantic search using vector similarity.

        Args:
            query: Natural language query to search for
            limit: Maximum number of results to return (default: 10)
            filter_tags: Optional list of tags to filter results by
            filter_pages: Optional list of page names to filter results by
            scope: Optional folder path to scope results to (e.g., "Projects/ProjectA")

        Returns:
            List of matching chunks with similarity scores

        Raises:
            ValueError: If embeddings are not enabled
        """
        if not self.enable_embeddings or not self.embedding_service:
            raise ValueError("Semantic search requires embeddings to be enabled")

        # Generate embedding for the query
        query_embedding = self.embedding_service.generate_embedding(query)
        logger.info(f"Generated query embedding with dimension: {len(query_embedding)}")

        conn = lb.Connection(self.db)

        # Build the vector search query
        if filter_tags or filter_pages or scope:
            # Use PROJECT_GRAPH_CYPHER for filtered search
            # First get candidates via vector search, then filter with Cypher
            base_query = """
            QUERY_VECTOR_INDEX chunk_embedding_idx
            WITH VECTOR $query_embedding
            LIMIT $limit
            """

            # Get vector search results
            vector_results = conn.execute(
                base_query,
                {
                    "query_embedding": query_embedding,
                    "limit": limit * 2,  # Get more candidates for filtering
                },
            )

            # Extract chunk IDs from vector results
            chunk_ids = []
            while vector_results.has_next():
                record = vector_results.get_next()
                chunk_ids.append(record[0])  # Assuming first column is chunk ID

            if not chunk_ids:
                return []

            # Build Cypher filter query
            filter_conditions = []
            if filter_tags:
                filter_conditions.append(
                    "EXISTS((c)-[:TAGGED]->(:Tag)) AND ANY(t IN $tags WHERE (c)-[:TAGGED]->(:Tag {name: t}))"
                )
            if filter_pages:
                filter_conditions.append("c.file_path IN $pages")
            if scope:
                filter_conditions.append(
                    "EXISTS((c)-[:IN_FOLDER]->(f:Folder) WHERE f.path = $scope OR f.path STARTS WITH $scope_prefix)"
                )

            filter_clause = (
                " AND ".join(filter_conditions) if filter_conditions else "TRUE"
            )

            filtered_query = (
                "MATCH (c:Chunk) "
                + "WHERE c.id IN $chunk_ids AND "
                + filter_clause
                + " "
                + "RETURN c "
                + "LIMIT $limit"
            )

            result = conn.execute(
                filtered_query,
                {
                    "chunk_ids": chunk_ids,
                    "tags": filter_tags or [],
                    "pages": filter_pages or [],
                    "scope": scope or "",
                    "scope_prefix": (scope + "/") if scope else "",
                    "limit": limit,
                },
            )
        else:
            # Simple vector search without filters
            vector_query = """
            QUERY_VECTOR_INDEX chunk_embedding_idx
            WITH VECTOR $query_embedding
            LIMIT $limit
            """

            result = conn.execute(
                vector_query, {"query_embedding": query_embedding, "limit": limit}
            )

        # Process results
        records = []
        while result.has_next():
            record = result.get_next()
            record_dict = {}
            for i, value in enumerate(record):
                record_dict[f"col{i}"] = self._convert_value(value)
            records.append(record_dict)

        logger.info(f"Semantic search returned {len(records)} results")
        return records

    def _convert_value(self, value: Any) -> Any:
        """Convert LadybugDB value to Python type.

        Args:
            value: Value from database

        Returns:
            Converted Python value
        """
        # LadybugDB values are already Python-compatible
        # Add any necessary conversions here
        return value
