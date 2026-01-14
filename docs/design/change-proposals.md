# Change Proposal System Design

## Problem Statement

The current `update_page` tool writes directly to the Silverbullet space filesystem. This is problematic for a personal knowledge base because:

1. **No review process** - AI modifies notes without oversight
2. **No undo mechanism** - Changes are immediate and permanent
3. **No context** - User doesn't see what changed or why
4. **Trust concerns** - Personal notes are sensitive data

## Goals

- AI can propose changes to the space
- User reviews and approves changes before they're applied
- Full history and rollback capability
- Familiar workflow (git/GitHub PRs)
- Minimal friction for small changes

## Prerequisite

**The Silverbullet space MUST be a git repository** for write tools to be available.

If the space is not a git repo, the MCP server will:
- Expose all read/search tools normally
- Return an error for write tools explaining the requirement
- Optionally provide a `get_write_setup_instructions` tool with guidance

## Proposed Solution: Git Branch + PR Workflow

### Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   AI Assistant  │────▶│  MCP Server     │────▶│  Git Worktree   │
│  (Claude, etc)  │     │  propose_change │     │  (proposals/)   │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │  GitHub/GitLab  │
                                                │  Pull Request   │
                                                └────────┬────────┘
                                                         │
                                                         ▼ (merge)
                                                ┌─────────────────┐
                                                │  Main Space     │
                                                │  (production)   │
                                                └─────────────────┘
```

### Space Setup Requirements

The Silverbullet space needs to be a git repository:

```bash
# One-time setup
cd /path/to/space
git init
git remote add origin git@github.com:user/silverbullet-space.git
git add .
git commit -m "Initial commit"
git push -u origin main
```

The MCP server container needs:
- Git installed
- SSH key or token for pushing to remote
- Write access to a worktree directory (separate from read-only space mount)

### Worktree Strategy

Use git worktrees to isolate proposal branches:

```
/space/              # Main space (read-only mount, main branch)
/proposals/          # Worktree directory for proposal branches
  └── proposal-123/  # Each proposal gets its own worktree
```

### New MCP Tools

#### 1. `propose_change`

Create a proposal for modifying or creating a page.

```python
@mcp.tool()
async def propose_change(
    page_name: str,
    content: str,
    title: str,
    description: str,
    change_type: Literal["create", "update", "delete"] = "update"
) -> Dict[str, Any]:
    """
    Propose a change to a Silverbullet page.

    Creates a git branch, commits the change, and opens a PR.
    The change is NOT applied until the user merges the PR.

    Args:
        page_name: Page path (e.g., 'Projects/MyProject.md')
        content: New page content (for create/update)
        title: Short title for the proposal (becomes PR title)
        description: Explanation of why this change is proposed
        change_type: Type of change (create, update, delete)

    Returns:
        Proposal ID, branch name, and PR URL
    """
```

#### 2. `list_proposals`

List open change proposals.

```python
@mcp.tool()
async def list_proposals(
    status: Literal["open", "merged", "closed", "all"] = "open"
) -> Dict[str, Any]:
    """
    List change proposals (PRs) for the space.

    Args:
        status: Filter by PR status

    Returns:
        List of proposals with ID, title, status, and URL
    """
```

#### 3. `get_proposal`

Get details of a specific proposal.

```python
@mcp.tool()
async def get_proposal(proposal_id: str) -> Dict[str, Any]:
    """
    Get details of a change proposal including the diff.

    Args:
        proposal_id: The proposal/PR identifier

    Returns:
        Proposal details, diff, and current status
    """
```

#### 4. `withdraw_proposal`

Close/withdraw a proposal without merging.

```python
@mcp.tool()
async def withdraw_proposal(
    proposal_id: str,
    reason: str
) -> Dict[str, Any]:
    """
    Withdraw/close a change proposal.

    Args:
        proposal_id: The proposal to withdraw
        reason: Why the proposal is being withdrawn

    Returns:
        Success confirmation
    """
```

### Implementation Considerations

#### Git Operations

Use `gitpython` or shell out to git CLI:

```python
import git

def create_proposal_branch(space_repo: git.Repo, proposal_id: str) -> str:
    branch_name = f"ai-proposal/{proposal_id}"
    space_repo.create_head(branch_name)
    return branch_name
