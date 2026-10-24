#!/usr/bin/env bash
# Smoke test for scripts/install.sh. Uses a temporary HOME. No network.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAILS=0

fail() {
  echo "FAIL: $*" >&2
  FAILS=$((FAILS + 1))
}

ok() { echo "ok   $*"; }

new_home() { mktemp -d; }

run_install() {
  local home="$1"
  shift
  env -u ZDOTDIR HOME="$home" bash "$REPO/scripts/install.sh" "$@"
}

assert_file() { [ -f "$1" ] || fail "missing file $1"; }
assert_dir() { [ -d "$1" ] || fail "missing dir $1"; }
assert_absent() { [ ! -e "$1" ] || fail "unexpected path $1"; }

test_help() {
  local out
  out="$(bash "$REPO/scripts/install.sh" --help)"
  grep -q -- "--uninstall" <<<"$out" || fail "help missing --uninstall"
  grep -q -- "--no-shell" <<<"$out" || fail "help missing --no-shell"
  grep -q -- "--agents" <<<"$out" || fail "help missing --agents"
  ok "help"
}

test_unknown() {
  local home
  home="$(new_home)"
  if run_install "$home" --nope >/dev/null 2>&1; then
    fail "unknown option should exit non-zero"
  else
    ok "unknown option"
  fi
}

test_no_target() {
  local home
  home="$(new_home)"
  if run_install "$home" --no-claude >/dev/null 2>&1; then
    fail "--no-claude alone should exit non-zero"
  else
    ok "no target"
  fi
}

test_refuse_repo_dest() {
  local home
  home="$(new_home)"
  if run_install "$home" --no-claude --dest "$REPO/skills" --no-shell >/dev/null 2>&1; then
    fail "install into the source repo should fail"
  else
    ok "refuse repo dest"
  fi
}

test_default_and_no_shell() {
  local home out count src dst
  home="$(new_home)"
  printf 'echo original-zsh\n' > "$home/.zshrc"
  printf 'echo original-bash\n' > "$home/.bashrc"
  run_install "$home" >/dev/null
  assert_file "$home/.claude/skills/asinhhc-bounty/SKILL.md"
  assert_file "$home/.claude/skills/asinhhc-bounty/list_bounties.py"
  assert_file "$home/.claude/skills/asinhhc-bounty/bounties.json"
  assert_file "$home/.claude/skills/asinhhc-verify/verify_replay.py"
  assert_file "$home/.claude/scripts/asinhhc.sh"
  assert_file "$home/.claude/.skill-manifests/asin-hhc-skills.txt"
  grep -q "claude/scripts/asinhhc.sh" "$home/.zshrc" || fail "zshrc was not wired"
  grep -q "original-zsh" "$home/.zshrc" || fail "zshrc lost its original line"
  if grep -q "asinhhc.sh" "$home/.bashrc"; then
    fail "bashrc changed even though zshrc exists"
  fi
  grep -qx "@home claude" "$home/.claude/.skill-manifests/asin-hhc-skills.txt" || fail "manifest missing @home claude"
  grep -qx "skills/asinhhc-bounty" "$home/.claude/.skill-manifests/asin-hhc-skills.txt" || fail "manifest missing bounty"
  out="$(python3 "$home/.claude/skills/asinhhc-bounty/list_bounties.py")"
  grep -q "4 open bounties" <<<"$out" || fail "bounty board did not list 4 bounties: $out"
  grep -q "BOUNTY-02" <<<"$out" || fail "bounty board missing BOUNTY-02"
  out="$(bash "$home/.claude/scripts/asinhhc.sh")"
  grep -q "asinhhc-bounty" <<<"$out" || fail "helper did not list asinhhc-bounty"
  grep -q "simulated by default" <<<"$out" || fail "helper missing credit wording"
  # Second install must not append another source line or park a backup.
  run_install "$home" >/dev/null
  count="$(grep -c "claude/scripts/asinhhc.sh" "$home/.zshrc")"
  [ "$count" = "1" ] || fail "source line count is $count"
  assert_absent "$home/.claude/install-backups"
  # Tamper, reinstall, and confirm the backup sits outside the skill load path.
  echo tamper >> "$home/.claude/skills/asinhhc-bounty/SKILL.md"
  run_install "$home" >/dev/null
  if grep -q tamper "$home/.claude/skills/asinhhc-bounty/SKILL.md"; then
    fail "tampered skill was not replaced"
  fi
  assert_dir "$home/.claude/install-backups"
  grep -R -q tamper "$home/.claude/install-backups" || fail "backup does not contain the tampered skill"
  count="$(find "$home/.claude/skills" -name SKILL.md | wc -l | tr -d ' ')"
  [ "$count" = "6" ] || fail "skill load path has $count SKILL.md files, expected 6"
  ok "default install, idempotent reinstall, backup"

  home="$(new_home)"
  printf 'echo original-bash\n' > "$home/.bashrc"
  src="$(cksum "$home/.bashrc")"
  run_install "$home" --no-shell >/dev/null
  dst="$(cksum "$home/.bashrc")"
  [ "$src" = "$dst" ] || fail "--no-shell modified bashrc"
  assert_file "$home/.claude/scripts/asinhhc.sh"
  assert_file "$home/.claude/skills/asinhhc-join/SKILL.md"
  ok "--no-shell"
}

