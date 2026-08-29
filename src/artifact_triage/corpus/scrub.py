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

# Separators seen between "Evaluated" and the tier in real READMEs: hyphens of
# three kinds, colon, slash, underscore, brackets, or nothing but whitespace.
SEP = r"[\s\-\u2013\u2014:/_()\[\]]*"

# Phrases that mark the surrounding sentence as being ABOUT artifact evaluation.
AE_CTX = (r"\b(?:badges?|(?:artefact|artifact)\s+evaluation|AEC"
          r"|AE\s+(?:committee|process|submission))\b")

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
    # The alternation here was UNGROUPED: `artefacts?|artifacts?\s*...` reads as
    # (artefacts?) OR (artifacts?...), so the British spelling matched the bare
    # word ALONE. "Artefacts Evaluated - Reusable" became
    # "[REDACTED] Evaluated - Reusable" - the word removed, the tier left in
    # plain sight. The same failure the badge-image comment above describes:
    # redact the label, keep the container.
    #
    # The separator class was also too narrow. Real READMEs write the tier as
    # "(Reusable)", "/ Functional" and "_reusable", none of which matched.
    ("acm_badge_phrase", re.compile(
        r"(?:artefacts?|artifacts?)" + SEP +
        r"(?:evaluated|available)" + SEP +
        r"(?:functional|reusable|available)", re.I)),
    ("results_reproduced", re.compile(
        r"\bresults?\b(?:\s+\w+){0,3}\s+(?:reproduced|replicated)\b", re.I)),
    ("badge_tier_bare", re.compile(
        r"\b(?:artifact|artefact)s?\s+(?:is|are|was|were)\s+"
        r"(?:functional|reusable)\b", re.I)),
    # NOTE: written first as `artefact|artifact\s+evaluation\s+committee` -
    # the EXACT ungrouped-alternation bug being fixed two patterns above,
    # reintroduced while fixing it. It silently redacted every bare "artefact".
    # Precedence errors in a regex are invisible until something tests the
    # branch, which is why the tests below assert both directions.
    ("ae_committee", re.compile(
        r"(?:artefact|artifact)\s+evaluation\s+committee", re.I)),
    # A tier word in the same sentence as badge / AE context is the answer,
    # however it is phrased ("we got the Reusable stamp from the AE committee").
    # Must precede `badge_word`, which would otherwise consume the very context
    # this rule depends on.
    #
    # This over-redacts: a sentence merely discussing artifact evaluation that
    # happens to say "reusable" is removed whole. That is the correct direction
    # to err. The baseline and the solution receive BYTE-IDENTICAL scrubbed
    # text, so over-redaction costs realism equally for both and cannot bias the
    # comparison - while leakage hands one side the answer and voids the result.
    ("tier_in_badge_sentence", re.compile(
        r"[^.\n]*" + AE_CTX + r"[^.\n]*\b(?:functional|reusable)\b[^.\n]*\.?"
        r"|[^.\n]*\b(?:functional|reusable)\b[^.\n]*" + AE_CTX + r"[^.\n]*\.?",
        re.I)),
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


# A redaction immediately followed by a bare tier word is the SIGNATURE of the
# British-spelling bug: the label was removed and the answer was left sitting
# next to the hole. Pattern-matching the phrasing cannot catch that - the
# surviving text matches nothing - but the shape is unmistakable, which is why
# this generalises to phrasings nobody anticipated.
# Deliberately narrow: only SEPARATORS and the structural words "evaluated" /
# "available" may sit between the redaction and the tier. A 40-character window
# was tried first and flagged innocent prose - "[REDACTED] and the code is
# reusable" - which would break the build on a false alarm. The signature is
# "redacted label + separator + tier", not "tier word somewhere nearby".
#
# `available` is deliberately NOT in the tier group. It is an extremely common
# English word - "[REDACTED] available at ..." is ordinary prose - and it is the
# FLOOR tier, so learning an artifact is merely `Available` is the least
# informative leak there is. Including it would trade frequent false build
# failures for almost no protection. `functional` and `reusable` are the two
# tiers that actually carry information, and both are rarer in prose.
_ORPHAN_TIER = re.compile(
    re.escape(REDACTION)
    + r"[\s\-\u2013\u2014:/_()\[\]]*(?:evaluated|available)?"
    # NOT \b before the tier: "_" is a word character, so there is no word
    # boundary in "[REDACTED]_reusable" and \b silently failed on one of the
    # very separator forms this check exists to catch.
    + r"[\s\-\u2013\u2014:/_()\[\]]*(?<![A-Za-z])(functional|reusable)"
      r"(?![A-Za-z])", re.I)


def assert_no_orphan_tier(text: str) -> None:
    """Catch 'redacted the label, kept the tier'."""
    m = _ORPHAN_TIER.search(text)
    if m:
        raise AssertionError(
            f"a tier word survives beside a redaction: {m.group(0)!r} - "
            f"scrubbing removed the container and left the answer")


def assert_clean(text: str) -> None:
    """Fail loudly if anything survived scrubbing.

    Called as a post-condition by the corpus build and the trajectory export.
    This docstring used to say it was "used as a post-condition in the corpus
    build" while nothing in the corpus build called it - a documented guarantee
    the repository did not contain, which is precisely the defect this project
    detects in other people's READMEs. It is wired in now, so the sentence is
    true.
    """
    leftover = scrub(text)
    if leftover.leaked:
        raise AssertionError(f"badge leakage survived scrubbing: {leftover.hits}")
    assert_no_orphan_tier(text)


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
