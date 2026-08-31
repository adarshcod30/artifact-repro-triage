"""Build a scrubbed, structured fact sheet per artifact - over the API, no clones.

WHY NOT CLONE
-------------
The first version shallow-cloned each repo. One artifact (`zhangxiaosa/LPR`)
was 15 GB on its own and drove the disk to 100% full mid-run. Research repos
routinely commit datasets, models and VM images.

The GitHub tree API returns the complete recursive file listing - paths and
sizes - without transferring a single blob. Two calls per artifact, zero disk,
and pinned to an explicit commit SHA so the fact sheet is reproducible.

The fact sheet is the ONLY input the baseline and solution ever see, and both
read the identical file. Fairness is structural, not promised.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from artifact_triage.corpus.github import API, _get
from artifact_triage.corpus.scrub import assert_clean, scrub

FIXTURES = Path("data/fixtures")

SIGNALS = {
    "dependency_manifest": ["requirements.txt", "environment.yml", "environment.yaml",
                            "pyproject.toml", "setup.py", "Pipfile", "poetry.lock",
                            "package.json", "Cargo.toml", "pom.xml", "build.gradle"],
    "container": ["dockerfile", "docker-compose.yml", "docker-compose.yaml", "vagrantfile"],
    "build_script": ["makefile", "cmakelists.txt", "build.sh", "install.sh", "setup.sh"],
    "ci_config": [".github/workflows", ".gitlab-ci.yml", ".travis.yml"],
    "licence": ["license", "license.md", "licence", "copying", "license.txt"],
    "tests": ["test", "tests", "test.py", "tests.py"],
}

_CODE_BLOCK = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)
_INLINE = re.compile(r"`([^`\n]{2,80})`")
# A dot does not make a path. The first version of this matched any token
# containing a dot, which swept up version numbers ("3.10.12"), Java class names
# ("com.foo.BarTest.testBaz"), module paths ("vllm.entrypoints.openai.api") and
# bare domains ("github.com") - 55 of 58 "broken claims" on one artifact were
# extraction noise. A claim now needs a real source/config extension.
CODE_EXT = {
    "py", "sh", "bash", "zsh", "r", "rb", "pl", "lua", "jl",
    "c", "h", "cc", "cpp", "hpp", "cxx", "java", "jar", "go", "rs", "kt", "scala",
    "js", "jsx", "ts", "tsx", "mjs", "php", "cs", "swift", "m",
    "json", "yaml", "yml", "toml", "ini", "cfg", "conf", "properties", "env",
    "txt", "md", "rst", "csv", "tsv", "sql", "xml", "html", "css",
    "ipynb", "lock", "mk", "cmake", "gradle", "dockerfile", "tf", "proto",
    # Build-system extensions. `Makefile.am` was missed until a regression test
    # caught it - autotools artifacts would have had their build files skipped.
    "am", "ac", "in", "m4", "nix", "bzl", "bazel", "cabal", "sbt",
}
_PATHLIKE = re.compile(r"^[\w./\-]+\.([A-Za-z0-9]{1,10})$")


def _is_path(tok: str) -> bool:
    m = _PATHLIKE.match(tok)
    if not m:
        return False
    ext = m.group(1).lower()
    if ext not in CODE_EXT:
        return False
    # "1.0.py" style false positives, and dotted identifiers with no separator.
    stem = tok[: -(len(ext) + 1)]
    if not stem or stem.replace(".", "").replace("-", "").isdigit():
        return False
    # Java/Python dotted identifiers: several dots, no slash, no real dir.
    # A LEADING dot means a dotfile, not an identifier - `.zenodo.json` and
    # `.pre-commit-config.yaml` both trip the two-dot rule and are not
    # `com.example.Foo`. Without this exemption, fixing the dot-stripping bug
    # merely moved the dotfiles from wrong to invisible.
    if "/" not in tok and tok.count(".") >= 2 and not tok.startswith("."):
        return False
    return True


def default_branch_sha(slug: str) -> tuple[str, str]:
    meta = _get(f"{API}/repos/{slug}", "repo-" + slug.replace("/", "__"))
    branch = meta.get("default_branch", "main")
    ref = _get(f"{API}/repos/{slug}/commits/{branch}",
               "head-" + slug.replace("/", "__"))
    return branch, ref.get("sha", "")[:12]


def tree(slug: str, sha: str) -> list[dict]:
    data = _get(f"{API}/repos/{slug}/git/trees/{sha}?recursive=1",
                "tree-" + slug.replace("/", "__"))
    return [{"path": e["path"], "size": e.get("size", 0)}
            for e in data.get("tree", []) if e.get("type") == "blob"]


def readme(slug: str) -> str:
    try:
        data = _get(f"{API}/repos/{slug}/readme", "readme-" + slug.replace("/", "__"))
        return base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
    except Exception:
        return ""


# A directory reference is a claim too: "see `reproduction/`" promises that
# directory exists. Only an EXPLICIT trailing slash counts - without it,
# `CC/CXX` and `ff-all-in-one/++` get swept in, and a checker that reports
# variable names as missing directories will be switched off.
_DIRREF = re.compile(r"^[\w.\-]+(?:/[\w.\-]+)*/$")


def _is_dir_ref(tok: str) -> bool:
    if not tok.endswith("/") or tok.startswith(("http", "-", "$", "/")):
        return False
    if not _DIRREF.match(tok):
        return False
    segs = [x for x in tok.rstrip("/").split("/") if x]
    # Reject single-letter segments and anything shell-ish.
    return bool(segs) and all(len(x) >= 2 for x in segs)


_URL_IN_TEXT = re.compile(r"(?:https?|ftp)://\S+|\bwww\.\S+", re.I)


def _norm_ref(tok: str) -> str | None:
    """Strip an explicit `./` prefix. Keep dotfiles. Drop parent traversal.

    This was `tok.lstrip("./")`, which strips CHARACTERS, not a prefix - the
    same class of bug as the `rstrip(".git")` that once turned "upbeat" into
    "upbea". It ate the leading dot of every dotfile:

        .zenodo.json            -> zenodo.json
        .pre-commit-config.yaml -> pre-commit-config.yaml
        .github/workflows/ci.yml-> github/workflows/ci.yml

    A repository that HAS `.zenodo.json` was therefore reported as missing
    `zenodo.json` - a file that never existed. That is a FALSE POSITIVE, and
    it accounted for 29 of 1,264 broken claims (2.29%) on the corpus.

    `../x` is dropped rather than rewritten: it points outside the repository,
    so nothing here can verify it, and silently reinterpreting it as `x` invents
    a claim the README never made.
    """
    while tok.startswith("./"):
        tok = tok[2:]
    if tok.startswith("../") or tok == ".." or tok == ".":
        return None
    return tok.lstrip("/") or None


def referenced_paths(text: str) -> list[str]:
    """Paths the README claims exist - raw material for claim verification.

    Scans the entire README rather than only fenced code blocks. Block-pairing
    was fragile: one unmatched or four-backtick fence upstream misaligned every
    delimiter after it, and the negative control caught the result - three
    injected false paths inside a ```bash block were silently never extracted,
    while the two in inline backticks were. `_is_path` is strict enough that a
    whole-document scan does not add false claims (verified: 0 false positives
    across the corpus).
    """
    # Strip URLs BEFORE extracting. The token pattern cannot contain ":", so
    # "https://github.com/other/repo/blob/main/x.py" degraded to
    # "//github.com/.../x.py" and survived as a claimed repo path - a file that
    # by construction can never exist here, counted as a broken claim.
    #
    # Measured on the 732-artifact sweep: 126 of 1,190 broken paths (10.6%) were
    # links to OTHER projects' files - github.com/..., conda.io/docs/...,
    # pandoc.org/MANUAL.html. A README linking to another project's source is
    # not claiming that source is in this repository. The datasheet already
    # warned this could happen; nobody had measured it.
    #
    # Link rot is still checked - links.py extracts URLs from the raw README
    # independently, which is why the two concerns were kept in separate
    # modules.
    text = _URL_IN_TEXT.sub(" ", text)

    found: set[str] = set()
    for tok in re.findall(r"[\w./\-]+\.[A-Za-z0-9]{1,10}", text):
        if _is_path(tok):
            norm = _norm_ref(tok)
            if norm:
                found.add(norm)
    for tok in _INLINE.findall(text):
        tok = _norm_ref(tok.strip()) or ""
        if _is_path(tok):
            found.add(tok)
        elif _is_dir_ref(tok):
            found.add(tok.rstrip("/"))
    return sorted(found)[:80]


def signals_present(paths: list[str]) -> dict[str, list[str]]:
    lower = [(p.lower(), p) for p in paths]
    out: dict[str, list[str]] = {}
    for kind, names in SIGNALS.items():
        hits = []
        for n in names:
            for pl, p in lower:
                base = pl.rsplit("/", 1)[-1]
                if base == n or pl == n or pl.startswith(n + "/"):
                    hits.append(p)
                    break
        out[kind] = sorted(set(hits))[:6]
    return out


def build(record: dict) -> dict | None:
    slug = record["repo"]["slug"]
    try:
        branch, sha = default_branch_sha(slug)
        entries = tree(slug, sha)
    except Exception as exc:
        print(f"    ! {slug}: {type(exc).__name__} {str(exc)[:60]}")
        return None
    paths = [e["path"] for e in entries]
    raw = readme(slug)
    rep = scrub(raw)
    # The post-condition `assert_clean`'s own docstring claimed it already had.
    # It did not: its only caller was the trajectory exporter, so the corpus
    # build - the one place badge leakage would actually contaminate a result -
    # had no check at all. Scrubbing is idempotent (the redaction token contains
    # no matchable keyword), so a second pass finding anything means the first
    # pass missed it.
    #
    # A second pass alone would NOT have caught the British-spelling leak -
    # "[REDACTED] Evaluated - Reusable" matches no pattern, which is why it
    # survived. Verified, rather than assumed. `assert_clean` therefore also
    # checks for a tier word orphaned beside a redaction, which is that bug's
    # actual signature.
    assert_clean(rep.text)
    total_bytes = sum(e["size"] for e in entries)
    return {
        "artifact_id": slug,
        "venue": record["venue"],
        "paper_title": record["title"],
        "commit": sha,
        "default_branch": branch,
        "n_files": len(paths),
        "repo_bytes": total_bytes,
        # NOT truncated: path-existence checks are only sound over the complete
        # tree. Capping at 4000 silently turned 4 of 15 artifacts' real paths
        # into false "broken claims" - and those artifacts were exactly the
        # outliers driving the headline result.
        "file_tree": paths,
        "largest_files": sorted(entries, key=lambda e: -e["size"])[:10],
        "readme": rep.text[:20000],
        "readme_present": bool(raw),
        "readme_scrub": {"leaked": rep.leaked, "hits": rep.hits},
        "signals": signals_present(paths),
        "readme_referenced_paths": referenced_paths(rep.text),
        "_label": {"badge": record["badge"], "rank": record["badge_rank"]},
    }


if __name__ == "__main__":
    FIXTURES.mkdir(parents=True, exist_ok=True)
    recs = [json.loads(l) for l in open("data/artifacts.jsonl")]
    corpus = [r for r in recs if r.get("repo")]
    leaked = ok = 0
    for i, r in enumerate(corpus, 1):
        fx = build(r)
        if fx is None:
            continue
        ok += 1
        leaked += fx["readme_scrub"]["leaked"]
        (FIXTURES / f"{fx['artifact_id'].replace('/', '__')}.json").write_text(
            json.dumps(fx, indent=1))
        print(f"[{i:2}/{len(corpus)}] {fx['n_files']:5d} files "
              f"{fx['repo_bytes']/1e6:8.1f}MB  claims={len(fx['readme_referenced_paths']):3d}  "
              f"{'LEAK' if fx['readme_scrub']['leaked'] else ' ok '}  {fx['artifact_id']}")
    print(f"\nfixtures      : {ok}/{len(corpus)}")
    print(f"badge leakage : {leaked} READMEs disclosed their own tier (scrubbed)")
    print("disk used     : 0 bytes of clones - tree API only")
