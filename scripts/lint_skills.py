#!/usr/bin/env python3
"""
lint_skills.py — structure gate for ASIN-HHC skills.

Adapted from scripts/lint_skills.py in elementalsouls/Claude-BugHunter (MIT):
https://github.com/elementalsouls/Claude-BugHunter/blob/main/scripts/lint_skills.py

Checks per skills/<name>/SKILL.md:
  - frontmatter block present (between the first two `---` lines)
  - `name` present, matches ^[a-z0-9-]+$, and equals the directory name
  - `description` present and <= 1024 characters
  - unquoted frontmatter values must not contain ': ' (strict YAML rejects
    that as a nested mapping — the asinhhc-escrow-review / asinhhc-bounty bug)

BugHunter-only checks are not applied here: `sources` / `report_count`
grounding, and the client-identifier denylist. A tight real-secret scan
still runs, because a skill file should not ship live credentials.

Exit code 0 = clean, 1 = at least one error. Warnings never fail the build.
Stdlib only.

Usage:
    python3 scripts/lint_skills.py                  # lint all skills
    python3 scripts/lint_skills.py skills/asinhhc-join
    python3 scripts/lint_skills.py --self-test      # fixture checks for this linter
"""
import os
import re
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(REPO, "skills")

NAME_RE = re.compile(r"^[a-z0-9-]+$")
MAX_DESC = 1024

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
        else:
            return fm, "", f"frontmatter line is not `key: value`: {line!r}"
    body = "\n".join(parts[close + 1 :])
    return fm, body, None


def yaml_safety_errors(name, raw):
    """Catch frontmatter a strict YAML parser rejects but a lenient scan accepts.

    An unquoted value containing ': ' is read as a nested mapping. That is the
    bug fixed once in asinhhc-escrow-review and again in asinhhc-bounty.
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
        if not quoted and ": " in val:
            errors.append(
                f"{name}: frontmatter `{match.group(1)}` is unquoted and contains ': ' — "
                f"wrap the value in double quotes (strict YAML parsers reject it)"
            )
    return errors


def unquote(val):
    """Drop one matching pair of YAML quotes so length limits apply to the text."""
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        return val[1:-1]
    return val


def lint_skill(skill_dir):
    errors, warnings = [], []
    name = os.path.basename(skill_dir.rstrip("/"))
    path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(path):
        return [f"{name}: missing SKILL.md"], []
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()

    fm, _body, fm_err = split_frontmatter(raw)
    if fm_err:
        errors.append(f"{name}: {fm_err}")
    errors += yaml_safety_errors(name, raw)

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
            f"(Codex rejects descriptions over 1024 characters)"
        )
    elif len(desc) < 40:
        warnings.append(f"{name}: description very short ({len(desc)} chars)")

    for lineno, line in enumerate(raw.splitlines(), 1):
        for label, pat in SECRET_PATTERNS:
            for match in pat.finditer(line):
                snippet = match.group(0)
                window = line[max(0, match.start() - 8) : match.end() + 8]
                if SECRET_ALLOW.search(window) or SECRET_ALLOW.search(snippet):
                    continue
                errors.append(f"{name}:{lineno}: possible {label} leaked — '{snippet[:24]}...'")
    return errors, warnings


def lint_targets(argv):
    if argv:
        targets = [a if os.path.isabs(a) else os.path.join(REPO, a) for a in argv]
    else:
        if not os.path.isdir(SKILLS_DIR):
            return [f"missing skills directory: {SKILLS_DIR}"], [], 0
        targets = [
            os.path.join(SKILLS_DIR, d)
            for d in sorted(os.listdir(SKILLS_DIR))
            if os.path.isdir(os.path.join(SKILLS_DIR, d))
        ]
    all_errors, all_warnings = [], []
    for target in targets:
        errs, warns = lint_skill(target)
        all_errors += errs
        all_warnings += warns
    return all_errors, all_warnings, len(targets)


def _write_skill(root, name, body):
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


def self_test():
    """Prove the linter rejects the frontmatter bugs this repo has already hit."""
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        cases = {
            "ok-skill": (
                "---\nname: ok-skill\ndescription: "
                + ("Use when a test skill needs a description long enough to pass. " * 2)
                + "\n---\n\n# Body\n",
                False,
            ),
            "quoted-colon": (
                '---\nname: quoted-colon\ndescription: "Use when work: happens, '
                'and the colon is quoted so YAML stays valid for agents."\n---\n\n# Body\n',
                False,
            ),
            "bad-colon": (
                "---\nname: bad-colon\ndescription: Use when work: happens and the colon is bare.\n---\n\n# Body\n",
                True,
            ),
            "wrong-name": (
                "---\nname: other\ndescription: Use when the directory name and the frontmatter name disagree on purpose.\n---\n\n# Body\n",
                True,
            ),
            "no-desc": (
                "---\nname: no-desc\n---\n\n# Body\n",
                True,
            ),
            "no-fm": (
                "# no frontmatter\n",
                True,
            ),
        }
        # Directory names that differ from the `name:` key on purpose.
        dir_names = {
            "wrong-name": "wrong-name",
        }
        for key, (body, expect_error) in cases.items():
            dirname = dir_names.get(key, key)
            errs, _warns = lint_skill(_write_skill(tmp, dirname, body))
            got = bool(errs)
            if got != expect_error:
                failures.append(f"{key}: expected error={expect_error}, got {errs}")
    if failures:
        for item in failures:
            print(f"SELF-TEST FAIL {item}")
        return 1
    print(f"Self-test passed ({len(cases)} fixtures).")
    return 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    all_errors, all_warnings, n = lint_targets(argv)
    for warning in all_warnings:
        print(f"::warning:: {warning}" if os.environ.get("GITHUB_ACTIONS") else f"WARN  {warning}")
    for error in all_errors:
        print(f"::error:: {error}" if os.environ.get("GITHUB_ACTIONS") else f"ERROR {error}")
    print(f"\nLinted {n} skill(s): {len(all_errors)} error(s), {len(all_warnings)} warning(s).")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
