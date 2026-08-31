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
        # Anchored to the headline row. Bare "100%" matched 11 lines and bare
        # "0%" matched 21 - a pass proved only that the digits exist somewhere.
        if sr and br:
            # Anchored to the headline table row. The previous anchor was a
            # sentence that a rewrite deleted - the checker caught it, which is
            # the point, but an anchor tied to prose breaks on every edit.
            # A table row is structural and survives rewording.
            out.append(("README.md",
                        f"| Noticed the fabrication | **{sum(br)/len(br):.0%}** "
                        f"| **{sum(sr)/len(sr):.0%}**",
                        "detection, baseline vs solution", "falsified_run.json"))
        if sr:
            out.append(("README.md", f"| **0%** | **{sum(sr)/len(sr):.0%}** |",
                        "solution detection (results table)",
                        "falsified_run.json"))
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
            # Was `str(fr["trials"])` - a bare "3", which matched 56 lines and
            # verified nothing at all.
            out.append(("README.md", f"{fr['trials']} trials", "trial count",
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
                # Anchored to the table row in the README: a bare "0.700"
                # also matches the anti-calibrated-confidence sentence, which
                # is a coincidence, not a verification.
                out.append(("README.md",
                            f"| {sysname.capitalize()} | "
                            f"{cp[sysname]['mae']:.3f} |",
                            f"{sysname} MAE (badge agreement)",
                            "comparison.json"))
                out.append(("docs/VIDEO_SCRIPT.md", f"{cp[sysname]['mae']:.3f}",
                            f"{sysname} MAE (spoken)", "comparison.json"))
        best = next((c for c in cp.get("controls", [])
                     if c["system"] == cp.get("best_control")), None)
        if best:
            out.append(("README.md", f"{best['mae']:.3f}",
                        f"best constant control ({best['system']})",
                        "comparison.json"))

    # The baseline's collapse onto one class is quoted in the README and was
    # hand-written as "14 of 15", then "13 of 15" - it moves between runs,
    # because the model is not deterministic. Derived now.
    bl = load("results/baseline.json")
    if bl and bl.get("raw"):
        tiers = [r.get("tier") for r in bl["raw"] if r.get("tier")]
        if tiers:
            top = max({t: tiers.count(t) for t in set(tiers)}.items(),
                      key=lambda kv: kv[1])
            out.append(("README.md", f"`Functional` for {top[1]} of {len(tiers)}",
                        "baseline collapse onto one class", "baseline.json"))

    # The issue-validation table was hand-written and had drifted on every
    # figure - including in a way that reversed the direction of the point
    # estimate. A negative result kept visible for honesty is worthless if its
    # numbers rot.
    iv = load("results/issue_validation.json")
    if iv:
        f, cl = iv.get("flagged_summary"), iv.get("clean_summary")
        if f and cl:
            out.append(("README.md", f"{f['share_with_a_complaint']:.1%}",
                        "complaint share, flagged", "issue_validation.json"))
            out.append(("README.md", f"{cl['share_with_a_complaint']:.1%}",
                        "complaint share, clean", "issue_validation.json"))
            n = f["n_repos"] + cl["n_repos"]
            withi = f["n_repos_with_issues"] + cl["n_repos_with_issues"]
            out.append(("README.md", f"only {withi} of {n} repositories",
                        "repositories with any issues", "issue_validation.json"))

    # The subtle-control and ablation tables were hand-written and both had
    # drifted. Every quantitative table in the write-up is now derived from
    # the results file it describes.
    sc = load("results/subtle_control.json")
    if sc:
        out.append(("README.md", f"| Mutations introduced | {sc['mutations']} |",
                    "subtle control: mutations", "subtle_control.json"))
        out.append(("README.md",
                    f"**{sc['detected']} ({sc['detection_rate']:.0%})**",
                    "subtle control: detected", "subtle_control.json"))
        out.append(("README.md",
                    f"**{sc['correctly_suggested']} "
                    f"({sc['suggestion_rate']:.0%})**",
                    "subtle control: suggested", "subtle_control.json"))

    ab = load("results/ablation.json")
    if ab and ab.get("totals"):
        t = ab["totals"]
        out.append(("README.md",
                    f"| {t['naive']['claims']} | {t['strict']['claims']} |",
                    "ablation: tokens extracted", "ablation.json"))
        out.append(("README.md",
                    f"**{t['naive']['flagged']}** | **{t['strict']['flagged']}**",
                    "ablation: flagged", "ablation.json"))

    adv = load("results/adversarial.json")
    if adv:
        out.append(("README.md",
                    f"**{adv['strong_baseline_detected']}/"
                    f"{adv['strong_baseline_eligible']} "
                    f"({adv['strong_baseline_detected']/adv['strong_baseline_eligible']:.0%})**",
                    "adversarial: strong baseline", "adversarial.json"))
        out.append(("README.md",
                    f"**{adv['placebo_detected']}/{adv['placebo_eligible']} "
                    f"({adv['placebo_detected']/adv['placebo_eligible']:.0%})**",
                    "adversarial: placebo control", "adversarial.json"))

    ll = load("results/falsified_llama.json")
    if ll and ll.get("solution_rates"):
        r = ll["solution_rates"]
        out.append(("README.md",
                    f"| **100%** | **{sum(r)/len(r):.0%}** |",
                    "cross-model: llama detection", "falsified_llama.json"))

    # The cross-TIER run: a 13x cheaper model on the same experiment. This is
    # the claim that the improvement is not model capability, so its number
    # must not be allowed to drift.
    cheap = load("results/falsified_nova2lite.json")
    if cheap and cheap.get("solution_rates"):
        r = cheap["solution_rates"]
        out.append(("README.md",
                    f"| **Nova 2 Lite** | 0% | **{sum(r)/len(r):.0%}** |",
                    "cross-tier: cheap model detection",
                    "falsified_nova2lite.json"))

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
    from artifact_triage.common.provenance import changed_functions, is_stale

    stale: list = []
    unstamped: list = []
    print("\nRESULT PROVENANCE")
    print("-" * 74)
    # This list used to cover five results while the summary line below said
    # "Every result was produced by the current code". Five OTHER result files
    # were unstamped and unchecked, so that sentence was a blanket claim over a
    # subset - the same "certifies what it cannot see" failure this checker
    # exists to prevent.
    for name in ("negative_control", "baseline", "solution", "falsified_run",
                 "falsified_llama", "prevalence", "comparison", "subtle_control",
                 "ablation", "adversarial", "issue_validation"):
        payload = load(f"results/{name}.json")
        if payload is None:
            continue
        if not payload.get("_provenance"):
            print(f"  ?      {name:<20} no provenance recorded - cannot be checked")
            unstamped.append(name)
            continue
        bad, why = is_stale(payload)
        print(f"  {'STALE' if bad else 'ok   '}  {name:<20} {why[:58]}")
        if bad:
            stale.append(name)
            # Say WHAT changed, not merely that something did. A file-level
            # fingerprint trips on a comment as readily as on a rewrite, and
            # "stale" with no detail invites either a needless paid re-run or a
            # shrug. The reader can then judge whether the change could reach
            # this result at all.
            prov = payload.get("_provenance") or {}
            since = (prov.get("commit") or "").replace("-dirty", "")
            fns = changed_functions(prov.get("kind", ""), since) if since else []
            if fns:
                print(f"           functions changed since {since}: "
                      f"{', '.join(fns[:6])}")
                if prov.get("commit", "").endswith("-dirty"):
                    print("           (that commit was recorded from a DIRTY "
                          "tree, so this diff is approximate)")
    return stale, unstamped


def main() -> int:
    rows = claims()
    if not rows:
        print("no results files found - run the pipeline first")
        return 0

    cache: dict[str, str] = {}
    failures: list = []
    weak_checks: list = []
    print("=" * 74)
    print("CHECKING DOCUMENTED NUMBERS AGAINST results/*.json")
    print("=" * 74)
    for doc, literal, what, src in rows:
        if doc not in cache:
            p = ROOT / doc
            cache[doc] = p.read_text() if p.exists() else ""
        # Substring matching means a value can pass against a COINCIDENTAL
        # occurrence elsewhere in the document - "100%" appears in several
        # unrelated sentences. The check cannot tell those apart, so it reports
        # where it matched and how often, making a false pass auditable instead
        # of invisible. An unaudited green check is the thing this project is
        # about.
        lines = [i for i, ln in enumerate(cache[doc].splitlines(), 1)
                 if literal in ln]
        present = bool(lines)
        where = (f"L{lines[0]}" + (f" +{len(lines) - 1} more" if len(lines) > 1
                                   else "")) if lines else "-"
        # A literal matching many lines is not evidence the right sentence is
        # correct - it is evidence the check is too loose to mean anything.
        weak = len(lines) > 8
        if weak:
            weak_checks.append((doc, what, literal, len(lines)))
        status = "FAIL" if not present else ("WEAK" if weak else "OK  ")
        print(f"  {status}  {doc:<20} "
              f"{what:<34} {literal[:26]:>26}  {where:<14} <- {src}")
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
    print("  (matched by substring - line numbers shown so a coincidental")
    print("   match can be audited rather than trusted.)")
    if weak_checks:
        print(f"\n  {len(weak_checks)} check(s) are TOO LOOSE to prove anything;")
        print("  the literal appears on many lines, so a pass may be coincidence:")
        for doc, what, literal, n in weak_checks:
            print(f"    {doc}: {what} - {literal!r} matches {n} lines")

    stale, unstamped = check_staleness()
    print("-" * 74)
    if stale:
        print(f"  {len(stale)} result(s) were produced by code that has since")
        print(f"  changed: {', '.join(stale)}")
        print("  The numbers may still be right, but nothing currently proves it.")
        print("  Re-run those before treating them as reported results.")
    if unstamped:
        # Never fold these into a clean bill of health. An unstamped result is
        # UNKNOWN, not current, and saying otherwise is the failure this
        # checker exists to prevent.
        print(f"  {len(unstamped)} result(s) carry NO provenance and cannot be")
        print(f"  checked at all: {', '.join(unstamped)}")
    if not stale and not unstamped:
        print("  Every result was produced by the current code.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
