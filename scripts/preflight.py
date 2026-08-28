"""Confirm the run will work before spending any tokens.

Checks credentials, model access and a real round trip. Prints only whether each
secret is present and its length - never a value - so this output is safe to
paste into an issue or a submitted trajectory.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, "src")
from artifact_triage.common import llm  # noqa: E402  (loads .env on import)

KEY_FOR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "grok": "XAI_API_KEY",
}


def presence(name: str) -> str:
    v = os.environ.get(name, "")
    return f"set ({len(v)} chars)" if v else "MISSING"


def main() -> int:
    print("=" * 62)
    print(f"provider : {llm.PROVIDER}")
    print(f"model    : {llm.MODEL}")
    print(f"pricing  : ${llm.USD_IN}/Mtok in, ${llm.USD_OUT}/Mtok out")
    print("-" * 62)
    if llm.PROVIDER == "bedrock":
        for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"):
            print(f"  {k:<24} {presence(k)}")
    else:
        k = KEY_FOR[llm.PROVIDER]
        print(f"  {k:<24} {presence(k)}")
    print("-" * 62)

    print("live round trip ...")
    try:
        answer = llm.ask(
            llm.client(),
            "You classify research software artifacts.",
            'Reply with JSON only: {"tier":"Functional","confidence":0.5,'
            '"reasons":["preflight"]}',
        )
    except SystemExit as exc:
        print(f"  FAILED: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - surface any client construction error
        print(f"  FAILED: {type(exc).__name__}: {str(exc)[:200]}")
        return 1

    if answer.error:
        print(f"  FAILED: {answer.error}")
        if "PAYMENT" in answer.error.upper():
            print("\n  This is an AWS ACCOUNT BILLING issue, not IAM.")
            print("  A new IAM user in the same account fails identically.")
            print("  Add a valid default payment method to the AWS account.")
        return 1

    print(f"  OK   tier={answer.tier}  confidence={answer.confidence}  "
          f"tokens={answer.input_tokens}/{answer.output_tokens}")

    # Measured from real runs: ~2300 input / ~145 output tokens per call.
    per_call = (2300 * llm.USD_IN + 145 * llm.USD_OUT) / 1e6
    print(f"\nmeasured cost per call            : ${per_call:.5f}")
    print(f"baseline + solution (30 calls)    : ${per_call * 30:.3f}")
    print(f"full cycle incl. 3 trials (210)   : ${per_call * 210:.3f}")
    print("READY - run `make repro`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
