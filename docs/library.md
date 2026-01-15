# AI-Proposals Library

The AI-Proposals library enables AI assistants to propose changes to your Silverbullet space. Instead of directly modifying pages, AI assistants create `.proposal` files that you can review with inline diffs and accept or reject.

## Why Proposals?

Direct page editing by AI can be risky:
- Changes might not match your intent
- Formatting or structure could be disrupted
- Important content might be accidentally removed

The proposal system gives you control:
- Review exactly what will change before it happens
- See inline diffs comparing original vs proposed content
- Accept with one click, or reject and provide feedback

## Installation

Use Silverbullet's built-in Library Manager:

1. Run the `Library: Manager` command in Silverbullet
2. Add this repository to your repositories list
3. Install the AI-Proposals library

The library installs to `Library/AI-Proposals/` in your space.

## How It Works

### MCP/gRPC Proposal Flow

1. **AI creates proposal**: When an AI assistant wants to modify a page, it calls `propose_change` instead of directly writing
2. **Proposal file created**: A `.proposal` file is created in `_Proposals/` with the proposed content and metadata
3. **User notification**: A banner appears in Silverbullet when you view a page with pending proposals
4. **Review with diff**: Open the proposal to see an inline diff of changes
5. **Accept or reject**: Click Accept to apply changes, or Reject to dismiss

```
AI Assistant                    Silverbullet Space
     │                                 │
     │  propose_change(...)            │
     │────────────────────────────────>│
     │                                 │  Creates _Proposals/Page.md.proposal
     │                                 │
     │                          User opens Page.md
     │                                 │
     │                          Banner: "Pending proposal"
     │                                 │
     │                          User reviews diff
     │                                 │
     │                          User clicks Accept
     │                                 │
     │                          Page.md updated
     │                          Proposal deleted
```

### Proposal File Format

Proposals are stored as `.proposal` files with YAML frontmatter:

```yaml
---
type: proposal
target_page: Projects/MyProject.md
title: Add installation instructions
description: Added step-by-step installation guide with code examples
proposed_by: claude-code
created_at: 2025-01-15T10:30:00
status: pending
is_new_page: false
---

# My Project

[Proposed content here...]
```

### Proposal Statuses

- **pending**: Awaiting user review
- **accepted**: User accepted and changes were applied (file deleted)
- **rejected**: User rejected (moved to `_Proposals/_Rejected/` for cleanup)

## MCP Tools

When the AI-Proposals library is installed, these MCP tools become available:

### propose_change

Create a proposal for page changes.

```json
{
  "name": "propose_change",
  "arguments": {
    "target_page": "Projects/MyProject.md",
    "content": "# My Project\n\nUpdated content...",
    "title": "Update project description",
    "description": "Clarified the project goals and added examples"
  }
}
```

**Parameters:**
- `target_page` (required): Path to the page to modify
- `content` (required): Complete proposed page content
- `title` (required): Short title for the proposal
- `description` (required): Explanation of why this change is proposed

**Returns:**
```json
{
  "success": true,
  "proposal_path": "_Proposals/Projects/MyProject.md.proposal",
  "is_new_page": false,
  "message": "Proposal created. User can review at _Proposals/Projects/MyProject.md.proposal"
}
```

### list_proposals

List proposals by status.

```json
{
  "name": "list_proposals",
  "arguments": {
    "status": "pending"
  }
}
```

**Parameters:**
- `status`: Filter by status (`pending`, `accepted`, `rejected`, or `all`)

**Returns:**
```json
{
  "success": true,
  "count": 2,
  "proposals": [
    {
      "path": "_Proposals/Projects/MyProject.md.proposal",
      "target_page": "Projects/MyProject.md",
      "title": "Update project description",
      "status": "pending",
      "created_at": "2025-01-15T10:30:00"
    }
  ]
}
```

### withdraw_proposal

Withdraw a pending proposal (e.g., if the AI made a mistake).

```json
{
  "name": "withdraw_proposal",
  "arguments": {
    "proposal_path": "_Proposals/Projects/MyProject.md.proposal"
  }
}
```

## gRPC Methods

The same functionality is available via gRPC:

```protobuf
service SilverbulletRAG {
  rpc ProposeChange(ProposeChangeRequest) returns (ProposeChangeResponse);
  rpc ListProposals(ListProposalsRequest) returns (ListProposalsResponse);
  rpc WithdrawProposal(WithdrawProposalRequest) returns (WithdrawProposalResponse);
}
```

### Python Example

```python
import grpc
from server.grpc import rag_pb2, rag_pb2_grpc

channel = grpc.insecure_channel('localhost:50051')
stub = rag_pb2_grpc.SilverbulletRAGStub(channel)

# Create a proposal
response = stub.ProposeChange(rag_pb2.ProposeChangeRequest(
    target_page="Projects/MyProject.md",
    content="# My Project\n\nUpdated content...",
    title="Update project description",
    description="Clarified goals and added examples"
))

if response.success:
    print(f"Proposal created: {response.proposal_path}")
```

## Configuration

Add to your Silverbullet `CONFIG.md`:

```space-lua
-- Proposal storage location (default: _Proposals/)
config.set("mcp.proposals.path_prefix", "_Proposals/")

-- Auto-cleanup rejected proposals after N days (default: 30)
config.set("mcp.proposals.cleanup_after_days", 30)
```

## Silverbullet Features

### Top Banner Widget

When viewing a page with pending proposals, a banner appears at the top:

```
+----------------------------------------------------------+
| Pending proposals: Update project description            |
+----------------------------------------------------------+
```

Click the proposal link to review it.

### Proposal Dashboard

View all proposals in one place at `Library/AI-Proposals/Proposals`:

- **Pending Proposals**: Awaiting your review
- **Recently Accepted**: Successfully applied
- **Recently Rejected**: Dismissed proposals

### Proposal Editor

The `.proposal` file extension triggers a custom editor that shows:

1. **Header**: Title, target page, description, metadata
2. **New Page Banner**: Shows if this creates a new page
3. **Inline Diff**: Line-by-line comparison with additions/deletions highlighted
4. **Action Buttons**: Accept, Reject, View Target

### Automatic Cleanup

Rejected proposals are automatically cleaned up after the configured number of days (default: 30). This prevents clutter while giving you time to reconsider.

## Best Practices for AI Assistants

When using the proposal system:

1. **Be descriptive**: Write clear titles and descriptions so users understand the change
2. **Propose complete content**: Send the full page content, not just the diff
3. **Check for existing proposals**: Use `list_proposals` before creating duplicates
4. **Withdraw mistakes**: If you made an error, use `withdraw_proposal` to clean up

## Troubleshooting

### "AI-Proposals library not installed"

The MCP/gRPC server checks for `Library/AI-Proposals.md` in your space. Install the library using the Library Manager.

### Proposals not appearing

1. Check that the file was created in `_Proposals/`
2. Verify the file has `.proposal` extension
3. Check file permissions in the space directory

### Diff not rendering

The inline diff requires the proposal editor to load. If you see raw YAML, the plug may not be loaded. Try refreshing Silverbullet.
