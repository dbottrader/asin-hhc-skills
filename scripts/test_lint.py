#!/usr/bin/env python3
"""Negative and positive checks for scripts/lint_skills.py. Stdlib only."""
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINTER = os.path.join(REPO, "scripts", "lint_skills.py")
COUNTER = os.path.join(REPO, "scripts", "check_doc_counts.py")


def run(args, cwd=REPO):
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def write_skill(root, name, body):
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write(textwrap.dedent(body).lstrip("\n"))
    return path


GOOD = """\
    ---
    name: {name}
    description: A sufficiently long description of the skill that an agent can trigger on without any colon-space in the unquoted value.
    ---

    # {name}

    HHC is a token-ready credit, simulated by default.
    """


def expect(code, output, want, label):
    if code != want:
        print(f"FAIL {label}: exit {code}, expected {want}\n{output}")
        return 1
    print(f"ok   {label}")
    return 0


def main():
    failed = 0
    code, output = run([LINTER])
    failed += expect(code, output, 0, "repo skills lint clean")

    code, output = run([COUNTER])
    failed += expect(code, output, 0, "doc counts match disk")

    tmp = tempfile.mkdtemp(prefix="asinhhc-lint-")
    try:
        good = write_skill(tmp, "asinhhc-sample", GOOD.format(name="asinhhc-sample"))
        code, output = run([LINTER, good])
        failed += expect(code, output, 0, "well-formed skill passes")

        bad_yaml = write_skill(
            tmp,
            "asinhhc-colon",
            """\
            ---
            name: asinhhc-colon
            description: Use when an agent wants work: list the steps plainly and keep going until this sentence is long enough to pass the short-description warning easily.
            ---

            HHC is a token-ready credit, simulated by default.
            """,
        )
        code, output = run([LINTER, bad_yaml])
        failed += expect(code, output, 1, "unquoted colon-space fails")
        if "': '" not in output and ": '" not in output:
            print(f"FAIL unquoted colon-space did not mention the YAML rule\n{output}")
            failed += 1

        stale = write_skill(
            tmp,
            "asinhhc-stale",
            """\
            ---
            name: asinhhc-stale
            description: A sufficiently long description of the skill that an agent can trigger on without any colon-space in the unquoted value.
            ---

            HHC is a utility credit and not a token.
            """,
        )
        code, output = run([LINTER, stale])
        failed += expect(code, output, 1, "stale credit wording fails")

        mismatch = write_skill(
            tmp,
            "asinhhc-mismatch",
            GOOD.format(name="other-name"),
        )
        code, output = run([LINTER, mismatch])
        failed += expect(code, output, 1, "name/directory mismatch fails")

        long_desc = "x" * 1100
        too_long = write_skill(
            tmp,
            "asinhhc-long",
            f"""\
            ---
            name: asinhhc-long
            description: {long_desc}
            ---

            HHC is a token-ready credit, simulated by default.
            """,
        )
        code, output = run([LINTER, too_long])
        failed += expect(code, output, 1, "description over 1024 fails")

        leaked = write_skill(
            tmp,
            "asinhhc-leak",
            """\
            ---
            name: asinhhc-leak
            description: A sufficiently long description of the skill that an agent can trigger on without any colon-space in the unquoted value.
            ---

            HHC is a token-ready credit, simulated by default.
            Key AKIAIOSFODNN7EXAMPLE is the documented sample and must be allowed.
            Live AKIAREALKEYEXAMPLE1 should still... 
            """,
        )
        # The allowlist exempts lines containing EXAMPLE. Use a key with no EXAMPLE.
        leaked_path = os.path.join(leaked, "SKILL.md")
        with open(leaked_path, "a", encoding="utf-8") as handle:
            handle.write("\nAKIA" + "A" * 16 + "\n")
        code, output = run([LINTER, leaked])
        failed += expect(code, output, 1, "live AWS key fails")
    finally:
        shutil.rmtree(tmp)

    if failed:
        print(f"\n{failed} lint self-test(s) failed.")
        return 1
    print("\nLint self-test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
