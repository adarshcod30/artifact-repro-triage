"""Two tests designed to break this project's central claim.

The claim is: the solution detects falsified READMEs because it is shown verified
evidence, and the baseline cannot because it is not. A sceptical reviewer has two
obvious objections, and neither had been tested.

OBJECTION 1 - "your baseline is a strawman."
    The baseline is never *told* to look for inconsistency. Maybe it could detect
    fabricated paths if simply asked. So: run a STRONGER baseline, explicitly
    instructed to hunt for internal contradictions, given the same README. If it
    still scores 0%, the limitation is structural rather than a prompting
    artefact - and the comparison survives its strongest objection.

OBJECTION 2 - "the solution is reading the README, not the evidence."
    Maybe the solution downgrades falsified artifacts because the injected text
    reads oddly, and the evidence block is decorative. So: give it a falsified
    README with a PLACEBO evidence block reporting everything resolves. If it
    still downgrades, the evidence is not doing the work and the causal claim is
    wrong. If it stops downgrading, the evidence is doing exactly what is
    claimed.

The placebo is the sharper of the two: it is a direct causal test, and it can
falsify the project's main finding rather than merely qualify it.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from artifact_triage.common.llm import USD_IN, USD_OUT, MODEL, ask, client
from artifact_triage.common.rubric import RUBRIC
from artifact_triage.eval.negative_control import falsify
from artifact_triage.solution.evidence import gather
from artifact_triage.common.provenance import stamp

OUT = Path("results/adversarial.json")
TIER_RANK = {"Available": 0, "Functional": 1, "Reusable": 2}

# The baseline as it should have been written by someone trying to win.
STRONG_BASELINE_HINT = """

Before answering, check the README against itself. Research artifacts frequently
document files, scripts and directories that are not actually present, and a
README that instructs the reader to run something which does not exist is not
"documented, consistent, complete and exercisable" whatever else it contains.
Look specifically for: instructions referencing files that appear nowhere else in
the document, setup steps that contradict each other, and commands whose inputs
are never produced by any earlier step. Weigh anything you find heavily."""


def placebo_block(real_block: str) -> str:
    """Same shape and length, but reporting a clean result.

    Kept structurally identical so the test isolates the *content* of the
    evidence rather than its presence or its formatting.
    """
    out = re.sub(r"README references (\d+) file path\(s\); \d+ do NOT exist.*",
                 r"README references \1 file path(s); 0 do NOT exist in the "
                 r"repository.", real_block)
    out = re.sub(r"^\s*- MISSING:.*$", "", out, flags=re.M)
    if "All referenced paths were found." not in out:
        out = out.replace("== Environment reproducibility ==",
                          "  All referenced paths were found.\n\n"
                          "== Environment reproducibility ==")
    return re.sub(r"\n{3,}", "\n\n", out)


def rank(t):
    return TIER_RANK.get(t) if t else None


def main() -> None:
    cl = client()
    fixtures = sorted(Path("data/fixtures").glob("*.json"))
    rows, cost = [], 0.0

    for i, p in enumerate(fixtures, 1):
        clean = json.loads(p.read_text())
        dirty, injected = falsify(clean)
        if not injected:
            continue

        def prompt(fx, block=None, hint=""):
            body = block if block is not None else gather(
                fx, with_network=False).as_prompt_block()
            return (f"Artifact repository: {fx['artifact_id']}\n"
                    f"Paper: {fx['paper_title']}\n\n{body}\n\n"
                    f"README (verbatim):\n---\n{fx['readme'][:16000]}\n---\n")

        def readme_only(fx):
            return (f"Artifact repository: {fx['artifact_id']}\n"
                    f"Paper: {fx['paper_title']}\n\n"
                    f"README (verbatim):\n---\n{fx['readme'][:16000]}\n---\n")

        row = {"artifact_id": clean["artifact_id"], "injected": len(injected)}

        # --- Objection 1: a baseline that is actually trying -----------------
        a_c = ask(cl, RUBRIC + STRONG_BASELINE_HINT, readme_only(clean))
        a_d = ask(cl, RUBRIC + STRONG_BASELINE_HINT, readme_only(dirty))
        rc, rd = rank(a_c.tier), rank(a_d.tier)
        row["strong_baseline"] = {
            "clean": a_c.tier, "dirty": a_d.tier,
            "downgraded": bool(rc is not None and rd is not None and rd < rc)}

        # --- Objection 2: placebo evidence on a falsified README -------------
        real = gather(dirty, with_network=False).as_prompt_block()
        fake = placebo_block(real)
        b_c = ask(cl, RUBRIC, prompt(clean))                    # honest, clean
        b_d = ask(cl, RUBRIC, prompt(dirty, block=fake))        # falsified + placebo
        rc2, rd2 = rank(b_c.tier), rank(b_d.tier)
        row["placebo"] = {
            "clean": b_c.tier, "dirty_with_placebo": b_d.tier,
            "downgraded": bool(rc2 is not None and rd2 is not None and rd2 < rc2)}

        for a in (a_c, a_d, b_c, b_d):
            cost += (a.input_tokens * USD_IN + a.output_tokens * USD_OUT) / 1e6
        rows.append(row)
        print(f"[{i:2}] strong-baseline {str(row['strong_baseline']['clean']):<11}->"
              f"{str(row['strong_baseline']['dirty']):<11}"
              f"{'DOWN' if row['strong_baseline']['downgraded'] else ' -  '}   "
              f"placebo {str(row['placebo']['clean']):<11}->"
              f"{str(row['placebo']['dirty_with_placebo']):<11}"
              f"{'DOWN' if row['placebo']['downgraded'] else ' -  '}  "
              f"{clean['artifact_id'][:30]}")

    def rate(key):
        elig = [r for r in rows if r[key]["clean"] != "Available"]
        down = sum(r[key]["downgraded"] for r in elig)
        return down, len(elig)

    sb_d, sb_n = rate("strong_baseline")
    pl_d, pl_n = rate("placebo")

    print("\n" + "=" * 72)
    print("ADVERSARIAL TESTS")
    print("=" * 72)
    print(f"  OBJECTION 1 - 'the baseline is a strawman'")
    print(f"    A baseline explicitly told to hunt for internal inconsistency,")
    print(f"    given the same falsified README:")
    print(f"      detected {sb_d}/{sb_n} "
          f"({sb_d/sb_n:.0%})" if sb_n else "      no eligible artifacts")
    print()
    print(f"  OBJECTION 2 - 'the solution reads the README, not the evidence'")
    print(f"    Falsified README + PLACEBO evidence claiming everything resolves:")
    print(f"      detected {pl_d}/{pl_n} "
          f"({pl_d/pl_n:.0%})" if pl_n else "      no eligible artifacts")
    print(f"    Reported solution detection with REAL evidence: 93%.")
    print("-" * 72)
    if pl_n and pl_d / pl_n < 0.4:
        print("  The placebo collapses detection -> the EVIDENCE is doing the")
        print("  work, not the README's wording. The causal claim holds.")
    elif pl_n:
        print("  The placebo does NOT collapse detection -> the solution is")
        print("  reading the README, and the causal claim is WRONG.")
    print(f"  cost: ${cost:.4f}   model: {MODEL}")
    print("=" * 72)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "_provenance": stamp("adversarial"),
        "model": MODEL, "n": len(rows),
        "strong_baseline_detected": sb_d, "strong_baseline_eligible": sb_n,
        "placebo_detected": pl_d, "placebo_eligible": pl_n,
        "usd": round(cost, 4), "per_artifact": rows}, indent=1))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
