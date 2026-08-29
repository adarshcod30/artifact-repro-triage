"""How widespread is broken documentation in research artifacts?

The badge-labelled corpus answers "can the system agree with experts?". This
answers a different and arguably more useful question: **how common is the defect
at all?**

It is only possible because the verifier needs no labels and no model. It is
deterministic Python over a file tree, so it can be pointed at every artifact we
can find, for free, and the result is a measurement about the world rather than a
score for a classifier.

TESTABLE HYPOTHESIS
-------------------
Published work reports that over 40% of "functional" artifacts from 2024-2025
fail within months, from drifting dependencies and incomplete environments. If
artifacts decay, then **older artifacts should have more broken claims than newer
ones**. That is checkable here: every repository carries a last-push date.

A null result is reported as a null result.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from artifact_triage.corpus.fetch import (default_branch_sha, readme,
                                          referenced_paths, signals_present, tree)
from artifact_triage.corpus.github import API, _get
from artifact_triage.corpus.scrub import scrub
from artifact_triage.solution.verify import verify

SRC = Path("data/discovered.jsonl")
OUT = Path("results/prevalence.json")
CACHE = Path("data/cache/prevalence")


def profile(slug: str) -> dict | None:
    """Build the minimum fact sheet the verifier needs, plus a last-push date."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{slug.replace('/', '__')}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    try:
        meta = _get(f"{API}/repos/{slug}", "repo-" + slug.replace("/", "__"))
        _, sha = default_branch_sha(slug)
        entries = tree(slug, sha)
        raw = readme(slug)
    except Exception as exc:
        print(f"    ! {slug}: {type(exc).__name__}")
        return None
    rep = scrub(raw)
    paths = [e["path"] for e in entries]
    fx = {
        "artifact_id": slug,
        "paper_title": meta.get("description") or "",
        "commit": sha,
        "n_files": len(paths),
        "file_tree": paths,
        "readme": rep.text[:20000],
        "readme_present": bool(raw),
        "readme_scrub": {"leaked": rep.leaked, "hits": rep.hits},
        "signals": signals_present(paths),
        "readme_referenced_paths": referenced_paths(rep.text),
        "pushed_at": meta.get("pushed_at"),
        "created_at": meta.get("created_at"),
        "stars": meta.get("stargazers_count", 0),
        "archived": meta.get("archived", False),
    }
    cached.write_text(json.dumps(fx))
    return fx


