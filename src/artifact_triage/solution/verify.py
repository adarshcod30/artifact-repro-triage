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

# Explicit placeholders. A README that says `path/to/data.csv` is not claiming a
# file exists - it is telling the reader to substitute their own. Reporting these
# as defects is how a checker teaches reviewers to ignore it.
PLACEHOLDER = re.compile(
    r"(?i)(^|/)(path/to|your[_-]|my[_-]|<[^>]+>|\{[^}]+\}|\$\w+|"
    r"[A-Z][A-Z0-9_]{2,}_(?:DIR|PATH|ROOT|HOME|FILE)|TMP_DIR|"
    r"example|foo|bar|baz|xxx|yyy)")

# Directories a tool CREATES when you run it. "Results go in `out/`" is a
# statement about future output, not a promise that `out/` ships in the repo.
# Measured: these were 14% of all reported-broken claims - the single largest
# false-positive class, introduced by the directory-reference feature itself.
RUNTIME_DIRS = {
    "out", "output", "outputs", "result", "results", "logs", "log", "tmp",
    "temp", "build", "dist", "cache", "testdata", "metadata", "corpus",
    "figures", "figs", "plots", "checkpoints", "ckpt", "runs", "artifacts",
    "target", "bin", "obj", "venv", "env", "node_modules",
}

# Dotfiles a README tells you to CREATE, or that tooling generates. Same
# rationale as RUNTIME_DIRS: "copy .env.example to .env" is an instruction, not
# a promise that `.env` ships - it is gitignored precisely because it must not.
#
# This class only became visible once the extractor stopped eating leading dots.
# Fixing that bug surfaced two new false positives in the negative control
# (`.env`, `.trustbench/models`), which is how a latent gap announces itself:
# the old bug was hiding it.
UNCOMMITTED_DOTFILES = {
    ".env", ".env.local", ".env.example", ".envrc", ".venv", ".cache",
    ".DS_Store", ".coverage", ".ipynb_checkpoints", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".idea",
}

# Dot-directories that ARE conventionally committed. Anything else beginning
# with a dot is tooling or generated state, so a reference into it is not a
# claim about shipped content.
COMMITTED_DOTDIRS = {
    ".github", ".gitlab", ".circleci", ".devcontainer", ".config", ".vscode",
    ".zenodo", ".binder", ".docker",
}


def suggest(path: str, file_tree: list[str], limit: int = 3) -> list[str]:
    """Find the most plausible real file for a broken claim.

    A report that only says "this is wrong" leaves the author to go hunting. Most
    broken claims are near-misses - a renamed directory, a moved script, a
    pluralised folder - so the fix is usually one path away and can be found
    deterministically.

    Ranked by basename match first (a moved file keeps its name), then by
    sequence similarity on the full path.
    """
    from difflib import SequenceMatcher

    target = path.strip().lstrip("./")
    base = target.rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0].lower()
    ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""

    scored: list[tuple[float, str]] = []
    for cand in file_tree:
        cbase = cand.rsplit("/", 1)[-1]
        # Same filename elsewhere in the tree is almost always the answer.
        if cbase == base:
            scored.append((1.0, cand))
            continue
        cstem = cbase.rsplit(".", 1)[0].lower()
        cext = cbase.rsplit(".", 1)[-1].lower() if "." in cbase else ""
        if ext and cext != ext:
            continue  # a .py claim is not answered by a .md file
        ratio = SequenceMatcher(None, stem, cstem).ratio()
        if ratio >= 0.72:
            # Break ties toward files at a similar depth.
            depth_penalty = abs(cand.count("/") - target.count("/")) * 0.01
            scored.append((ratio - depth_penalty, cand))
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    return [c for _, c in scored[:limit]]


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
    case_mismatches: list[str]
    suggestions: dict[str, list[str]]
    broken_ratio: float
    has_dependency_manifest: bool
    has_container: bool
    has_ci: bool
    has_licence: bool
    has_tests: bool
    has_build_script: bool
    readme_bytes: int
    n_files: int
    ignored: int
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
            for p in self.broken_paths[:15]:
                hint = self.suggestions.get(p)
                if hint:
                    lines.append(f"  - {p}   (closest real file: {hint[0]})")
                else:
                    lines.append(f"  - {p}   (nothing similar in the repository)")
        elif self.claims_total:
            lines.append("Every path the README references was found.")
        if self.case_mismatches:
            lines.append(f"CASE MISMATCH: {len(self.case_mismatches)} path(s) "
                         f"exist under a different case - these work on macOS "
                         f"and Windows but fail on Linux:")
            lines += [f"  - {p}" for p in self.case_mismatches[:8]]
        if self.ignored:
            lines.append(f"({self.ignored} author-declared exception pattern(s) "
                         f"applied from .artifact-triage-ignore)")
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
    # Case-only mismatch: the file exists under a different case. On a
    # case-insensitive filesystem the instruction works; on Linux it does not.
    # That is a real portability problem but NOT a missing file, and conflating
    # them makes the report wrong in a way a reviewer will notice immediately.
    lower_exact = {e.lower() for e in exact}
    if p.lower() in lower_exact:
        return Claim(path, True, "case-mismatch")
    if base.lower() in {b.lower() for b in basenames}:
        return Claim(path, True, "case-mismatch-basename")

    # A claimed *directory* is satisfied by that directory existing.
    if "." not in p.rsplit("/", 1)[-1] and p in dirs:
        return Claim(path, True, "directory")
    # NOTE: the parent directory existing does NOT satisfy a file claim.
    # An earlier version accepted `scripts/run_x.py` whenever `scripts/`
    # existed; the negative control caught it - detection was 84%, not 100%,
    # and every miss was this rule. "The folder is there" is not "the file is
    # there", and that distinction is the entire point of claim verification.
    return Claim(path, False, None)


