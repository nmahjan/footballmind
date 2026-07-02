#!/usr/bin/env bash
# Delete stale cursor/critical-bug-investigation remote branches.
set -euo pipefail
git fetch origin --prune
git branch -r | grep 'origin/cursor/critical-bug-investigation' | sed 's|^[[:space:]]*origin/||' | while read -r b; do
  echo "Deleting origin/$b ..."
  gh api -X DELETE "repos/nmahjan/footballmind/git/refs/heads/$b"
done
echo "Done."
