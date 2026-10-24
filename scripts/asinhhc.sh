#!/usr/bin/env bash
# ASIN-HHC skills pack helper.
# Sourced from ~/.zshrc or ~/.bashrc by scripts/install.sh (skip with --no-shell).
# Defines `asinhhc`. No network calls, no credentials, no eval.
# HHC is a token-ready credit. The simulated ledger backend is the default.

asinhhc() {
  local here skills_dir d found=0
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  skills_dir="$(cd "$here/../skills" && pwd)" || {
    echo "asinhhc: skills directory not found next to ${BASH_SOURCE[0]}" >&2
    return 1
  }
  echo "ASIN-HHC skills — token-ready credits, simulated by default"
  echo "Skills: $skills_dir"
  for d in "$skills_dir"/asinhhc-*/; do
    [ -f "${d}SKILL.md" ] || continue
    echo "  - $(basename "$d")"
    found=1
  done
  if [ "$found" = "0" ]; then
    echo "  (no asinhhc-* skills in $skills_dir)"
  fi
  echo "Promotion is human-only. A worker's done is input to verification, never self-credit."
  echo "Do not deploy contracts or mint tokens. The simulated backend stays on."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  asinhhc "$@"
fi