```

#### GitHub API Integration

Use `PyGithub` or `gh` CLI for PR operations:

```python
from github import Github

def create_pull_request(repo_name: str, branch: str, title: str, body: str) -> str:
    g = Github(os.getenv("GITHUB_TOKEN"))
    repo = g.get_repo(repo_name)
    pr = repo.create_pull(
        title=title,
        body=body,
        head=branch,
        base="main"
    )
    return pr.html_url
```

#### Proposal Metadata

Store proposal metadata in the database or as JSON files:

```json
{
    "id": "proposal-2024-01-15-001",
    "branch": "ai-proposal/proposal-2024-01-15-001",
    "pr_number": 42,
    "pr_url": "https://github.com/user/space/pull/42",
    "page_name": "Projects/MyProject.md",
    "change_type": "update",
    "title": "Add implementation notes",
    "description": "Added notes from our discussion about...",
    "created_at": "2024-01-15T10:30:00Z",
    "status": "open"
}
```

### Alternative: Simpler Staging Approach

If full git/PR workflow is too heavy, consider a simpler staging area:

```python
@mcp.tool()
async def propose_change(page_name: str, content: str, reason: str):
    """
    Stage a proposed change in _ai_proposals/ folder.

    Creates a file like: _ai_proposals/2024-01-15-001-Projects-MyProject.md
    With frontmatter containing the original path and reason.
    """
    proposal_path = f"_ai_proposals/{proposal_id}-{safe_name}.md"
    proposal_content = f"""---
original_path: {page_name}
proposed_by: ai
reason: {reason}
created: {datetime.now().isoformat()}
---
{content}
"""
```

User can then review in Silverbullet and manually move/merge.

### Security Considerations

1. **Path traversal** - Validate page_name stays within space
2. **Content injection** - Sanitize content for git commit messages
3. **Rate limiting** - Prevent AI from creating excessive proposals
4. **Token security** - GitHub token needs minimal permissions (repo write)

---

## Git Provider Abstraction

Support multiple git hosting providers through a common interface:

### Provider Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class PullRequest:
    id: str
    number: int
    url: str
    title: str
    description: str
    branch: str
    status: str  # open, merged, closed
    created_at: str

class GitProvider(ABC):
    """Abstract interface for git hosting providers."""

    @abstractmethod
    async def create_pull_request(
        self,
        branch: str,
        title: str,
        body: str,
        base: str = "main"
    ) -> PullRequest:
        """Create a pull/merge request."""
        pass

    @abstractmethod
    async def list_pull_requests(
        self,
        status: str = "open"
    ) -> List[PullRequest]:
        """List pull/merge requests."""
        pass

    @abstractmethod
    async def get_pull_request(self, pr_id: str) -> PullRequest:
        """Get details of a specific PR."""
        pass

    @abstractmethod
    async def close_pull_request(self, pr_id: str, reason: str) -> bool:
        """Close/withdraw a PR without merging."""
        pass
```

### Provider Implementations

```
server/
  git_providers/
    __init__.py
    base.py          # GitProvider ABC
    github.py        # GitHub/GitHub Enterprise
    gitlab.py        # GitLab (cloud and self-hosted)
    gitea.py         # Gitea/Forgejo
    bitbucket.py     # Bitbucket (future)
```

### Auto-Detection

Detect provider from git remote URL:

```python
def detect_provider(remote_url: str) -> str:
    """Detect git provider from remote URL."""
    if "github.com" in remote_url or os.getenv("GITHUB_API_URL"):
        return "github"
    elif "gitlab.com" in remote_url or os.getenv("GITLAB_URL"):
        return "gitlab"
    elif "gitea" in remote_url or os.getenv("GITEA_URL"):
        return "gitea"
    elif "bitbucket" in remote_url:
        return "bitbucket"
    else:
        return "unknown"
```

### Configuration

