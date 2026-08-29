"""Re-apply the current slug rules to an already-harvested corpus.

WHY THIS IS A SCRIPT AND NOT A HAND EDIT
----------------------------------------
`github_repos` used to capture the full stop from a GitHub link written in
prose - "see https://github.com/owner/repo." - producing a slug that could only
404, because GitHub does not allow a trailing dot in a repository name. Ten of
769 harvested repositories were affected and ALL TEN were confirmed real via the
GitHub API: legitimate artifacts silently dropped from the measured population.

Re-harvesting from Zenodo to pick them up would take a network sweep and would
also add unrelated new deposits, changing two things at once. The correction is
purely mechanical - it is exactly what the fixed extractor produces from the
same records - so it is applied here as a deterministic, reviewable migration
that prints every change it makes.

Idempotent: running it on a corrected corpus changes nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from artifact_triage.corpus.zenodo import _NOT_REPOS  # noqa: E402

OUT = Path("data/discovered.jsonl")


def main() -> int:
    if not OUT.exists():
        print(f"{OUT} not found"); return 1
    rows = [json.loads(l) for l in OUT.read_text().splitlines() if l.strip()]

    seen: set[str] = set()
    kept, fixed, dropped = [], [], []
    for r in rows:
        owner, _, name = r["repo"].partition("/")
        new = name.removesuffix(".git").rstrip(".")
        if not new or owner.lower() in _NOT_REPOS:
            dropped.append(r["repo"]); continue
        slug = f"{owner}/{new}"
        if slug != r["repo"]:
            fixed.append((r["repo"], slug))
            r["repo"] = slug
        if slug.lower() in seen:
            dropped.append(slug + "  (duplicate after correction)"); continue
        seen.add(slug.lower())
        kept.append(r)

    print(f"  corrected : {len(fixed)}")
    for old, new in fixed:
        print(f"      {old}  ->  {new}")
    print(f"  dropped   : {len(dropped)}")
    for d in dropped:
        print(f"      {d}")
    print(f"  corpus    : {len(rows)} -> {len(kept)} repositories")

    if fixed or dropped:
        OUT.write_text("".join(json.dumps(r) + "\n" for r in kept))
        print(f"-> {OUT}")
    else:
        print("  already correct - nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
