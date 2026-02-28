#!/usr/bin/env bash
set -euo pipefail

TOOL_NAME="${1:?Usage: scaffold.sh <tool_name>}"
TOOLS_DIR="${HOME}/.ntrp/tools"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAFFOLD="${SCRIPT_DIR}/../assets/scaffold.py"
TARGET="${TOOLS_DIR}/${TOOL_NAME}.py"

if [[ -f "$TARGET" ]]; then
  echo "ERROR: ${TARGET} already exists" >&2
  exit 1
fi

mkdir -p "$TOOLS_DIR"
cp "$SCAFFOLD" "$TARGET"
echo "Created ${TARGET}"
