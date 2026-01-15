# MCP Integration Guide

Silverbullet RAG exposes a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that provides RAG tools to AI assistants. This guide covers how to connect various clients to the MCP server.

## Server Details

- **Transport**: Streamable HTTP
- **Port**: 8000
- **Endpoint**: `http://localhost:8000/mcp`
- **Protocol**: MCP 1.0

## Available Tools

| Tool                  | Description                                         |
| --------------------- | --------------------------------------------------- |
| `cypher_query`        | Execute Cypher queries against the knowledge graph  |
| `keyword_search`      | BM25-ranked keyword search                          |
| `semantic_search`     | AI-powered vector similarity search                 |
| `hybrid_search_tool`  | Combined keyword + semantic search with RRF fusion  |
| `get_project_context` | Get project context by GitHub remote or folder path |
| `read_page`           | Read contents of a Silverbullet page                |
| `propose_change`      | Propose a change for user review (requires Proposals library) |
| `list_proposals`      | List pending/accepted/rejected proposals            |
| `withdraw_proposal`   | Withdraw a pending proposal                         |

---

## Claude Code

Claude Code supports MCP servers natively via the `.mcp.json` configuration file.

### Configuration

Create or edit `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "silverbullet-rag": {
      "type": "url",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

For remote servers or Docker:

```json
{
  "mcpServers": {
    "silverbullet-rag": {
      "type": "url",
      "url": "http://your-server:8000/mcp"
    }
  }
}
```

### Usage

Once configured, Claude Code will automatically discover the tools. You can:

```
# Search your knowledge base
/mcp silverbullet-rag keyword_search "authentication"

# Get project context
/mcp silverbullet-rag get_project_context {"github_remote": "org/repo"}

# Execute a Cypher query
/mcp silverbullet-rag cypher_query "MATCH (t:Tag) RETURN t.name LIMIT 10"
```

Or simply ask Claude to search your knowledge base - it will use the appropriate tool automatically.

---

## Gemini CLI

Gemini CLI supports MCP servers through its settings configuration.

### Configuration

Edit your Gemini CLI settings file (typically `~/.gemini/settings.json`):

```json
{
  "mcpServers": {
    "silverbullet-rag": {
      "transport": {
        "type": "http",
        "url": "http://localhost:8000/mcp"
      }
    }
  }
}
```

### Usage

```bash
# List available tools
gemini mcp list-tools silverbullet-rag

# Call a tool directly
gemini mcp call silverbullet-rag keyword_search --query "database"

# Use in conversation
gemini chat --mcp silverbullet-rag
```

---

## VS Code

VS Code can connect to MCP servers through the Copilot Chat extension with MCP support.

### Configuration

Create `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "silverbullet-rag": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Or add to your user settings (`settings.json`):

```json
{
  "mcp.servers": {
    "silverbullet-rag": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Usage

1. Open the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`)
2. Search for "MCP: List Tools"
3. Select "silverbullet-rag" server
4. Browse and invoke available tools

Or use the chat panel:
- Type `@silverbullet-rag` to reference the server
- Ask questions that will trigger tool usage

---

## JetBrains IDEs

JetBrains IDEs (IntelliJ, PyCharm, WebStorm, etc.) support MCP through their AI Assistant plugins.

### Configuration

1. Open **Settings** → **Tools** → **AI Assistant** → **MCP Servers**
2. Click **Add Server**
3. Configure:
   - **Name**: `silverbullet-rag`
   - **Transport**: HTTP
   - **URL**: `http://localhost:8000/mcp`
4. Click **Test Connection** to verify
5. Click **OK** to save

### Alternative: Config File

Create `~/.config/jetbrains/mcp-servers.json`:

```json
{
  "servers": [
    {
      "name": "silverbullet-rag",
      "transport": {
        "type": "http",
        "url": "http://localhost:8000/mcp"
      }
    }
  ]
}
```

### Usage

1. Open the AI Assistant panel
2. Click the **Tools** icon to see available MCP tools
3. Use natural language to trigger tools:
   - "Search my knowledge base for authentication"
   - "Find pages tagged with #api"
   - "Get context for the current project"

---

## Cursor

Cursor supports MCP servers for enhanced AI assistance.

