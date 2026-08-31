"""Are the artifact's dependencies pinned, or will they drift?

WHY THIS CHECK EXISTS
---------------------
The single most-cited cause of artifact decay in the literature is unpinned
dependencies: over 40% of "functional" artifacts from 2024-2025 fail within
months, from drifting dependencies, unpinned versions and incomplete
environments.

`requirements.txt` containing `torch` will install a different library next year
than it did last year. `torch==2.1.0` will not. That distinction is mechanically
checkable, costs nothing, and predicts a failure mode that has already been
measured in the wild - so it belongs next to the path verifier.

Like the path checker, this reports facts rather than opinions: how many
requirements are pinned, how many float, and exactly which ones.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, asdict

from artifact_triage.corpus.github import API, CACHE as CACHE_DIR, _get

# Manifests we can meaningfully assess, in rough order of how strong a pin they
# usually represent.
#
# Lock files that fix a PYTHON/CONDA dependency graph. Only these can speak for
# a requirements.txt or an environment.yml.
PY_LOCKFILES = {"poetry.lock", "Pipfile.lock", "uv.lock", "conda-lock.yml"}
# Lock files from other ecosystems. A `package-lock.json` under a docs site says
# nothing about whether the artifact's Python environment is reproducible, and
# treating it as authoritative certified 8 corpus artifacts as 100% pinned
# without a single requirement ever being read.
OTHER_LOCKFILES = {"package-lock.json", "yarn.lock", "Cargo.lock"}
LOCKFILES = PY_LOCKFILES | OTHER_LOCKFILES
PY_MANIFESTS = {"requirements.txt", "requirements-dev.txt", "constraints.txt"}
CONDA = {"environment.yml", "environment.yaml"}

# `pkg==1.2.3` or `pkg @ git+...@sha` are pins; `pkg`, `pkg>=1.0`, `pkg~=1.0`
# are not. `>=x,<y` is a bounded range - better than nothing, worse than a pin.
_EXACT = re.compile(r"==\s*[\w.!+\-]+|@\s*git\+\S+@[0-9a-f]{7,}")
_BOUNDED = re.compile(r"[<>]=?\s*[\w.]+.*,.*[<>]=?\s*[\w.]+|~=\s*[\w.]+")
_COMMENT = re.compile(r"^\s*(#|$)")
_OPTION = re.compile(r"^\s*-")


# A container is only reproducible if its base image is pinned. `FROM python`
# or `FROM python:latest` resolves to a different image every month - the same
# drift problem as an unpinned pip requirement, one layer down.
_FROM = re.compile(r"^\s*FROM\s+(\S+)", re.I | re.M)


@dataclass
class DockerReport:
    dockerfile: str | None
    base_images: list[str]
    unpinned: list[str]

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        if self.dockerfile is None:
            return "no Dockerfile"
        if not self.base_images:
            return f"{self.dockerfile}: no FROM directive found"
        if not self.unpinned:
            return (f"{self.dockerfile}: all {len(self.base_images)} base "
                    f"image(s) pinned")
        return (f"{self.dockerfile}: {len(self.unpinned)} of "
                f"{len(self.base_images)} base image(s) unpinned "
                f"({', '.join(self.unpinned[:3])})")


def analyse_docker(slug: str, file_tree: list[str], fetch=None) -> DockerReport:
    """Is the container's base image pinned, or will it drift?"""
    if fetch is None:
        fetch = fetch_file
    path = _shallowest(file_tree, {"Dockerfile", "dockerfile"})
    if path is None:
        return DockerReport(None, [], [])
    text = fetch(slug, path)
    if text is None:
        return DockerReport(path, [], [])
    images, unpinned = [], []
    for raw in _FROM.findall(text):
        img = raw.split(" AS ")[0].split(" as ")[0].strip()
        if img.startswith("$"):           # ARG-parameterised, cannot judge
            continue
        images.append(img)
        tag = img.rsplit(":", 1)[-1] if ":" in img.rsplit("/", 1)[-1] else ""
        # A digest (@sha256:...) is the strongest possible pin.
        if "@sha256:" in img:
            continue
        if not tag or tag in ("latest", "main", "master", "stable", "edge"):
            unpinned.append(img)
    return DockerReport(path, images, unpinned)


@dataclass
class PinReport:
    manifest: str | None
    total: int
    pinned: int
    bounded: int
    floating: int
    floating_examples: list[str]
    has_lockfile: bool
    pinned_ratio: float
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        if self.has_lockfile:
            return f"lock file present ({self.manifest}) - versions are pinned"
        if self.manifest is None:
            return "no dependency manifest found"
        if self.total == 0:
            return f"{self.manifest} present but lists no requirements"
        return (f"{self.manifest}: {self.pinned}/{self.total} pinned, "
                f"{self.bounded} bounded, {self.floating} floating "
                f"({self.pinned_ratio:.0%} pinned)")


