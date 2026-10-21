#!/usr/bin/env python3
"""asinhhc-verify — read-only replay of the ASIN-HHC mesh hash-chained ledger.

Independently recomputes the ledger under pinned canon v1 and reports,
segment by segment, what verifies and what does not. Read-only: it makes
GET requests only, needs no token, and writes nothing anywhere.

Canon v1 (pinned):
  entry_hash = SHA-256( canonical_json( {ts, actor, kind, payload, prev_hash} ) )
  canonical_json = JSON with sort_keys=True, separators (',',':'),
                   ensure_ascii=True, encoded UTF-8.
  Genesis prev_hash = 64 zero characters.

Procedure (mirrors SKILL.md):
  1. Self-test: fetch GET /receipt/vectors and reproduce every pinned
     known-answer hash before trusting your own implementation.
  2. Page the ledger: GET /ledger?since=<seq> until a short page returns.
  3. Recompute every entry hash; walk prev_hash linkage across the chain.
  4. Segment-aware verdict: entries carry a `canon` field. Pre-v1 entries
     (canon='v0-compat', legacy seq 1-15) do NOT verify under canon v1 —
     report the first failing sequence, never skip it, never force it.
     The canonical (v1) segment is judged on its own linkage + hashes.
  5. Cross-check against the server's own GET /ledger/verify.

Usage:
  python3 verify_replay.py <mesh-api-base-url>
  # e.g. python3 verify_replay.py http://localhost:8220

Output: a JSON report on stdout. Exit code 0 if the canonical segment
verifies to the tip (legacy state is reported, not hidden); 1 otherwise.
"""
import hashlib
import json
import sys
import urllib.request
from collections import Counter

ZERO = "0" * 64


def get(base, path):
    req = urllib.request.Request(base.rstrip("/") + path,
                                 headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def canon_v1(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def sha_hex(b):
    return hashlib.sha256(b).hexdigest()


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    base = sys.argv[1]

    # 1. Self-test against the pinned known-answer vectors.
    vec = get(base, "/receipt/vectors")
    vectors = vec["vectors"]
    vectors_ok = all(sha_hex(canon_v1(v["input"])) == v["canon_sha256"]
                     for v in vectors)
    if not vectors_ok:
        print(json.dumps({"vectors_selftest": False,
                          "error": "canon implementation failed the pinned "
                                   "known-answer vectors — fix your canon "
                                   "before trusting any replay result."},
                         indent=2))
        return 1

    # 2. Page the full ledger.
    entries = []
    since = 0
    while True:
        page = get(base, "/ledger?since=%d" % since)
        es = page["entries"]
        if not es:
            break
        entries.extend(es)
        since = es[-1]["seq"]
        if len(es) < 200:
            break

    # 3 + 4. Recompute, walk linkage, judge segment by segment.
    kinds = Counter(e["kind"] for e in entries)
    canons = Counter(e["canon"] for e in entries)
    prev = ZERO
    first_v1_seq = None
    seg_legacy = []
    legacy_recompute_match = []
    hash_fail_v1 = []
    link_breaks = []
    for e in entries:
        if e["prev_hash"] != prev:
            link_breaks.append(e["seq"])
        body = {"ts": e["ts"], "actor": e["actor"], "kind": e["kind"],
                "payload": e["payload"], "prev_hash": e["prev_hash"]}
        match = sha_hex(canon_v1(body)) == e["hash"]
        if e["canon"] == "v1":
            if first_v1_seq is None:
                first_v1_seq = e["seq"]
            if not match:
                hash_fail_v1.append(e["seq"])
        else:
            seg_legacy.append(e["seq"])
            if match:
                legacy_recompute_match.append(e["seq"])
        prev = e["hash"]

    v1_entries = [e for e in entries if e["canon"] == "v1"]
    canon_seg_ok = bool(v1_entries) and not hash_fail_v1 and all(
        entries[i]["prev_hash"] == entries[i - 1]["hash"]
        for i in range(1, len(entries)) if entries[i]["canon"] == "v1")

    # 5. Server cross-check.
    lv = get(base, "/ledger/verify")

    tip = entries[-1] if entries else None
    report = {
        "vectors_selftest": True,
        "vectors_count": len(vectors),
        "height": tip["seq"] if tip else 0,
        "tip_hash": tip["hash"] if tip else ZERO,
        "entries_recomputed": len(entries),
        "kind_counts": dict(kinds),
        "canon_counts": dict(canons),
        "legacy_segment": {
            "seqs": seg_legacy,
            "first_failing_seq_under_pinned_canon":
                seg_legacy[0] if seg_legacy else None,
            "recompute_under_canon_v1_matches": legacy_recompute_match,
        },
        "v1_segment": {
            "first_v1_seq": first_v1_seq,
            "count": len(v1_entries),
            "hash_failures": hash_fail_v1,
            "segment_verifies_to_tip": canon_seg_ok,
        },
        "linkage_breaks": link_breaks,
        "chain_verifies_to_tip_under_pinned_canon":
            (not seg_legacy and not hash_fail_v1 and not link_breaks),
        "server_ledger_verify": {"ok": lv.get("ok"),
                                 "failing_seq": lv.get("failing_seq")},
    }
    print(json.dumps(report, indent=2))
    return 0 if canon_seg_ok else 1


if __name__ == "__main__":
    sys.exit(main())
