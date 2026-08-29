"""A harder negative control: mutate real paths instead of inventing fake ones.

WHY THE FIRST CONTROL WAS TOO EASY
----------------------------------
`negative_control.py` appends five invented paths to a README. The verifier finds
all 75, every trial. But invented paths are the easy case - they bear no
relationship to anything in the repository.

Real breakage does not look like that. A file gets renamed, a directory is
pluralised, a script moves one level up, and the README is not updated. The stale
reference still *looks* right, sits in a sentence that still reads correctly, and
differs from a working path by a few characters.

So this control takes paths that genuinely exist and mutates them, then rewrites
the README to use the mutated form. Ground truth stays exact - we know which
paths we broke, and we know each one existed a moment ago.

This is strictly harder in a way that matters: it is the only variant where the
"did you mean" suggester should be able to name the fix, because the correct file
really is one edit away.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

from artifact_triage.solution.verify import verify

OUT = Path("results/subtle_control.json")


def mutations(path: str) -> list[tuple[str, str]]:
    """Ways a reference goes stale in practice. Returns (mutated, kind)."""
    out: list[tuple[str, str]] = []
    parts = path.split("/")
    base = parts[-1]
    stem, dot, ext = base.partition(".")

    # A directory gets pluralised (or de-pluralised).
    if len(parts) > 1:
        d = parts[-2]
        if not d.endswith("s"):
            out.append(("/".join(parts[:-2] + [d + "s", base]), "dir pluralised"))
        elif len(d) > 2:
            out.append(("/".join(parts[:-2] + [d[:-1], base]), "dir singularised"))

    # The file is renamed with a common suffix.
    if dot:
        out.append(("/".join(parts[:-1] + [f"{stem}_v2{dot}{ext}"]), "renamed _v2"))
        out.append(("/".join(parts[:-1] + [f"{stem}_old{dot}{ext}"]), "renamed _old"))
        if "_" in stem:
            head, _, tail = stem.rpartition("_")
            out.append(("/".join(parts[:-1] + [f"{head}{dot}{ext}"]),
                        "suffix dropped"))

    # The file moves one level up.
    if len(parts) > 1:
        out.append(("/".join(parts[:-2] + [base]) if len(parts) > 2 else base,
                    "moved up one level"))
    return out


def falsify_subtle(fixture: dict, n: int = 4,
                   seed: int = 0) -> tuple[dict, list[dict]]:
    """Rewrite the README so real references point at near-miss paths."""
    rng = random.Random(f"{fixture['artifact_id']}:subtle:{seed}")
    tree = set(fixture["file_tree"])
    readme = fixture.get("readme", "")

    # Only mutate paths the README actually references AND that exist, so the
    # break is genuinely introduced by us.
    ev = verify(fixture)
    working = [c["path"] for c in ev.claims if c["exists"]]
    rng.shuffle(working)

    applied: list[dict] = []
    for original in working:
        if len(applied) >= n:
            break
        options = [(m, k) for m, k in mutations(original)
                   if m not in tree and m != original]
        if not options:
            continue
        mutated, kind = options[rng.randrange(len(options))]
        # Replace the reference wherever it appears, as a whole token.
        pattern = re.compile(rf"(?<![\w/]){re.escape(original)}(?![\w])")
        new_readme, count = pattern.subn(mutated, readme)
        if count == 0:
            continue
        readme = new_readme
        applied.append({"original": original, "mutated": mutated, "kind": kind})

    if not applied:
        return fixture, []

    twin = json.loads(json.dumps(fixture))
    twin["artifact_id"] = fixture["artifact_id"] + "#subtle"
    twin["readme"] = readme
    from artifact_triage.corpus.fetch import referenced_paths
    twin["readme_referenced_paths"] = referenced_paths(readme)
    return twin, applied


def main() -> None:
    rows = []
    total = detected = suggested_right = 0
    for p in sorted(Path("data/fixtures").glob("*.json")):
        fx = json.loads(p.read_text())
        twin, applied = falsify_subtle(fx)
        if not applied:
            continue
        ev = verify(twin)
        found = [a for a in applied if a["mutated"] in ev.broken_paths]
        # The suggester should name the original file, because it still exists.
        # Compare on suffix, not string equality: a README may reference a bare
        # basename ("collect_builds.sh") that the verifier resolves to a full
        # path ("artifact/collect_builds.sh"). An earlier version compared the
        # two directly and reported 39% when the true figure was far higher -
        # a metric that under-reported its own system.
        def names_original(a: dict) -> bool:
            hints = ev.suggestions.get(a["mutated"]) or []
            orig = a["original"].lstrip("./")
            return any(h == orig or h.endswith("/" + orig)
                       or orig.endswith("/" + h) for h in hints)

        right = [a for a in found if names_original(a)]
        total += len(applied)
        detected += len(found)
        suggested_right += len(right)
        rows.append({"artifact_id": fx["artifact_id"], "applied": applied,
                     "detected": [a["mutated"] for a in found],
                     "correctly_suggested": [a["original"] for a in right]})
        print(f"  {len(found)}/{len(applied)} detected, "
              f"{len(right)} correctly suggested   {fx['artifact_id'][:44]}")
        for a in applied[:2]:
            mark = "detected" if a in found else "MISSED  "
            print(f"      {mark}  {a['original']}  ->  {a['mutated']}  "
                  f"({a['kind']})")

    print("\n" + "=" * 70)
    print("SUBTLE CONTROL - real paths mutated into near-misses")
    print("=" * 70)
    print(f"  mutations introduced        : {total}")
    print(f"  detected as broken          : {detected} "
          f"({detected/total:.0%})" if total else "  none")
    print(f"  correct original suggested  : {suggested_right} "
          f"({suggested_right/total:.0%})" if total else "")
    print("-" * 70)
    print("  Harder than the invented-path control: each mutated reference")
    print("  still reads correctly and differs from a working path by a few")
    print("  characters. This is what a stale README actually looks like.")
    print("=" * 70)
    Path("results").mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "mutations": total, "detected": detected,
        "detection_rate": round(detected / total, 4) if total else 0.0,
        "correctly_suggested": suggested_right,
        "suggestion_rate": round(suggested_right / total, 4) if total else 0.0,
        "per_artifact": rows}, indent=1))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
