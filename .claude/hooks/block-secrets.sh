#!/usr/bin/env bash
set -euo pipefail

# Basic secret scanner for Claude hooks or manual use.
# This is intentionally conservative and should be expanded later.

TARGET_DIR="${1:-.}"

PATTERNS=(
  "NOTION_TOKEN"
  "OPENAI_API_KEY"
  "ANTHROPIC_API_KEY"
  "API_KEY"
  "SECRET"
  "PASSWORD"
  "BEGIN PRIVATE KEY"
)

for pattern in "${PATTERNS[@]}"; do
  if grep -RIn --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv --exclude='*.png' --exclude='*.jpg' "$pattern" "$TARGET_DIR" >/tmp/aulaforge_secret_scan.txt 2>/dev/null; then
    echo "Potential secret found for pattern: $pattern"
    cat /tmp/aulaforge_secret_scan.txt
    exit 1
  fi
done

echo "No obvious secrets found."
