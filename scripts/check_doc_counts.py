#!/usr/bin/env python3
"""
check_doc_counts.py — skill counts in the README and plugin manifests match disk.

Adapted from scripts/check_doc_counts.py in elementalsouls/Claude-BugHunter (MIT):
https://github.com/elementalsouls/Claude-BugHunter/blob/main/scripts/check_doc_counts.py

Ground truth is the set of skills/<name>/SKILL.md directories. Checked:

  - README hero line `**N skills**, one repo`
  - README pack-table links `skills/<name>/SKILL.md` (the set, not only the count)
  - plugin.json and marketplace.json descriptions contain that same N
  - marketplace entry name matches plugin.json, source is `./`
  - README install lines for the marketplace add command and `npx skills add`
  - README attributes elementalsouls/Claude-BugHunter
  - docs/ECOSYSTEM_BRIEF.md is present

Exit code 0 = match, 1 = at least one mismatch. Stdlib only.

Usage:
    python3 scripts/check_doc_counts.py
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(REPO, "skills")

HERO_RE = re.compile(r"\*\*(\d+) skills\*\*, one repo")
LINK_RE = re.compile(r"skills/([a-z0-9-]+)/SKILL\.md")
COUNT_RE = re.compile(r"\b(\d+) skills\b")

MARKETPLACE_ADD = "/plugin marketplace add dbottrader/asin-hhc-skills"
SKILLS_ADD = "npx skills add dbottrader/asin-hhc-skills"
TEMPLATE_URL = "https://github.com/elementalsouls/Claude-BugHunter"
BRIEF_TITLE = "# ASIN-HHC Ecosystem — Shared Brief"


def skill_names():
    names = []
    for entry in sorted(os.listdir(SKILLS_DIR)):
        if os.path.isfile(os.path.join(SKILLS_DIR, entry, "SKILL.md")):
            names.append(entry)
    return names


def read(path):
    with open(os.path.join(REPO, path), encoding="utf-8") as fh:
        return fh.read()


def load_json(path):
    with open(os.path.join(REPO, path), encoding="utf-8") as fh:
        return json.load(fh)


def count_phrase_errors(label, text, actual):
    found = [int(n) for n in COUNT_RE.findall(text)]
    if not found:
        return [f"{label}: no 'N skills' phrase; expected {actual}"]
    bad = [n for n in found if n != actual]
    if bad:
        return [f"{label}: says {bad} skill(s) but disk has {actual}"]
    return []


def main():
    errors = []
    names = skill_names()
    actual = len(names)
    if actual == 0:
        errors.append("skills/: no SKILL.md directories found")

    readme = read("README.md")
    hero = HERO_RE.search(readme)
    if not hero:
        errors.append("README.md: hero line `**N skills**, one repo` not found")
    elif int(hero.group(1)) != actual:
        errors.append(
            f"README.md: hero says {hero.group(1)} skills but disk has {actual}"
        )

    linked = LINK_RE.findall(readme)
    if sorted(set(linked)) != names:
        errors.append(
            "README.md: skill links "
            f"{sorted(set(linked))} != directories {names}"
        )
    if len(linked) != len(set(linked)):
        errors.append(f"README.md: duplicate skill links {linked}")

    for needle, label in (
        (MARKETPLACE_ADD, "marketplace add command"),
        (SKILLS_ADD, "npx skills add command"),
        (TEMPLATE_URL, "Claude-BugHunter attribution"),
    ):
        if needle not in readme:
            errors.append(f"README.md: missing {label}: {needle}")

    plugin = load_json(".claude-plugin/plugin.json")
    market = load_json(".claude-plugin/marketplace.json")
    plugins = market.get("plugins") or []
    if len(plugins) != 1:
        errors.append(f"marketplace.json: expected 1 plugin entry, found {len(plugins)}")
    else:
        entry = plugins[0]
        if entry.get("name") != plugin.get("name"):
            errors.append(
                "plugin name mismatch: "
                f"plugin.json {plugin.get('name')!r} vs marketplace {entry.get('name')!r}"
            )
        if entry.get("source") != "./":
            errors.append(f"marketplace.json: source is {entry.get('source')!r}, expected './'")
        if entry.get("description") != plugin.get("description"):
            errors.append("plugin.json description != marketplace plugin description")
        if entry.get("version") != plugin.get("version"):
            errors.append("plugin.json version != marketplace plugin version")
        install_id = f"/plugin install {plugin.get('name')}@{market.get('name')}"
        if install_id not in readme:
            errors.append(f"README.md: missing install id {install_id}")
        errors += count_phrase_errors("plugin.json description", plugin.get("description", ""), actual)
        errors += count_phrase_errors(
            "marketplace.json plugin description", entry.get("description", ""), actual
        )

    if not market.get("name"):
        errors.append("marketplace.json: missing name")
    owner = market.get("owner") or {}
    if not owner.get("name"):
        errors.append("marketplace.json: owner.name is required")

    brief_path = os.path.join(REPO, "docs", "ECOSYSTEM_BRIEF.md")
    if not os.path.isfile(brief_path):
        errors.append("docs/ECOSYSTEM_BRIEF.md is missing")
    else:
        brief = read("docs/ECOSYSTEM_BRIEF.md")
        if not brief.startswith(BRIEF_TITLE):
            errors.append("docs/ECOSYSTEM_BRIEF.md: unexpected title")

    for error in errors:
        print(f"::error:: {error}" if os.environ.get("GITHUB_ACTIONS") else f"ERROR {error}")

    print(f"\nGround truth: {actual} skills ({', '.join(names)}).")
    print(f"Doc/manifest checks: {len(errors)} error(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
