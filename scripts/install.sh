#!/usr/bin/env bash
# install.sh — install the ASIN-HHC skills pack
#
# Packaging adapted from elementalsouls/Claude-BugHunter scripts/install.sh (MIT).
# This script does not install hunt commands, Burp MCP config, or any security
# skills. It copies files, optionally appends one shell-rc line, and writes a
# manifest. It does not make network calls, read credentials, or eval input.
#
# DEFAULT (no flags): Claude Code copy install
#   skills/<name>/  → ~/.claude/skills/<name>/
#   scripts/asinhhc.sh → ~/.claude/scripts/asinhhc.sh
#   and append `source ~/.claude/scripts/asinhhc.sh` to ~/.zshrc or ~/.bashrc
#
# FLAGS
#   --agents      also copy skills to ~/.agents/skills/ (OpenAI Codex)
#   --dest DIR    also copy skills to DIR (generic agents)
#   --no-claude   skip the ~/.claude/skills copy and the shell-rc edit
#   --no-shell    do not modify ~/.zshrc or ~/.bashrc
#   --uninstall   remove this pack's footprint using the install manifest
#   -h, --help    show this help
#
# Idempotent. A skill that is already installed and identical is left in place.
# A skill that differs is moved to ~/.claude/install-backups/<timestamp>/,
# outside the directory agents load skills from.
# The manifest is ~/.claude/.skill-manifests/asin-hhc-skills.txt.
# Uninstall deletes only manifest entries. A relative path listed by another
# manifest in that directory is kept. Entries containing '..' are ignored.
#
# Requires bash. --agents description truncation uses python3 when it is present.
#
# ===
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_NAME="asin-hhc-skills"
MANIFEST_DIR="${HOME}/.claude/.skill-manifests"
MANIFEST="${MANIFEST_DIR}/${BUNDLE_NAME}.txt"
BACKUP_DEST="${HOME}/.claude/install-backups/$(date +%Y%m%d-%H%M%S)"
SOURCE_LINE="source ~/.claude/scripts/asinhhc.sh"
SHELL_MARKER="# asin-hhc-skills: source the pack helper"

usage() {
  sed -n '2,/^# ===$/p' "$0" | sed '/^# ===$/d; s/^# \{0,1\}//'
}

DO_CLAUDE=1
DO_AGENTS=0
DO_UNINSTALL=0
NO_SHELL=0
DEST=""
DEST_RECORDED=()

while [ $# -gt 0 ]; do
  case "$1" in
    --agents) DO_AGENTS=1 ;;
    --no-claude) DO_CLAUDE=0 ;;
    --no-shell) NO_SHELL=1 ;;
    --uninstall) DO_UNINSTALL=1 ;;
    --dest)
      if [ $# -lt 2 ] || [ -z "${2:-}" ]; then
        echo "error: --dest needs a directory" >&2
        exit 2
      fi
      DEST="$2"
      shift
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

home_root() {
  case "$1" in
    claude) printf '%s\n' "${HOME}/.claude" ;;
    agents) printf '%s\n' "${HOME}/.agents" ;;
    *) printf '\n' ;;
  esac
}

