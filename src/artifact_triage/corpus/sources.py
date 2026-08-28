"""Scrape conference artifact-evaluation pages for (title, badge) ground truth.

Badges are expert-assigned by the conference Artifact Evaluation Committee and
published independently of this project. They are the labels we score against.

Researchr-based conference sites render each accepted artifact as a table row
carrying a `data-facet-badge` attribute, which is what we parse (rather than
visible text, which varies by theme).
"""
from __future__ import annotations

import html
import re
import ssl
import urllib.request
from dataclasses import dataclass, asdict

try:  # python.org macOS builds ship without a CA bundle; certifi makes this portable
    import certifi

    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover - system python with OS trust store
    _SSL = ssl.create_default_context()

UA = "artifact-repro-triage/0.1 (academic reproducibility research)"

# Ordinal severity of ACM artifact badges. Higher = stronger reproducibility
# guarantee from the expert committee.
BADGE_ORDER = {"Available": 0, "Functional": 1, "Reusable": 2}

SOURCES = {
    "issta-2024": "https://2024.issta.org/track/issta-2024-artifact-evaluation",
}

_ROW = re.compile(r"<tr.*?</tr>", re.S | re.I)
_BADGE = re.compile(r'data-facet-badge="([^"]+)"')
_ANCHOR = re.compile(r"<a[^>]*data-event-modal[^>]*>(.*?)</a>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class LabeledArtifact:
    venue: str
    title: str
    badge: str
    badge_rank: int


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30, context=_SSL) as r:
        return r.read().decode("utf-8", errors="replace")


def parse(venue: str, page_html: str) -> list[LabeledArtifact]:
    out: list[LabeledArtifact] = []
    seen: set[str] = set()
    for row in _ROW.findall(page_html):
        badge_m = _BADGE.search(row)
        anchor_m = _ANCHOR.search(row)
        if not (badge_m and anchor_m):
            continue
        badge = badge_m.group(1).strip()
        if badge not in BADGE_ORDER:
            continue  # e.g. "Best Artifact Award" is an accolade, not a tier
        # Anchor text = title + the badge label appended by the theme. Strip tags,
        # then remove the trailing badge word so the title stays clean.
        title = _TAGS.sub("", anchor_m.group(1))
        title = html.unescape(title).strip()
        if title.endswith(badge):
            title = title[: -len(badge)].strip()
        if not title or title in seen:
            continue
        seen.add(title)
        out.append(LabeledArtifact(venue, title, badge, BADGE_ORDER[badge]))
    return out


def collect() -> list[LabeledArtifact]:
    found: list[LabeledArtifact] = []
    for venue, url in SOURCES.items():
        found.extend(parse(venue, fetch(url)))
    return found


if __name__ == "__main__":
    import json
    arts = collect()
    from collections import Counter
    print(f"labeled artifacts: {len(arts)}")
    print("badge distribution:", dict(Counter(a.badge for a in arts)))
    for a in arts[:5]:
        print(f"  [{a.badge:10s}] {a.title[:70]}")
    with open("data/labels.jsonl", "w") as f:
        for a in arts:
            f.write(json.dumps(asdict(a)) + "\n")
    print("-> data/labels.jsonl")
