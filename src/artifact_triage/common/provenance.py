"""Stamp every result with the code that produced it.

A results file is a claim about what the code does. If the code changes and the
result does not, the claim silently becomes false - the number still looks
authoritative, the file still parses, and nothing complains.

That is this project's own subject applied to itself: documentation that no
longer matches the thing it documents. So each result records the commit it was
produced at and a fingerprint of the modules that actually influence it, and
`check_claims.py` reports when a result predates a change to its own code.

The fingerprint is content-based, not timestamp-based: reformatting a comment in
an unrelated module must not invalidate a result, and editing the verifier must.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent

# Modules whose behaviour determines a result. Deliberately explicit: an
# automatic "everything under src/" fingerprint would invalidate every result
# on any edit, and a warning that always fires is a warning nobody reads.
INFLUENCERS = {
    "verify": ["src/artifact_triage/solution/verify.py",
               "src/artifact_triage/corpus/fetch.py"],
    "baseline": ["src/artifact_triage/baseline/run.py",
                 "src/artifact_triage/corpus/fetch.py",
                 "src/artifact_triage/common/rubric.py",
                 "src/artifact_triage/common/llm.py"],
    "solution": ["src/artifact_triage/solution/run.py",
                 "src/artifact_triage/solution/verify.py",
                 "src/artifact_triage/solution/evidence.py",
                 "src/artifact_triage/corpus/fetch.py",
                 "src/artifact_triage/common/rubric.py",
                 "src/artifact_triage/common/llm.py"],
    # fetch.py belongs in every one of these: it decides which claims exist at
    # all. Omitting it meant a change to the extractor invalidated `baseline`
    # and `solution` but silently left `falsified` looking current - a
    # staleness detector with a blind spot is worse than none, because it
    # certifies the thing it cannot see.
    "falsified": ["src/artifact_triage/eval/falsified_run.py",
                  "src/artifact_triage/solution/run.py",
                  "src/artifact_triage/solution/evidence.py",
                  "src/artifact_triage/solution/verify.py",
                  "src/artifact_triage/corpus/fetch.py",
                  "src/artifact_triage/baseline/run.py",
                  "src/artifact_triage/eval/negative_control.py"],
    "negative_control": ["src/artifact_triage/eval/negative_control.py",
                         "src/artifact_triage/solution/verify.py",
                         "src/artifact_triage/corpus/fetch.py"],
    "prevalence": ["src/artifact_triage/eval/prevalence.py",
                   "src/artifact_triage/solution/verify.py",
                   "src/artifact_triage/corpus/fetch.py"],
}


def commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, cwd=ROOT, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def fingerprint(kind: str) -> str:
    """Content hash of the modules that determine this kind of result."""
    h = hashlib.sha256()
    for rel in sorted(INFLUENCERS.get(kind, [])):
        p = ROOT / rel
        h.update(rel.encode())
        h.update(p.read_bytes() if p.exists() else b"<missing>")
    return h.hexdigest()[:12]


def stamp(kind: str) -> dict:
    """Attach to any results payload as `_provenance`."""
    return {"kind": kind, "commit": commit(), "code_fingerprint": fingerprint(kind)}


def is_stale(payload: dict) -> tuple[bool, str]:
    """Does this result predate a change to the code that produced it?"""
    prov = payload.get("_provenance")
    if not prov:
        return True, "no provenance recorded - cannot tell which code produced it"
    kind = prov.get("kind", "")
    now = fingerprint(kind)
    if prov.get("code_fingerprint") != now:
        return True, (f"produced at commit {prov.get('commit')} by different "
                      f"code (fingerprint {prov.get('code_fingerprint')} vs "
                      f"{now} now)")
    return False, "current"