safe_rel() {
  local rel="$1" base
  case "$rel" in
    *..*) return 1 ;;
    skills/*|scripts/*|commands/*) ;;
    *) return 1 ;;
  esac
  base="${rel#*/}"
  case "$base" in
    */*|.|..) return 1 ;;
  esac
  [[ "$base" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || return 1
  return 0
}

safe_dest() {
  local target="$1" base resolved
  case "$target" in
    /*) ;;
    *) return 1 ;;
  esac
  case "$target" in
    *..*) return 1 ;;
  esac
  base="$(basename "$target")"
  [[ "$base" =~ ^asinhhc-[a-z0-9-]+$ ]] || return 1
  if [ "$target" = "/" ] || [ "$target" = "${HOME}" ] || [ "$target" = "${HOME}/.claude" ] || [ "$target" = "${HOME}/.agents" ]; then
    return 1
  fi
  if [ -e "$target" ]; then
    resolved="$(realpath "$target")"
    if [ "$resolved" = "/" ] || [ "$resolved" = "${HOME}" ] || [ "$resolved" = "${HOME}/.claude" ] || [ "$resolved" = "${HOME}/.agents" ]; then
      return 1
    fi
  fi
  return 0
}

other_owns() {
  local rel="$1" other
  shopt -s nullglob
  for other in "$MANIFEST_DIR"/*.txt; do
    [ "$other" = "$MANIFEST" ] && continue
    if grep -qxF "$rel" "$other" 2>/dev/null; then
      return 0
    fi
  done
  return 1
}

strip_shell_rc() {
  local rc
  for rc in "${HOME}/.zshrc" "${HOME}/.bashrc" "${ZDOTDIR:-}/.zshrc"; do
    [ -n "$rc" ] && [ -f "$rc" ] || continue
    if grep -q "claude/scripts/asinhhc.sh" "$rc" 2>/dev/null; then
      sed -i.bak '/claude\/scripts\/asinhhc.sh/d; /asin-hhc-skills: source the pack helper/d' "$rc"
      echo "  ✓ removed asinhhc.sh source line from $rc (backup: ${rc}.bak)"
    fi
  done
}

uninstall_bundle() {
  if [ ! -f "$MANIFEST" ]; then
    echo "No manifest at $MANIFEST — nothing tracked to uninstall."
    return 0
  fi
  echo "Uninstalling ${BUNDLE_NAME} using $MANIFEST"
  local line homes=() rel target root removed=0 kept=0 skipped=0
  local -a lines=()
  while IFS= read -r line || [ -n "$line" ]; do
    lines+=("$line")
  done < "$MANIFEST"

  if [ "${#lines[@]}" -gt 0 ]; then
    for line in "${lines[@]}"; do
      case "$line" in
        "@home "*) homes+=("${line#@home }") ;;
      esac
    done
  fi

  if [ "${#lines[@]}" -gt 0 ]; then
    for line in "${lines[@]}"; do
      case "$line" in
        ""|\#*|@home\ *) continue ;;
        @dest\ *)
          target="${line#@dest }"
          if ! safe_dest "$target"; then
            echo "  ! skip unsafe dest entry: $target" >&2
            skipped=$((skipped + 1))
            continue
          fi
          if other_owns "$line"; then
            kept=$((kept + 1))
            continue
          fi
          rm -rf -- "$target"
          removed=$((removed + 1))
          ;;
        *)
          if ! safe_rel "$line"; then
            echo "  ! skip unsafe manifest entry: $line" >&2
            skipped=$((skipped + 1))
            continue
          fi
          if other_owns "$line"; then
            kept=$((kept + 1))
            continue
          fi
          if [ "${#homes[@]}" -eq 0 ]; then
            echo "  ! skip $line (no @home recorded)" >&2
            skipped=$((skipped + 1))
            continue
          fi
          for rel in "${homes[@]}"; do
            root="$(home_root "$rel")"
            if [ -z "$root" ]; then
              echo "  ! skip unknown home: $rel" >&2
              skipped=$((skipped + 1))
              continue
            fi
            rm -rf -- "$root/$line"
          done
          removed=$((removed + 1))
          ;;
      esac
    done
  fi

  rm -f "$MANIFEST"
  strip_shell_rc
  echo "  ✓ removed ${removed} item(s); kept ${kept} still owned by another manifest; skipped ${skipped} unsafe"
  echo "Done. Install backups, if any, remain under ${HOME}/.claude/install-backups/."
}

if [ "$DO_UNINSTALL" = "1" ]; then
  uninstall_bundle
  exit 0
fi

if [ "$DO_CLAUDE" = "0" ] && [ "$DO_AGENTS" = "0" ] && [ -z "$DEST" ]; then
  echo "error: nothing to install. Drop --no-claude, or pass --agents or --dest." >&2
  exit 2
fi

SKILL_COUNT="$(find "$REPO_DIR/skills" -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')"
if [ "$SKILL_COUNT" = "0" ]; then
  echo "No skills/*/SKILL.md found under $REPO_DIR" >&2
  exit 1
fi

