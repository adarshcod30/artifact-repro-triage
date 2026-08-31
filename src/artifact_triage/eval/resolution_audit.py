"""HOW does a claim "resolve"? An audit of this project's own leniency.

WHY THIS EXISTS
---------------
The headline says 18.5% of documented file references resolve to nothing. That
number is only as meaningful as the definition of "resolve", and this project's
definition is deliberately LENIENT: `check_claim` accepts a path if it exists
exactly, or if any real path ENDS WITH it, or - failing that - if any file
anywhere in the tree shares its basename.

So a README saying `src/train.py` is counted as correct when the file actually
lives at `experiments/train.py`. The instruction a reader would follow does not
work, and we score it as fine.

That leniency is a choice, and the right one for a tool whose headline is "zero
false positives": flagging a file that plainly exists somewhere would be the
most annoying possible error. But it has two consequences that must be stated
rather than discovered:

  1. **The reported broken rate is a LOWER BOUND.** The true rate of "the
     documented path does not work as written" is higher.
  2. **This corpus is not a fair label set for a competing detector.** A tool
     that correctly flags a relocated file would be scored a false positive
     against our labels.

Neither is visible from the headline, so this module measures the breakdown and
the README publishes it.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

from artifact_triage.common.provenance import stamp
from artifact_triage.eval.prevalence import profile
from artifact_triage.solution.verify import _index, check_claim, interesting

SRC = Path("results/prevalence.json")
OUT = Path("results/resolution_audit.json")

# How `check_claim` resolved it, and whether the path works AS WRITTEN.
AS_WRITTEN = {"exact", "directory"}


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"{SRC} missing - run `make prevalence` first")
    pv = json.loads(SRC.read_text())

    kinds: collections.Counter = collections.Counter()
    examples: list[dict] = []
    for r in pv["per_artifact"]:
        fx = profile(r["artifact_id"])
        if not fx:
            continue
        exact, base, dirs = _index(fx["file_tree"])
        for p in [q for q in fx.get("readme_referenced_paths", []) if interesting(q)]:
            cl = check_claim(p, exact, base, dirs)
            how = (cl.matched_as or "exact") if cl.exists else "BROKEN"
            kinds[how] += 1
            if (cl.exists and how not in AS_WRITTEN and not how.startswith("case")
                    and len(examples) < 12):
                examples.append({"artifact_id": r["artifact_id"], "claimed": p,
                                 "resolved_as": how, "matched": cl.matched_as})

    total = sum(kinds.values())
    resolved = total - kinds["BROKEN"]
    lenient = sum(v for k, v in kinds.items()
                  if k not in AS_WRITTEN and k != "BROKEN" and not k.startswith("case"))

    payload = {
        "_provenance": stamp("resolution_audit"),
        "total_claims": total,
        "resolved": resolved,
        "broken": kinds["BROKEN"],
        "by_resolution": dict(kinds),
        "resolved_leniently": lenient,
        "lenient_share_of_resolutions": round(lenient / resolved, 4) if resolved else None,
        "lenient_share_of_all_claims": round(lenient / total, 4) if total else None,
        "note": "suffix and basename matches do NOT work as written; the reported "
                "broken rate is therefore a lower bound",
        "examples": examples,
    }
    OUT.write_text(json.dumps(payload, indent=1))

    print("=" * 72)
    print("HOW CLAIMS RESOLVE - an audit of this project's own leniency")
    print("=" * 72)
    for k, v in kinds.most_common():
        works = "works as written" if k in AS_WRITTEN else (
            "NOT FOUND" if k == "BROKEN" else "resolved leniently")
        print(f"  {k:<24}{v:>6}  ({v/total:5.1%})   {works}")
    print("-" * 72)
    print(f"  resolved leniently: {lenient} of {resolved} resolutions "
          f"({lenient/resolved:.1%}), {lenient/total:.1%} of all claims")
    print("  These paths do NOT work as the README writes them - the file exists")
    print("  somewhere else. We count them as fine, so the published broken rate")
    print("  is a LOWER BOUND, and this corpus is not a fair label set for a")
    print("  competing detector that flags relocated files.")
    print("-" * 72)
    for e in examples[:6]:
        print(f"    {e['artifact_id'][:34]:<36} {e['claimed'][:30]:<32} {e['resolved_as']}")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
