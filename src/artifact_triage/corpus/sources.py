"""Scrape conference artifact-evaluation pages for (title, badge) ground truth.

Badges are expert-assigned by the conference Artifact Evaluation Committee and
published independently of this project. They are the labels we score against.

Researchr-based conference sites render each accepted artifact as a table row
carrying a `data-facet-badge` attribute, which is what we parse (rather than
visible text, which varies by theme).
"""
from __future__ import annotations

import html
import sys
from pathlib import Path
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
        anchor_m = _ANCHOR.search(row)
        if not anchor_m:
            continue
        # ALL badges on the row, not just the first. Taking `search()` and then
        # skipping the row when it was not a tier discarded the row's real tier
        # badge whenever an accolade like "Best Artifact Award" happened to come
        # first in DOM order. Today ISSTA 2024 emits Reusable first, so the
        # correct label was picked by luck of ordering rather than by logic.
        labels = [m.strip() for m in _BADGE.findall(row)]
        tiers = [b for b in labels if b in BADGE_ORDER]
        if not tiers:
            continue  # e.g. only "Best Artifact Award" - an accolade, not a tier
        badge = max(tiers, key=lambda b: BADGE_ORDER[b])
        # Anchor text = title + a label span the theme appends for EVERY badge.
        # Stripping only one left the surplus label words inside the title on
        # multi-badge rows, which then failed to match the Zenodo deposit.
        title = _TAGS.sub("", anchor_m.group(1))
        title = html.unescape(title).strip()
        # Peel labels off the END repeatedly. One pass per label is not enough:
        # the spans are concatenated, so removing the last one exposes the next.
        # Iterating the label list once in length order left
        # "TitleBest Artifact Award" behind on a two-badge row.
        changed = True
        while changed:
            changed = False
            for lab in labels:
                if lab and title.endswith(lab):
                    title = title[: -len(lab)].strip()
                    changed = True
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
    # Never overwrite a good corpus with an empty one. `collect()` returns []
    # on any silent scrape failure - a theme change that drops the
    # data-facet-badge attribute, a soft-404, a page move - and this block used
    # to truncate data/labels.jsonl to zero bytes and exit 0. It is the FIRST of
    # the three commands REPRODUCTION.md tells a reproducer to run, and the two
    # after it both read that file, so an empty write propagated silently
    # through the whole corpus rebuild. Same class as `make discover`
    # overwriting a stratified harvest with a smaller one.
    out = Path("data/labels.jsonl")
    if not arts:
        raise SystemExit(
            "REFUSING to write an empty data/labels.jsonl: the scrape returned "
            "0 artifacts, which almost always means the page structure changed "
            "rather than that the venue has no badges.\n"
            f"  {out} left untouched.")
    if out.exists():
        have = len([l for l in out.read_text().splitlines() if l.strip()])
        if have > len(arts) and "--force" not in sys.argv:
            raise SystemExit(
                f"REFUSING to shrink the label set: {out} holds {have} "
                f"artifacts, this scrape found {len(arts)}. Use --force to "
                f"replace it anyway.")
    with out.open("w") as f:
        for a in arts:
            f.write(json.dumps(asdict(a)) + "\n")
    print(f"-> {out}")
