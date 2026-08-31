"""Scoring. One scorer, used by baseline and solution alike.

PRIMARY METRIC - Mean Absolute Rank Error (MAE), in badge tiers.
    Badges are ordinal (Available 0 < Functional 1 < Reusable 2), so being one
    tier off is meaningfully better than being two tiers off. Plain accuracy
    throws that structure away; rank correlation is unstable at N=15 with three
    classes. MAE keeps the ordering, stays interpretable ("off by 0.4 tiers on
    average"), and is well behaved at this sample size. Lower is better.

The task is asymmetric in the same way triage always is: over-promising is worse
than under-promising. Calling an `Available` artifact `Reusable` tells a
researcher to build on something that was never checked to work. The reverse
merely wastes some of their time. OVERCLAIM_RATE tracks that direction
separately, because a single averaged number hides it.

ESCALATION. A prediction below the confidence threshold is not scored as a guess;
it is routed to a human. That is the product working as intended, so the report
gives both autonomous accuracy and the human workload it costs.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

TIERS = {"Available": 0, "Functional": 1, "Reusable": 2}
RANK_TO_TIER = {v: k for k, v in TIERS.items()}

# Minutes a human artifact reviewer spends assessing one artifact unaided.
# Sourced from published AE committee guidance; see README for provenance.
HUMAN_MINUTES_PER_ARTIFACT = 45.0
# Minutes to check an agent's evidence-backed recommendation instead.
REVIEW_MINUTES_WITH_EVIDENCE = 8.0


@dataclass
class Prediction:
    artifact_id: str
    predicted: str | None       # tier name, or None if the run failed
    confidence: float           # 0..1
    escalated: bool = False
    evidence: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Report:
    system: str
    n: int
    n_scored: int
    n_escalated: int
    n_failed: int
    mae: float | None
    exact_accuracy: float | None
    adjacent_accuracy: float | None
    overclaim_rate: float | None
    escalation_rate: float
    human_minutes: float
    human_minutes_saved: float
    input_tokens: int
    output_tokens: int
    usd: float
    per_item: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def score(system: str, preds: list[Prediction], labels: dict[str, str],
          usd_per_mtok_in: float, usd_per_mtok_out: float) -> Report:
    scored, per_item = [], []
    n_esc = n_fail = 0

    for p in preds:
        truth = labels[p.artifact_id]
        t_rank = TIERS[truth]
        row = {"artifact_id": p.artifact_id, "truth": truth,
               "predicted": p.predicted, "confidence": round(p.confidence, 3),
               "escalated": p.escalated}
        if p.escalated:
            n_esc += 1
            row["outcome"] = "escalated"
        elif p.predicted is None or p.predicted not in TIERS:
            n_fail += 1
            row["outcome"] = "failed"
        else:
            err = TIERS[p.predicted] - t_rank
            scored.append(err)
            row["rank_error"] = err
            row["outcome"] = "correct" if err == 0 else (
                "overclaim" if err > 0 else "underclaim")
        per_item.append(row)

    n = len(preds)
    if scored:
        mae = sum(abs(e) for e in scored) / len(scored)
        exact = sum(1 for e in scored if e == 0) / len(scored)
        adjacent = sum(1 for e in scored if abs(e) <= 1) / len(scored)
        overclaim = sum(1 for e in scored if e > 0) / len(scored)
    else:
        mae = exact = adjacent = overclaim = None

    # Escalated items still cost a full human review; handled items cost a check.
    human = n_esc * HUMAN_MINUTES_PER_ARTIFACT + \
        (n - n_esc) * REVIEW_MINUTES_WITH_EVIDENCE
    baseline_human = n * HUMAN_MINUTES_PER_ARTIFACT

    tin = sum(p.input_tokens for p in preds)
    tout = sum(p.output_tokens for p in preds)
    usd = tin / 1e6 * usd_per_mtok_in + tout / 1e6 * usd_per_mtok_out

    return Report(
        system=system, n=n, n_scored=len(scored), n_escalated=n_esc, n_failed=n_fail,
        mae=mae and round(mae, 3), exact_accuracy=exact and round(exact, 3),
        adjacent_accuracy=adjacent and round(adjacent, 3),
        overclaim_rate=overclaim if overclaim is None else round(overclaim, 3),
        escalation_rate=round(n_esc / n, 3) if n else 0.0,
        human_minutes=round(human, 1),
        human_minutes_saved=round(baseline_human - human, 1),
        input_tokens=tin, output_tokens=tout, usd=round(usd, 4),
        per_item=per_item,
    )


def comparison_table(reports: list[Report]) -> str:
    """The brief's required table: primary outcome, human time, cost per task."""
    if not reports:
        return ""
    head = reports[0]
    cols = [r.system for r in reports]
    w = max(22, max(len(c) for c in cols) + 2)

    def fmt(v, nd=3, suffix=""):
        return "n/a" if v is None else f"{v:.{nd}f}{suffix}"

    # Every rate below is computed over `n_scored`, which EXCLUDES escalated
    # items - so the columns do not share a denominator. The solution escalates
    # 5 of 15 and is scored on 10; the baseline is scored on all 15. Printing
    # them side by side under a single "n = 15" footer let a system look better
    # for answering fewer questions. Scoring the solution's identical answers
    # over all 15 gives MAE 1.000, not 0.700.
    #
    # The denominator is now printed per column, and the row is labelled, so the
    # comparison cannot be read as like-for-like when it is not.
    rows = [
        ("Scored over (excludes escalated)",
         [f"{r.n_scored} of {r.n}" for r in reports]),
        ("PRIMARY  MAE (tiers, lower better)",
         [fmt(r.mae) for r in reports]),
        ("Exact tier accuracy", [fmt(r.exact_accuracy) for r in reports]),
        ("Adjacent (within 1 tier)", [fmt(r.adjacent_accuracy) for r in reports]),
        ("Overclaim rate (unsafe dir.)", [fmt(r.overclaim_rate) for r in reports]),
        ("Escalated to human", [f"{r.escalation_rate:.0%}" for r in reports]),
        ("Human minutes per task",
         [fmt(r.human_minutes / max(r.n, 1), 1) for r in reports]),
        ("Cost per task (USD)",
         [fmt(r.usd / max(r.n, 1), 4) for r in reports]),
    ]
    out = ["", f"{'METRIC':<36}" + "".join(f"{c:>{w}}" for c in cols), "-" * (36 + w * len(cols))]
    for name, vals in rows:
        out.append(f"{name:<36}" + "".join(f"{v:>{w}}" for v in vals))
    out.append("")
    out.append(f"corpus = {head.n} artifacts, labels = ACM artifact-evaluation "
               f"badges (ISSTA 2024)")
    if len({r.n_scored for r in reports}) > 1:
        out.append("")
        out.append("  NOT LIKE FOR LIKE. The rate rows above use different"
                   " denominators:")
        for r in reports:
            out.append(f"    {r.system:<12} scored {r.n_scored} of {r.n}"
                       f"  ({r.escalation_rate:.0%} escalated and excluded)")
        out.append("  A system that answers fewer questions is not thereby"
                   " better. Escalation")
        out.append("  is a feature of the product, but it is not free in a"
                   " comparison, and this")
        out.append("  table would otherwise reward it silently.")
    return "\n".join(out)
