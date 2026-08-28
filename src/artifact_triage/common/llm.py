"""Shared model access. Baseline and solution use the SAME model and settings.

Holding the model fixed is what makes the comparison attributable: any measured
difference comes from what each system *shows* the model, not from a capability
gap between models.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import anthropic

MODEL = os.environ.get("ARTIFACT_TRIAGE_MODEL", "claude-opus-5")
# Claude Opus 5 list pricing, USD per million tokens.
USD_IN, USD_OUT = 5.00, 25.00
MAX_TOKENS = 8000

TIERS = ["Available", "Functional", "Reusable"]

# Both systems must emit exactly this shape, so the scorer is identical for both.
SCHEMA = {
    "type": "object",
    "properties": {
        "tier": {"type": "string", "enum": TIERS},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasons": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
    },
    "required": ["tier", "confidence", "reasons"],
    "additionalProperties": False,
}


@dataclass
class Answer:
    tier: str | None
    confidence: float
    reasons: list[str]
    input_tokens: int
    output_tokens: int
    error: str | None = None


def client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def ask(cl: anthropic.Anthropic, system: str, user: str) -> Answer:
    try:
        resp = cl.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": SCHEMA},
            },
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIStatusError as exc:
        return Answer(None, 0.0, [], 0, 0, f"{type(exc).__name__}: {exc}")
    except anthropic.APIConnectionError as exc:
        return Answer(None, 0.0, [], 0, 0, f"connection: {exc}")

    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return Answer(None, 0.0, [], resp.usage.input_tokens,
                      resp.usage.output_tokens, "unparseable response")
    return Answer(
        tier=data.get("tier"),
        confidence=float(data.get("confidence", 0.0)),
        reasons=list(data.get("reasons", []))[:6],
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
    )