```yaml
# Environment variables for provider configuration
SPACE_GIT_PROVIDER: github  # auto, github, gitlab, gitea, bitbucket

# GitHub (supports GitHub App auth via github-app-auth-container)
GITHUB_AUTH_SERVICE: http://github-auth-service:8080
AGENT_NAME: silverbullet-rag
AGENT_TOKEN: <pre-signed-token>
# OR traditional token auth:
GITHUB_TOKEN: ghp_xxxxx

# GitLab
GITLAB_URL: https://gitlab.com
GITLAB_TOKEN: glpat-xxxxx

# Gitea
GITEA_URL: https://gitea.example.com
GITEA_TOKEN: xxxxx
```

---

## GitHub App Authentication Integration

For production deployments, integrate with [github-app-auth-container](https://github.com/boblangley/github-app-auth-container) for:

- **Proper attribution** - Commits show as coming from the AI agent's GitHub App identity
- **Scoped tokens** - Request only the permissions needed
- **Signed commits** - SSH signing for verified commits
- **No long-lived tokens** - Installation tokens are short-lived and auto-refreshed

### Container Setup

```yaml
services:
  github-auth-service:
    image: ghcr.io/boblangley/github-app-auth-container:latest
    environment:
      - BW_SESSION=${BW_SESSION}
      - BW_COLLECTION_ID=${BW_COLLECTION_ID}
    networks:
      - agent-network

  silverbullet-rag:
    image: ghcr.io/boblangley/silverbullet-rag:latest
    environment:
      - GITHUB_AUTH_SERVICE=http://github-auth-service:8080
      - AGENT_NAME=silverbullet-rag
      - AGENT_TOKEN=${SILVERBULLET_RAG_AGENT_TOKEN}
      - SPACE_PATH=/space
      - DB_PATH=/data/rag.lbug
    volumes:
      - silverbullet-space:/space
      - rag-db:/data
    networks:
      - agent-network
```

### Git Configuration in Container

```dockerfile
FROM ghcr.io/boblangley/github-app-auth-container-helpers:latest AS helpers

FROM python:3.12-slim
COPY --from=helpers /usr/local/bin/git-* /usr/local/bin/

RUN apt-get update && apt-get install -y git && \
    git config --system credential.helper github-app && \
    git config --system gpg.format ssh && \
    git config --system gpg.ssh.program git-ssh-sign && \
    git config --system commit.gpgsign true
```

---

## Local Diff Workflow (Alternative)

For users who don't want PR-based workflows, or for local-only setups:

### Concept

1. AI writes proposed changes to a local worktree/branch
2. Generate unified diff files
3. Open diff in IDE (VSCode, etc.) for review
4. User applies or discards

### Implementation

```python
@mcp.tool()
async def propose_change_local(
    page_name: str,
    content: str,
    title: str,
    description: str,
) -> Dict[str, Any]:
    """
    Create a local proposal with diff file for IDE review.

    Returns:
        - proposal_id
        - diff_file_path (can be opened in VSCode diff viewer)
        - instructions for applying
    """
    proposal_id = generate_proposal_id()

    # Create proposal branch in worktree
    worktree_path = create_worktree(proposal_id)

    # Write the proposed content
    proposed_file = worktree_path / page_name
    proposed_file.parent.mkdir(parents=True, exist_ok=True)
    proposed_file.write_text(content)

    # Generate diff
    original_file = space_path / page_name
    diff_content = generate_unified_diff(original_file, proposed_file, page_name)

    # Write diff to temp location
    diff_file = Path(f"/tmp/proposals/{proposal_id}.diff")
    diff_file.parent.mkdir(parents=True, exist_ok=True)
    diff_file.write_text(diff_content)

    # Also write metadata
    metadata = {
        "id": proposal_id,
        "title": title,
        "description": description,
        "page_name": page_name,
        "original_path": str(original_file),
        "proposed_path": str(proposed_file),
        "diff_path": str(diff_file),
        "created_at": datetime.now().isoformat(),
    }

    return {
        "success": True,
        "proposal_id": proposal_id,
        "diff_file": str(diff_file),
        "view_command": f"code --diff {original_file} {proposed_file}",
        "apply_command": f"git apply {diff_file}",
        "metadata": metadata,
    }
```

### VSCode Integration

The returned `view_command` can be run to open VSCode's diff viewer:

```bash
code --diff /space/Projects/MyProject.md /tmp/proposals/abc123/Projects/MyProject.md
```

Or users could install a simple VSCode extension that:
1. Watches `/tmp/proposals/` for new diffs
2. Shows a notification with "Review Proposal" button
3. Opens the diff view automatically

### Applying/Discarding

```python
@mcp.tool()
async def apply_proposal(proposal_id: str) -> Dict[str, Any]:
    """Apply a local proposal to the main space."""
    # Read metadata
    metadata = load_proposal_metadata(proposal_id)

    # Copy proposed file to space
    shutil.copy(metadata["proposed_path"], metadata["original_path"])

    # Commit if space is git repo
    if is_git_repo(space_path):
        repo = git.Repo(space_path)
        repo.index.add([metadata["page_name"]])
        repo.index.commit(f"{metadata['title']}\n\n{metadata['description']}")

    # Cleanup
    cleanup_proposal(proposal_id)

    return {"success": True, "message": f"Applied proposal {proposal_id}"}

@mcp.tool()
async def discard_proposal(proposal_id: str) -> Dict[str, Any]:
    """Discard a local proposal without applying."""
    cleanup_proposal(proposal_id)
    return {"success": True, "message": f"Discarded proposal {proposal_id}"}
```

---

## Safe Write Patterns

For users who want some direct writes without full PR workflow:

### Configuration

```yaml
# Environment variable or config file
SAFE_WRITE_PATTERNS:
  - "_inbox/**"           # AI can write directly to inbox
  - "_ai_notes/**"        # Dedicated AI notes folder
  - "Journal/AI/**"       # AI journal entries
  - "**/_ai_*.md"         # Any file prefixed with _ai_
```

### Implementation

```python
import fnmatch

def is_safe_write_path(page_name: str, patterns: List[str]) -> bool:
    """Check if path matches safe write patterns."""
    for pattern in patterns:
        if fnmatch.fnmatch(page_name, pattern):
            return True
    return False

@mcp.tool()
async def update_page(page_name: str, content: str) -> Dict[str, Any]:
    """
    Update a page - either directly (if safe path) or via proposal.
    """
    safe_patterns = get_safe_write_patterns()

    if is_safe_write_path(page_name, safe_patterns):
        # Direct write allowed
        return await direct_write(page_name, content)
    else:
        # Must go through proposal workflow
        return {
            "success": False,
            "error": "Direct writes not allowed to this path",
            "suggestion": "Use propose_change() instead, or write to a safe path like _inbox/",
            "safe_patterns": safe_patterns,
        }
```

### Append-Only Mode

Some paths could be append-only (AI can add but not modify):

```python
APPEND_ONLY_PATTERNS:
  - "Journal/**"          # Can append entries, not modify
  - "Logs/**"             # Append-only logs
```

```python
@mcp.tool()
async def append_to_page(
    page_name: str,
    content: str,
    position: Literal["top", "bottom"] = "bottom"
) -> Dict[str, Any]:
    """
    Append content to a page (for append-only paths).
    """
    if not is_append_allowed(page_name):
        return {"success": False, "error": "Append not allowed to this path"}

    existing = read_page(page_name)
    if position == "bottom":
        new_content = existing + "\n\n" + content
    else:
        new_content = content + "\n\n" + existing

    return await direct_write(page_name, new_content)
```

---

## Summary: Write Tool Availability

| Scenario | Tools Available |
|----------|-----------------|
| Space is not a git repo | Read/search only. Write tools return error with setup instructions. |
| Git repo, no remote configured | Local proposals with diff files. No PR workflow. |
| Git repo with GitHub remote | Full PR workflow via GitHub API/App |
| Git repo with GitLab/Gitea remote | Full PR workflow via respective API |
| Safe write patterns configured | Direct writes to matching paths |
| Append-only patterns configured | `append_to_page` for matching paths |

---

## Next Steps

1. [ ] Implement git repo detection on startup
2. [ ] Create `GitProvider` abstraction and GitHub implementation
3. [ ] Add github-app-auth-container integration
4. [ ] Implement `propose_change` tool (PR-based)
5. [ ] Implement local diff workflow as fallback
6. [ ] Add safe write pattern configuration
7. [ ] Test end-to-end workflows
8. [ ] Add GitLab/Gitea providers (can be community contributed)
9. [ ] Documentation and examples
