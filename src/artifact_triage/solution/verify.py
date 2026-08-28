"""Deterministic claim verification - the core of the advanced solution.

THE IDEA
--------
A README is a set of promises: "run `python train.py`", "install with
`requirements.txt`", "see `configs/base.yaml`". The baseline reads those promises
and believes them, because a fluent README reads like a well-maintained project.

This module checks each promise against the repository's actual file tree. A
promise that fails is hard evidence of exactly the reproducibility gap an
artifact reviewer is looking for - and it is established with zero model calls,
so it cannot be hallucinated and costs nothing.

The model is then asked to judge *verified facts* rather than *claims*. That
single change is the difference between the baseline and the solution.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, asdict

# Paths that appear in READMEs but are outputs, examples, or third-party
# references rather than promises about this repository.
IGNORE_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".log", ".out")
IGNORE_TOKENS = ("http://", "https://", "e.g.", "i.e.", "*.")


@dataclass
class Claim:
    path: str
    exists: bool
    matched_as: str | None   # how it resolved: exact, basename, or directory


@dataclass
class Evidence:
    artifact_id: str
    claims_total: int
    claims_broken: int
    broken_paths: list[str]
    broken_ratio: float
    has_dependency_manifest: bool
    has_container: bool
    has_ci: bool
    has_licence: bool
    has_tests: bool
    has_build_script: bool
    readme_bytes: int
    n_files: int
    claims: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)

    def as_prompt_block(self) -> str:
        """Render verified facts for the model. Facts only - no interpretation."""
        lines = [
            "VERIFIED REPOSITORY FACTS (checked against the actual file tree):",
            f"- files in repository: {self.n_files}",
            f"- README size: {self.readme_bytes} bytes",
            f"- dependency manifest present: {self.has_dependency_manifest}",
            f"- container definition present: {self.has_container}",
            f"- CI configuration present: {self.has_ci}",
            f"- build/install script present: {self.has_build_script}",
            f"- test files present: {self.has_tests}",
            f"- licence present: {self.has_licence}",
            "",
            f"README PATH CLAIMS: {self.claims_total} checked, "
            f"{self.claims_broken} could NOT be found in the repository.",
        ]
        if self.broken_paths:
            lines.append("Paths the README references that do not exist:")
            lines += [f"  - {p}" for p in self.broken_paths[:15]]
        elif self.claims_total:
            lines.append("Every path the README references was found.")
        else:
            lines.append("The README references no checkable file paths.")
        return "\n".join(lines)


def _index(file_tree: list[str]) -> tuple[set[str], set[str], set[str]]:
    exact = set(file_tree)
    basenames = {p.rsplit("/", 1)[-1] for p in file_tree}
    dirs: set[str] = set()
    for p in file_tree:
        parts = p.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
    return exact, basenames, dirs


def check_claim(path: str, exact: set[str], basenames: set[str],
                dirs: set[str]) -> Claim:
    p = path.strip().lstrip("./")
    if p in exact:
        return Claim(path, True, "exact")
    # A README often cites a path relative to a subdirectory it told you to cd into.
    base = p.rsplit("/", 1)[-1]
    if any(e.endswith("/" + p) for e in exact):
        return Claim(path, True, "suffix")
    if base in basenames:
        return Claim(path, True, "basename")
    if p in dirs or posixpath.dirname(p) in dirs:
        return Claim(path, True, "directory")
    return Claim(path, False, None)


def interesting(path: str) -> bool:
    low = path.lower()
    if any(t in low for t in IGNORE_TOKENS):
        return False
    if low.endswith(IGNORE_SUFFIX):
        return False
    return True


def verify(fixture: dict) -> Evidence:
    tree = fixture["file_tree"]
    exact, basenames, dirs = _index(tree)
    raw = [p for p in fixture.get("readme_referenced_paths", []) if interesting(p)]
    claims = [check_claim(p, exact, basenames, dirs) for p in raw]
    broken = [c.path for c in claims if not c.exists]
    sig = fixture.get("signals", {})
    return Evidence(
        artifact_id=fixture["artifact_id"],
        claims_total=len(claims),
        claims_broken=len(broken),
        broken_paths=broken,
        broken_ratio=round(len(broken) / len(claims), 3) if claims else 0.0,
        has_dependency_manifest=bool(sig.get("dependency_manifest")),
        has_container=bool(sig.get("container")),
        has_ci=bool(sig.get("ci_config")),
        has_licence=bool(sig.get("licence")),
        has_tests=bool(sig.get("tests")),
        has_build_script=bool(sig.get("build_script")),
        readme_bytes=len(fixture.get("readme", "")),
        n_files=fixture.get("n_files", 0),
        claims=[asdict(c) for c in claims],
    )


if __name__ == "__main__":
    import json
    from pathlib import Path
    rows = []
    for p in sorted(Path("data/fixtures").glob("*.json")):
        fx = json.loads(p.read_text())
        ev = verify(fx)
        rows.append((fx["_label"]["badge"], ev))
    print(f"{'BADGE':<11}{'CLAIMS':>7}{'BROKEN':>7}{'RATIO':>7}"
          f"{'DEP':>5}{'CI':>4}{'DOC':>5}{'TEST':>6}  ARTIFACT")
    print("-" * 96)
    for badge, ev in sorted(rows, key=lambda r: r[0]):
        print(f"{badge:<11}{ev.claims_total:>7}{ev.claims_broken:>7}{ev.broken_ratio:>7.2f}"
              f"{'Y' if ev.has_dependency_manifest else '.':>5}"
              f"{'Y' if ev.has_ci else '.':>4}"
              f"{'Y' if ev.has_container else '.':>5}"
              f"{'Y' if ev.has_tests else '.':>6}  {ev.artifact_id}")
    # Does the deterministic signal alone separate the tiers?
    from statistics import mean
    print()
    for tier in ("Available", "Functional", "Reusable"):
        g = [e for b, e in rows if b == tier]
        if g:
            print(f"{tier:<11} n={len(g):<3} mean broken-claim ratio={mean(e.broken_ratio for e in g):.3f}"
                  f"  mean claims={mean(e.claims_total for e in g):.1f}"
                  f"  dep-manifest={sum(e.has_dependency_manifest for e in g)}/{len(g)}")