test_uninstall_and_safety() {
  local home manifest
  home="$(new_home)"
  printf 'echo original\n' > "$home/.bashrc"
  run_install "$home" >/dev/null
  grep -q "asinhhc.sh" "$home/.bashrc" || fail "expected bashrc source line"
  run_install "$home" --uninstall >/dev/null
  assert_absent "$home/.claude/skills/asinhhc-bounty"
  assert_absent "$home/.claude/skills/asinhhc-join"
  assert_absent "$home/.claude/scripts/asinhhc.sh"
  assert_absent "$home/.claude/.skill-manifests/asin-hhc-skills.txt"
  if grep -q "asinhhc.sh" "$home/.bashrc"; then
    fail "uninstall left the source line in bashrc"
  fi
  grep -q "echo original" "$home/.bashrc" || fail "uninstall dropped the original bashrc line"
  ok "uninstall"

  home="$(new_home)"
  run_install "$home" --no-shell >/dev/null
  echo "skills/asinhhc-bounty" > "$home/.claude/.skill-manifests/other-bundle.txt"
  run_install "$home" --uninstall >/dev/null
  assert_dir "$home/.claude/skills/asinhhc-bounty"
  assert_absent "$home/.claude/skills/asinhhc-join"
  assert_absent "$home/.claude/skills/asinhhc-verify"
  ok "sibling manifest keeps the shared skill"

  home="$(new_home)"
  run_install "$home" --no-shell >/dev/null
  echo canary > "$home/.claude/CANARY"
  echo canary-home > "$home/CANARY_HOME"
  manifest="$home/.claude/.skill-manifests/asin-hhc-skills.txt"
  {
    echo "skills/.."
    echo "skills/../../CANARY_HOME"
    echo "@dest /"
    echo "@dest $home"
    echo "@dest $home/.claude"
  } >> "$manifest"
  run_install "$home" --uninstall >/dev/null
  assert_file "$home/.claude/CANARY"
  assert_file "$home/CANARY_HOME"
  assert_absent "$home/.claude/skills/asinhhc-verify"
  ok "unsafe manifest entries skipped"
}

test_agents_and_dest() {
  local home dest src dst
  home="$(new_home)"
  printf 'echo original\n' > "$home/.bashrc"
  src="$(cksum "$home/.bashrc")"
  run_install "$home" --no-claude --agents --no-shell >/dev/null
  dst="$(cksum "$home/.bashrc")"
  [ "$src" = "$dst" ] || fail "codex install modified bashrc"
  assert_file "$home/.agents/skills/asinhhc-bounty/SKILL.md"
  assert_file "$home/.agents/skills/asinhhc-connectors/SKILL.md"
  assert_absent "$home/.claude/skills/asinhhc-bounty"
  src="$(grep '^description:' "$REPO/skills/asinhhc-bounty/SKILL.md")"
  dst="$(grep '^description:' "$home/.agents/skills/asinhhc-bounty/SKILL.md")"
  [ "$src" = "$dst" ] || fail "Codex copy changed the bounty description"
  grep -qx "@home agents" "$home/.claude/.skill-manifests/asin-hhc-skills.txt" || fail "manifest missing @home agents"
  if grep -qx "@home claude" "$home/.claude/.skill-manifests/asin-hhc-skills.txt"; then
    fail "claude home recorded for a --no-claude install"
  fi
  run_install "$home" --uninstall >/dev/null
  assert_absent "$home/.agents/skills/asinhhc-bounty"
  ok "codex --agents --no-shell"

  home="$(new_home)"
  dest="$home/generic/skills"
  run_install "$home" --no-claude --dest "$dest" --no-shell >/dev/null
  assert_file "$dest/asinhhc-connectors/SKILL.md"
  assert_file "$dest/asinhhc-escrow-review/SKILL.md"
  assert_file "$dest/asinhhc-heartbeat/SKILL.md"
  assert_absent "$home/.claude/skills"
  assert_absent "$home/.agents/skills"
  echo keep > "$dest/keep.txt"
  run_install "$home" --uninstall >/dev/null
  assert_absent "$dest/asinhhc-connectors"
  assert_absent "$dest/asinhhc-bounty"
  assert_file "$dest/keep.txt"
  ok "generic --dest --no-shell"
}

test_verify_usage() {
  local code=0
  python3 "$REPO/skills/asinhhc-verify/verify_replay.py" >/dev/null 2>&1 || code=$?
  [ "$code" = "2" ] || fail "verify_replay.py exited $code, expected 2"
  ok "verify_replay usage"
}

test_help
test_unknown
test_no_target
test_refuse_repo_dest
test_default_and_no_shell
test_uninstall_and_safety
test_agents_and_dest
test_verify_usage

if [ "$FAILS" -ne 0 ]; then
  echo "$FAILS install test(s) failed." >&2
  exit 1
fi
echo "Install smoke test passed."