def fetch_file(slug: str, path: str) -> str | None:
    # The readable part is TRUNCATED, so it cannot be the whole key. Slug and
    # path were concatenated and then cut to 80 characters, so on a
    # long-slugged repository every file collapsed onto one cache entry and the
    # cache returned whichever file was fetched first - a Dockerfile answered
    # with a requirements.txt, silently. Measured: 16 of 754 corpus slugs (2.1%)
    # have two or more pipeline-fetched paths sharing a key; on one repo, 14
    # distinct paths share a single entry.
    #
    # A short digest of the FULL identity keeps filenames readable while making
    # a collision require a hash collision rather than a long name.
    ident = f"{slug}-{path}".lower()
    slugpath = re.sub(r"[^a-z0-9]+", "-", ident)
    digest = hashlib.sha256(ident.encode()).hexdigest()[:12]
    key = "content-" + slugpath[:64] + "-" + digest

    # 533 cache entries were committed under the old key, and this repository's
    # offline guarantee depends on them. A LEGACY key is unambiguous exactly
    # when it was not truncated, so it is accepted as a fallback only in that
    # case - which preserves every sound entry and refuses precisely the ones
    # that could have collided.
    legacy = "content-" + slugpath[:80]
    if len(slugpath) <= 80:
        legacy_path = CACHE_DIR / f"{legacy}.json"
        if legacy_path.exists() and not (CACHE_DIR / f"{key}.json").exists():
            key = legacy

    try:
        data = _get(f"{API}/repos/{slug}/contents/{path}", key)
    except Exception:
        return None
    if not isinstance(data, dict) or "content" not in data:
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except Exception:
        return None


def classify_requirements(text: str) -> tuple[int, int, int, list[str]]:
    pinned = bounded = floating = 0
    examples: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or _COMMENT.match(raw) or _OPTION.match(line):
            continue
        if _EXACT.search(line):
            pinned += 1
        elif _BOUNDED.search(line):
            bounded += 1
        else:
            floating += 1
            if len(examples) < 8:
                examples.append(line[:60])
    return pinned, bounded, floating, examples


# A conda constraint that is a RANGE, not a pin. Tested before the bare "="
# check, because ">=", "<=", "!=" and "~=" all contain "=".
#
# The two-sided / one-sided split matches `classify_requirements` exactly:
# `>=1.0,<2.0` is BOUNDED (better than nothing, worse than a pin); a lone
# `>=1.0` is FLOATING. Fixing the pin test without also matching this split
# would have left the two paths disagreeing about the same input, which is the
# defect that made the original bug invisible.
_CONDA_BOUNDED = re.compile(r"[<>]=?\s*[\w.]+.*,.*[<>]=?\s*[\w.]+|~=\s*[\w.]+")
_CONDA_RANGE = re.compile(r"(>=|<=|!=|~=|>|<)")


def classify_conda(text: str) -> tuple[int, int, int, list[str]]:
    pinned = bounded = floating = 0
    examples: list[str] = []
    in_channels = False
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if stripped and not stripped[0].isspace() and stripped.endswith(":"):
            in_channels = stripped.startswith("channels")
        line = raw.strip()
        if not line.startswith("-") or line.startswith("- name"):
            continue
        dep = line.lstrip("- ").strip()
        if not dep or dep.endswith(":"):
            continue
        # Skip the `channels:` block: its entries are repositories, not
        # dependencies. Counting them made `conda-forge` and `defaults`
        # register as two unpinned requirements.
        if in_channels:
            continue
        # `pkg=1.2.3` is a conda pin. `pkg>=1.18`, `pkg<=1.9` and `pkg!=2.0`
        # are not - but every one of those operators CONTAINS an "=", so the
        # old test (`"=" in dep and not dep.endswith("=")`) counted all of them
        # as pinned, inverting the check this function exists to perform.
        # `classify_requirements` had the same distinction right, so the two
        # code paths disagreed about identical input.
        if _CONDA_BOUNDED.search(dep):
            bounded += 1
        elif _CONDA_RANGE.search(dep):
            floating += 1
            if len(examples) < 8:
                examples.append(dep[:60])
        elif "=" in dep and not dep.endswith("="):
            pinned += 1
        else:
            floating += 1
            if len(examples) < 8:
                examples.append(dep[:60])
    return pinned, bounded, floating, examples


