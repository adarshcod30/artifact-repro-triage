"""SOLUTION - judge verified facts, not unchecked claims.

Same model, same rubric, same output schema, same scrubbed README as the
baseline. The one difference: before the model sees anything, every file path the
README references is checked against the repository's real file tree, and the
result of those checks is placed in the prompt as established fact.

The verification is deterministic Python. It cannot hallucinate, costs nothing,
and its findings are citable by path - so the model is reasoning over evidence
instead of over prose.

Low-confidence answers are escalated to a human rather than recorded as guesses
(ground rules 4 and 5: a qualified human makes the call that affects an author).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from artifact_triage.common.llm import USD_IN, USD_OUT, Answer, ask, client
from artifact_triage.common.rubric import RUBRIC
from artifact_triage.eval.metrics import Prediction, score
from artifact_triage.solution.verify import verify

OUT = Path("results/solution.json")
# Below this the artifact goes to a human reviewer instead of being scored.
ESCALATE_BELOW = float(os.environ.get("ARTIFACT_TRIAGE_ESCALATE_BELOW", "0.55"))


def prompt_for(fx: dict) -> str:
    ev = verify(fx)
    return (
        f"Artifact repository: {fx['artifact_id']}\n"
        f"Paper: {fx['paper_title']}\n\n"
        f"{ev.as_prompt_block()}\n\n"
        f"README (verbatim):\n---\n{fx['readme'][:16000]}\n---\n\n"
        "Weigh the verified facts above the README's own claims wherever the two "
        "disagree. A README that references files which do not exist has not been "
        "kept consistent with the artifact, whatever it asserts about itself."
    )


def main() -> None:
    cl = client()
    fixtures = sorted(Path("data/fixtures").glob("*.json"))
    preds, labels, raw = [], {}, []
    for i, p in enumerate(fixtures, 1):
        fx = json.loads(p.read_text())
        ev = verify(fx)
        a: Answer = ask(cl, RUBRIC, prompt_for(fx))
        escalate = a.tier is None or a.confidence < ESCALATE_BELOW
        labels[fx["artifact_id"]] = fx["_label"]["badge"]
        preds.append(Prediction(
            artifact_id=fx["artifact_id"], predicted=a.tier,
            confidence=a.confidence, escalated=escalate,
            evidence=a.reasons + [f"broken README path: {b}" for b in ev.broken_paths[:5]],
            input_tokens=a.input_tokens, output_tokens=a.output_tokens))
        raw.append({"artifact_id": fx["artifact_id"], "tier": a.tier,
                    "confidence": a.confidence, "escalated": escalate,
                    "reasons": a.reasons, "verified": ev.to_dict(), "error": a.error})
        mark = "ESC" if escalate else "   "
        print(f"[{i:2}/{len(fixtures)}] {mark} {str(a.tier):<11} conf={a.confidence:.2f}  "
              f"truth={fx['_label']['badge']:<11} broken={ev.claims_broken}/{ev.claims_total}  "
              f"{fx['artifact_id']}")
    rep = score("solution", preds, labels, USD_IN, USD_OUT)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"report": rep.to_dict(), "raw": raw}, indent=1))
    print(f"\nMAE {rep.mae}  exact {rep.exact_accuracy}  overclaim {rep.overclaim_rate}  "
          f"escalated {rep.escalation_rate:.0%}  ${rep.usd:.4f}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
