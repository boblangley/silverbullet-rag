#!/bin/bash
# Validate that git tags follow the format X.Y.Z (no 'v' prefix)
# and that library versions match the tag being pushed.
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

        # For semver tags, validate that library versions match
        if [[ "$tag_name" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            library_file="library/Proposals.md"

            # Get version from the committed file at the tag (not working directory)
            library_version=$(git show "$local_sha:$library_file" 2>/dev/null | grep -E "^version:" | head -1 | sed 's/version: *//')

            if [[ -z "$library_version" ]]; then
                echo "ERROR: Could not read version from $library_file at tag $tag_name"
                exit 1
            fi

            if [[ "$library_version" != "$tag_name" ]]; then
                echo "ERROR: $library_file version ($library_version) doesn't match tag ($tag_name)"
                echo ""
                echo "To fix, run:"
                echo "  sed -i 's/^version:.*/version: $tag_name/' $library_file"
                echo "  git add $library_file"
                echo "  git commit --amend --no-edit"
                echo "  git tag -f $tag_name"
                exit 1
            fi
        fi
    fi
done

exit 0
