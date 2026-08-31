"""How much of this defect can an existing markdown link checker already see?

WHY THIS EXISTS
---------------
The obvious objection to this project is "why not just use lychee?" It is a fair
objection and it deserves a number rather than an argument.

`lycheeverse/lychee` and `remarkjs/remark-validate-links` are mature, widely
adopted, and both check that local file references in Markdown resolve. They are
genuine prior art for part of this problem. But they are *Markdown link*
checkers: they parse `[text](path)` and `![alt](path)`, because that is what a
Markdown parser yields. A README that says

    Run `scripts/train.py` with the config in configs/default.yaml

contains two file references and zero Markdown links. Nothing to parse, nothing
to check.

This module measures the size of that gap on the corpus: of every broken claim
this project finds, what fraction sits inside Markdown link syntax at all?

METHOD, AND ITS LIMIT
---------------------
This is a SYNTACTIC analysis of what a Markdown link checker can parse - it does
not execute lychee or remark-validate-links. A path is counted as "visible" if
it appears inside `[...](path)` or `![...](path)` in the README. That is an
upper bound on what those tools could find: seeing a link is necessary to check
it, not sufficient (they must also resolve it the same way we do).

So the reported gap is, if anything, conservative in our favour being *smaller*
than reality - a tool cannot check what it never parses.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from artifact_triage.common.provenance import stamp
from artifact_triage.eval.prevalence import profile
from artifact_triage.solution.verify import verify

SRC = Path("results/prevalence.json")
OUT = Path("results/linkchecker_gap.json")

# What a Markdown parser yields as a link target. Inline links and images only;
# reference-style definitions resolve to the same set for our purposes.
MD_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)>\s]+)")


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"{SRC} missing - run `make prevalence` first")
    published = json.loads(SRC.read_text())
    corpus = [r["artifact_id"] for r in published["per_artifact"]]

    total = visible = n_art = 0
    examples: list[dict] = []
    for slug in corpus:
        # profile() re-derives; reading the cache directly would use the path
        # list a previous version of the extractor produced.
        fx = profile(slug)
        if not fx or not fx.get("readme"):
            continue
        ev = verify(fx)
        if not ev.broken_paths:
            continue
        n_art += 1
        linked = {m.strip("./") for m in MD_LINK.findall(fx["readme"])}
        for p in ev.broken_paths:
            total += 1
            if p in linked or any(l.endswith(p) for l in linked):
                visible += 1
            elif len(examples) < 12:
                examples.append({"artifact_id": slug, "path": p})

    invisible = total - visible
    payload = {
        "_provenance": stamp("linkchecker_gap"),
        "n_artifacts_with_broken_claims": n_art,
        "total_broken_claims": total,
        "inside_markdown_link_syntax": visible,
        "invisible_to_a_markdown_link_checker": invisible,
        "invisible_share": round(invisible / total, 4) if total else None,
        "method": "syntactic upper bound on what a Markdown link checker parses; "
                  "lychee/remark-validate-links were not executed",
        "examples_invisible": examples,
    }
    OUT.write_text(json.dumps(payload, indent=1))

    print("=" * 70)
    print("WHAT AN EXISTING MARKDOWN LINK CHECKER WOULD ALREADY CATCH")
    print("=" * 70)
    print(f"  broken claims found by this project     : {total}")
    print(f"  of those, inside [text](path) syntax    : {visible} "
          f"({visible/total:.1%})" if total else "")
    print(f"  INVISIBLE to a Markdown link checker    : {invisible} "
          f"({invisible/total:.1%})" if total else "")
    print("-" * 70)
    print("  lychee and remark-validate-links parse Markdown links. Most file")
    print("  references in research READMEs are bare tokens in prose and code")
    print("  fences - there is no link for a link checker to follow.")
    print("-" * 70)
    print("  Examples they would not see:")
    for e in examples[:6]:
        print(f"    {e['artifact_id'][:38]:<40} {e['path']}")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
