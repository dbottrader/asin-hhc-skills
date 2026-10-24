#!/usr/bin/env python3
"""Verify documented skill counts against skills/ on disk.

Ported from the *idea* of elementalsouls/Claude-BugHunter scripts/check_doc_counts.py
(MIT). That script also checks hunt-* and slash-command totals. This pack has
neither, so the ground truth is: every skills/<name>/SKILL.md, the README
table that links them, and the "N skills" counts in the README and the
Claude Code plugin manifests.

A missing pattern is a failure. Update this script when the wording of a
checked sentence changes on purpose.

Exit code 0 = counts match, 1 = at least one mismatch. Stdlib only.

Usage:
    python3 scripts/check_doc_counts.py
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(REPO, "skills")
README = "README.md"
PLUGIN = os.path.join(".claude-plugin", "plugin.json")
MARKET = os.path.join(".claude-plugin", "marketplace.json")
REPO_SLUG = "dbottrader/asin-hhc-skills"

README_REQUIRED = (
    "token-ready",
    "simulated by default",
    "Claude-BugHunter",
    "elementalsouls",
    "https://github.com/elementalsouls/Claude-BugHunter",
    "Codex",
    "Generic agents",
    "--agents",
    "--no-shell",
    "--uninstall",
    "--no-claude",
    "MIT",
)
README_FORBIDDEN = (
    "not a token",
    "never a token",
    "utility credit",
    "token investment",
    "five skills",
    "Five skills",
)


def read(path):
    with open(os.path.join(REPO, path), encoding="utf-8") as handle:
        return handle.read()


def skill_names():
    names = []
    problems = []
    if not os.path.isdir(SKILLS_DIR):
        return [], ["skills/ directory is missing"]
    for name in sorted(os.listdir(SKILLS_DIR)):
        path = os.path.join(SKILLS_DIR, name)
        if not os.path.isdir(path):
            continue
        if os.path.isfile(os.path.join(path, "SKILL.md")):
            names.append(name)
        else:
            problems.append(f"skills/{name} is missing SKILL.md")
    return names, problems


def emit(errors):
    for error in errors:
        print(f"::error:: {error}" if os.environ.get("GITHUB_ACTIONS") else f"ERROR {error}")


def check_counts(text, label, actual, errors):
    found = [int(n) for n in re.findall(r"(\d+) skills", text)]
    if not found:
        errors.append(f"{label}: no 'N skills' count found — docs must state the skill count")
        return
    for n in found:
        if n != actual:
            errors.append(f"{label}: says {n} skills but {actual} skills are on disk")


def check_readme(names, errors):
    text = read(README)
    actual = len(names)
    check_counts(text, README, actual, errors)
    linked = set(re.findall(r"skills/([a-z0-9-]+)/SKILL\.md", text))
    missing = [name for name in names if name not in linked]
    extra = sorted(linked - set(names))
    if missing:
        errors.append(f"{README}: does not link skills/<name>/SKILL.md for: {', '.join(missing)}")
    if extra:
        errors.append(f"{README}: links skills that are not on disk: {', '.join(extra)}")
    for phrase in README_REQUIRED:
        if phrase not in text:
            errors.append(f"{README}: missing required wording '{phrase}'")
    lowered = text.lower()
    for phrase in README_FORBIDDEN:
        if phrase.lower() in lowered:
            errors.append(f"{README}: contains stale wording '{phrase}'")


def check_plugin_files(errors):
    try:
        plugin = json.loads(read(PLUGIN))
        market = json.loads(read(MARKET))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"plugin manifest is not readable JSON: {exc}")
        return None, None

    versions = [
        plugin.get("version"),
        market.get("metadata", {}).get("version"),
    ]
    plugins = market.get("plugins") or []
    if len(plugins) != 1:
        errors.append(f"{MARKET}: expected exactly one plugin entry, found {len(plugins)}")
        entry = {}
    else:
        entry = plugins[0]
        versions.append(entry.get("version"))
    if len(set(versions)) != 1 or not versions[0]:
        errors.append(f"plugin versions disagree: {versions}")

    if plugin.get("name") != entry.get("name"):
        errors.append(
            f"plugin name '{plugin.get('name')}' != marketplace plugin '{entry.get('name')}'"
        )
    if entry.get("source") != "./":
        errors.append(f"{MARKET}: plugin source must be \"./\" so the repo root is the plugin")
    if market.get("name") != "dbottrader":
        errors.append(f"{MARKET}: marketplace name must be 'dbottrader' (install slug)")
    if plugin.get("license") != "MIT":
        errors.append(f"{PLUGIN}: license must be MIT")

    actual = None  # filled by caller via check_counts on the raw text
    for path in (PLUGIN, MARKET):
        check_counts(read(path), path, skill_count_holder[0], errors)
        raw = read(path)
        for phrase in ("token-ready", "simulated by default"):
            if phrase not in raw:
                errors.append(f"{path}: missing '{phrase}'")
    return plugin, entry


# Set in main before check_plugin_files reads it. A list so the nested
# function sees the count without a class.
skill_count_holder = [0]


def check_install_commands(plugin, errors):
    if not plugin:
        return
    text = read(README)
    market = json.loads(read(MARKET))
    install = f"/plugin install {plugin['name']}@{market['name']}"
    marketplace_add = f"/plugin marketplace add {REPO_SLUG}"
    if marketplace_add not in text:
        errors.append(f"{README}: missing `{marketplace_add}`")
    if install not in text:
        errors.append(f"{README}: missing `{install}`")


def main():
    names, errors = skill_names()
    skill_count_holder[0] = len(names)
    if not names:
        errors.append("no skills found under skills/")
    check_readme(names, errors)
    plugin, _entry = check_plugin_files(errors)
    check_install_commands(plugin, errors)

    emit(errors)
    print(f"\nGround truth: {len(names)} skills ({', '.join(names)}).")
    print(f"Checked README links, plugin manifests, and wording: {len(errors)} error(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
