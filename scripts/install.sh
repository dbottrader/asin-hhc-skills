#!/usr/bin/env bash
# install.sh — install the ASIN-HHC agent-network skill pack into ~/.claude/skills
#
# Adapted from the manifest installer in elementalsouls/Claude-BugHunter (MIT):
# https://github.com/elementalsouls/Claude-BugHunter/blob/main/scripts/install.sh
#
#   bash scripts/install.sh
#       Copy skills/* to ~/.claude/skills and write
#       ~/.claude/.skill-manifests/asinhhc-agent-network.txt
#   bash scripts/install.sh --no-shell
#       Same install. This pack never edits shell startup files; the flag
#       is accepted so the contract matches the Claude-BugHunter installer.
#   bash scripts/install.sh --uninstall
#       Remove only the paths this pack's manifest lists. A skill still
#       listed in another bundle's manifest is kept.
#   bash scripts/install.sh --help
#
# Idempotent. An existing skill directory that differs is moved to
# ~/.claude/install-backups/<timestamp>/ before it is replaced, outside
# Claude's skill loading path.
# ===
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${HOME:?HOME is not set}"

BUNDLE_NAME="asinhhc-agent-network"
MANIFEST_DIR="$HOME/.claude/.skill-manifests"
MANIFEST="$MANIFEST_DIR/$BUNDLE_NAME.txt"
BACKUP_DEST="$HOME/.claude/install-backups/$(date +%Y%m%d-%H%M%S)-$$"

usage() { sed -n '2,/^# ===/p' "$0" | sed 's/^#\{0,1\} \{0,1\}//'; }

DO_UNINSTALL=0
NO_SHELL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --no-shell) NO_SHELL=1 ;;
    --uninstall) DO_UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

# Refuse manifest entries that could escape ~/.claude.
safe_rel() {
  case "$1" in
    ""|/*|*..*) return 1 ;;
    *) return 0 ;;
  esac
}

uninstall_bundle() {
  if [ ! -f "$MANIFEST" ]; then
    echo "No manifest at $MANIFEST — nothing tracked to uninstall."
    return 0
  fi
  echo "Uninstalling $BUNDLE_NAME using $MANIFEST"
  local rel target other owned removed=0 kept=0
  while IFS= read -r rel || [ -n "${rel:-}" ]; do
    [ -z "$rel" ] && continue
    if ! safe_rel "$rel"; then
      echo "Refusing unsafe manifest path: $rel" >&2
      exit 1
    fi
    target="$HOME/.claude/$rel"
    owned=0
    for other in "$MANIFEST_DIR"/*.txt; do
      [ -e "$other" ] || continue
      [ "$other" = "$MANIFEST" ] && continue
      if grep -qxF "$rel" "$other" 2>/dev/null; then
        owned=1
        break
      fi
    done
    if [ "$owned" = "1" ]; then
      kept=$((kept + 1))
    else
      rm -rf "$target"
      removed=$((removed + 1))
    fi
  done < "$MANIFEST"
  rm -f "$MANIFEST"
  echo "  removed $removed item(s); kept $kept still owned by another bundle"
  echo "Done. Install backups under ~/.claude/install-backups/ are left in place."
}

if [ "$DO_UNINSTALL" = "1" ]; then
  uninstall_bundle
  exit 0
fi

shopt -s nullglob
skill_dirs=("$REPO_DIR/skills"/*/)
shopt -u nullglob
if [ "${#skill_dirs[@]}" -eq 0 ]; then
  echo "No skill directories under $REPO_DIR/skills" >&2
  exit 1
fi

install_skills() {
  local dest="$1"
  local skill_dir name
  mkdir -p "$dest"
  echo "Skills →  $dest"
  for skill_dir in "${skill_dirs[@]}"; do
    name="$(basename "$skill_dir")"
    if [ -d "$dest/$name" ] && [ ! -L "$dest/$name" ]; then
      if diff -rq --exclude=__pycache__ "$skill_dir" "$dest/$name" >/dev/null 2>&1; then
        continue
      fi
      mkdir -p "$BACKUP_DEST"
      mv "$dest/$name" "$BACKUP_DEST/$name"
    elif [ -e "$dest/$name" ] || [ -L "$dest/$name" ]; then
      mkdir -p "$BACKUP_DEST"
      mv "$dest/$name" "$BACKUP_DEST/$name"
    fi
    cp -R "$skill_dir" "$dest/$name"
  done
  echo "  installed ${#skill_dirs[@]} skills"
}

echo "Installing $BUNDLE_NAME from $REPO_DIR"
echo ""
install_skills "$HOME/.claude/skills"

mkdir -p "$MANIFEST_DIR"
{
  for skill_dir in "${skill_dirs[@]}"; do
    basename "$skill_dir"
  done | sort | while IFS= read -r name; do
    printf 'skills/%s\n' "$name"
  done
} > "$MANIFEST"

echo "  manifest ($(wc -l < "$MANIFEST" | tr -d ' ') entries) → $MANIFEST"
echo "  uninstall later with:  bash scripts/install.sh --uninstall"
if [ "$NO_SHELL" = "1" ]; then
  echo "  --no-shell: shell startup files were not modified."
else
  echo "  Shell startup files were not modified (this pack has no shell hook)."
fi
echo ""
echo "Install complete: $HOME/.claude/skills"
