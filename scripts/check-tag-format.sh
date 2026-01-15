#!/bin/bash
# Validate that git tags follow the format X.Y.Z (no 'v' prefix)
# This script can be used as a pre-push hook or run manually

# Check tags being pushed
while read local_ref local_sha remote_ref remote_sha; do
    if [[ "$local_ref" == refs/tags/* ]]; then
        tag_name="${local_ref#refs/tags/}"
        # Check if tag starts with 'v' (which we don't want)
        if [[ "$tag_name" =~ ^v[0-9] ]]; then
            echo "ERROR: Tag '$tag_name' has 'v' prefix."
            echo "       This project uses tags without 'v' prefix (e.g., '0.6.0' not 'v0.6.0')"
            echo "       Please delete and recreate: git tag -d $tag_name && git tag ${tag_name#v}"
            exit 1
        fi
        # Check if tag follows semver format
        if ! [[ "$tag_name" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "WARNING: Tag '$tag_name' doesn't follow semver format (X.Y.Z)"
        fi
    fi
done

exit 0
