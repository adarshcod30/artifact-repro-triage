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
            "leaked_badge": fx["readme_scrub"]["leaked"],
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

    leaked = sum(1 for r in rows if r["leaked_badge"])
    print(f"\n  READMEs disclosing their own badge  : {leaked}/{len(rows)} "
          f"({leaked/len(rows):.0%})")

    # --- decay hypothesis ----------------------------------------------------
    dated = [r for r in checkable if r["stale_days"] is not None]
    decay = None
    if len(dated) >= 12:
        dated.sort(key=lambda r: r["stale_days"])
        half = len(dated) // 2
        fresh, stale = dated[:half], dated[half:]
        f_ratio = statistics.mean(r["broken_ratio"] for r in fresh)
        s_ratio = statistics.mean(r["broken_ratio"] for r in stale)
        decay = {
            "fresh_n": len(fresh), "stale_n": len(stale),
            "fresh_median_days": round(statistics.median(r["stale_days"] for r in fresh)),
            "stale_median_days": round(statistics.median(r["stale_days"] for r in stale)),
            "fresh_broken_ratio": round(f_ratio, 4),
            "stale_broken_ratio": round(s_ratio, 4),
            "supports_decay": s_ratio > f_ratio,
        }
        print("\n  DECAY HYPOTHESIS (do older artifacts have more broken claims?)")
        print(f"    recently pushed  (n={len(fresh)}, median "
              f"{decay['fresh_median_days']}d old): {f_ratio:.3f}")
        print(f"    least recent     (n={len(stale)}, median "
              f"{decay['stale_median_days']}d old): {s_ratio:.3f}")
        print(f"    -> {'SUPPORTS' if decay['supports_decay'] else 'DOES NOT SUPPORT'}"
              f" the decay hypothesis")
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
