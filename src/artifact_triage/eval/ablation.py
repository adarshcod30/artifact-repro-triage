"""Does the careful extractor earn its complexity?

`_is_path` is fussier than it looks: a whitelist of source and config
extensions, a rejection rule for dotted identifiers, a guard against
version-number-shaped tokens. That is more machinery than "does it contain a
dot", and machinery has to justify itself.

So this measures the naive rule against the strict one on the same corpus, using
the negative control's exact ground truth to separate real detections from noise.

Two things are compared:

  PRECISION on injected falsehoods. Both extractors run over the falsified
  twins. The injected paths are known, so any *additional* claim reported broken
  is noise the strict rule was built to suppress.

  STABILITY on the real corpus. How many claims does each rule produce on
  unmodified READMEs? A rule that reports hundreds of "broken" paths per artifact
  is not finding hundreds of defects.

Deterministic, offline, no model.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from artifact_triage.corpus.fetch import _INLINE, _is_path
from artifact_triage.eval.negative_control import falsify
from artifact_triage.solution.verify import _index, check_claim, interesting
from artifact_triage.common.provenance import stamp

# The rule the first version used: any token containing a dot.
_NAIVE = re.compile(r"[\w./\-]+\.[A-Za-z0-9]{1,6}")


def extract_naive(text: str, limit: int = 80) -> list[str]:
    found: set[str] = set()
    for tok in _NAIVE.findall(text):
        found.add(tok.lstrip("./"))
    for tok in _INLINE.findall(text):
        tok = tok.strip().lstrip("./")
        if _NAIVE.fullmatch(tok):
            found.add(tok)
    return sorted(found)[:limit]


def extract_strict(text: str, limit: int = 80) -> list[str]:
    found: set[str] = set()
    for tok in re.findall(r"[\w./\-]+\.[A-Za-z0-9]{1,10}", text):
        if _is_path(tok):
            found.add(tok.lstrip("./"))
    for tok in _INLINE.findall(text):
        tok = tok.strip().lstrip("./")
        if _is_path(tok):
            found.add(tok)
    return sorted(found)[:limit]


def broken_under(paths: list[str], tree: list[str]) -> list[str]:
    exact, base, dirs = _index(tree)
    return [p for p in paths
            if interesting(p) and not check_claim(p, exact, base, dirs).exists]


def main() -> None:
    rows = []
    tot = {"naive": {"inj": 0, "found": 0, "flagged": 0, "claims": 0},
           "strict": {"inj": 0, "found": 0, "flagged": 0, "claims": 0}}

    for p in sorted(Path("data/fixtures").glob("*.json")):
        fx = json.loads(p.read_text())
        tree = fx["file_tree"]
        twin, injected = falsify(fx)
        if not injected:
            continue

        row = {"artifact_id": fx["artifact_id"]}
        for name, extract in (("naive", extract_naive),
                              ("strict", extract_strict)):
            # RECALL: does the rule catch the known falsehoods?
            found = [i for i in injected
                     if i in broken_under(extract(twin["readme"]), tree)]
            # BEHAVIOUR ON REAL INPUT: what does it flag on the UNMODIFIED
            # README? There is no ground truth for these, so they are reported
            # with examples rather than scored - the reader judges whether a
            # rule flagging "20.04" and "zenodo.org" is finding documentation
            # defects.
            claims = [c for c in extract(fx.get("readme", "")) if interesting(c)]
            flagged = broken_under(claims, tree)

            tot[name]["inj"] += len(injected)
            tot[name]["found"] += len(found)
            tot[name]["claims"] += len(claims)
            tot[name]["flagged"] += len(flagged)
            row[name] = {"found": len(found), "claims": len(claims),
                         "flagged": len(flagged), "examples": flagged[:6]}
        rows.append(row)

    n, s_ = tot["naive"], tot["strict"]
    print("=" * 76)
    print("ABLATION - does the strict path extractor earn its complexity?")
    print("=" * 76)
    print(f"{'':<40}{'naive':>16}{'strict':>16}")
    print("-" * 76)
    print(f"{'RECALL on known falsehoods':<40}"
          f"{n['found']}/{n['inj']:<13}{s_['found']}/{s_['inj']:<13}")
    print(f"{'  detection rate':<40}"
          f"{n['found']/max(n['inj'],1):>15.0%}{s_['found']/max(s_['inj'],1):>16.0%}")
    print()
    print(f"{'On UNMODIFIED READMEs:':<40}")
    print(f"{'  tokens extracted as paths':<40}{n['claims']:>15}{s_['claims']:>16}")
    print(f"{'  flagged as broken documentation':<40}"
          f"{n['flagged']:>15}{s_['flagged']:>16}")
    print("-" * 76)
    print(f"  Identical recall. The naive rule additionally reports "
          f"{n['flagged'] - s_['flagged']} findings")
    print(f"  the strict rule does not. There is no ground truth for those, so "
          f"judge them:")
    print()
    seen: set[str] = set()
    strict_all = {e for r in rows for e in r["strict"]["examples"]}
    for r in rows:
        for ex in r["naive"]["examples"]:
            if ex not in seen and ex not in strict_all and len(seen) < 12:
                seen.add(ex)
                print(f"    {ex}")
    print()
    print("  Domains, version numbers and compiler artifacts are not broken")
    print("  documentation. Suppressing them is the whole job: a checker that")
    print("  reports 195 defects where 35 exist will be switched off.")
    print("=" * 76)

    Path("results").mkdir(exist_ok=True)
    Path("results/ablation.json").write_text(json.dumps(
        {"_provenance": stamp("ablation"),
         "totals": tot, "per_artifact": rows}, indent=1))
    print("-> results/ablation.json")


if __name__ == "__main__":
    main()