# Validate --dest before copying anything, so a bad path cannot leave a
# Claude or Codex copy with no manifest to uninstall.
DEST_ABS=""
if [ -n "$DEST" ]; then
  mkdir -p "$DEST"
  DEST_ABS="$(cd "$DEST" && pwd)"
  case "$DEST_ABS" in
    "$REPO_DIR"|"$REPO_DIR"/*)
      echo "error: refusing to install into the source repo ($DEST_ABS)" >&2
      exit 2
      ;;
  esac
  if [ "$DEST_ABS" = "${HOME}/.claude/skills" ] || [ "$DEST_ABS" = "${HOME}/.agents/skills" ]; then
    echo "error: use the default install or --agents for $DEST_ABS" >&2
    exit 2
  fi
fi

install_skills() {
  local dest="$1" label="$2" name skill_dir
  mkdir -p "$dest"
  echo "Skills →  $dest   ($label)"
  for skill_dir in "$REPO_DIR/skills"/*/; do
    [ -d "$skill_dir" ] || continue
    [ -f "${skill_dir}SKILL.md" ] || continue
    name="$(basename "$skill_dir")"
    if [ -L "$dest/$name" ]; then
      rm -f "$dest/$name"
    elif [ -d "$dest/$name" ]; then
      if diff -rq --exclude=__pycache__ "$skill_dir" "$dest/$name" >/dev/null 2>&1; then
        continue
      fi
      mkdir -p "$BACKUP_DEST/$label"
      mv "$dest/$name" "$BACKUP_DEST/$label/$name"
    fi
    cp -r "$skill_dir" "$dest/$name"
  done
  echo "  ✓ ${SKILL_COUNT} skills in place"
  echo ""
}

truncate_codex_descriptions() {
  local dest="$1"
  if ! command -v python3 >/dev/null 2>&1; then
    echo "  ! python3 not found — skipped Codex description truncation" >&2
    return 0
  fi
  python3 - "$dest" <<'PY'
import os, re, sys
root = sys.argv[1]
LIMIT = 1024
for name in sorted(os.listdir(root)):
    path = os.path.join(root, name, "SKILL.md")
    if not os.path.isfile(path):
        continue
    lines = open(path, encoding="utf-8").read().split("\n")
    out, changed = [], False
    for i, line in enumerate(lines):
        match = re.match(r"^description:\s*(.*)$", line) if i < 12 else None
        if match:
            val = match.group(1)
            quoted = len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'"
            inner = val[1:-1] if quoted else val
            if len(inner) > LIMIT:
                cut = inner[: LIMIT - 1].rsplit(" ", 1)[0].rstrip(" ,;:—-")
                line = 'description: "' + cut + '…"'
                changed = True
                print(f"    truncated {name} description {len(inner)}→{len(cut) + 1} (Codex 1024 limit)")
        out.append(line)
    if changed:
        open(path, "w", encoding="utf-8").write("\n".join(out))
PY
}

echo "Installing ${BUNDLE_NAME} from ${REPO_DIR}"
echo "HHC is a token-ready credit, simulated by default."
echo ""

