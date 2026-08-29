"""Harvest research-artifact repositories at scale from Zenodo.

WHY SCALE MATTERS HERE
----------------------
The badge-labelled corpus is 15 artifacts, because ISSTA 2024 was the only venue
found publishing machine-readable badge outcomes. That is enough to compare two
systems, but far too few to say anything about the world.

The verifier needs no labels and no model: it is deterministic Python that reads
a file tree. So it can be pointed at *hundreds* of artifacts to measure how
widespread broken documentation actually is - turning the tool into a measurement
instrument rather than only a classifier.

Published work motivates the question:
  - Over 40% of "functional" artifacts from 2024-2025 fail within months, from
    drifting dependencies, unpinned versions and incomplete environments.
  - Link rot in SE research artifacts averages 9.4%, reaching 29.8% in some years.
  - Only 56.4% of artifacts were reachable at the links their papers gave.

None of that measures whether an artifact's own README is consistent with its own
repository, which is what this corpus is built to answer.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from dataclasses import dataclass, asdict
from pathlib import Path

from artifact_triage.corpus.zenodo import _SSL, API, UA, github_repos
import urllib.request

CACHE = Path("data/cache/discover")
OUT = Path("data/discovered.jsonl")

# Phrases research artifacts actually use to describe themselves. Deliberately
# venue-spanning: the question is about research software generally, not ISSTA.
QUERIES = [
    'artifact ISSTA', 'artifact ICSE', 'artifact FSE', 'artifact ASE',
    'artifact ESEC', 'artifact MSR', 'artifact ISSRE',
    '"replication package"', '"reproduction package"',
    '"artifact evaluation"', '"research artifact" software',
    '"supplementary material" software repository',
]


@dataclass
class Discovered:
    zenodo_id: int
    doi: str | None
    title: str
    publication_date: str | None
    repo: str
    query: str


def _get(url: str, key: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    delay = 8.0
    for attempt in range(7):
        try:
            with urllib.request.urlopen(req, timeout=45, context=_SSL) as r:
                data = json.loads(r.read().decode())
            path.write_text(json.dumps(data))
            time.sleep(2.5)  # Zenodo rate-limits anonymous search aggressively
            return data
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 5:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


# Zenodo rejects size > 25 with HTTP 400 ("Page size ..."), not a rate-limit
# error. Paginate more instead of asking for bigger pages.
ZENODO_MAX_PAGE_SIZE = 25


def search(query: str, page: int, size: int = ZENODO_MAX_PAGE_SIZE) -> list[dict]:
    params = urllib.parse.urlencode({
        "q": query, "size": size, "page": page,
        "type": "software", "sort": "mostrecent",
    })
    key = re.sub(r"[^a-z0-9]+", "-", f"{query}-p{page}".lower())[:80]
    try:
        return _get(f"{API}?{params}", key).get("hits", {}).get("hits", [])
    except urllib.error.HTTPError as exc:
        # Surface the status code: an earlier version printed only the exception
        # type, which made a plain 429 look like an unknown failure.
        print(f"    ! {query} p{page}: HTTP {exc.code}")
        return []
    except Exception as exc:
        print(f"    ! {query} p{page}: {type(exc).__name__}: {str(exc)[:60]}")
        return []


def harvest(pages: int = 6) -> list[Discovered]:
    seen_repo: set[str] = set()
    found: list[Discovered] = []
    for q in QUERIES:
        before = len(found)
        for page in range(1, pages + 1):
            for hit in search(q, page):
                repos = github_repos(hit)
                if not repos:
                    continue
                slug = repos[0]
                if slug.lower() in seen_repo:
                    continue
                seen_repo.add(slug.lower())
                m = hit.get("metadata", {})
                found.append(Discovered(
                    zenodo_id=hit.get("id"), doi=hit.get("doi"),
                    title=(m.get("title") or "")[:180],
                    publication_date=m.get("publication_date"),
                    repo=slug, query=q))
        print(f"  {q:<44} +{len(found) - before:<4} (total {len(found)})")
    return found


def harvest_stratified(years=range(2018, 2027), per_year_pages: int = 3,
                       seen_repo: set | None = None) -> list[Discovered]:
    """Sample evenly across publication years.

    The default harvest uses Zenodo's `mostrecent` sort, which returned a corpus
    spanning about a month at the median - enough to measure prevalence, but far
    too narrow to test whether broken claims accumulate with age. Querying each
    year separately gives the temporal spread that test needs, and removes the
    recency skew that the datasheet had to declare as a limitation.
    """
    seen_repo = seen_repo if seen_repo is not None else set()
    found: list[Discovered] = []
    base_queries = ['artifact', '"replication package"', '"reproduction package"']
    for year in years:
        before = len(found)
        for bq in base_queries:
            q = f'{bq} AND publication_date:[{year}-01-01 TO {year}-12-31]'
            for page in range(1, per_year_pages + 1):
                for hit in search(q, page):
                    repos = github_repos(hit)
                    if not repos:
                        continue
                    slug = repos[0]
                    if slug.lower() in seen_repo:
                        continue
                    seen_repo.add(slug.lower())
                    m = hit.get("metadata", {})
                    found.append(Discovered(
                        zenodo_id=hit.get("id"), doi=hit.get("doi"),
                        title=(m.get("title") or "")[:180],
                        publication_date=m.get("publication_date"),
                        repo=slug, query=f"year:{year}"))
        print(f"  {year}  +{len(found) - before:<4} (total {len(found)})")
    return found


if __name__ == "__main__":
    import sys
    if "--stratified" in sys.argv:
        existing = set()
        prior: list[Discovered] = []
        if OUT.exists():
            for line in OUT.read_text().splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                prior.append(Discovered(**d))
                existing.add(d["repo"].lower())
        print(f"existing corpus: {len(prior)} repos")
        extra = harvest_stratified(seen_repo=existing)
        items = prior + extra
        OUT.write_text("".join(json.dumps(asdict(d)) + "\n" for d in items))
        print(f"\nadded {len(extra)}; corpus now {len(items)} repositories")
        raise SystemExit(0)

    items = harvest()

    # `make discover` overwrites. The corpus reached 769 repositories through a
    # stratified harvest across publication years; a plain run finds 398 and
    # would silently replace the larger file with the smaller one, shrinking the
    # measured population without saying so. That happened once, during
    # development, and was only caught because a backup existed.
    #
    # Destroying data is not something a build target should do quietly.
    if OUT.exists():
        have = len([l for l in OUT.read_text().splitlines() if l.strip()])
        if have > len(items) and "--force" not in sys.argv:
            raise SystemExit(
                f"REFUSING to shrink the corpus: {OUT} holds {have} "
                f"repositories, this run found {len(items)}.\n"
                f"  To EXTEND the corpus:  make discover ARGS=--stratified\n"
                f"  To replace it anyway:  ... --force")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(asdict(d)) + "\n" for d in items))
    print(f"\ndiscovered {len(items)} distinct artifact repositories")
    print(f"-> {OUT}")
