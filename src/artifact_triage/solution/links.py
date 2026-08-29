"""Check whether the URLs a README promises still resolve.

The stated main failure mode of the path verifier is that it only checks claims
shaped like file paths. This closes part of that gap: a README also promises
*locations* - a dataset download, a project page, a dependency, a DOI.

Published measurements say this matters. Link rot in software-engineering
research artifacts averages 9.4% and reaches 29.8% in some years, and only 56.4%
of artifacts were reachable at the links their papers provided. A README pointing
at a dead dataset is unusable however well written it is.

DETERMINISM BOUNDARY
--------------------
This module is the one part of the pipeline that depends on the outside world,
and the outside world changes. It is therefore kept *separate* from
`verify.py`, which stays offline and byte-deterministic. Results are cached to
`data/cache/links/` and committed, so a reported figure can be reproduced exactly
even after a host goes down - and re-running with `--refresh` shows the drift,
which is itself a measurement.
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    _SSL = ssl.create_default_context()

CACHE = Path("data/cache/links")
UA = "artifact-repro-triage/0.1 (academic reproducibility research; link check)"
TIMEOUT = 12

_URL = re.compile(r"https?://[^\s\)\]\}<>\"'`,;]+")

# Hosts that reject automated HEAD requests or require auth. A 403 from these
# says nothing about whether a human could reach the page, so they are reported
# as "unverifiable" rather than counted as dead - miscounting them would inflate
# the headline number in our favour.
UNVERIFIABLE_HOSTS = (
    "twitter.com", "x.com", "linkedin.com", "facebook.com",
    "docs.google.com", "drive.google.com", "researchgate.net",
    "sciencedirect.com", "ieeexplore.ieee.org", "dl.acm.org",
    "springer.com", "link.springer.com", "wiley.com",
)


@dataclass
class LinkResult:
    url: str
    status: int | None
    ok: bool
    unverifiable: bool
    error: str | None = None


def extract(text: str, limit: int = 40) -> list[str]:
    seen, out = set(), []
    for u in _URL.findall(text):
        u = u.rstrip(".,;:!?")
        # Badge/shield images are decoration, not promises.
        if "shields.io" in u or "badge" in u.lower():
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= limit:
            break
    return out


def _unverifiable(url: str) -> bool:
    return any(h in url.lower() for h in UNVERIFIABLE_HOSTS)


def check(url: str) -> LinkResult:
    if _unverifiable(url):
        return LinkResult(url, None, True, True, "host blocks automated checks")
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_SSL) as r:
            return LinkResult(url, r.status, 200 <= r.status < 400, False)
    except urllib.error.HTTPError as exc:
        # Some servers reject HEAD but serve GET. Retry once before calling it dead.
        if exc.code in (403, 405, 501):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=TIMEOUT, context=_SSL) as r:
                    return LinkResult(url, r.status, 200 <= r.status < 400, False)
            except Exception:
                return LinkResult(url, exc.code, False, True,
                                  "rejects automated requests")
        return LinkResult(url, exc.code, False, False, f"HTTP {exc.code}")
    except Exception as exc:
        return LinkResult(url, None, False, False, type(exc).__name__)


def check_all(urls: list[str], workers: int = 8) -> list[LinkResult]:
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(check, urls))


def for_artifact(artifact_id: str, readme: str, refresh: bool = False) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{artifact_id.replace('/', '__')}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    urls = extract(readme)
    results = [asdict(r) for r in check_all(urls)]
    dead = [r for r in results if not r["ok"] and not r["unverifiable"]]
    checked = [r for r in results if not r["unverifiable"]]
    summary = {
        "artifact_id": artifact_id,
        "urls_found": len(urls),
        "urls_checked": len(checked),
        "urls_unverifiable": len(results) - len(checked),
        "urls_dead": len(dead),
        "dead_ratio": round(len(dead) / len(checked), 3) if checked else 0.0,
        "dead_urls": [r["url"] for r in dead][:15],
        "results": results,
    }
    path.write_text(json.dumps(summary, indent=1))
    return summary


if __name__ == "__main__":
    import sys
    from statistics import mean

    refresh = "--refresh" in sys.argv
    rows = []
    for p in sorted(Path("data/fixtures").glob("*.json")):
        fx = json.loads(p.read_text())
        s = for_artifact(fx["artifact_id"], fx.get("readme", ""), refresh)
        rows.append((fx["_label"]["badge"], s))
        print(f"  {s['urls_dead']:>2}/{s['urls_checked']:<3} dead  "
              f"({s['urls_unverifiable']} unverifiable)  {s['artifact_id']}")
    checked = sum(r[1]["urls_checked"] for r in rows)
    dead = sum(r[1]["urls_dead"] for r in rows)
    with_dead = sum(1 for r in rows if r[1]["urls_dead"] > 0)
    print("\n" + "=" * 60)
    print(f"artifacts scanned          : {len(rows)}")
    print(f"URLs checked               : {checked}")
    print(f"dead URLs                  : {dead}  ({dead/checked:.1%})"
          if checked else "no URLs checked")
    print(f"artifacts with >=1 dead URL: {with_dead}/{len(rows)} "
          f"({with_dead/len(rows):.0%})")
    print("=" * 60)
    print("Published baseline: link rot in SE research artifacts averages 9.4%,")
    print("reaching 29.8% in some years (arXiv 2404.06852).")
