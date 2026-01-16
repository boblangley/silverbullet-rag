#!/bin/sh
set -e

SPACE_PATH="${SPACE_PATH:-/space}"

# Detect the uid/gid of the space folder
if [ -d "$SPACE_PATH" ]; then
    SPACE_UID=$(stat -c '%u' "$SPACE_PATH")
    SPACE_GID=$(stat -c '%g' "$SPACE_PATH")

    # If space is owned by non-root, run as that user
    if [ "$SPACE_UID" != "0" ]; then
        echo "Space folder owned by uid:gid $SPACE_UID:$SPACE_GID, running as that user"

        # Create a user with matching uid/gid if it doesn't exist
        if ! getent passwd "$SPACE_UID" > /dev/null 2>&1; then
            addgroup --gid "$SPACE_GID" --system appgroup 2>/dev/null || true
            adduser --uid "$SPACE_UID" --gid "$SPACE_GID" --system --no-create-home appuser 2>/dev/null || true
        fi

        # Ensure /data directory is writable by the app user
        if [ -d "/data" ]; then
            chown -R "$SPACE_UID:$SPACE_GID" /data 2>/dev/null || true
        fi

        # Execute as the space owner
        exec gosu "$SPACE_UID:$SPACE_GID" "$@"
    fi
fi

# Fall back to running as current user (root)
echo "Running as root (space folder owned by root or not found)"
exec "$@"
