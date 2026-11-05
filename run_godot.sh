#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v godot >/dev/null 2>&1; then
  echo "Godot 4.x was not found in PATH. Install Godot 4.3+ and run this script again."
  exit 1
fi
exec godot --path "$ROOT/godot"