def age_days(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - d).total_seconds() / 86400


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"{SRC} missing - run corpus.discover first")
    items = [json.loads(l) for l in open(SRC)]
    print(f"discovered artifacts: {len(items)}")

    rows = []
    for i, item in enumerate(items, 1):
        fx = profile(item["repo"])
        if fx is None or not fx["readme_present"]:
            continue
        ev = verify(fx)
        rows.append({
            "artifact_id": fx["artifact_id"],
            "n_files": fx["n_files"],
            "claims": ev.claims_total,
            "broken": ev.claims_broken,
            "broken_ratio": ev.broken_ratio,
            "broken_paths": ev.broken_paths[:8],
            "has_dependency_manifest": ev.has_dependency_manifest,
            "has_container": ev.has_container,
            "has_ci": ev.has_ci,
            "has_licence": ev.has_licence,
            "has_tests": ev.has_tests,
            "readme_bytes": ev.readme_bytes,
            "stale_days": age_days(fx.get("pushed_at")),
            "stars": fx.get("stars", 0),
            "archived": fx.get("archived", False),
            "scrub_hits": fx["readme_scrub"]["hits"],
            # A shields.io "build passing" badge is not an ACM tier disclosure.
            # Only these patterns indicate a README revealing its own grade.
            "leaked_tier": any(k in fx["readme_scrub"]["hits"] for k in
                               ("acm_badge_phrase", "badge_tier_bare",
                                "results_reproduced", "ae_committee")),
        })
        if i % 20 == 0:
            print(f"  [{i}/{len(items)}] profiled {len(rows)}")

    # --- headline prevalence -------------------------------------------------
    checkable = [r for r in rows if r["claims"] > 0]
    with_broken = [r for r in checkable if r["broken"] > 0]
    total_claims = sum(r["claims"] for r in checkable)
    total_broken = sum(r["broken"] for r in checkable)

    print("\n" + "=" * 68)
    print("PREVALENCE OF BROKEN README CLAIMS IN RESEARCH ARTIFACTS")
    print("=" * 68)
    print(f"  artifacts profiled                 : {len(rows)}")
    print(f"  with checkable path claims         : {len(checkable)}")
    print(f"  WITH >=1 BROKEN CLAIM              : {len(with_broken)} "
          f"({len(with_broken)/len(checkable):.1%})" if checkable else "  n/a")
    print(f"  total claims checked               : {total_claims}")
    print(f"  total broken                       : {total_broken} "
          f"({total_broken/total_claims:.1%})" if total_claims else "")
    if checkable:
        med = statistics.median(r["broken_ratio"] for r in checkable)
        print(f"  median broken-claim ratio          : {med:.3f}")

    # --- reproducibility infrastructure --------------------------------------
    print("\n  Infrastructure present:")
    for key, label in (("has_dependency_manifest", "dependency manifest"),
                       ("has_container", "container definition"),
                       ("has_ci", "CI configuration"),
                       ("has_tests", "tests"),
                       ("has_licence", "licence")):
        n = sum(1 for r in rows if r[key])
        print(f"    {label:<24} {n:>4}/{len(rows)}  ({n/len(rows):.0%})")

    tier_leak = sum(1 for r in rows if r["leaked_tier"])
    any_badge = sum(1 for r in rows if r["scrub_hits"])
    print(f"\n  READMEs disclosing an ACM tier      : {tier_leak}/{len(rows)} "
          f"({tier_leak/len(rows):.0%})")
    print(f"  (any badge-like text redacted      : {any_badge}/{len(rows)} - "
          f"mostly ordinary CI/coverage badges, not tier disclosure)")

    # --- decay hypothesis ----------------------------------------------------
    # A median split is the wrong instrument here: last-push dates are heavily
    # skewed toward "recently touched", so both halves end up recent (medians of
    # 0 and 33 days) even though the corpus spans nearly six years. Fixed age
    # buckets compare genuinely old artifacts against genuinely new ones.
    BUCKETS = [(0, 90, "under 3 months"), (90, 365, "3-12 months"),
               (365, 730, "1-2 years"), (730, 10**6, "over 2 years")]
    dated = [r for r in checkable if r["stale_days"] is not None]
    decay = None
    if len(dated) >= 20:
        rows_by_bucket = []
        for lo, hi, label in BUCKETS:
            g = [r for r in dated if lo <= r["stale_days"] < hi]
            if len(g) >= 8:  # too few to mean anything
                rows_by_bucket.append({
                    "label": label, "n": len(g),
                    "median_days": round(statistics.median(r["stale_days"] for r in g)),
                    "mean_broken_ratio": round(
                        statistics.mean(r["broken_ratio"] for r in g), 4),
                    "share_with_broken": round(
                        sum(1 for r in g if r["broken"] > 0) / len(g), 3),
                })
        print("\n  DECAY HYPOTHESIS (do older artifacts have more broken claims?)")
        print(f"    {'age bucket':<18}{'n':>5}{'median':>9}"
              f"{'broken ratio':>15}{'% with a break':>16}")
        for b in rows_by_bucket:
            print(f"    {b['label']:<18}{b['n']:>5}{b['median_days']:>8}d"
                  f"{b['mean_broken_ratio']:>15.3f}{b['share_with_broken']:>15.0%}")
        conclusive = len(rows_by_bucket) >= 3
        trend = None
        if conclusive:
            ratios = [b["mean_broken_ratio"] for b in rows_by_bucket]
            delta = ratios[-1] - ratios[0]
            # Check "flat" FIRST. An earlier version tested `increasing` first,
            # so a delta of 0.001 was reported as an increasing trend - noise
            # dressed up as a finding.
            if abs(delta) < 0.05:
                trend = "flat"
            elif delta > 0:
                trend = "increasing"
            else:
                trend = "decreasing"
            print(f"    -> broken-claim ratio is {trend.upper()} with age "
                  f"(delta {delta:+.3f} across buckets)")
            if trend == "increasing":
                print("       CONSISTENT with the decay literature")
            elif trend == "flat":
                print("       NO age effect. The defect is present from")
                print("       publication rather than acquired over time - so it")
                print("       is not explained by dependency drift, and a reviewer")
                print("       could have caught it on day one.")
            else:
                print("       Broken claims DECREASE with age (unexpected;")
                print("       likely survivorship - maintained repos stay listed)")
            small = [b["label"] for b in rows_by_bucket if b["n"] < 15]
            if small:
                print(f"       CAVEAT: small n in bucket(s): {', '.join(small)}")
        else:
            print(f"    -> INCONCLUSIVE: only {len(rows_by_bucket)} populated "
                  f"bucket(s); need at least 3")
        decay = {"buckets": rows_by_bucket, "conclusive": conclusive,
                 "trend": trend,
                 "age_span_days": round(max(r["stale_days"] for r in dated) -
                                        min(r["stale_days"] for r in dated))}
    print("=" * 68)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "n_profiled": len(rows), "n_checkable": len(checkable),
        "n_with_broken": len(with_broken),
        "prevalence": round(len(with_broken) / len(checkable), 4) if checkable else None,
        "total_claims": total_claims, "total_broken": total_broken,
        "broken_claim_rate": round(total_broken / total_claims, 4) if total_claims else None,
        "decay": decay, "per_artifact": rows,
    }, indent=1))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
