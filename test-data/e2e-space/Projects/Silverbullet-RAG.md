---
tags: project
github: boblangley/silverbullet-rag
status: active
---

# Silverbullet RAG

A RAG (Retrieval-Augmented Generation) system for [[Silverbullet]].

## Features

- Knowledge graph with Cypher queries
- BM25 keyword search
- Semantic vector search
- Hybrid search with RRF fusion
- MCP server for LLM integration

## Architecture

```
Silverbullet Space (markdown files)
         ↓
    SpaceParser (markdown-it-py)
         ↓
    GraphDB (LadybugDB)
    ├── Knowledge Graph
    ├── BM25 Index
    └── HNSW Vector Index
         ↓
    MCP Server
```

## Related

- [[Notes/Testing]]
- [[Notes/Development]]
