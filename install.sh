#!/bin/bash
# Symlink `ntool` onto your PATH without Homebrew (dev / single-machine use).
# Usage: ./install.sh [target-dir]   (default: /usr/local/bin)
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-/usr/local/bin}"

if ! command -v mitmdump >/dev/null 2>&1; then
  echo "warning: mitmproxy not found — install it with: brew install --cask mitmproxy"
fi

mkdir -p "$TARGET" 2>/dev/null || true
if ln -sf "$DIR/bin/ntool" "$TARGET/ntool" 2>/dev/null; then
  echo "✓ linked $TARGET/ntool -> $DIR/bin/ntool"
else
  echo "could not write to $TARGET (try: sudo ./install.sh, or ./install.sh \$HOME/bin)"
  exit 1
fi

case ":$PATH:" in
  *":$TARGET:"*) : ;;
  *) echo "note: $TARGET is not on your PATH — add it to use \`ntool\` directly." ;;
esac
echo "next: ntool setup"