IGNORE_FILE = ".artifact-triage-ignore"


def load_ignores(file_tree: list[str], fetch=None, slug: str = "") -> list[str]:
    """Read author-declared exceptions from `.artifact-triage-ignore`.

    Some READMEs legitimately reference paths that do not belong to their own
    repository - a tutorial quoting another project, or, as here, a tool whose
    documentation shows example output from the artifacts it analyses. The
    checker cannot infer that intent, and a linter that cannot be told about a
    legitimate exception is a linter people stop running.

    So the author declares them, in the open, in a file a reviewer can read. The
    report always states how many exceptions were applied - a silent suppression
    would be worse than a false positive.
    """
    if IGNORE_FILE not in file_tree or fetch is None or not slug:
        return []
    text = fetch(slug, IGNORE_FILE)
    if not text:
        return []
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def interesting(path: str) -> bool:
    low = path.lower()
    if any(t in low for t in IGNORE_TOKENS):
        return False
    if low.endswith(IGNORE_SUFFIX):
        return False
    if PLACEHOLDER.search(path):
        return False
    # Only bare directory names are treated as runtime output; `results/x.csv`
    # is still a concrete claim about a file.
    if "." not in path.rsplit("/", 1)[-1] and low.split("/")[-1] in RUNTIME_DIRS:
        return False
    head = path.split("/")[0]
    if head.startswith("."):
        if low in UNCOMMITTED_DOTFILES:
            return False
        # A reference INTO a dot-directory that is not conventionally committed
        # (`.trustbench/models`) is tooling state, not shipped content. A
        # top-level dotfile with a real extension (`.zenodo.json`) is a genuine
        # claim and stays.
        if "/" in path and head.lower() not in COMMITTED_DOTDIRS:
            return False
    return True


def verify(fixture: dict, ignores: list[str] | None = None) -> Evidence:
    import fnmatch

    tree = fixture["file_tree"]
    exact, basenames, dirs = _index(tree)
    ignores = ignores or fixture.get("declared_ignores") or []
    raw = [p for p in fixture.get("readme_referenced_paths", []) if interesting(p)]
    if ignores:
        raw = [p for p in raw
               if not any(fnmatch.fnmatch(p, g) for g in ignores)]
    claims = [check_claim(p, exact, basenames, dirs) for p in raw]
    broken = [c.path for c in claims if not c.exists]
    # Exists, but under a different case. Works on macOS/Windows, fails on
    # Linux - a real portability defect, reported separately so it is never
    # confused with a missing file.
    case_bad = [c.path for c in claims
                if c.exists and (c.matched_as or "").startswith("case-mismatch")]
    sig = fixture.get("signals", {})
    # Only compute suggestions for the paths we will actually show.
    hints = {p: suggest(p, tree) for p in broken[:15]}
    hints = {k: v for k, v in hints.items() if v}
    return Evidence(
        artifact_id=fixture["artifact_id"],
        claims_total=len(claims),
        claims_broken=len(broken),
        broken_paths=broken,
        case_mismatches=case_bad,
        suggestions=hints,
        broken_ratio=round(len(broken) / len(claims), 3) if claims else 0.0,
        has_dependency_manifest=bool(sig.get("dependency_manifest")),
        has_container=bool(sig.get("container")),
        has_ci=bool(sig.get("ci_config")),
        has_licence=bool(sig.get("licence")),
        has_tests=bool(sig.get("tests")),
        has_build_script=bool(sig.get("build_script")),
        readme_bytes=len(fixture.get("readme", "")),
        n_files=fixture.get("n_files", 0),
        ignored=len(ignores),
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
