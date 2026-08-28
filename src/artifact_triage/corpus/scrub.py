"""Remove badge self-disclosure from artifact text before any model sees it.

THE LEAKAGE PROBLEM
-------------------
We score an agent on predicting an artifact's ACM badge tier. Many artifacts
announce that tier in their own README ("This artifact received the Artifacts
Evaluated - Reusable badge"). Feeding that text to a model measures nothing: it
reads the answer instead of judging the work.

Scrubbing has to happen before the baseline AND the solution see anything, and
both must receive byte-identical scrubbed input, or the comparison is unfair.

Every redaction is counted and reported so the audit is checkable rather than
asserted - `make corpus` prints how many artifacts were leaking and how many
spans were removed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Deliberately contains no matchable keyword, so redactions cannot re-match.
REDACTION = "[REDACTED]"

# Ordered most-specific first; each is a distinct way an artifact can leak.
PATTERNS: list[tuple[str, re.Pattern]] = [
    # Order matters: broad structures (images, whole sentences) must fire before
    # the bare-word rule, or the word is redacted and its container survives -
    # which previously left `.../badge/artifact-reusable-green` fully readable.
    ("badge_image", re.compile(
        r"!\[[^\]]*\]\([^)]*badge[^)]*\)"
        r"|<img[^>]+badge[^>]*>"
        r"|\[!\[[^\]]*\]\([^)]*badge[^)]*\)\]\([^)]*\)", re.I)),
    ("badge_url", re.compile(
        r"https?://\S*(?:badge|shields\.io)\S*", re.I)),
    ("badge_award_sentence", re.compile(
        r"[^.\n]*\b(?:awarded|received|earned|granted|holds?|obtained)\b"
        r"[^.\n]{0,80}\bbadges?\b[^.\n]*\.?", re.I)),
    ("acm_badge_phrase", re.compile(
        r"artefacts?|artifacts?\s*(?:evaluated|available)\s*[-\u2013\u2014:]?\s*"
        r"(?:functional|reusable|available)", re.I)),
    ("results_reproduced", re.compile(
        r"\bresults?\b(?:\s+\w+){0,3}\s+(?:reproduced|replicated)\b", re.I)),
    ("badge_tier_bare", re.compile(
        r"\b(?:artifact|artefact)s?\s+(?:is|are|was|were)\s+"
        r"(?:functional|reusable)\b", re.I)),
    ("ae_committee", re.compile(
        r"artifact\s+evaluation\s+committee", re.I)),
    ("badge_word", re.compile(
        r"\b(?:acm\s+)?badges?\b", re.I)),
]


@dataclass
class ScrubReport:
    text: str
    hits: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.hits.values())

    @property
    def leaked(self) -> bool:
        return self.total > 0


def scrub(text: str) -> ScrubReport:
    hits: dict[str, int] = {}
    for name, pat in PATTERNS:
        text, n = pat.subn(REDACTION, text)
        if n:
            hits[name] = n
    return ScrubReport(text, hits)


def assert_clean(text: str) -> None:
    """Fail loudly if anything survived. Used as a post-condition in the corpus build."""
    leftover = scrub(text)
    if leftover.leaked:
        raise AssertionError(f"badge leakage survived scrubbing: {leftover.hits}")


if __name__ == "__main__":
    samples = [
        "This artifact received the **Artifacts Evaluated - Reusable** badge at ISSTA 2024.",
        "![ACM Badge](https://img.shields.io/badge/artifact-reusable-green)",
        "Our results were reproduced by the Artifact Evaluation Committee.",
        "The artifact is Reusable and well documented.",
        "[![badge](https://img.shields.io/badge/ACM-Functional-blue)](https://acm.org)",
        "A normal README describing how to run `python main.py --seed 0`.",
    ]
    # A scrubbed sample must contain no residual tier word outside code context.
    TIERS = re.compile(r"\b(reusable|functional)\b", re.I)
    bad = 0
    for text in samples:
        r = scrub(text)
        residue = TIERS.findall(r.text)
        status = "clean" if not r.leaked else "scrubbed"
        if residue:
            status, bad = "RESIDUE!", bad + 1
        print(f"[{status:8s}] {r.hits}")
        print(f"   in : {text}")
        print(f"   out: {r.text}")
        if residue:
            print(f"   !! tier word survived: {residue}")
        print()
    print("FAIL: tier words survived scrubbing" if bad else "OK: no tier words survived")