if [ "$DO_CLAUDE" = "1" ]; then
  install_skills "${HOME}/.claude/skills" "claude"
  mkdir -p "${HOME}/.claude/scripts"
  cp "$REPO_DIR/scripts/asinhhc.sh" "${HOME}/.claude/scripts/asinhhc.sh"
  chmod +x "${HOME}/.claude/scripts/asinhhc.sh"
  echo "  ✓ ${HOME}/.claude/scripts/asinhhc.sh"
  # shellcheck disable=SC1091
  source "${HOME}/.claude/scripts/asinhhc.sh"

  if [ -d "$REPO_DIR/commands" ]; then
    mkdir -p "${HOME}/.claude/commands"
    echo "Commands →  ${HOME}/.claude/commands"
    for cmd_file in "$REPO_DIR/commands"/*.md; do
      [ -e "$cmd_file" ] || continue
      cmd_name="$(basename "$cmd_file")"
      if [ -f "${HOME}/.claude/commands/$cmd_name" ] && [ ! -L "${HOME}/.claude/commands/$cmd_name" ]; then
        if cmp -s "$cmd_file" "${HOME}/.claude/commands/$cmd_name"; then
          continue
        fi
        mkdir -p "$BACKUP_DEST/commands"
        mv "${HOME}/.claude/commands/$cmd_name" "$BACKUP_DEST/commands/$cmd_name"
      fi
      cp "$cmd_file" "${HOME}/.claude/commands/$cmd_name"
    done
    echo ""
  fi

  SHELL_RC=""
  if [ -n "${ZDOTDIR:-}" ] && [ -f "${ZDOTDIR}/.zshrc" ]; then
    SHELL_RC="${ZDOTDIR}/.zshrc"
  elif [ -f "${HOME}/.zshrc" ]; then
    SHELL_RC="${HOME}/.zshrc"
  elif [ -f "${HOME}/.bashrc" ]; then
    SHELL_RC="${HOME}/.bashrc"
  fi
  if [ "$NO_SHELL" = "1" ]; then
    echo "  --no-shell: leaving your shell rc untouched. To enable the asinhhc command,"
    echo "    add these lines to your ~/.zshrc or ~/.bashrc yourself:"
    echo "        ${SHELL_MARKER}"
    echo "        ${SOURCE_LINE}"
  elif [ -n "$SHELL_RC" ]; then
    if grep -q "claude/scripts/asinhhc.sh" "$SHELL_RC" 2>/dev/null; then
      echo "  ✓ asinhhc.sh already sourced from $SHELL_RC"
    else
      printf '\n%s\n%s\n' "$SHELL_MARKER" "$SOURCE_LINE" >> "$SHELL_RC"
      echo "  ✓ appended a source line to $SHELL_RC (re-run with --no-shell to skip this)"
    fi
  else
    echo "  ! No ~/.zshrc or ~/.bashrc found. Add this line yourself:"
    echo "        ${SOURCE_LINE}"
  fi
  echo ""
fi

if [ "$DO_AGENTS" = "1" ]; then
  install_skills "${HOME}/.agents/skills" "agents"
  truncate_codex_descriptions "${HOME}/.agents/skills"
fi

if [ -n "$DEST_ABS" ]; then
  install_skills "$DEST_ABS" "dest"
  dest_skill=""
  for dest_skill in "$REPO_DIR/skills"/*/; do
    [ -f "${dest_skill}SKILL.md" ] || continue
    DEST_RECORDED+=("$DEST_ABS/$(basename "$dest_skill")")
  done
fi

mkdir -p "$MANIFEST_DIR"
{
  if [ "$DO_CLAUDE" = "1" ]; then echo "@home claude"; fi
  if [ "$DO_AGENTS" = "1" ]; then echo "@home agents"; fi
  if [ "$DO_CLAUDE" = "1" ] || [ "$DO_AGENTS" = "1" ]; then
    for skill_dir in "$REPO_DIR/skills"/*/; do
      [ -f "${skill_dir}SKILL.md" ] || continue
      echo "skills/$(basename "$skill_dir")"
    done
  fi
  if [ "$DO_CLAUDE" = "1" ]; then
    echo "scripts/asinhhc.sh"
    if [ -d "$REPO_DIR/commands" ]; then
      for cmd_file in "$REPO_DIR/commands"/*.md; do
        [ -e "$cmd_file" ] || continue
        echo "commands/$(basename "$cmd_file")"
      done
    fi
  fi
  if [ "${#DEST_RECORDED[@]}" -gt 0 ]; then
    for recorded in "${DEST_RECORDED[@]}"; do
      echo "@dest $recorded"
    done
  fi
} > "$MANIFEST"

echo "  ✓ Install manifest ($(wc -l < "$MANIFEST" | tr -d ' ') lines) → $MANIFEST"
echo "    Uninstall later with:  bash scripts/install.sh --uninstall"
echo ""
echo "Claude Code plugin (no copy):"
echo "  /plugin marketplace add dbottrader/asin-hhc-skills"
echo "  /plugin install asin-hhc-skills@dbottrader"
if [ "$DO_CLAUDE" = "1" ]; then echo "Claude Code copy:   ${HOME}/.claude/skills"; fi
if [ "$DO_AGENTS" = "1" ]; then echo "Codex:              ${HOME}/.agents/skills"; fi
if [ -n "$DEST" ]; then echo "Generic:            ${DEST_ABS}"; fi
if [ -d "$BACKUP_DEST" ]; then echo "Backups:            $BACKUP_DEST"; fi
echo ""
echo "Install complete. Token-ready credits, simulated by default."