def _shallowest(file_tree: list[str], wanted: set[str]) -> str | None:
    """Pick the manifest nearest the repository root.

    A naive basename lookup selected `FF_AFL++/frida_mode/ts/package-lock.json`
    - a vendored sub-dependency six levels deep - as an artifact's dependency
    manifest. The artifact's own manifest is the one closest to the root; deeply
    nested ones belong to bundled third-party code and say nothing about whether
    the artifact itself is reproducible.
    """
    best, best_depth = None, 10**6
    for path in file_tree:
        if path.rsplit("/", 1)[-1] not in wanted:
            continue
        depth = path.count("/")
        if depth < best_depth:
            best, best_depth = path, depth
    # Beyond two directories deep it is almost certainly vendored code.
    return best if best is not None and best_depth <= 2 else None


def analyse(slug: str, file_tree: list[str]) -> PinReport:
    # A lock file is authoritative only for its OWN ecosystem. This used to
    # accept any lock file and return immediately at pinned_ratio 1.0, so a
    # `package-lock.json` belonging to a docs site suppressed the artifact's own
    # `requirements.txt`, which was then never fetched at all. Measured: 8 of
    # 754 cached artifacts were certified fully pinned that way without a single
    # requirement being read, and 24 had a coexisting manifest suppressed.
    py_lock = _shallowest(file_tree, PY_LOCKFILES)
    if py_lock:
        return PinReport(py_lock, 0, 0, 0, 0, [], True, 1.0,
                         "lock file fixes the full dependency graph")
    foreign_lock = _shallowest(file_tree, OTHER_LOCKFILES)

    manifest = _shallowest(file_tree, PY_MANIFESTS)
    if manifest:
        text = fetch_file(slug, manifest)
        if text is None:
            return PinReport(manifest, 0, 0, 0, 0, [], False, 0.0,
                             "manifest present but could not be read")
        p, b, f, ex = classify_requirements(text)
        total = p + b + f
        return PinReport(manifest, total, p, b, f, ex, False,
                         round(p / total, 3) if total else 0.0)

    if foreign_lock and not _shallowest(file_tree, CONDA):
        # The repository pins SOMETHING, but nothing Python or conda to assess.
        # Say exactly that, rather than implying the artifact's own environment
        # is reproducible.
        return PinReport(foreign_lock, 0, 0, 0, 0, [], True, 1.0,
                         f"lock file for another ecosystem ({foreign_lock}); "
                         f"no Python or conda manifest found to check")

    conda = _shallowest(file_tree, CONDA)
    if conda:
        text = fetch_file(slug, conda)
        if text is None:
            return PinReport(conda, 0, 0, 0, 0, [], False, 0.0,
                             "manifest present but could not be read")
        p, b, f, ex = classify_conda(text)
        total = p + b + f
        return PinReport(conda, total, p, b, f, ex, False,
                         round(p / total, 3) if total else 0.0)

    return PinReport(None, 0, 0, 0, 0, [], False, 0.0,
                     "no dependency manifest - environment cannot be recreated")


if __name__ == "__main__":
    from pathlib import Path
    from statistics import mean

    rows = []
    for p in sorted(Path("data/fixtures").glob("*.json")):
        fx = json.loads(p.read_text())
        rep = analyse(fx["artifact_id"], fx["file_tree"])
        rows.append((fx["_label"]["badge"], fx["artifact_id"], rep))
        print(f"  {fx['artifact_id'][:44]:<46} {rep.summary()}")

    assessable = [r for _, _, r in rows if r.total > 0]
    none_at_all = [r for _, _, r in rows if r.manifest is None]
    locked = [r for _, _, r in rows if r.has_lockfile]
    print("\n" + "=" * 68)
    print("DEPENDENCY PINNING")
    print("=" * 68)
    print(f"  artifacts                        : {len(rows)}")
    print(f"  no manifest at all               : {len(none_at_all)} "
          f"({len(none_at_all)/len(rows):.0%})")
    print(f"  lock file present                : {len(locked)}")
    print(f"  manifests with listed requirements: {len(assessable)}")
    if assessable:
        print(f"  mean pinned ratio                : "
              f"{mean(r.pinned_ratio for r in assessable):.1%}")
        fully = sum(1 for r in assessable if r.pinned_ratio == 1.0)
        print(f"  fully pinned                     : {fully}/{len(assessable)}")
        drifting = sum(1 for r in assessable if r.floating > 0)
        print(f"  WITH >=1 FLOATING DEPENDENCY     : {drifting}/{len(assessable)} "
              f"({drifting/len(assessable):.0%})")
    print("=" * 68)
    print("Literature: unpinned versions are the most-cited cause of artifact")
    print("decay; >40% of 2024-25 'functional' artifacts fail within months.")
