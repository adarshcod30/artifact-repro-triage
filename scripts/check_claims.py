"""Verify that every number claimed in the documentation matches the results.

This project detects READMEs whose claims have drifted from their repository.
Its own README quotes roughly twenty figures from `results/*.json` - detection
rates, prevalence, corpus sizes, spend - and nothing checked that they still
agree with the data after each re-run.

That is the same defect, one level up: a document whose claims are no longer
verified against the thing it describes.

So each claim is registered here with the results file it comes from. If a
re-run changes a number and the prose is not updated, this fails and names both
values. A write-up that cannot be checked against its own data is exactly what
this project argues against.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(rel: str):
    p = ROOT / rel
    return json.loads(p.read_text()) if p.exists() else None


def claims() -> list[tuple[str, str, str, str]]:
    """(document, literal string that must appear, actual value, source)."""
    out: list[tuple[str, str, str, str]] = []

    fr = load("results/falsified_run.json")
    if fr:
        sr = fr.get("solution_rates") or []
        br = fr.get("baseline_rates") or []
        if sr:
            out.append(("README.md", f"{sum(sr)/len(sr):.0%}",
                        "solution detection mean", "falsified_run.json"))
        if br:
            out.append(("README.md", f"{sum(br)/len(br):.0%}",
                        "baseline detection mean", "falsified_run.json"))
        # Derive the floor-free figure from the per-artifact records of EVERY
        # model run, rather than a top-level key. The key did not exist, so
        # this claim was being silently skipped - a claim checker that quietly
        # omits a claim is the same defect class it exists to catch.
        tb = ts = tn = 0
        for fname in ("results/falsified_run.json", "results/falsified_llama.json"):
            d = load(fname)
            if not d:
                continue
            for t in d.get("per_trial", []):
                for r in t.get("per_artifact", []):
                    tn += 1
                    tb += bool(r["systems"]["baseline"]["mentions_absence"])
                    ts += bool(r["systems"]["solution"]["mentions_absence"])
        if tn:
            out.append(("README.md", f"{ts}/{tn}",
                        "floor-free: solution cites absence",
                        "falsified_run.json + falsified_llama.json"))
            out.append(("README.md", f"{tb}/{tn}",
                        "floor-free: baseline cites absence",
                        "falsified_run.json + falsified_llama.json"))
        if fr.get("trials"):
            out.append(("README.md", str(fr["trials"]), "trial count",
                        "falsified_run.json"))

    # The negative result is a documented claim too, and it drifted: the table
    # read 0.733 / 1.000 long after a re-run put both at 0.800. A result kept
    # visible for honesty is worthless if its numbers are stale.
    cp = load("results/comparison.json")
    if cp:
        for sysname in ("baseline", "solution"):
            if cp.get(sysname):
                # The video script quotes these too. A spoken number is still a
                # claim, and it had drifted there as well.
                for doc in ("README.md", "docs/VIDEO_SCRIPT.md"):
                    out.append((doc, f"{cp[sysname]['mae']:.3f}",
                                f"{sysname} MAE (badge agreement)",
                                "comparison.json"))
        best = next((c for c in cp.get("controls", [])
                     if c["system"] == cp.get("best_control")), None)
        if best:
            out.append(("README.md", f"{best['mae']:.3f}",
                        f"best constant control ({best['system']})",
                        "comparison.json"))

    nc = load("results/negative_control.json")
    if nc:
        out.append(("README.md", f"{nc['injected']}/{nc['injected']}",
                    "negative control detection", "negative_control.json"))
        out.append(("CHANGELOG.md", f"{nc['injected']}/{nc['injected']}",
                    "negative control detection", "negative_control.json"))

    pv = load("results/prevalence.json")
    if pv:
        # Prefer the display strings the producer wrote, so the checker and the
        # producer can never disagree about rounding.
        disp = pv.get("display") or {}
        for key, label in (("prevalence", "prevalence of broken claims"),
                           ("broken_claim_rate", "broken claim rate"),
                           ("total_claims", "total claims checked"),
                           ("n_profiled", "artifacts profiled")):
            val = disp.get(key)
            if val:
                out.append(("README.md", val, label, "prevalence.json"))

    sp = load("results/spend.json")
    if sp:
        for doc in ("README.md", "AGENTS.md"):
            out.append((doc, f"${sp['total_usd']:.2f}",
                        "total model spend", "spend.json"))

    return out


def check_staleness() -> list[str]:
    """Report results produced by code that has since changed.

    A results file is a claim about what the code does. If the code changes and
    the result does not, the claim silently becomes false while still looking
    authoritative - the project's own subject, applied to itself.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from artifact_triage.common.provenance import is_stale

    stale = []
    print("\nRESULT PROVENANCE")
    print("-" * 74)
    for name in ("negative_control", "baseline", "solution", "falsified_run",
                 "prevalence"):
        payload = load(f"results/{name}.json")
        if payload is None:
            continue
        bad, why = is_stale(payload)
        print(f"  {'STALE' if bad else 'ok   '}  {name:<20} {why[:58]}")
        if bad:
            stale.append(name)
    return stale


def main() -> int:
    rows = claims()
    if not rows:
        print("no results files found - run the pipeline first")
        return 0

    cache: dict[str, str] = {}
    failures = []
    print("=" * 74)
    print("CHECKING DOCUMENTED NUMBERS AGAINST results/*.json")
    print("=" * 74)
    for doc, literal, what, src in rows:
        if doc not in cache:
            p = ROOT / doc
            cache[doc] = p.read_text() if p.exists() else ""
        present = literal in cache[doc]
        print(f"  {'OK  ' if present else 'FAIL'}  {doc:<14} "
              f"{what:<32} {literal:>10}   <- {src}")
        if not present:
            failures.append((doc, what, literal, src))

    print("-" * 74)
    if failures:
        print(f"  {len(failures)} DOCUMENTED NUMBER(S) NO LONGER MATCH THE DATA:")
        for doc, what, literal, src in failures:
            print(f"    {doc}: {what} should read {literal} (from {src})")
        print("\n  The write-up has drifted from its results - the same defect")
        print("  this project detects, in this project's own documentation.")
        return 1
    print(f"  All {len(rows)} documented numbers match the results files.")

    stale = check_staleness()
    print("-" * 74)
    if stale:
        print(f"  {len(stale)} result(s) were produced by code that has since")
        print(f"  changed: {', '.join(stale)}")
        print("  The numbers may still be right, but nothing currently proves it.")
        print("  Re-run those before treating them as reported results.")
    else:
        print("  Every result was produced by the current code.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
