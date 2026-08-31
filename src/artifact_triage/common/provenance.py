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
    # A kind MISSING from this map hashes nothing, so every result of that kind
    # would look permanently "current" - a silent false pass, which is worse
    # than an alarm. Five result files were unstamped and five kinds were
    # unmapped; both gaps are closed here.
    "subtle": ["src/artifact_triage/eval/subtle_control.py",
               "src/artifact_triage/solution/verify.py",
               "src/artifact_triage/corpus/fetch.py"],
    "ablation": ["src/artifact_triage/eval/ablation.py",
                 "src/artifact_triage/solution/verify.py",
                 "src/artifact_triage/corpus/fetch.py"],
    "comparison": ["src/artifact_triage/eval/compare.py",
                   "src/artifact_triage/eval/metrics.py"],
    "adversarial": ["src/artifact_triage/eval/adversarial.py",
                    "src/artifact_triage/solution/evidence.py",
                    "src/artifact_triage/solution/verify.py",
                    "src/artifact_triage/common/rubric.py",
                    "src/artifact_triage/corpus/fetch.py"],
    "issue_validation": ["src/artifact_triage/eval/issue_validation.py",
                         "src/artifact_triage/solution/verify.py",
                         "src/artifact_triage/corpus/fetch.py"],
    "resolution_audit": ["src/artifact_triage/eval/resolution_audit.py",
                         "src/artifact_triage/eval/prevalence.py",
                         "src/artifact_triage/solution/verify.py",
                         "src/artifact_triage/corpus/fetch.py"],
    "linkchecker_gap": ["src/artifact_triage/eval/linkchecker_gap.py",
                        "src/artifact_triage/eval/prevalence.py",
                        "src/artifact_triage/solution/verify.py",
                        "src/artifact_triage/corpus/fetch.py"],
    "prevalence": ["src/artifact_triage/eval/prevalence.py",
                   "src/artifact_triage/solution/verify.py",
                   "src/artifact_triage/corpus/fetch.py"],
}


def commit() -> str:
    """The commit, marked `-dirty` when the tree had uncommitted changes.

    Without the mark this field quietly lies. A result produced from a modified
    working tree was labelled with a commit whose code never produced it - the
    hash looks authoritative and cannot recover what actually ran. That happened
    here: results stamped `7363401` were produced by code that only landed two
    commits later, and comparing against that commit gave a misleading answer
    until the discrepancy was noticed by hand.
    """
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, cwd=ROOT, timeout=10)
        sha = out.stdout.strip() or "unknown"
        st = subprocess.run(["git", "status", "--porcelain",
                             "src", "data/fixtures"],
                            capture_output=True, text=True, cwd=ROOT, timeout=15)
        if st.stdout.strip():
            sha += "-dirty"
        return sha
    except Exception:
        return "unknown"


def changed_functions(kind: str, since: str) -> list[str]:
    """Which influencing FUNCTIONS differ from a recorded commit, by AST.

    A file-level fingerprint says a result is stale without saying why, and a
    comment or an unrelated helper is enough to trip it. Comparing the parsed
    functions tells the reader whether the change could possibly matter - e.g.
    "only fetch.build changed", which experiments reading committed fixtures
    never call.

    Best effort: returns [] if the commit is unavailable or unparseable.
    """
    import ast
    out: list[str] = []
    for rel in sorted(INFLUENCERS.get(kind, [])):
        try:
            old = subprocess.run(["git", "show", f"{since}:{rel}"],
                                 capture_output=True, text=True, cwd=ROOT,
                                 timeout=15).stdout
            if not old:
                continue
            def fns(src):
                t = ast.parse(src)
                return {n.name: ast.dump(n) for n in ast.walk(t)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            o, n = fns(old), fns((ROOT / rel).read_text())
            for name in sorted(set(o) | set(n)):
                if o.get(name) != n.get(name):
                    out.append(f"{Path(rel).name}:{name}")
        except Exception:
            continue
    return out


def fingerprint(kind: str) -> str:
    """Content hash of the modules that determine this kind of result."""
    h = hashlib.sha256()
    for rel in sorted(INFLUENCERS.get(kind, [])):
        p = ROOT / rel
        h.update(rel.encode())
        h.update(p.read_bytes() if p.exists() else b"<missing>")
    return h.hexdigest()[:12]


# The CORPUS is an input, not code, and it had no fingerprint at all.
#
# `scrub.py` decides the exact README text every model reads - it is the single
# strongest lever on what a model can possibly conclude - yet it appeared in no
# influencer list. The same blind spot `fetch.py` had, and the changelog already
# says why that matters: a detector that cannot see something certifies it.
#
# But scrub.py does NOT influence a result directly. `baseline` and `solution`
# read committed fixtures that were scrubbed when the corpus was built, so the
# fixtures are the interface. Adding scrub.py to every list would mark results
# stale for a change provably unable to alter them - the cry-wolf failure that
# the budget/inference split was made to stop.
#
# So the corpus is fingerprinted separately, over the fixture BYTES plus the two
# modules that produce them. A change to scrubbing marks the corpus stale, which
# is true; results stay current while the fixtures they actually consumed are
# unchanged, which is also true.
CORPUS_INPUTS = ["src/artifact_triage/corpus/scrub.py",
                 "src/artifact_triage/corpus/fetch.py"]

# Only these read `data/fixtures`. `prevalence` has its own cache and recomputes
# everything derived on load, so its inputs cannot drift from its code - the
# code fingerprint alone covers it.
#
# Applying one global corpus hash to every kind was itself a cry-wolf bug,
# introduced in the very mechanism added to stop cry-wolf: rebuilding the
# fixtures marked `prevalence` stale for data it never reads. A fingerprint must
# cover exactly what a result consumed. Too little certifies stale numbers; too
# much trains you to ignore it.
FIXTURE_KINDS = {"verify", "baseline", "solution", "falsified",
                 "negative_control", "subtle", "ablation", "adversarial",
                 "comparison"}


def corpus_fingerprint() -> str:
    h = hashlib.sha256()
    for rel in CORPUS_INPUTS:
        p = ROOT / rel
        h.update(rel.encode())
        h.update(p.read_bytes() if p.exists() else b"<missing>")
    for f in sorted((ROOT / "data" / "fixtures").glob("*.json")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


def stamp(kind: str) -> dict:
    """Attach to any results payload as `_provenance`."""
    out = {"kind": kind, "commit": commit(),
           "code_fingerprint": fingerprint(kind)}
    if kind in FIXTURE_KINDS:
        out["corpus_fingerprint"] = corpus_fingerprint()
    return out


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
    # Absent on results recorded before corpus fingerprinting existed. That is
    # "not recorded", not "stale" - claiming otherwise would be inventing a
    # failure, which is the same dishonesty as hiding one.
    if kind not in FIXTURE_KINDS:
        return False, "current"          # does not consume the fixtures at all
    recorded = prov.get("corpus_fingerprint")
    if recorded is None:
        return False, "current (corpus fingerprint predates this check)"
    if recorded != corpus_fingerprint():
        return True, (f"the corpus changed since this ran (fixtures or "
                      f"scrubbing differ: {recorded} vs {corpus_fingerprint()})")
    return False, "current"
