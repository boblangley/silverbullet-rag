#!/bin/bash
# Install git hooks that need native git functionality
# (pre-commit framework doesn't pass stdin to local hooks)

HOOKS_DIR="$(git rev-parse --git-dir)/hooks"

# Create pre-push hook for tag format validation
cat > "$HOOKS_DIR/pre-push" << 'HOOK'
#!/bin/bash
# Pre-push hook: validate tag format (no 'v' prefix)
exec scripts/check-tag-format.sh
HOOK

chmod +x "$HOOKS_DIR/pre-push"
echo "Installed pre-push hook to $HOOKS_DIR/pre-push"