### Configuration

Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "silverbullet-rag": {
      "transport": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Usage

In Cursor's AI chat:
- Tools are automatically available
- Ask questions that reference your knowledge base
- The AI will use appropriate tools to find relevant context

---

## Generic HTTP Client

You can also interact with the MCP server directly via HTTP.

### List Available Tools

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

### Call a Tool

```bash
# Keyword search
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "keyword_search",
      "arguments": {"query": "database"}
    },
    "id": 2
  }'

# Semantic search
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "semantic_search",
      "arguments": {
        "query": "How do I configure authentication?",
        "limit": 5
      }
    },
    "id": 3
  }'

# Hybrid search
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "hybrid_search_tool",
      "arguments": {
        "query": "database optimization",
        "limit": 10,
        "fusion_method": "rrf",
        "semantic_weight": 0.6,
        "keyword_weight": 0.4
      }
    },
    "id": 4
  }'
```

---

## Tool Reference

### cypher_query

Execute Cypher queries against the knowledge graph.

```json
{
  "name": "cypher_query",
  "arguments": {
    "query": "MATCH (c:Chunk)-[:TAGGED]->(t:Tag) RETURN t.name, COUNT(c) ORDER BY COUNT(c) DESC LIMIT 10"
  }
}
```

### keyword_search

BM25-ranked keyword search with tag and header boosting.

```json
{
  "name": "keyword_search",
  "arguments": {
    "query": "authentication api"
  }
}
```

### semantic_search

AI-powered vector similarity search.

```json
{
  "name": "semantic_search",
  "arguments": {
    "query": "How do I handle user sessions?",
    "limit": 10,
    "filter_tags": ["auth", "session"],
    "filter_pages": ["Authentication.md"]
  }
}
```

### hybrid_search_tool

Combined keyword and semantic search with result fusion.

```json
{
  "name": "hybrid_search_tool",
  "arguments": {
    "query": "database performance tuning",
    "limit": 10,
    "fusion_method": "rrf",
    "semantic_weight": 0.5,
    "keyword_weight": 0.5,
    "scope": "Projects/ProjectA"
  }
}
```

Parameters:
- `fusion_method`: `"rrf"` (Reciprocal Rank Fusion) or `"weighted"`
- `semantic_weight`: Weight for semantic results (0-1)
- `keyword_weight`: Weight for keyword results (0-1)
- `scope`: Optional folder path to scope results

### get_project_context

Get project context by GitHub remote or folder path.

```json
{
  "name": "get_project_context",
  "arguments": {
    "github_remote": "anthropics/claude-code"
  }
}
```

Or by folder:

```json
{
  "name": "get_project_context",
  "arguments": {
    "folder_path": "Projects/MyProject"
  }
}
```

### read_page

Read contents of a Silverbullet page.

```json
{
  "name": "read_page",
  "arguments": {
    "page_name": "Documentation/API.md"
  }
}
```

### propose_change

Propose a change to a page for user review. Requires the Proposals library installed in the Silverbullet space.

```json
{
  "name": "propose_change",
  "arguments": {
    "target_page": "Projects/MyProject.md",
    "content": "# My Project\n\nUpdated content with improvements...",
    "title": "Improve project documentation",
    "description": "Added installation instructions and usage examples"
  }
}
```

Parameters:
- `target_page`: Path to the page to modify
- `content`: Complete proposed page content
- `title`: Short title for the proposal
- `description`: Explanation of why this change is proposed

### list_proposals

List change proposals by status.

```json
{
  "name": "list_proposals",
  "arguments": {
    "status": "pending"
  }
}
```

Parameters:
- `status`: Filter by status (`pending`, `accepted`, `rejected`, or `all`)

### withdraw_proposal

Withdraw a pending proposal.

```json
{
  "name": "withdraw_proposal",
  "arguments": {
    "proposal_path": "_Proposals/Projects/MyProject.md.proposal"
  }
}
```

See [library.md](library.md) for detailed documentation on the proposal system.

---

## Troubleshooting

### Connection Refused

```
Error: Connection refused to localhost:8000
```

1. Ensure the MCP server is running:
   ```bash
   docker ps | grep silverbullet-rag-mcp
   ```
2. Check if the port is exposed correctly
3. For Docker, ensure you're using the correct host (may need `host.docker.internal` on Mac/Windows)

### Tool Not Found

```
Error: Tool 'xyz' not found
```

1. List available tools to verify names:
   ```bash
   curl -X POST http://localhost:8000/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
   ```
2. Tool names are case-sensitive

### Timeout Errors

For large knowledge bases, searches may take longer:

1. Increase client timeout settings
2. Use `limit` parameter to reduce results
3. Use `scope` parameter to narrow search area

### Authentication Issues

The MCP server currently does not require authentication. For production deployments behind a reverse proxy, configure authentication at the proxy level.
