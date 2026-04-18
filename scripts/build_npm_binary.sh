#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/npm/bin"
ENTRY="$ROOT_DIR/scripts/pyinstaller_entry.py"

rm -rf "$ROOT_DIR/build" "$ROOT_DIR/dist"
mkdir -p "$OUT_DIR"

# PyInstaller needs the package directory named qq_cli, not src
ln -sfn "$ROOT_DIR/src" "$ROOT_DIR/qq_cli"

uv run --with pyinstaller --with-editable "$ROOT_DIR" pyinstaller \
  --clean \
  --noconfirm \
  --onefile \
  --name qq-cli \
  --paths "$ROOT_DIR" \
  --collect-all qq_cli \
  "$ENTRY"

rm -f "$ROOT_DIR/qq_cli"

cp "$ROOT_DIR/dist/qq-cli" "$OUT_DIR/qq-cli"
chmod +x "$OUT_DIR/qq-cli"
