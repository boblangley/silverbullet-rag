# Silverbullet Proposal System

## Overview

A system for AI assistants to propose changes to a Silverbullet space. Users review and accept/reject proposals within Silverbullet itself.

**Components:**
1. **MCP Tools** - `propose_change`, `list_proposals`, `withdraw_proposal`
2. **Silverbullet Library** - Document Editor for `.proposal` files, widgets, meta page

**Key constraint:** Propose tools are only registered if the Library is installed. At MCP server startup, we check for `Library/AI-Proposals.md` - if present, register the tools; if not, they simply don't appear (no errors, just logged).

---

## Proposal Files

Proposals are stored as `.proposal` files in the space:

```
# With PROPOSAL_PATH_PREFIX="_Proposals/" (default)
Target: Projects/MyProject.md
Proposal: _Proposals/Projects/MyProject.md.proposal

# With PROPOSAL_PATH_PREFIX="" (sibling mode)
Target: Projects/MyProject.md
Proposal: Projects/MyProject.md.proposal
```

### File Format

```yaml
---
type: proposal
target_page: Projects/MyProject.md
title: Add implementation notes
description: Added notes from our discussion about the architecture
proposed_by: claude-code
created_at: 2024-01-15T10:30:00Z
status: pending
is_new_page: false
---

The full proposed content goes here...
```

Status values: `pending`, `accepted`, `rejected`

---

## MCP Tools

### `propose_change`

Create a proposal for a new or existing page.

```python
@mcp.tool()
async def propose_change(
    target_page: str,
    content: str,
    title: str,
    description: str,
) -> Dict[str, Any]:
    """
    Propose a change to a page. Requires AI-Proposals library installed.

    Args:
        target_page: Page path (e.g., 'Projects/MyProject.md')
        content: Proposed page content
        title: Short title for the proposal
        description: Why this change is proposed

    Returns:
        Proposal path and status
    """
    # Check library is installed
    if not library_installed():
        return {
            "success": False,
            "error": "AI-Proposals library not installed",
            "instructions": "Install from: https://github.com/boblangley/silverbullet-rag"
        }

    # Determine if new page
    is_new_page = not page_exists(target_page)

    # Generate proposal path
    proposal_path = get_proposal_path(target_page)

    # Build proposal content
    proposal_content = f"""---
type: proposal
target_page: {target_page}
title: {title}
description: {description}
proposed_by: {agent_name}
created_at: {datetime.now().isoformat()}
status: pending
is_new_page: {str(is_new_page).lower()}
---

{content}
"""

    # Write proposal file
    write_file(proposal_path, proposal_content)

    return {
        "success": True,
        "proposal_path": proposal_path,
        "is_new_page": is_new_page,
        "message": f"Proposal created. User can review at {proposal_path}"
    }
```

### `list_proposals`

List pending proposals.

```python
@mcp.tool()
async def list_proposals(
    status: str = "pending"  # pending, accepted, rejected, all
) -> Dict[str, Any]:
    """List proposals by status."""
    proposals = find_proposals(status)
    return {
        "success": True,
        "proposals": [
            {
                "path": p.path,
                "target_page": p.target_page,
                "title": p.title,
                "status": p.status,
                "created_at": p.created_at
            }
            for p in proposals
        ]
    }
```

### `withdraw_proposal`

