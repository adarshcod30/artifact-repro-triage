"""BASELINE - one direct prompt over the README.

This is the honest naive approach, and it is deliberately a *fair* baseline: the
same model, the same rubric, the same output schema, the same scrubbed README the
solution sees. The single difference is that it receives the README's claims
without any of them being checked.

It is what a person actually does today: skim the README and form an impression.
"""
from __future__ import annotations

import json
from pathlib import Path

from artifact_triage.common.llm import USD_IN, USD_OUT, Answer, ask, client
from artifact_triage.common.rubric import RUBRIC
from artifact_triage.eval.metrics import Prediction, score
from artifact_triage.common.provenance import stamp

OUT = Path("results/baseline.json")


def prompt_for(fx: dict) -> str:
    return (
        f"Artifact repository: {fx['artifact_id']}\n"
        f"Paper: {fx['paper_title']}\n\n"
        f"README (verbatim):\n---\n{fx['readme'][:16000]}\n---\n"
    )


def main() -> None:
    cl = client()
    fixtures = sorted(Path("data/fixtures").glob("*.json"))
    preds, labels, raw = [], {}, []
    for i, p in enumerate(fixtures, 1):
        fx = json.loads(p.read_text())
        a: Answer = ask(cl, RUBRIC, prompt_for(fx))
        labels[fx["artifact_id"]] = fx["_label"]["badge"]
        preds.append(Prediction(
            artifact_id=fx["artifact_id"], predicted=a.tier,
            confidence=a.confidence, escalated=False, evidence=a.reasons,
            input_tokens=a.input_tokens, output_tokens=a.output_tokens))
        raw.append({"artifact_id": fx["artifact_id"], "tier": a.tier,
                    "confidence": a.confidence, "reasons": a.reasons,
                    "error": a.error})
        print(f"[{i:2}/{len(fixtures)}] {str(a.tier):<11} conf={a.confidence:.2f}  "
              f"truth={fx['_label']['badge']:<11} {fx['artifact_id']}")
    rep = score("baseline", preds, labels, USD_IN, USD_OUT)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"_provenance": stamp("baseline"),
                           "report": rep.to_dict(), "raw": raw}, indent=1))
    print(f"\nMAE {rep.mae}  exact {rep.exact_accuracy}  "
          f"overclaim {rep.overclaim_rate}  ${rep.usd:.4f}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
