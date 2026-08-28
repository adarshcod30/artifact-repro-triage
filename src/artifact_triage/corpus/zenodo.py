"""Resolve each labeled artifact title to its Zenodo deposit.

The Zenodo record IS the artifact the committee evaluated, so it is the correct
unit of analysis - more faithful than a GitHub mirror that may have drifted
since the badge was awarded.

Matching is fuzzy (Zenodo titles are decorated, e.g. `Artifact of [ISSTA'24] "..."`),
so every match records a similarity score. Low-confidence matches are kept but
flagged, never silently accepted - the corpus is auditable by a human.
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    _SSL = ssl.create_default_context()

UA = "artifact-repro-triage/0.1 (academic reproducibility research)"
API = "https://zenodo.org/api/records"
CACHE = Path("data/cache/zenodo")
MATCH_THRESHOLD = 0.62  # below this we flag for human review rather than trust

_NORM = re.compile(r"[^a-z0-9 ]+")
_GH = re.compile(r"https?://github\.com/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)")


def github_repos(record: dict) -> list[str]:
    """Pull candidate GitHub repos out of anywhere in the Zenodo metadata.

    Zenodo deposits are archival bundles - often tens of GB of VM images and
    datasets - so the code itself is analysed via its GitHub mirror instead.
    """
    blob = json.dumps(record.get("metadata", {}))
    seen, out = set(), []
    for owner, repo in _GH.findall(blob):
        # rstrip() strips CHARACTERS, not a suffix: "upbeat".rstrip(".git")
        # returns "upbea". removesuffix is the correct operation.
        repo = repo.removesuffix(".git")
        slug = f"{owner}/{repo}"
        if slug.lower() not in seen:
            seen.add(slug.lower())
            out.append(slug)
    return out


def normalise(s: str) -> str:
    """Strip Zenodo's decoration so titles compare on substance alone."""
    s = s.lower()
    s = re.sub(r"artifact\s*(of|for)?\s*", " ", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)          # [ISSTA'24]
    s = re.sub(r"\((replication|artifact)[^)]*\)", " ", s)
    s = _NORM.sub(" ", s)
    return " ".join(s.split())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalise(a), normalise(b)).ratio()


def query(title: str) -> dict:
    """Search Zenodo, caching raw responses so re-runs are offline + deterministic."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^a-z0-9]+", "-", title.lower())[:90]
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    params = urllib.parse.urlencode({"q": f'"{title}"', "size": 5})
    req = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": UA})
    # Zenodo returns 429 under sustained querying; back off rather than lose the row.
    delay = 2.0
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL) as r:
                data = json.loads(r.read().decode())
            path.write_text(json.dumps(data))
            time.sleep(1.5)
            return data
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 5:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def resolve(title: str) -> dict | None:
    try:
        data = query(title)
    except Exception as exc:  # network/API hiccup - record, do not crash the run
        return {"error": str(exc)}
    best, best_score = None, 0.0
    for hit in data.get("hits", {}).get("hits", []):
        score = similarity(title, hit.get("metadata", {}).get("title", ""))
        if score > best_score:
            best, best_score = hit, score
    if best is None:
        return None
    files = best.get("files", [])
    return {
        "github_repos": github_repos(best),
        "zenodo_id": best.get("id"),
        "doi": best.get("doi"),
        "zenodo_title": best.get("metadata", {}).get("title"),
        "match_score": round(best_score, 3),
        "low_confidence": best_score < MATCH_THRESHOLD,
        "files": [
            {"key": f.get("key"), "size": f.get("size"),
             "link": f.get("links", {}).get("self")}
            for f in files
        ],
        "total_bytes": sum(f.get("size", 0) for f in files),
    }


if __name__ == "__main__":
    labels = [json.loads(l) for l in open("data/labels.jsonl")]
    out, hits, low = [], 0, 0
    for i, lab in enumerate(labels, 1):
        res = resolve(lab["title"])
        rec = {**lab, "zenodo": res}
        out.append(rec)
        ok = bool(res and res.get("zenodo_id") and not res.get("low_confidence"))
        hits += ok
        low += bool(res and res.get("low_confidence"))
        mark = "OK " if ok else ("LOW" if res and res.get("zenodo_id") else "MISS")
        mb = round((res or {}).get("total_bytes", 0) / 1e6, 1) if res else 0
        print(f"[{i:2}/{len(labels)}] {mark} {lab['badge']:10s} {mb:6.1f}MB  {lab['title'][:56]}")
    Path("data/artifacts.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in out))
    total_mb = sum((r["zenodo"] or {}).get("total_bytes", 0) for r in out) / 1e6
    print(f"\nresolved cleanly : {hits}/{len(labels)}")
    print(f"low confidence   : {low}  (flagged for human review)")
    print(f"corpus download  : {total_mb:.0f} MB")