Withdraw a pending proposal (AI decides it's no longer needed).

```python
@mcp.tool()
async def withdraw_proposal(
    proposal_path: str,
) -> Dict[str, Any]:
    """
    Withdraw a pending proposal.

    Args:
        proposal_path: Path to the .proposal file

    Returns:
        Success status
    """
    if not proposal_exists(proposal_path):
        return {"success": False, "error": "Proposal not found"}

    delete_file(proposal_path)

    return {"success": True, "message": "Proposal withdrawn"}
```

---

## Library Detection (At Startup)

At MCP server startup, check if the library is installed:

```python
def library_installed() -> bool:
    """Check if AI-Proposals library is installed."""
    library_marker = space_path / "Library" / "AI-Proposals.md"
    return library_marker.exists()

# In server initialization:
if library_installed():
    logger.info("AI-Proposals library found, registering propose tools")
    register_propose_tools()
else:
    logger.info("AI-Proposals library not installed, propose tools not available")
```

Tools are simply not registered if library isn't found - no runtime errors.

---

## Silverbullet Library

Located at `Library/AI-Proposals.md` (and supporting files).

### Document Editor for `.proposal`

Renders an **inline diff view** - simpler than side-by-side:

```
───────────────────────────────────────────
📋 Add implementation notes
Target: Projects/MyProject.md
───────────────────────────────────────────

  # My Project

  This is existing content.

- This line was removed by the proposal.
+ This line was added by the proposal.

  More unchanged content.

+ ## New Section
+
+ This entire section is new.

───────────────────────────────────────────
[✓ Accept]  [✗ Reject]
───────────────────────────────────────────
```

**Styling:**
- `-` lines: red background, strikethrough
- `+` lines: green background
- Context lines: normal
- New pages: just show content with "NEW PAGE" banner (no diff)

**Accept/Reject Behavior:**
- **Accept**: Write proposed content to target page, delete the `.proposal` file
- **Reject**: Move `.proposal` file to `_Proposals/_Rejected/` (or configured location), plug's cron job cleans up after N days

### Implementation

```typescript
// proposal_editor.ts
export async function editor(): Promise<{ html: string }> {
  return {
    html: `
<!DOCTYPE html>
<html>
<head>
  <style>
    body {
      margin: 0;
      font-family: system-ui;
      background: var(--bg, #fff);
      color: var(--fg, #333);
    }
    .header {
      padding: 16px;
      border-bottom: 1px solid #ddd;
      background: #f8f9fa;
    }
    .title { font-size: 18px; font-weight: bold; margin-bottom: 4px; }
    .target { color: #666; font-size: 14px; }
    .description { margin-top: 8px; font-style: italic; }
    .new-page-banner {
      background: #dbeafe;
      color: #1e40af;
      padding: 8px 16px;
      font-weight: bold;
    }
    .diff {
      font-family: monospace;
      font-size: 14px;
      padding: 16px;
      white-space: pre-wrap;
      line-height: 1.5;
    }
    .diff-add {
      background: #dcfce7;
      color: #166534;
    }
    .diff-del {
      background: #fee2e2;
      color: #991b1b;
      text-decoration: line-through;
    }
    .diff-context {
      color: #666;
    }
    .actions {
      padding: 16px;
      border-top: 1px solid #ddd;
      display: flex;
      gap: 8px;
    }
    .btn {
      padding: 10px 20px;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
    }
    .btn-accept { background: #22c55e; color: white; }
    .btn-accept:hover { background: #16a34a; }
    .btn-reject { background: #ef4444; color: white; }
    .btn-reject:hover { background: #dc2626; }
  </style>
</head>
<body>
  <div class="header">
    <div class="title" id="title">Loading...</div>
    <div class="target">Target: <span id="target"></span></div>
    <div class="description" id="description"></div>
  </div>
  <div id="new-page-banner" class="new-page-banner" style="display:none">
    🆕 NEW PAGE - This will create a new page
  </div>
  <div id="diff" class="diff"></div>
  <div class="actions">
    <button class="btn btn-accept" onclick="acceptProposal()">✓ Accept</button>
    <button class="btn btn-reject" onclick="rejectProposal()">✗ Reject</button>
  </div>

  <script>
    let meta = {};
    let proposedContent = '';
    let originalContent = '';

    window.silverbullet.addEventListener("file-open", async (event) => {
      const decoder = new TextDecoder();
      const content = decoder.decode(event.detail.data);

      // Parse frontmatter
      const match = content.match(/^---\\n([\\s\\S]*?)\\n---\\n([\\s\\S]*)$/);
      if (!match) return;

      const [, frontmatter, body] = match;
      meta = parseFrontmatter(frontmatter);
      proposedContent = body.trim();

      document.getElementById('title').textContent = meta.title || 'Proposal';
      document.getElementById('target').textContent = meta.target_page;
      document.getElementById('description').textContent = meta.description || '';

      if (meta.is_new_page === 'true') {
        document.getElementById('new-page-banner').style.display = 'block';
        document.getElementById('diff').innerHTML = escapeHtml(proposedContent);
      } else {
        // Fetch original and render diff
        try {
          originalContent = await window.silverbullet.syscall('space.readPage', meta.target_page);
          renderInlineDiff();
        } catch (e) {
          // Page might not exist
          document.getElementById('new-page-banner').style.display = 'block';
          document.getElementById('diff').innerHTML = escapeHtml(proposedContent);
        }
      }
    });

    function parseFrontmatter(yaml) {
      const meta = {};
      yaml.split('\\n').forEach(line => {
        const idx = line.indexOf(':');
        if (idx > 0) {
          const key = line.slice(0, idx).trim();
          const value = line.slice(idx + 1).trim();
          meta[key] = value;
        }
      });
      return meta;
    }

    function escapeHtml(text) {
      return text.replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[c]));
    }

    function renderInlineDiff() {
      const origLines = originalContent.split('\\n');
      const propLines = proposedContent.split('\\n');

      // Simple line-by-line diff (could use a proper diff algorithm)
      const diff = computeDiff(origLines, propLines);

      let html = '';
      for (const line of diff) {
        if (line.type === 'add') {
          html += '<div class="diff-add">+ ' + escapeHtml(line.text) + '</div>';
        } else if (line.type === 'del') {
          html += '<div class="diff-del">- ' + escapeHtml(line.text) + '</div>';
        } else {
          html += '<div class="diff-context">  ' + escapeHtml(line.text) + '</div>';
        }
      }

      document.getElementById('diff').innerHTML = html;
    }

    function computeDiff(orig, prop) {
      // Simple diff: show all deletions, then all additions
      // In production, use Myers diff or similar
      const result = [];
      const origSet = new Set(orig);
      const propSet = new Set(prop);

      // Lines only in original (deleted)
      for (const line of orig) {
        if (!propSet.has(line)) {
          result.push({ type: 'del', text: line });
        }
      }

      // All lines from proposed (mark additions)
      for (const line of prop) {
        if (!origSet.has(line)) {
          result.push({ type: 'add', text: line });
        } else {
          result.push({ type: 'context', text: line });
        }
      }

      return result;
    }

    async function acceptProposal() {
      if (!confirm('Apply this proposal to ' + meta.target_page + '?')) return;

      try {
        // Write proposed content to target page
        await window.silverbullet.syscall('space.writePage', meta.target_page, proposedContent);

        // Delete the proposal file (it's been "merged")
        const currentPage = await window.silverbullet.syscall('editor.getCurrentPage');
        await window.silverbullet.syscall('space.deletePage', currentPage);

        alert('Proposal accepted! Page updated.');
        // Navigate to the target page
        await window.silverbullet.syscall('editor.navigate', meta.target_page);
      } catch (e) {
        alert('Failed to apply proposal: ' + e.message);
      }
    }

    async function rejectProposal() {
      if (!confirm('Reject this proposal?')) return;

      try {
        const currentPage = await window.silverbullet.syscall('editor.getCurrentPage');
        // Move to rejected folder - cron job will clean up after X days
        const rejectedPath = currentPage.replace('_Proposals/', '_Proposals/_Rejected/');
        await window.silverbullet.syscall('space.renamePage', currentPage, rejectedPath);

        alert('Proposal rejected. It will be cleaned up automatically.');
        await window.silverbullet.syscall('editor.navigate', 'Library/AI-Proposals/Proposals');
      } catch (e) {
        alert('Failed to reject proposal: ' + e.message);
      }
    }
  </script>
</body>
</html>
    `
  };
}
```

### Top Widget

Shows banner when current page has pending proposals:

```lua
-- In Library/AI-Proposals.md

event.listen("hooks:renderTopWidgets", function()
  local current = editor.getCurrentPage()

  -- Query for proposals targeting this page
  local proposals = query[[
    from index.tag "proposal"
    where target_page = @current and status = "pending"
  ]]

  if #proposals == 0 then
    return {}
  end

  local links = {}
  for _, p in ipairs(proposals) do
    table.insert(links, "[[" .. p.name .. "|" .. p.title .. "]]")
  end

  return {
    {
      html = "<div style='background:#fef3c7;padding:8px 12px;border-bottom:1px solid #f59e0b'>"
           .. "📋 <strong>Pending proposals:</strong> "
           .. table.concat(links, ", ")
           .. "</div>"
    }
  }
end)
```

### Meta Page: `Library/AI-Proposals/Proposals.md`

```markdown
---
displayName: AI Proposals
---

# Pending Proposals

${query[[
  from index.tag "proposal"
  where status = "pending"
  order by created_at desc
]]}

# Recently Accepted

${query[[
  from index.tag "proposal"
  where status = "accepted"
  order by created_at desc
  limit 10
]]}

# Recently Rejected

${query[[
  from index.tag "proposal"
  where status = "rejected"
  order by created_at desc
  limit 10
]]}
```

### Command

```lua
command.define {
  name = "AI: View Proposals",
  run = function()
    editor.navigate("Library/AI-Proposals/Proposals")
  end
}
```

### Cron Job for Cleanup

Uses `cron:secondPassed` event (fires every second) to periodically clean up old rejected proposals:

```lua
-- Track last cleanup time
local last_cleanup = os.time()
local CLEANUP_INTERVAL = 3600  -- Check once per hour

event.listen("cron:secondPassed", function()
  local now = os.time()
  if now - last_cleanup < CLEANUP_INTERVAL then
    return
  end
  last_cleanup = now

  -- Get cleanup config (default 30 days)
  local cleanup_days = config.get("mcp.proposals.cleanup_after_days", 30)
  local cutoff = now - (cleanup_days * 24 * 60 * 60)

  -- Find old rejected proposals
  local rejected = query[[
    from index.tag "proposal"
    where name:startsWith("_Proposals/_Rejected/")
  ]]

  for _, p in ipairs(rejected) do
    -- Parse created_at from frontmatter and compare
    if p.created_at then
      local created_ts = os.time(os.date("*t", p.created_at))
      if created_ts < cutoff then
        space.deletePage(p.name)
      end
    end
  end
end)
```

---

## Configuration

### MCP Server

```python
# Environment variables
PROPOSAL_PATH_PREFIX = "_Proposals/"  # Empty for sibling mode
```

### Silverbullet (CONFIG.md)

```lua
-- MCP server reads this
config.set("mcp.proposals.path_prefix", "_Proposals/")

-- Library reads this (for cron cleanup)
config.set("mcp.proposals.cleanup_after_days", 30)
```

---

## Reading Silverbullet Config

### Architecture

The **watcher** (indexer) handles CONFIG.md specially:
1. Extracts `space-lua` blocks from CONFIG.md
2. Parses `config.set()` calls using [slpp](https://github.com/SirAnthony/slpp) (Lua literal parser)
3. Writes parsed config to `space_config.json` next to the database
4. MCP server reads `space_config.json` at startup and when needed

This keeps config parsing in one place (watcher) and gives MCP simple JSON to read.

### Watcher Implementation

```python
# indexer/config_parser.py
import re
import json
from pathlib import Path
from slpp import slpp as lua  # pip install slpp

def set_nested(d: dict, key: str, value) -> None:
    """Set a value in a nested dict using dot-notation key."""
    parts = key.split('.')
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value


def parse_config_page(content: str) -> dict:
    """
    Parse CONFIG.md and extract config.set() values.

    Args:
        content: Raw markdown content of CONFIG.md

    Returns:
        Nested dict matching config key structure
    """
    # Extract space-lua blocks
    lua_blocks = re.findall(
        r'```space-lua\n(.*?)```',
        content,
        re.DOTALL
    )

    config = {}

    for block in lua_blocks:
        # Match config.set("key", value) calls
        # Value can be: string, number, boolean, or table
        pattern = r'config\.set\s*\(\s*"([^"]+)"\s*,\s*(.+?)\s*\)(?=\s*(?:config\.|--|$|\n))'
        matches = re.findall(pattern, block, re.MULTILINE)

        for key, value_str in matches:
            try:
                # Use slpp to parse Lua literals
                parsed = lua.decode(value_str)
                set_nested(config, key, parsed)
            except Exception:
                # Fall back to simple parsing for edge cases
                value_str = value_str.strip()
                if value_str in ('true', 'false'):
                    set_nested(config, key, value_str == 'true')
                elif value_str.replace('.', '').replace('-', '').isdigit():
                    set_nested(config, key, float(value_str) if '.' in value_str else int(value_str))
                elif value_str.startswith('"') and value_str.endswith('"'):
                    set_nested(config, key, value_str[1:-1])

    return config


def write_config_json(config: dict, db_path: Path):
    """Write parsed config to JSON file next to database."""
    config_path = db_path.parent / "space_config.json"
    config_path.write_text(json.dumps(config, indent=2))


# In watcher's file change handler:
def on_file_change(file_path: str, content: str, db_path: Path):
    if file_path == "CONFIG.md":
        config = parse_config_page(content)
        write_config_json(config, db_path)
        # Don't index CONFIG.md normally, or do both
```

### MCP Server Usage

```python
# server/mcp_http_server.py
import json
from pathlib import Path

def load_space_config() -> dict:
    """Load space config from JSON file written by watcher."""
    config_path = Path(os.getenv("DB_PATH")).parent / "space_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {}

# Usage - just read the path prefix:
config = load_space_config()
path_prefix = config.get("mcp", {}).get("proposals", {}).get("path_prefix", "_Proposals/")
```

### Example

CONFIG.md in space:
```markdown
# Configuration

```space-lua
config.set("mcp.proposals.path_prefix", "_Proposals/")
config.set("mcp.proposals.cleanup_after_days", 14)
`` `
```

Generated `space_config.json`:
```json
{
  "mcp": {
    "proposals": {
      "path_prefix": "_Proposals/",
      "cleanup_after_days": 14
    }
  }
}
```

MCP reads path_prefix, library reads cleanup_after_days (via Lua `config.get()`).

### Dependencies

Add to `pyproject.toml`:
```toml
[project]
dependencies = [
    "slpp>=1.2.3",
    # ... existing deps
]
```

---

## Summary

| Component | Description |
|-----------|-------------|
| `propose_change` | MCP tool to create proposals |
| `list_proposals` | MCP tool to list proposals by status |
| `withdraw_proposal` | MCP tool for AI to withdraw a proposal |
| `.proposal` files | Storage format in space |
| Document Editor | Inline diff view with Accept/Reject |
| Top Widget | Banner on pages with pending proposals |
| Meta Page | List all proposals |
| Cron Cleanup | Auto-delete rejected proposals after N days |

**Workflow:**
- **Accept** → Write to target, delete proposal file
- **Reject** → Move to `_Rejected/`, cron cleans up later
- **Withdraw** → AI deletes its own pending proposal

**No `update_page` tool** - all changes go through proposals.

---

## Repo Structure

```
silverbullet-rag/
  server/
    mcp_http_server.py      # Includes propose_* tools (conditionally registered)
  library/
    AI-Proposals.md         # Main library file
    AI-Proposals/
      Proposals.md          # Meta page
      proposal_editor.ts    # Document editor
      plug.json             # Plug manifest
```

Users install the library from the repo URL in Silverbullet's Library Manager.

---

## Next Steps

### Watcher/Indexer
1. [ ] Add `slpp` dependency to pyproject.toml
2. [ ] Add CONFIG.md special handling in watcher
3. [ ] Write `space_config.json` on CONFIG.md changes

### MCP Server
4. [ ] Add `load_space_config()` helper
5. [ ] Implement `propose_change` MCP tool
6. [ ] Implement `list_proposals` MCP tool
7. [ ] Implement `withdraw_proposal` MCP tool
8. [ ] Add library detection at startup (conditional tool registration)

### Silverbullet Library
9. [ ] Create library files in `library/` folder
10. [ ] Build Document Editor with inline diff
11. [ ] Add top widget for proposal banners
12. [ ] Create meta page
13. [ ] Add cron job for cleanup

### Testing
14. [ ] Test end-to-end workflow
