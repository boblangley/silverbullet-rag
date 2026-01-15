# Open WebUI Pipe

The Silverbullet RAG pipe integrates your Silverbullet knowledge base with [Open WebUI](https://openwebui.com/), providing context-aware chat with automatic knowledge retrieval.

## Features

- **Folder Context Mapping**: Map Open WebUI folders to Silverbullet project pages via `openwebui-folder` frontmatter
- **Hybrid Search**: Combines BM25 keyword search with semantic vector search per message
- **Configurable Scoping**: Choose strict, prefer, or no scoping with custom include paths and tags
- **Context Budgeting**: Control total context size to fit your model's context window
- **Per-User Settings**: Users can customize their own scope preferences and context limits
- **gRPC Communication**: Fast, efficient binary protocol for low-latency responses

## Installation

### 1. Start the gRPC Server

The gRPC server must be running and accessible from Open WebUI:

```bash
docker-compose up -d
```

The gRPC server listens on port 50051 by default.

### 2. Upload the Pipe to Open WebUI

1. Download [openwebui/silverbullet_rag.py](../openwebui/silverbullet_rag.py)
2. In Open WebUI, go to **Workspace** → **Functions** → **+**
3. Upload the `silverbullet_rag.py` file
4. Enable the pipe

### 3. Configure the Pipe

The pipe has two types of settings: **Valves** (admin settings) and **UserValves** (per-user settings).

#### Admin Settings (Valves)

In Open WebUI, click on the pipe settings (gear icon) to configure:

| Valve | Default | Description |
|-------|---------|-------------|
| `GRPC_HOST` | `localhost:50051` | gRPC server address |
| `MAX_RESULTS` | `5` | Maximum search results to inject |
| `SEARCH_TYPE` | `hybrid` | Search type: `hybrid`, `semantic`, or `keyword` |
| `ENABLE_FOLDER_CONTEXT` | `true` | Enable folder-to-page mapping |

For Docker deployments, set `GRPC_HOST` to your Docker network address (e.g., `silverbullet-rag:50051`).

#### User Settings (UserValves)

Users can customize their own settings by clicking the pipe icon in their chat:

| Setting | Default | Description |
|---------|---------|-------------|
| `include_paths` | `""` | Additional folder paths to always include (comma-separated) |
| `include_tags` | `""` | Tags to always include regardless of scope (comma-separated) |
| `scope_mode` | `prefer` | Scoping mode: `strict`, `prefer`, or `none` |
| `max_context_chars` | `8000` | Maximum total context characters (0 = unlimited) |
| `project_context_chars` | `4000` | Maximum project context characters (0 = full page) |
| `truncate_results` | `true` | Truncate results to fit within budget |

**Scope Modes:**
- `strict`: Only show results from the scoped folder and include paths/tags
- `prefer`: Show scoped results first, then include paths/tags, then others
- `none`: No scoping - show all relevant results regardless of folder

## Folder Context Mapping

The pipe can automatically inject project context when chatting within Open WebUI folders.

### Setting Up Folder Mapping

1. In your Silverbullet space, add `openwebui-folder` to your project page frontmatter:

```yaml
---
openwebui-folder: Projects/MyApp
---
# My Application

This is the main documentation for MyApp...
```

2. In Open WebUI, create a folder named `Projects/MyApp`

3. When you start a chat in that folder, the pipe will:
   - Find the Silverbullet page with matching `openwebui-folder`
   - Inject the page content as "Project Context"
   - Scope all searches to the `Projects/MyApp` folder in Silverbullet

### How It Works

```
Open WebUI                          Silverbullet RAG
    │                                      │
    │  Chat in "Projects/MyApp" folder     │
    │ ──────────────────────────────────>  │
    │                                      │
    │  GetFolderContext("Projects/MyApp")  │
    │ ──────────────────────────────────>  │
    │                                      │  Query: pages with
    │                                      │  openwebui-folder = "Projects/MyApp"
    │                                      │
    │  <─── page_name, page_content,       │
    │       folder_scope                   │
    │                                      │
    │  HybridSearch(query, scope)          │
    │ ──────────────────────────────────>  │
    │                                      │  Search scoped to folder
    │  <─── search results                 │
    │                                      │
    │  Inject context into chat            │
    └──────────────────────────────────────┘
```

## Context Injection

The pipe injects two types of context into chat messages:

### 1. Project Context (once per chat)

When a folder mapping is found, the full page content is injected:

```
# Project Context: Projects/MyApp/index

[Full page content from Silverbullet]
```

### 2. Search Results (per message)

Relevant chunks from hybrid search:

```
# Relevant Knowledge

## Section Header
[Chunk content]

Source: Projects/MyApp/notes.md

---

## Another Section
[Another chunk]

Source: Projects/MyApp/api.md
```

## Architecture

The pipe is a **single-file gRPC client** that embeds:
- Protobuf message definitions
- gRPC service stub
- Pipe logic with caching

This allows easy deployment to Open WebUI without additional dependencies.

### Building the Pipe

The pipe is generated from `proto/rag.proto` and the template in `scripts/build_openwebui_pipe.py`:

```bash
python scripts/build_openwebui_pipe.py
```

This regenerates `openwebui/silverbullet_rag.py` with updated protobuf stubs.

## Troubleshooting

### Connection Refused

If you see `gRPC error: UNAVAILABLE`, check:
- Is the gRPC server running? (`docker-compose ps`)
- Is the `GRPC_HOST` valve set correctly?
- For Docker, use the service name (e.g., `silverbullet-rag:50051`) not `localhost`

### No Search Results

- Verify the index is built: `docker-compose exec silverbullet-rag python -m server.init_index`
- Check that embeddings are enabled (`ENABLE_EMBEDDINGS=true`)
- Try keyword search type first to rule out embedding issues

### Folder Context Not Working

- Verify the `openwebui-folder` frontmatter is set correctly
- The folder path comparison is case-insensitive
- Check the gRPC server logs for `Found folder context for...` messages

### Slow Responses

- Reduce `MAX_RESULTS` to return fewer chunks
- Use `keyword` search type instead of `hybrid` for faster responses
- Ensure the gRPC server is on the same network as Open WebUI

## Example Setup

### docker-compose.yml

```yaml
services:
  silverbullet-rag:
    image: ghcr.io/your-username/silverbullet-rag:latest
    volumes:
      - silverbullet-space:/space:ro
      - ladybug-db:/data
    environment:
      - DB_PATH=/data/ladybug
      - SPACE_PATH=/space
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    ports:
      - "8000:8000"   # MCP
      - "50051:50051" # gRPC

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    ports:
      - "3000:8080"
    # ... other config
```

### Silverbullet Page

```markdown
---
openwebui-folder: Work/ProjectX
tags:
  - project
  - active
---

# Project X

## Overview
Project X is a customer portal application...

## Architecture
The system uses a microservices architecture...

## API Reference
See [[ProjectX/API]] for endpoint documentation.
```

When chatting in Open WebUI's "Work/ProjectX" folder, this page content will be automatically injected, and searches will be scoped to the `Work/ProjectX` folder in Silverbullet.

## Including Orthogonal Knowledge

By default, folder scoping limits results to the matched folder. However, you often need access to reference material, glossaries, or shared templates from other folders.

### Using Include Paths

Add folders that should always be included in results:

```
include_paths: Reference,Shared/Templates,Glossary
```

Results from these folders will be included alongside scoped results.

### Using Include Tags

Include content tagged with specific tags regardless of folder:

```
include_tags: reference,glossary,api-docs
```

Any chunk with these tags will be included in results.

### Choosing a Scope Mode

- **`prefer`** (default): Best for most users. Shows scoped results first, then includes, then global results. Ensures you see relevant project content while still accessing broader knowledge.

- **`strict`**: For focused work. Only shows results from the scoped folder and include paths/tags. Use when you want to avoid distraction from unrelated content.

- **`none`**: Disables scoping entirely. All search results are shown based purely on relevance, ignoring folder context.

### Example Configuration

A data scientist working on a project might configure:

```
scope_mode: prefer
include_paths: Reference/Statistics,Datasets
include_tags: methodology,glossary
max_context_chars: 12000
```

This ensures they see project-specific notes first, but also have access to their statistics reference materials and glossary definitions.
