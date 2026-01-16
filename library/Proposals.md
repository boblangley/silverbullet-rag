---
name: Library/Proposals
tags: meta/library
displayName: Proposals
description: Review and manage proposed changes to your Silverbullet space
author: silverbullet-rag
version: 0.12.0
files:
- Proposals/Proposals.plug.js
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
  local prefix = config.get("mcp.proposals.path_prefix", "_Proposals/")

  -- Check if a proposal exists for this page using predictable path
  -- Proposals are stored at: {prefix}{page_name}.md.proposal
  -- editor.getCurrentPage() returns "Folder/Page" without .md extension
  local proposal_path = prefix .. current .. ".md.proposal"

  -- Try to fetch the proposal file directly (works even without sync)
  local ok, content = pcall(function()
    return space.readDocument(proposal_path)
  end)

  if not ok or not content then
    return {}
  end

  -- Parse frontmatter to check status
  local content_str = string.char(table.unpack(content))
  local status = content_str:match("status:%s*(%w+)")

  if status ~= "pending" then
    return {}
  end

  -- Extract title from frontmatter
  local title = content_str:match("title:%s*([^\n]+)") or "View Proposal"

  return {
    {
      html = "<div style='background:#fef3c7;padding:8px 12px;border-bottom:1px solid #f59e0b'>"
           .. "📋 <strong>Pending proposal:</strong> "
           .. "[[" .. proposal_path .. "|" .. title .. "]]"
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
    editor.navigate("Proposals:")
  end
}
```

## Virtual Dashboard Page

```space-lua
-- Helper function to parse frontmatter from proposal content
local function parse_proposal(content_bytes)
  local content = string.char(table.unpack(content_bytes))
  local fm = {}

  fm.status = content:match("status:%s*([^\n]+)") or "pending"
  fm.title = content:match("title:%s*([^\n]+)") or "Untitled"
  fm.target_page = content:match("target_page:%s*([^\n]+)")
  fm.description = content:match("description:%s*([^\n]+)")
  fm.created_at = content:match("created_at:%s*([^\n]+)")

  -- Trim whitespace
  for k, v in pairs(fm) do
    if type(v) == "string" then
      fm[k] = v:match("^%s*(.-)%s*$")
    end
  end

  return fm
end

-- Virtual page for the proposals dashboard
virtualPage.define {
  pattern = "Proposals:",
  run = function()
    -- Fetch all proposals from server
    local documents = space.listDocuments()
    local proposals = {}

    for _, doc in ipairs(documents) do
      if doc.name:match("%.proposal$") then
        local ok, content = pcall(function()
          return space.readDocument(doc.name)
        end)

        if ok and content then
          local fm = parse_proposal(content)
          fm.name = doc.name
          table.insert(proposals, fm)
        end
      end
    end

    -- Sort by created_at descending
    table.sort(proposals, function(a, b)
      return (a.created_at or "") > (b.created_at or "")
    end)

    -- Build page content
    local text = "# 📋 Proposals Dashboard\n\n"

    -- Pending section
    text = text .. "## Pending\n\n"
    text = text .. "| Proposal | Target | Created |\n"
    text = text .. "|----------|--------|--------|\n"
    local pending_count = 0
    for _, p in ipairs(proposals) do
      if p.status == "pending" then
        local target = (p.target_page or "Unknown"):gsub("%.md$", "")
        text = text .. "| [[" .. p.name .. "|" .. p.title .. "]] | [[" .. target .. "]] | " .. (p.created_at or "") .. " |\n"
        pending_count = pending_count + 1
      end
    end
    if pending_count == 0 then
      text = text .. "| _No pending proposals_ | | |\n"
    end

    -- Accepted section
    text = text .. "\n## Recently Accepted\n\n"
    text = text .. "| Proposal | Target | Created |\n"
    text = text .. "|----------|--------|--------|\n"
    local accepted_count = 0
    for _, p in ipairs(proposals) do
      if p.status == "accepted" and accepted_count < 10 then
        local target = (p.target_page or "Unknown"):gsub("%.md$", "")
        text = text .. "| [[" .. p.name .. "|" .. p.title .. "]] | [[" .. target .. "]] | " .. (p.created_at or "") .. " |\n"
        accepted_count = accepted_count + 1
      end
    end
    if accepted_count == 0 then
      text = text .. "| _No accepted proposals_ | | |\n"
    end

    -- Rejected section
    text = text .. "\n## Recently Rejected\n\n"
    text = text .. "| Proposal | Target | Created |\n"
    text = text .. "|----------|--------|--------|\n"
    local rejected_count = 0
    for _, p in ipairs(proposals) do
      if p.status == "rejected" and rejected_count < 10 then
        local target = (p.target_page or "Unknown"):gsub("%.md$", "")
        text = text .. "| [[" .. p.name .. "|" .. p.title .. "]] | [[" .. target .. "]] | " .. (p.created_at or "") .. " |\n"
        rejected_count = rejected_count + 1
      end
    end
    if rejected_count == 0 then
      text = text .. "| _No rejected proposals_ | | |\n"
    end

    return text
  end
}
```

## Cleanup Cron Job

```space-lua
-- Track last cleanup time
local last_cleanup = os.time()
local CLEANUP_INTERVAL = 3600  -- Check once per hour

-- Helper to parse ISO date string to timestamp
local function parse_iso_date(date_str)
  if not date_str then return nil end
  -- Parse ISO 8601 format: 2024-01-15T10:30:00Z or 2024-01-15T10:30:00.000Z
  local year, month, day, hour, min, sec = date_str:match("(%d+)-(%d+)-(%d+)T(%d+):(%d+):(%d+)")
  if year then
    return os.time({
      year = tonumber(year),
      month = tonumber(month),
      day = tonumber(day),
      hour = tonumber(hour),
      min = tonumber(min),
      sec = tonumber(sec)
    })
  end
  return nil
end

event.listen("cron:secondPassed", function()
  local now = os.time()
  if now - last_cleanup < CLEANUP_INTERVAL then
    return
  end
  last_cleanup = now

  -- Get cleanup config (default 30 days)
  local cleanup_days = config.get("mcp.proposals.cleanup_after_days", 30)
  local cutoff = now - (cleanup_days * 24 * 60 * 60)

  -- Find old rejected proposals using direct server fetch
  local documents = space.listDocuments()

  for _, doc in ipairs(documents) do
    -- Only process rejected proposals
    if doc.name:match("^_Proposals/_Rejected/.*%.proposal$") then
      local ok, content = pcall(function()
        return space.readDocument(doc.name)
      end)

      if ok and content then
        local content_str = string.char(table.unpack(content))
        local created_at = content_str:match("created_at:%s*([^\n]+)")

        if created_at then
          -- Trim whitespace
          created_at = created_at:match("^%s*(.-)%s*$")
          local created_ts = parse_iso_date(created_at)

          if created_ts and created_ts < cutoff then
            space.deleteDocument(doc.name)
          end
        end
      end
    end
  end
end)
```

## See Also

- [[Proposals:]] - View all proposals (virtual page)
