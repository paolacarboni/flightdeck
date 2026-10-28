#!/usr/bin/env bash
# Installs flightdeck by symlinking each part from this checkout:
#   commands  -> ~/.local/bin
#   widgets   -> ~/Library/Application Support/Übersicht/widgets
#   menu bar  -> ~/Library/Application Support/xbar/plugins
#   /park     -> ~/.claude/commands
# Existing symlinks are replaced; real files are never overwritten.
# Usage: ./install.sh [all|cc-panel|focus-panel|news-panel|harlock-panel|harlock-bar]...
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
WIDGETS="$HOME/Library/Application Support/Übersicht/widgets"
XBAR="$HOME/Library/Application Support/xbar/plugins"
COMMANDS="$HOME/.claude/commands"

link() {
  local source="$1" target="$2"
  mkdir -p "$(dirname "$target")"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "skip  $target (exists and is not a symlink)" >&2
    return
  fi
  ln -sfn "$source" "$target"
  echo "link  $target -> $source"
}

install_part() {
  case "$1" in
    cc-panel)
      link "$ROOT/cc-panel/bin/cc-panel" "$BIN/cc-panel"
      link "$ROOT/cc-panel/commands/park.md" "$COMMANDS/park.md"
      link "$ROOT/cc-panel/widget" "$WIDGETS/cc-panel.widget"
      link "$ROOT/cc-panel/xbar/cc-panel.10s.sh" "$XBAR/cc-panel.10s.sh" ;;
    focus-panel)
      link "$ROOT/focus-panel/bin/focus-panel" "$BIN/focus-panel"
      link "$ROOT/focus-panel/widget" "$WIDGETS/focus-panel.widget" ;;
    news-panel)
      link "$ROOT/news-panel/bin/news-panel" "$BIN/news-panel"
      link "$ROOT/news-panel/widget" "$WIDGETS/news-panel.widget" ;;
    harlock-panel)
      link "$ROOT/harlock-panel/widget" "$WIDGETS/harlock-panel.widget" ;;
    harlock-bar)
      link "$ROOT/harlock-bar/xbar/harlock-bar.30s.sh" "$XBAR/harlock-bar.30s.sh" ;;
    *)
      echo "unknown part: $1" >&2
      exit 2 ;;
  esac
}

parts=("$@")
if [ ${#parts[@]} -eq 0 ] || [ "${parts[0]}" = "all" ]; then
  parts=(cc-panel focus-panel news-panel harlock-panel harlock-bar)
fi
for part in "${parts[@]}"; do
  install_part "$part"
done
