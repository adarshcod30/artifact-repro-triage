"""When should a human decide instead of the model?

WHY THE FIRST DESIGN FAILED
---------------------------
Escalation was originally gated on the model's self-reported confidence, below a
threshold of 0.55. Measured over the corpus, it fired **0 times out of 15**.

The reason is worse than the threshold being wrong. Self-reported confidence took
exactly three values (0.7, 0.8, 0.9) and was **anti-calibrated**: mean confidence
was 0.700 when the answer was right and 0.750 when it was wrong. The gate was
wired to the one signal in the system that carries no information.

WHAT REPLACES IT
----------------
Evidence-based rules. Each asks a question about what was actually verified, not
about how the model feels, so each is deterministic and cannot be talked out of.

The rules are deliberately conservative: escalation costs a reviewer's attention,
so a rule earns its place only if a human genuinely adds something the evidence
cannot settle. Every escalation names the rule that fired, so a reviewer can see
why their time is being asked for - and disagree.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Decision:
    escalate: bool
    reasons: list[str]

    def explain(self) -> str:
        # NOT "handled automatically". Two of ACM's four Functional criteria
        # cannot be settled mechanically at all - `Consistent` needs the paper,
        # `Exercisable` needs execution - so no artifact is ever fully
        # auto-dispositioned. Claiming otherwise here while `criteria.py` says
        # the opposite in the same report is the self-contradiction this
        # project exists to catch, committed by this project.
        if not self.escalate:
            return ("no additional escalation triggered - a reviewer must still "
                    "rule on Consistent and must run the artifact")
        return "routed to a human reviewer: " + "; ".join(self.reasons)


# A README asserting a tier this strong while its own documented paths are
# missing is the specific contradiction this project exists to surface.
CONTRADICTION_RATIO = 0.30

# The exact opening of every reason `decide()` can produce. The self-audit below
# compares against these rather than guessing.
#
# It used to take the SECOND WORD of a hand-written label and substring-match it
# against the fired reasons. "no README - nothing to assess" yielded "README",
# which matches the DIFFERENT rule "README makes no checkable file references",
# so a rule that never fired was reported as fired and vanished from both lists.
# A self-audit that cannot name its own rules is not an audit.
RULES = {
    "no_readme": "no README",
    "no_answer": "model returned no usable answer",
    "no_claims": "README makes no checkable file references",
    "contradiction": "rated",
    "readme_tiny": "README is only",
    "no_environment": "neither a dependency manifest nor a container",
}


def decide(evidence, tier: str | None, confidence: float,
           readme_present: bool = True) -> Decision:
    """Escalate on the evidence, not on the model's opinion of itself."""
    reasons: list[str] = []

    if not readme_present:
        reasons.append("no README - nothing to assess mechanically")

    if tier is None:
        reasons.append("model returned no usable answer")

    # No verifiable claims means we have no evidence in EITHER direction. A
    # confident answer here is confidence about nothing.
    if readme_present and evidence.claims_total == 0:
        reasons.append(
            "README makes no checkable file references, so no claim could be "
            "verified either way")

    # The model overriding verified evidence is the case a human must see.
    #
    # This originally required tier == "Reusable", and NEVER FIRED: the model
    # does not use that tier on this corpus. I had tested the rule by passing
    # the true badge instead of the model's prediction, saw it fire, and wrote
    # it up - documenting a capability that does not exist in the pipeline. The
    # same dead-code failure the confidence gate had, in its replacement.
    #
    # `Functional` is defined by ACM as "documented, consistent, complete,
    # exercisable", so a Functional verdict over a third of missing paths is
    # exactly as contradictory as a Reusable one.
    if (tier in ("Functional", "Reusable") and evidence.claims_total >= 4
            and evidence.broken_ratio >= CONTRADICTION_RATIO):
        reasons.append(
            f"rated {tier} while {evidence.claims_broken} of "
            f"{evidence.claims_total} documented paths do not exist - the "
            f"verdict contradicts the evidence")

    # Documentation so thin that any verdict is mostly inference.
    if readme_present and evidence.readme_bytes < 400:
        reasons.append(
            f"README is only {evidence.readme_bytes} bytes - too little to "
            f"support a judgement")

    # No manifest AND no container: the environment cannot be recreated at all,
    # which is a call about acceptability, not a fact about the files.
    if not evidence.has_dependency_manifest and not evidence.has_container:
        reasons.append(
            "neither a dependency manifest nor a container - whether that is "
            "acceptable depends on the artifact's kind, which needs a human")

    return Decision(bool(reasons), reasons)


if __name__ == "__main__":
    import json
    from pathlib import Path

    from artifact_triage.solution.verify import verify

    # Read the model's PREDICTIONS. Passing the true badge here is what
    # produced a documented claim about a rule that never fires in production.
    try:
        preds = {r["artifact_id"]: r["tier"]
                 for r in json.loads(Path("results/solution.json").read_text())["raw"]}
    except Exception:
        preds = {}
        print("(results/solution.json not found - showing rule logic only)\n")

    print(f"{'ARTIFACT':<46}{'PREDICTED':<12}{'DECISION'}")
    print("-" * 96)
    n_esc = 0
    rule_counts: dict[str, int] = {}
    rows = []
    for p in sorted(Path("data/fixtures").glob("*.json")):
        fx = json.loads(p.read_text())
        ev = verify(fx)
        # Confidence is passed but deliberately unused by the rules.
        tier = preds.get(fx["artifact_id"])
        d = decide(ev, tier, 0.8, fx.get("readme_present", True))
        n_esc += d.escalate
        for r in d.reasons:
            key = r.split(" - ")[0][:46]
            rule_counts[key] = rule_counts.get(key, 0) + 1
        rows.append((fx["artifact_id"], tier, d))
        mark = "ESCALATE" if d.escalate else "auto"
        print(f"{fx['artifact_id'][:44]:<46}{str(tier):<12}{mark}")
        for r in d.reasons:
            print(f"{'':<58}- {r[:70]}")

    print("-" * 96)
    print(f"  escalated: {n_esc}/{len(rows)} ({n_esc/len(rows):.0%})   "
          f"handled automatically: {len(rows)-n_esc}")
    print(f"  previous confidence-threshold design escalated 0/15 (0%)")
    print()
    print("  UNTRIGGERED RULES. These are guards, not demonstrated capabilities:")
    fired_keys = set(rule_counts)
    untriggered = [rid for rid, prefix in RULES.items()
                   if not any(k.startswith(prefix) for k in fired_keys)]
    for rid in untriggered:
        print(f"    - {rid}: reasons starting \"{RULES[rid]}...\"")
    if not untriggered:
        print("    (none - every rule fired at least once)")
    if "contradiction" in untriggered:
        print("    The contradiction rule has never fired on this corpus, because")
        print("    the model shown verified evidence already downgrades the")
        print("    contradictory artifacts itself (LPR: 88% broken -> Available).")
        print("    That is a good sign about the solution and leaves the rule")
        print("    unvalidated on real data. It is exercised only by tests.")
    print("\n  Rules that fired:")
    for k, v in sorted(rule_counts.items(), key=lambda x: -x[1]):
        print(f"    {v:>3}x  {k}")
