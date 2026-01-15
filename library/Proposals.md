---
displayName: Proposals
description: Review and manage proposed changes to your Silverbullet space
author: silverbullet-rag
version: 0.9.0
---

# Proposals Library

This library enables external tools to propose changes to your Silverbullet space.
You can review, accept, or reject these proposals before they modify your content.

## Features

- **Proposal Review**: View inline diffs of proposed changes
- **Accept/Reject**: Apply or dismiss proposals with one click
- **Top Banner**: See pending proposals for the current page
- **Proposal Dashboard**: View all proposals in one place

## Configuration

Add to your `CONFIG.md`:

```space-lua
-- Proposal storage location (default: _Proposals/)
config.set("mcp.proposals.path_prefix", "_Proposals/")

-- Auto-cleanup rejected proposals after N days (default: 30)
config.set("mcp.proposals.cleanup_after_days", 30)
```

## Commands

- **Proposals: View All** - Navigate to the proposals dashboard

## Top Widget

```space-lua
-- Show banner when current page has pending proposals
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

## Command Definition

```space-lua
command.define {
  name = "Proposals: View All",
  run = function()
    editor.navigate("Library/Proposals/Proposals")
  end
}
```

## Cleanup Cron Job

```space-lua
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

## See Also

- [[Library/Proposals/Proposals]] - View all proposals
