#!/usr/bin/env python3
"""Lint skills/<name>/SKILL.md for structure, YAML safety, wording, and secrets.

Ported from the *idea* of elementalsouls/Claude-BugHunter scripts/lint_skills.py
(MIT). Not ported, on purpose:

- the client/engagement identifier denylist (that repo's private-name scanner)
- hunt-* `sources` / `report_count` grounding (security-skill metadata)

Checks per skills/<name>/SKILL.md:
  STRUCTURE (errors)
    - frontmatter block present
    - `name` matches ^[a-z0-9-]+$ and equals the directory name
    - `description` present and <= 1024 characters (Codex rejects longer)
    - unquoted frontmatter values must not contain ': ' (strict YAML)
  WORDING (errors)
    - body states that HHC is a token-ready credit, simulated by default
    - body does not call HHC "not a token" or a generic "utility credit"
  SAFETY (errors)
    - obvious live secrets (AWS keys, private-key blocks, JWTs, Slack,
      Google, GitHub PATs). The public AWS example key is allowlisted.

Body length over 500 lines is a warning. Warnings do not fail the run.
Exit code 0 = clean, 1 = at least one error. Stdlib only.

Usage:
    python3 scripts/lint_skills.py
    python3 scripts/lint_skills.py skills/asinhhc-bounty
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(REPO, "skills")

NAME_RE = re.compile(r"^[a-z0-9-]+$")
MAX_DESC = 1024
MAX_BODY_LINES = 500

REQUIRED_PHRASES = ("token-ready", "simulated by default")
FORBIDDEN_PHRASES = (
    "not a token",
    "never a token",
    "isn't a token",
    "isnt a token",
    "utility credit",
    "token investment",
)

SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("GitHub PAT", re.compile(r"\bghp_[0-9A-Za-z]{36}\b")),
]
SECRET_ALLOW = re.compile(
    r"AKIAIOSFODNN7EXAMPLE|EXAMPLE|wJalrXUtnFEMI|\[0-9A-Z\]|\{1[06]\}|<[^>]+>|\.\.\."
)
TEXT_SUFFIXES = {".md", ".py", ".json", ".sh", ".txt", ".yml", ".yaml"}


def unquote(val):
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        return val[1:-1]
    return val


def split_frontmatter(raw):
    """Return (frontmatter_dict, body_text, error_or_None)."""
    if not raw.startswith("---"):
        return {}, raw, "no frontmatter block (file must start with '---')"
    parts = raw.split("\n")
    close = None
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            close = i
            break
    if close is None:
        return {}, raw, "frontmatter opened with '---' but never closed"
    fm = {}
    for line in parts[1:close]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match:
            fm[match.group(1)] = match.group(2).strip()
    body = "\n".join(parts[close + 1:])
    return fm, body, None


def yaml_safety_errors(name, raw):
    """Flag unquoted frontmatter values that contain ': '.

    A strict YAML parser (Codex) reads that colon as a nested mapping.
    Quoted values are accepted. This is the same bug class as an unquoted
    description that happens to contain a colon.
    """
    errors = []
    if not raw.startswith("---"):
        return errors
    lines = raw.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            break
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", lines[i])
        if not match or not match.group(2):
            continue
        val = match.group(2)
        quoted = len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'"
        if quoted and '"' in val[1:-1]:
            errors.append(
                f"{name}: frontmatter `{match.group(1)}` contains an unescaped "
                f"double quote inside a double-quoted value"
            )
        if not quoted and ": " in val:
            errors.append(
                f"{name}: frontmatter `{match.group(1)}` is unquoted and contains ': ' — "
                f"wrap the value in double quotes (strict YAML parsers like Codex reject it)"
            )
    return errors


def secret_errors(name, rel, text):
    errors = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(line):
                snippet = match.group(0)
                window = line[max(0, match.start() - 8): match.end() + 8]
                if SECRET_ALLOW.search(window) or SECRET_ALLOW.search(snippet):
                    continue
                where = f"{name}:{rel}:{lineno}" if rel != "SKILL.md" else f"{name}:{lineno}"
                errors.append(f"{where}: possible {label} leaked — '{snippet[:24]}...'")
    return errors


def iter_skill_files(skill_dir):
    for root, dirs, files in os.walk(skill_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for filename in files:
            if os.path.splitext(filename)[1].lower() not in TEXT_SUFFIXES:
                continue
            path = os.path.join(root, filename)
            rel = os.path.relpath(path, skill_dir)
            yield rel, path


def lint_skill(skill_dir):
    errors, warnings = [], []
    name = os.path.basename(skill_dir.rstrip(os.sep))
    path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(path):
        return [f"{name}: missing SKILL.md"], []
    with open(path, encoding="utf-8") as handle:
        raw = handle.read()

    fm, body, fm_err = split_frontmatter(raw)
    if fm_err:
        errors.append(f"{name}: {fm_err}")
    errors.extend(yaml_safety_errors(name, raw))

    fn = fm.get("name", "")
    if not fn:
        errors.append(f"{name}: frontmatter missing `name`")
    else:
        if not NAME_RE.match(fn):
            errors.append(f"{name}: `name` '{fn}' must match ^[a-z0-9-]+$")
        if fn != name:
            errors.append(f"{name}: `name` '{fn}' != directory '{name}'")

    desc = unquote(fm.get("description", ""))
    if not desc:
        errors.append(f"{name}: frontmatter missing `description`")
    elif len(desc) > MAX_DESC:
        errors.append(
            f"{name}: description {len(desc)} chars > {MAX_DESC} limit "
            f"(Codex rejects >1024; install.sh --agents truncates that copy only)"
        )
    elif len(desc) < 40:
        warnings.append(f"{name}: description very short ({len(desc)} chars) — weak trigger surface")

    body_lines = len(body.splitlines())
    if body_lines > MAX_BODY_LINES:
        warnings.append(
            f"{name}: body {body_lines} lines > {MAX_BODY_LINES} guideline "
            f"(move reference material beside SKILL.md)"
        )

    lowered = raw.lower()
    for phrase in REQUIRED_PHRASES:
        if phrase not in lowered:
            errors.append(f"{name}: SKILL.md must say '{phrase}' (token-ready credits, simulated by default)")
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            errors.append(f"{name}: SKILL.md still says '{phrase}' — HHC is a token-ready credit, simulated by default")

    for rel, file_path in iter_skill_files(skill_dir):
        with open(file_path, encoding="utf-8") as handle:
            errors.extend(secret_errors(name, rel, handle.read()))
    return errors, warnings


def skill_targets(argv):
    if argv:
        targets = []
        for arg in argv:
            targets.append(arg if os.path.isabs(arg) else os.path.join(REPO, arg))
        return targets
    if not os.path.isdir(SKILLS_DIR):
        return []
    return [
        os.path.join(SKILLS_DIR, name)
        for name in sorted(os.listdir(SKILLS_DIR))
        if os.path.isdir(os.path.join(SKILLS_DIR, name))
    ]


def main(argv):
    targets = skill_targets(argv)
    if not targets:
        print("ERROR no skills found. Expected skills/<name>/SKILL.md")
        return 1

    all_errors, all_warnings = [], []
    for target in targets:
        if not os.path.isdir(target):
            all_errors.append(f"{target}: not a directory")
            continue
        found_errors, found_warnings = lint_skill(target)
        all_errors.extend(found_errors)
        all_warnings.extend(found_warnings)

    for warning in all_warnings:
        print(f"::warning:: {warning}" if os.environ.get("GITHUB_ACTIONS") else f"WARN  {warning}")
    for error in all_errors:
        print(f"::error:: {error}" if os.environ.get("GITHUB_ACTIONS") else f"ERROR {error}")

    print(f"\nLinted {len(targets)} skill(s): {len(all_errors)} error(s), {len(all_warnings)} warning(s).")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
