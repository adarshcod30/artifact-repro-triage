"""Do real users complain about the defects this tool detects?

THE VALIDATION GAP
------------------
Everything so far is either self-referential (we injected the fault, so of course
we detect it) or mismatched (ACM badges measure a past state). Neither answers the
question a sceptical reviewer should ask: **does anyone actually care?**

GitHub issues are an independent, unprompted signal. When a researcher tries to
run an artifact and the documented script is missing, they frequently open an
issue saying so - in their own words, with no knowledge of this project.

So: for each artifact, count issues whose text matches reproduction-failure
language, and compare repositories the verifier flags against those it does not.

WHAT WOULD FALSIFY THIS
-----------------------
If flagged and unflagged repositories complain at the same rate, the verifier is
detecting something users do not experience, and the finding is null. That
outcome is reported as-is. The hypothesis is stated before the measurement
precisely so it cannot be adjusted afterwards.

CAVEAT, STATED UP FRONT
-----------------------
This is correlational and the sample is small. It cannot establish that broken
paths *cause* complaints - a busy repository attracts more issues of every kind.
Issue volume is therefore reported alongside the rate.
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

from artifact_triage.corpus.github import API, _get
from artifact_triage.common.provenance import stamp

OUT = Path("results/issue_validation.json")

# Language a person uses when documented instructions fail. Deliberately narrow:
# generic words like "error" or "problem" would match ordinary bug reports and
# wash out the signal.
COMPLAINT = re.compile(
    r"(?i)("
    r"no such file|file not found|cannot find|can't find|could not find|"
    r"does not exist|doesn'?t exist|missing (?:file|script|folder|directory)|"
    r"not (?:present|included) in the repo|"
    r"where (?:is|are|can i find) the|"
    r"unable to (?:locate|reproduce)|cannot reproduce|can't reproduce|"
    r"failed to reproduce|no module named|importerror"
    r")")


def issues(slug: str, limit: int = 100) -> list[dict]:
    key = "issues-" + slug.replace("/", "__")
    try:
        data = _get(f"{API}/repos/{slug}/issues?state=all&per_page={limit}", key)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    # Pull requests are returned by this endpoint too; they are not user reports.
    return [i for i in data if "pull_request" not in i]


def complaints(slug: str) -> dict:
    items = issues(slug)
    hits = []
    for i in items:
        text = f"{i.get('title', '')}\n{(i.get('body') or '')[:2000]}"
        m = COMPLAINT.search(text)
        if m:
            hits.append({"number": i.get("number"),
                         "title": (i.get("title") or "")[:110],
                         "matched": m.group(1).lower()})
    return {"n_issues": len(items), "n_complaints": len(hits),
            "complaint_rate": round(len(hits) / len(items), 3) if items else 0.0,
            "examples": hits[:4]}


def main() -> None:
    src = Path("results/prevalence.json")
    if not src.exists():
        raise SystemExit("run eval.prevalence first")
    rows = json.loads(src.read_text())["per_artifact"]

    # Only repositories with checkable claims can be flagged or not flagged.
    checkable = [r for r in rows if r["claims"] > 0]
    flagged = [r for r in checkable if r["broken"] > 0]
    clean = [r for r in checkable if r["broken"] == 0]
    # Balance the comparison and bound the API cost.
    n = min(len(flagged), len(clean), 60)
    flagged = sorted(flagged, key=lambda r: -r["broken_ratio"])[:n]
    clean = sorted(clean, key=lambda r: -r["claims"])[:n]
    print(f"comparing {len(flagged)} flagged vs {len(clean)} clean repositories")

    out = {"flagged": [], "clean": []}
    for group, items in (("flagged", flagged), ("clean", clean)):
        for i, r in enumerate(items, 1):
            c = complaints(r["artifact_id"])
            c["artifact_id"] = r["artifact_id"]
            c["broken"] = r["broken"]
            c["claims"] = r["claims"]
            out[group].append(c)
            if i % 15 == 0:
                print(f"  {group}: {i}/{len(items)}")

    def summarise(group: str) -> dict:
        g = [x for x in out[group] if x["n_issues"] > 0]
        if not g:
            return {"n_repos_with_issues": 0}
        return {
            "n_repos": len(out[group]),
            "n_repos_with_issues": len(g),
            "repos_with_a_complaint": sum(1 for x in g if x["n_complaints"] > 0),
            "share_with_a_complaint": round(
                sum(1 for x in g if x["n_complaints"] > 0) / len(g), 3),
            "median_issues": statistics.median(x["n_issues"] for x in g),
            "mean_complaint_rate": round(
                statistics.mean(x["complaint_rate"] for x in g), 4),
        }

    fs, cs = summarise("flagged"), summarise("clean")
    print("\n" + "=" * 70)
    print("DO USERS COMPLAIN ABOUT WHAT THE VERIFIER DETECTS?")
    print("=" * 70)
    print(f"{'':<34}{'flagged':>16}{'clean':>16}")
    print("-" * 70)
    for label, key in (("repos with >=1 issue", "n_repos_with_issues"),
                       ("repos with a complaint", "repos_with_a_complaint"),
                       ("share with a complaint", "share_with_a_complaint"),
                       ("median issue count", "median_issues"),
                       ("mean complaint rate", "mean_complaint_rate")):
        print(f"{label:<34}{str(fs.get(key, 'n/a')):>16}{str(cs.get(key, 'n/a')):>16}")
    print("-" * 70)
    fshare = fs.get("share_with_a_complaint")
    cshare = cs.get("share_with_a_complaint")
    if fshare is not None and cshare is not None:
        if fshare > cshare:
            print(f"Repositories the verifier flags are MORE likely to carry a "
                  f"reproduction complaint ({fshare:.0%} vs {cshare:.0%}).")
        elif fshare == cshare:
            print("NULL RESULT: identical complaint rates.")
        else:
            print(f"NULL / REVERSED: flagged {fshare:.0%} vs clean {cshare:.0%}. "
                  f"The verifier detects something users do not report.")
    # The engagement figure reframes the whole comparison, so it is printed
    # with the result rather than buried in the JSON.
    tot = len(out["flagged"]) + len(out["clean"])
    with_any = sum(1 for g in ("flagged", "clean")
                   for x in out[g] if x["n_issues"] > 0)
    print()
    print(f"ENGAGEMENT: only {with_any}/{tot} repositories "
          f"({with_any/tot:.0%}) have ANY issues at all.")
    print("This bounds what the comparison can show. A GitHub issue requires")
    print("someone to try the artifact, hit a problem, and take the time to")
    print("report it. Most research artifacts are published and never exercised,")
    print("so silence is not evidence that they work - and user complaints are")
    print("a weak instrument for validating a defect detector, whichever way")
    print("the numbers fall.")
    print()
    print("Correlational only. Small n on the clean side; treat the point")
    print("estimates as indistinguishable rather than as a measured equality.")
    print("=" * 70)

    OUT.write_text(json.dumps({
        "_provenance": stamp("issue_validation"),
        "flagged_summary": fs, "clean_summary": cs, "detail": out}, indent=1))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
