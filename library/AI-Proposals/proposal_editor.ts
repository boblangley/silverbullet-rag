/**
 * Document Editor for .proposal files
 *
 * Renders an inline diff view showing the proposed changes compared to the
 * original page content. Provides Accept/Reject buttons for user action.
 */

export async function editor(): Promise<{ html: string }> {
  return {
    html: `
<!DOCTYPE html>
<html>
<head>
  <style>
    * {
      box-sizing: border-box;
    }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, sans-serif;
      background: var(--root-background, #fff);
      color: var(--root-color, #333);
      line-height: 1.5;
    }
    .header {
      padding: 16px;
      border-bottom: 1px solid var(--ui-border, #ddd);
      background: var(--ui-background, #f8f9fa);
    }
    .title {
      font-size: 18px;
      font-weight: bold;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .title-icon {
      font-size: 24px;
    }
    .target {
      color: var(--text-secondary, #666);
      font-size: 14px;
    }
    .target a {
      color: var(--link-color, #0066cc);
      text-decoration: none;
    }
    .target a:hover {
      text-decoration: underline;
    }
    .description {
      margin-top: 8px;
      font-style: italic;
      color: var(--text-secondary, #666);
    }
    .metadata {
      margin-top: 8px;
      font-size: 12px;
      color: var(--text-muted, #999);
    }
    .new-page-banner {
      background: #dbeafe;
      color: #1e40af;
      padding: 8px 16px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .diff {
      font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
      font-size: 13px;
      padding: 16px;
      white-space: pre-wrap;
      word-wrap: break-word;
      line-height: 1.6;
      overflow-x: auto;
    }
    .diff-line {
      padding: 2px 8px;
      margin: 0 -8px;
    }
    .diff-add {
      background: #dcfce7;
      color: #166534;
    }
    .diff-add::before {
      content: "+ ";
      font-weight: bold;
    }
    .diff-del {
      background: #fee2e2;
      color: #991b1b;
      text-decoration: line-through;
    }
    .diff-del::before {
      content: "- ";
      font-weight: bold;
    }
    .diff-context {
      color: var(--text-secondary, #666);
    }
    .diff-context::before {
      content: "  ";
    }
    .diff-separator {
      color: var(--text-muted, #999);
      background: var(--ui-background, #f8f9fa);
      padding: 4px 8px;
      margin: 8px -8px;
      font-style: italic;
    }
    .actions {
      padding: 16px;
      border-top: 1px solid var(--ui-border, #ddd);
      display: flex;
      gap: 12px;
      background: var(--ui-background, #f8f9fa);
      position: sticky;
      bottom: 0;
    }
    .btn {
      padding: 10px 24px;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: background-color 0.15s, transform 0.1s;
    }
    .btn:hover {
      transform: translateY(-1px);
    }
    .btn:active {
      transform: translateY(0);
    }
    .btn-accept {
      background: #22c55e;
      color: white;
    }
    .btn-accept:hover {
      background: #16a34a;
    }
    .btn-reject {
      background: #ef4444;
      color: white;
    }
    .btn-reject:hover {
      background: #dc2626;
    }
    .btn-view {
      background: var(--ui-background-secondary, #e5e7eb);
      color: var(--text-color, #333);
    }
    .btn-view:hover {
      background: var(--ui-background-tertiary, #d1d5db);
    }
    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 40px;
      color: var(--text-secondary, #666);
    }
    .error {
      padding: 16px;
      background: #fee2e2;
      color: #991b1b;
      border-radius: 6px;
      margin: 16px;
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="title">
      <span class="title-icon">📋</span>
      <span id="title">Loading...</span>
    </div>
    <div class="target">Target: <a href="#" id="target-link"><span id="target"></span></a></div>
    <div class="description" id="description"></div>
    <div class="metadata">
      <span id="proposed-by"></span> • <span id="created-at"></span>
    </div>
  </div>
  <div id="new-page-banner" class="new-page-banner" style="display:none">
    🆕 NEW PAGE - This will create a new page
  </div>
  <div id="content">
    <div class="loading">Loading proposal...</div>
  </div>
  <div class="actions">
    <button class="btn btn-accept" onclick="acceptProposal()">✓ Accept</button>
    <button class="btn btn-reject" onclick="rejectProposal()">✗ Reject</button>
    <button class="btn btn-view" onclick="viewTarget()">👁 View Target</button>
  </div>

  <script>
    let meta = {};
    let proposedContent = '';
    let originalContent = '';

    window.silverbullet.addEventListener("file-open", async (event) => {
      try {
        const decoder = new TextDecoder();
        const content = decoder.decode(event.detail.data);

        // Parse frontmatter
        const match = content.match(/^---\\n([\\s\\S]*?)\\n---\\n([\\s\\S]*)$/);
        if (!match) {
          showError('Invalid proposal file format');
          return;
        }

        const [, frontmatter, body] = match;
        meta = parseFrontmatter(frontmatter);
        proposedContent = body.trim();

        // Update UI
        document.getElementById('title').textContent = meta.title || 'Untitled Proposal';
        document.getElementById('target').textContent = meta.target_page || 'Unknown';
        document.getElementById('target-link').href = '#';
        document.getElementById('description').textContent = meta.description || '';
        document.getElementById('proposed-by').textContent = 'Proposed by: ' + (meta.proposed_by || 'Unknown');
        document.getElementById('created-at').textContent = formatDate(meta.created_at);

        if (meta.is_new_page === 'true' || meta.is_new_page === true) {
          document.getElementById('new-page-banner').style.display = 'flex';
          showNewPageContent();
        } else {
          // Fetch original and render diff
          try {
            originalContent = await window.silverbullet.syscall('space.readPage', meta.target_page);
            renderInlineDiff();
          } catch (e) {
            // Page might not exist (was deleted since proposal created)
            document.getElementById('new-page-banner').style.display = 'flex';
            document.getElementById('new-page-banner').innerHTML =
              '⚠️ Original page not found - will create as new page';
            showNewPageContent();
          }
        }
      } catch (e) {
        showError('Failed to load proposal: ' + e.message);
      }
    });

    function parseFrontmatter(yaml) {
      const meta = {};
      yaml.split('\\n').forEach(line => {
        const idx = line.indexOf(':');
        if (idx > 0) {
          const key = line.slice(0, idx).trim();
          let value = line.slice(idx + 1).trim();
          // Remove quotes if present
          if ((value.startsWith('"') && value.endsWith('"')) ||
              (value.startsWith("'") && value.endsWith("'"))) {
            value = value.slice(1, -1);
          }
          meta[key] = value;
        }
      });
      return meta;
    }

    function formatDate(isoString) {
      if (!isoString) return '';
      try {
        const date = new Date(isoString);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
      } catch {
        return isoString;
      }
    }

    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }

    function showError(message) {
      document.getElementById('content').innerHTML =
        '<div class="error">' + escapeHtml(message) + '</div>';
    }

    function showNewPageContent() {
      document.getElementById('content').innerHTML =
        '<div class="diff">' + escapeHtml(proposedContent) + '</div>';
    }

    function renderInlineDiff() {
      const origLines = originalContent.split('\\n');
      const propLines = proposedContent.split('\\n');

      // Use a simple LCS-based diff algorithm
      const diff = computeDiff(origLines, propLines);

      let html = '<div class="diff">';
      for (const line of diff) {
        const escapedText = escapeHtml(line.text);
        if (line.type === 'add') {
          html += '<div class="diff-line diff-add">' + escapedText + '</div>';
        } else if (line.type === 'del') {
          html += '<div class="diff-line diff-del">' + escapedText + '</div>';
        } else {
          html += '<div class="diff-line diff-context">' + escapedText + '</div>';
        }
      }
      html += '</div>';

      document.getElementById('content').innerHTML = html;
    }

    function computeDiff(orig, prop) {
      // Simple line-by-line diff using longest common subsequence approach
      const result = [];
      const origSet = new Set(orig);
      const propSet = new Set(prop);

      let i = 0, j = 0;

      while (i < orig.length || j < prop.length) {
        if (i < orig.length && j < prop.length && orig[i] === prop[j]) {
          // Lines match
          result.push({ type: 'context', text: orig[i] });
          i++;
          j++;
        } else if (i < orig.length && !propSet.has(orig[i])) {
          // Line only in original (deleted)
          result.push({ type: 'del', text: orig[i] });
          i++;
        } else if (j < prop.length && !origSet.has(prop[j])) {
          // Line only in proposed (added)
          result.push({ type: 'add', text: prop[j] });
          j++;
        } else if (i < orig.length) {
          // Line in original but moved
          result.push({ type: 'del', text: orig[i] });
          i++;
        } else {
          // Line in proposed but moved
          result.push({ type: 'add', text: prop[j] });
          j++;
        }
      }

      return result;
    }

    async function acceptProposal() {
      if (!confirm('Apply this proposal to ' + meta.target_page + '?')) return;

      try {
        // Write proposed content to target page
        await window.silverbullet.syscall('space.writePage', meta.target_page, proposedContent);

        // Delete the proposal file (it's been applied)
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

        // Read current content, update status, write to new location
        const content = await window.silverbullet.syscall('space.readPage', currentPage);
        const updatedContent = content.replace(/status: pending/, 'status: rejected');

        await window.silverbullet.syscall('space.writePage', rejectedPath, updatedContent);
        await window.silverbullet.syscall('space.deletePage', currentPage);

        alert('Proposal rejected. It will be cleaned up automatically.');
        await window.silverbullet.syscall('editor.navigate', 'Library/AI-Proposals/Proposals');
      } catch (e) {
        alert('Failed to reject proposal: ' + e.message);
      }
    }

    async function viewTarget() {
      if (meta.target_page) {
        try {
          await window.silverbullet.syscall('editor.navigate', meta.target_page);
        } catch (e) {
          alert('Could not navigate: ' + e.message);
        }
      }
    }
  </script>
</body>
</html>
    `
  };
}
