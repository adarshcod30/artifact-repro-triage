"""Will this artifact run anywhere but the author's machine?

The literature names "incomplete environments" alongside unpinned dependencies as
a cause of artifact decay. One concrete, mechanically detectable form of that is
**environment leakage**: paths, hostnames and credentials that only resolve on the
machine where the artifact was written.

`/home/alice/projects/data/train.csv` in a config file is not a bug on the
author's laptop. It is a guaranteed failure for every subsequent reader, and it
is invisible in a README that says "run `python train.py`".

Everything here is deterministic and free: it reads text the GitHub API already
returned. Findings cite file and line, so a reviewer can check each one.

DELIBERATELY NARROW
-------------------
Only patterns that are near-certainly non-portable are reported. `/usr/bin` and
`/tmp` are conventional and excluded; a user-specific home directory is not.
Over-reporting would train a reviewer to ignore the output, which is worse than
reporting nothing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field

# Config and script files worth reading. Binaries and data are skipped.
INSPECTABLE = (".py", ".sh", ".bash", ".yaml", ".yml", ".json", ".cfg", ".ini",
               ".toml", ".conf", ".env", ".r", ".m", ".jl", ".txt", ".md")

PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("absolute_home_path", re.compile(
        r"[\"'`\s=(]((?:/home/|/Users/|/root/)[A-Za-z0-9._\-]+/[^\s\"'`)]{3,})"),
     "hard-coded path to a specific user's home directory"),
    ("windows_user_path", re.compile(
        r"[\"'`\s=(]([A-Za-z]:\\\\?Users\\\\?[^\s\"'`)]{3,})"),
     "hard-coded Windows user path"),
    ("absolute_mnt_path", re.compile(
        r"[\"'`\s=(]((?:/mnt/|/media/|/data[0-9]?/|/scratch/)[^\s\"'`)]{4,})"),
     "hard-coded mount point that will not exist elsewhere"),
    ("localhost_port", re.compile(
        r"\b(?:127\.0\.0\.1|localhost):(\d{4,5})\b"),
     "hard-coded local service address"),
    ("private_host", re.compile(
        r"\b((?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\.\d{1,3})\b"),
     "private network address only reachable on the author's network"),
    ("conda_env_path", re.compile(
        r"[\"'`\s=(]((?:/opt/conda|/anaconda3|~/anaconda3|~/miniconda3)/envs/[^\s\"'`)]+)"),
     "absolute conda environment path"),
]

# Conventional locations that are portable in practice.
BENIGN = re.compile(r"^/(?:usr|bin|etc|tmp|var|opt|proc|sys|dev)(?:/|$)")


@dataclass
class Finding:
    kind: str
    detail: str
    file: str
    line: int
    excerpt: str


@dataclass
class PortabilityReport:
    files_scanned: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.findings)

    def to_dict(self) -> dict:
        return {"files_scanned": self.files_scanned,
                "n_findings": self.n,
                "findings": [asdict(f) for f in self.findings]}

    def summary(self) -> str:
        if not self.findings:
            return (f"no environment leakage found across "
                    f"{self.files_scanned} inspected file(s)")
        kinds = {}
        for f in self.findings:
            kinds[f.kind] = kinds.get(f.kind, 0) + 1
        parts = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in kinds.items())
        return f"{self.n} portability issue(s): {parts}"


def scan_text(text: str, path: str, limit: int = 6) -> list[Finding]:
    out: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if len(line) > 400:  # minified or data line
            continue
        for kind, pat, detail in PATTERNS:
            m = pat.search(line)
            if not m:
                continue
            value = m.group(1)
            if BENIGN.match(value):
                continue
            out.append(Finding(kind, detail, path, lineno,
                               line.strip()[:110]))
            break
        if len(out) >= limit:
            break
    return out


def inspect(slug: str, file_tree: list[str], max_files: int = 12,
            fetch=None) -> PortabilityReport:
    """Scan a bounded sample of shallow config/script files.

    Bounded on purpose: a full scan of a 40,000-file repository would cost
    thousands of API calls to find defects that cluster in the entry points a
    user actually touches.
    """
    if fetch is None:
        from artifact_triage.solution.pinning import fetch_file as fetch

    candidates = [
        p for p in file_tree
        if p.lower().endswith(INSPECTABLE)
        and p.count("/") <= 2
        and not any(seg in p.lower() for seg in
                    ("node_modules/", "vendor/", "third_party/", "/site-packages/",
                     ".git/", "docs/", "test/", "tests/"))
    ]
    candidates.sort(key=lambda p: (p.count("/"), len(p)))
    candidates = candidates[:max_files]

    findings: list[Finding] = []
    scanned = 0
    for path in candidates:
        text = fetch(slug, path)
        if text is None:
            continue
        scanned += 1
        findings.extend(scan_text(text, path))
    return PortabilityReport(scanned, findings)


if __name__ == "__main__":
    import json
    from pathlib import Path

    rows = []
    for p in sorted(Path("data/fixtures").glob("*.json")):
        fx = json.loads(p.read_text())
        rep = inspect(fx["artifact_id"], fx["file_tree"])
        rows.append((fx["artifact_id"], rep))
        print(f"  {fx['artifact_id'][:44]:<46} {rep.summary()}")
        for f in rep.findings[:2]:
            print(f"        {f.file}:{f.line}  {f.excerpt[:78]}")

    affected = [r for _, r in rows if r.n]
    total = sum(r.n for _, r in rows)
    print("\n" + "=" * 68)
    print("ENVIRONMENT LEAKAGE (hard-coded, machine-specific values)")
    print("=" * 68)
    print(f"  artifacts scanned            : {len(rows)}")
    print(f"  WITH >=1 PORTABILITY ISSUE   : {len(affected)}/{len(rows)} "
          f"({len(affected)/len(rows):.0%})")
    print(f"  total findings               : {total}")
    print("=" * 68)
    print("Literature names 'incomplete environments' alongside unpinned")
    print("dependencies as a leading cause of artifact decay.")
