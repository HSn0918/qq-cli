#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/npm/bin"
ENTRY="$ROOT_DIR/scripts/pyinstaller_entry.py"

rm -rf "$ROOT_DIR/build" "$ROOT_DIR/dist"
mkdir -p "$OUT_DIR"

uv run --with pyinstaller --with-editable "$ROOT_DIR" pyinstaller \
  --clean \
  --noconfirm \
  --onefile \
  --name qq-cli \
  --paths "$ROOT_DIR" \
  --collect-all qq_cli \
  "$ENTRY"

cp "$ROOT_DIR/dist/qq-cli" "$OUT_DIR/qq-cli"
chmod +x "$OUT_DIR/qq-cli"
