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
                # The README row now carries its denominator, which is the
                # honest form; that literal is registered below.
                out.append(("docs/VIDEO_SCRIPT.md", f"{cp[sysname]['mae']:.3f}",
                            f"{sysname} MAE (spoken)", "comparison.json"))
        fc = cp.get("mae_full_coverage") or {}
        if fc.get("solution") is not None:
            out.append(("README.md", f"**{fc['solution']:.3f}**",
                        "solution MAE at full coverage", "comparison.json"))
        for sysname in ("baseline", "solution"):
            if fc.get(sysname) is not None and cp.get(sysname):
                out.append(("README.md",
                            f"| {sysname.capitalize()} | "
                            f"{cp[sysname]['mae']:.3f} "
                            f"({cp[sysname]['n_scored']} of {cp[sysname]['n']}) |",
                            f"{sysname} MAE with its denominator", "comparison.json"))
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

    # The answer to "why not just use lychee?" - it must not be allowed to drift.
    lg = load("results/linkchecker_gap.json")
    if lg and lg.get("total_broken_claims"):
        t = lg["total_broken_claims"]
        out.append(("README.md",
                    f"**{lg['inside_markdown_link_syntax']} "
                    f"({lg['inside_markdown_link_syntax']/t:.1%})**",
                    "link-checker gap: visible", "linkchecker_gap.json"))
        out.append(("README.md",
                    # from the raw counts: the stored share is rounded to 4dp,
                    # which formats to 95.7% where 1209/1264 is 95.6%.
                    f"**{lg['invisible_to_a_markdown_link_checker']:,} "
                    f"({lg['invisible_to_a_markdown_link_checker']/t:.1%})**",
                    "link-checker gap: invisible", "linkchecker_gap.json"))

    # Our own leniency. A headline broken-rate is meaningless without it.
    ra = load("results/resolution_audit.json")
    if ra and ra.get("resolved"):
        out.append(("README.md",
                    f"**{ra['resolved_leniently']:,} of {ra['resolved']:,} "
                    f"resolutions ({ra['resolved_leniently']/ra['resolved']:.1%})**",
                    "resolution audit: lenient", "resolution_audit.json"))
        by = ra.get("by_resolution", {})
        for kind in ("exact", "suffix"):
            if by.get(kind):
                out.append(("README.md", f"| **{by[kind]:,}** |",
                            f"resolution audit: {kind} matches",
                            "resolution_audit.json"))
        if ra.get("broken"):
            out.append(("README.md",
                        f"| **broken — not found at all** | **{ra['broken']:,}** |",
                        "resolution audit: broken row", "resolution_audit.json"))

    # The decay table backs the "artifacts ship broken, they do not rot" claim
    # and was never under this checker. It had drifted on every cell.
    pvd = load("results/prevalence.json")
    if pvd and pvd.get("decay"):
        dc = pvd["decay"]
        buckets = dc["buckets"] if isinstance(dc, dict) and "buckets" in dc else dc
        if buckets:
            old, new = buckets[-1], buckets[0]
            out.append(("README.md",
                        f"| **{old['label']}** | **{old['n']}** | "
                        f"**{old['median_days']:,}d** | "
                        f"**{old['mean_broken_ratio']:.3f}** |",
                        "decay: oldest bucket", "prevalence.json"))
            out.append(("README.md",
                        f"delta {old['mean_broken_ratio'] - new['mean_broken_ratio']:+.3f} "
                        f"across four years",
                        "decay: delta across four years", "prevalence.json"))

    # The ecosystem table, likewise never covered and likewise drifted.
    if pvd and pvd.get("by_language"):
        langs = sorted(pvd["by_language"], key=lambda x: x["mean_broken_ratio"])
        for x in (langs[0], langs[-1]):
            out.append(("README.md",
                        f"| {x['language']} | {x['n']} | "
                        f"{x['mean_broken_ratio']:.3f} | {x['share_with_broken']:.0%} |",
                        f"ecosystem: {x['language']}", "prevalence.json"))

    # The video script quotes figures aloud. A spoken number cannot be matched,
    # so the script carries a digits table at the top and that is checked.
    if fr:
        srr = fr.get("solution_rates") or []
        if srr:
            out.append(("docs/VIDEO_SCRIPT.md",
                        f"**0%** → **{sum(srr)/len(srr):.0%}**",
                        "video: detection headline", "falsified_run.json"))
            out.append(("docs/VIDEO_SCRIPT.md",
                        f"{min(srr):.0%}–{max(srr):.0%}",
                        "video: detection range", "falsified_run.json"))
    if pvd:
        out.append(("docs/VIDEO_SCRIPT.md", f"{pvd['total_claims']:,}",
                    "video: documented references", "prevalence.json"))
        out.append(("docs/VIDEO_SCRIPT.md", f"{pvd['prevalence']:.1%}",
                    "video: prevalence", "prevalence.json"))

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
                 "falsified_llama", "falsified_nova2lite", "prevalence",
                 "comparison", "subtle_control",
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


# Every results file the registered claims draw on. If one goes missing, its
# claims vanish from `claims()` and the summary happily reports "All N
# documented numbers match" over a SMALLER N - success printed over shrunken
# coverage. That is the same failure as the floor-free claim being silently
# skipped for weeks, and as `verify_targets` reporting success over targets it
# never ran.
EXPECTED_SOURCES = [
    "baseline.json", "solution.json", "comparison.json", "falsified_run.json",
    "falsified_llama.json", "falsified_nova2lite.json", "adversarial.json",
    "negative_control.json", "subtle_control.json", "ablation.json",
    "prevalence.json", "resolution_audit.json", "linkchecker_gap.json",
    "issue_validation.json", "spend.json",
]


def missing_sources() -> list[str]:
    return [f for f in EXPECTED_SOURCES if not (ROOT / "results" / f).exists()]


def main() -> int:
    absent = missing_sources()
    rows = claims()
    if not rows:
        print("no results files found - run the pipeline first")
        return 0
    if absent:
        print("=" * 74)
        print("  MISSING RESULTS FILES - their claims are NOT being checked:")
        for f in absent:
            print(f"    results/{f}")
        print("  Coverage has shrunk. Re-run the pipeline before trusting the")
        print("  summary below, which can only speak for the files present.")
        print("=" * 74)

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
    if absent:
        print(f"  {len(rows)} documented numbers match, but {len(absent)} results "
              f"file(s) are MISSING and their claims went unchecked.")
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
