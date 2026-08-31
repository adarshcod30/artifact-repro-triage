"""Check whether the URLs a README promises still resolve.

The stated main failure mode of the path verifier is that it only checks claims
shaped like file paths. This closes part of that gap: a README also promises
*locations* - a dataset download, a project page, a dependency, a DOI.

Published measurements say this matters. Link rot in software-engineering
research artifacts averages 9.4% and reaches 29.8% in some years, and only 56.4%
of artifacts were reachable at the links their papers provided. A README pointing
at a dead dataset is unusable however well written it is.

UNTRUSTED INPUT
---------------
The URLs checked here come from READMEs written by other people, and link
checking is on by default. That makes this the one module in the project that
takes an adversarial input and acts on it, so it refuses to fetch loopback,
private, link-local or reserved addresses - including after a redirect. See
`is_internal`.

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

import ipaddress
import json
import re
import socket
import ssl
import urllib.error
import urllib.parse
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


# ---------------------------------------------------------------------------
# SSRF defence. This module fetches URLs taken from UNTRUSTED READMEs, which is
# the tool's entire purpose: it is pointed at third-party research artifacts,
# it runs in CI, and it is built for reviewers assessing submitted work. That
# is an adversarial setting by construction.
#
# Without this, a README could make the tool request:
#   http://169.254.169.254/latest/meta-data/...  the cloud metadata endpoint,
#                                                which serves IAM credentials
#                                                under IMDSv1
#   http://localhost:8080/...                    services on the host
#   http://10.x / 192.168.x / 172.16.x           the internal network
#
# HEAD-only is not a defence: the status code alone is an internal port-scan
# oracle. And urllib FOLLOWS REDIRECTS by default, so an entirely public URL
# can redirect into private space - which is why the redirect target is
# re-validated rather than only the original URL.
# ---------------------------------------------------------------------------
class BlockedURL(Exception):
    """The URL resolves somewhere a link check has no business going."""


def _addresses(host: str) -> list[str]:
    try:
        return [ai[4][0] for ai in socket.getaddrinfo(host, None)]
    except Exception:
        return []


def is_internal(url: str) -> bool:
    """True if the URL resolves to a loopback, private or reserved address."""
    try:
        host = urllib.parse.urlsplit(url).hostname
    except ValueError:
        return True                      # unparseable: refuse rather than guess
    if not host:
        return True
    candidates = [host] + _addresses(host)
    for cand in candidates:
        try:
            ip = ipaddress.ip_address(cand)
        except ValueError:
            continue                     # a name, not an address
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return True
    # A name that resolves to nothing cannot be fetched anyway; let the request
    # fail normally rather than reporting it as blocked.
    return False


class _GuardedRedirects(urllib.request.HTTPRedirectHandler):
    """Re-check every hop. A public URL may redirect into private space."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if is_internal(newurl):
            raise BlockedURL(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_GuardedRedirects,
                                      urllib.request.HTTPSHandler(context=_SSL))


@dataclass
class LinkResult:
    url: str
    status: int | None
    ok: bool
    unverifiable: bool
    error: str | None = None


# Hosts that exist to serve badge images, and the shapes those images take.
#
# The filter used to be `"badge" in url.lower()`, which skipped ANY url merely
# mentioning badges - including documentation pages ABOUT badging, which are
# exactly the pages a reproducibility artifact is likely to link to. A badge is
# identified by where it comes from and what it is, not by the word appearing
# somewhere in a path.
_BADGE_HOSTS = ("shields.io", "badgen.net", "badge.fury.io", "coveralls.io",
                "codecov.io/gh", "travis-ci.org", "travis-ci.com",
                "circleci.com/gh", "app.codacy.com/project/badge",
                "api.codeclimate.com", "zenodo.org/badge")


def _is_badge_image(url: str) -> bool:
    low = url.lower()
    if any(h in low for h in _BADGE_HOSTS):
        return True
    # `.../badge.svg`, `.../badge.png`, `.../workflows/ci/badge.svg`
    return low.rsplit("/", 1)[-1].startswith("badge.") or low.endswith("/badge")


def extract(text: str, limit: int = 40) -> list[str]:
    seen, out = set(), []
    for u in _URL.findall(text):
        u = u.rstrip(".,;:!?")
        # Badge/shield images are decoration, not promises.
        if _is_badge_image(u):
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
    if is_internal(url):
        # Reported, never fetched. Counting it as dead would be wrong too - we
        # simply decline to find out, and say so.
        return LinkResult(url, None, True, True,
                          "internal or loopback address - not fetched")
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with _OPENER.open(req, timeout=TIMEOUT) as r:
            return LinkResult(url, r.status, 200 <= r.status < 400, False)
    except urllib.error.HTTPError as exc:
        # Some servers reject HEAD but serve GET. Retry once before calling it dead.
        if exc.code in (403, 405, 501):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with _OPENER.open(req, timeout=TIMEOUT) as r:
                    return LinkResult(url, r.status, 200 <= r.status < 400, False)
            except Exception:
                return LinkResult(url, exc.code, False, True,
                                  "rejects automated requests")
        return LinkResult(url, exc.code, False, False, f"HTTP {exc.code}")
    except BlockedURL as exc:
        return LinkResult(url, None, True, True,
                          f"redirected to an internal address ({exc})")
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
