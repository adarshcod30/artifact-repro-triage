"""Find the GitHub mirror for artifacts Zenodo could not give us.

Only ~half of Zenodo records embed a repo link, and 12 of 43 artifacts never
resolved to Zenodo at all. GitHub's search API recovers many of them, but search
is fuzzy, so every candidate must be *verified* before it enters the corpus:
the repo's own text has to corroborate the paper. An unverified match would
silently poison the ground truth, which is worse than a smaller corpus.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    _SSL = ssl.create_default_context()

API = "https://api.github.com"
CACHE = Path("data/cache/github")
STOP = {"the", "a", "an", "of", "for", "and", "in", "on", "to", "with", "is",
        "are", "how", "far", "we", "not", "or", "at", "by", "from", "does",
        "can", "do", "toward", "towards", "study", "empirical", "large",
        "scale", "better", "more", "using", "via", "beyond"}


def _token() -> str | None:
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok
    try:  # gh stores its token in the keychain; reuse it if the CLI is present
        out = subprocess.run(["gh", "auth", "token"], capture_output=True,
                             text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None


def _get(url: str, cache_key: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{cache_key}.json"
    if path.exists():
        return json.loads(path.read_text())
    headers = {"User-Agent": "artifact-repro-triage/0.1",
               "Accept": "application/vnd.github+json"}
    tok = _token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers)
    delay = 3.0
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL) as r:
                data = json.loads(r.read().decode())
            path.write_text(json.dumps(data))
            # /search/* is capped at 30 req/min; the rest of the REST API allows
            # 5000/hr authenticated. Throttling both at search speed made a
            # 60-call corpus build take over two minutes for no reason.
            time.sleep(2.2 if "/search/" in url else 0.15)
            return data
        except urllib.error.HTTPError as exc:
            if exc.code not in (403, 429) or attempt == 4:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def keywords(title: str) -> list[str]:
    """Distinctive words only - generic paper vocabulary produces noise."""
    head = re.split(r"[:–—?]", title)[0]
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", head)
    return [w for w in words if w.lower() not in STOP][:6]


def search(title: str) -> list[dict]:
    kw = keywords(title)
    if not kw:
        return []
    q = " ".join(kw)
    key = re.sub(r"[^a-z0-9]+", "-", q.lower())[:80]
    url = f"{API}/search/repositories?{urllib.parse.urlencode({'q': q, 'per_page': 5})}"
    try:
        return _get(url, key).get("items", [])
    except Exception:
        return []


def readme(slug: str) -> str:
    """Fetch a repo's README. This is the corroborating evidence."""
    key = "readme-" + re.sub(r"[^a-z0-9]+", "-", slug.lower())
    try:
        data = _get(f"{API}/repos/{slug}/readme", key)
    except Exception:
        return ""
    import base64
    try:
        return base64.b64decode(data.get("content", "")).decode(
            "utf-8", errors="replace")
    except Exception:
        return ""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower())


def verify(repo: dict, title: str) -> tuple[bool, str]:
    """Strict verification against the repo's README.

    An earlier version scored keyword overlap against repo *metadata* and
    accepted `jekyll/minima` as the artifact for a patch-generation paper and a
    LodeRunner game clone for "Total Recall?". Generic paper vocabulary matches
    almost anything, so corroboration now has to come from the README, and the
    evidence string records exactly which rule fired so a human can audit it.
    """
    slug = repo["full_name"]
    text = _norm(readme(slug))
    if not text:
        return False, "no README to corroborate"

    head = _norm(re.split(r"[:\u2013\u2014?]", title)[0]).strip()

    # Rule 1 - strongest: the paper's title phrase appears verbatim.
    if len(head) >= 12 and head in text:
        return True, f"README contains title phrase '{head[:40]}'"

    # Rule 2: the README names the venue AND shares distinctive vocabulary.
    kw = [w.lower() for w in keywords(title)]
    overlap = sum(1 for w in kw if w in text)
    if re.search(r"issta[^a-z0-9]{0,3}(2024|24)", text) and overlap >= 2:
        return True, f"README cites ISSTA 2024 and {overlap}/{len(kw)} keywords"

    # Rule 3: near-total keyword coverage in the README body.
    if kw and overlap == len(kw) and len(kw) >= 3:
        return True, f"README contains all {len(kw)} distinctive keywords"

    return False, f"insufficient corroboration ({overlap}/{len(kw)} kw, no venue cite)"


def resolve(title: str) -> dict | None:
    for repo in search(title):
        ok, why = verify(repo, title)
        if ok:
            return {"slug": repo["full_name"], "stars": repo.get("stargazers_count"),
                    "pushed_at": repo.get("pushed_at"), "evidence": why,
                    "source": "github-search"}
    return None


if __name__ == "__main__":
    recs = [json.loads(l) for l in open("data/artifacts.jsonl")]
    added = 0
    for i, r in enumerate(recs, 1):
        z = r.get("zenodo") or {}
        if z.get("github_repos"):
            r["repo"] = {"slug": z["github_repos"][0], "source": "zenodo-metadata",
                         "evidence": "link embedded in Zenodo record"}
            continue
        found = resolve(r["title"])
        if found:
            r["repo"] = found
            added += 1
            print(f"[{i:2}/{len(recs)}] + {found['slug']:38s} <- {r['title'][:40]}")
        else:
            r["repo"] = None
    Path("data/artifacts.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in recs))
    have = [r for r in recs if r.get("repo")]
    from collections import Counter
    print(f"\nrecovered by GitHub search : {added}")
    print(f"total with a repo          : {len(have)}/{len(recs)}")
    print(f"badge distribution         : {dict(Counter(r['badge'] for r in have))}")
