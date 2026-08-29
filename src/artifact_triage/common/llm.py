"""Provider-agnostic model access.

Baseline and solution both call `ask()` and both read the SAME provider/model
from the environment. Holding the model fixed across the two systems is what
makes the comparison attributable: any measured difference comes from what each
system SHOWS the model, not from a capability gap.

Development runs use free-tier providers (Gemini, Grok); the final reported
numbers come from a single clean run on one provider. Mixed-provider results are
not comparable and are never reported side by side.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

TIERS = ["Available", "Functional", "Reusable"]
MAX_TOKENS = 4000

# Response contract. Identical for every provider, so the scorer never branches.
SCHEMA = {
    "type": "object",
    "properties": {
        "tier": {"type": "string", "enum": TIERS},
        "confidence": {"type": "number"},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tier", "confidence", "reasons"],
}

# provider -> (default model, USD per 1M input, USD per 1M output)
PROVIDERS = {
    # Bedrock is the primary path: one account, one model, start to finish, so
    # dev runs and reported runs are the same runs. Model access is granted
    # per-model in the Bedrock console - `list-foundation-models` shows the
    # catalogue, not what is enabled, so probe with a real Converse call.
    "bedrock": ("us.anthropic.claude-sonnet-4-5-20250929-v1:0", 3.00, 15.00),
    # Cheap non-Claude options on the same Bedrock endpoint. Same Converse API,
    # so switching is a model-id change only. (All Bedrock models share the
    # account's billing state - these do not bypass a payment block.)
    # Bedrock pricing is per-model; ARTIFACT_TRIAGE_MODEL overrides the default
    # and PRICE_OVERRIDES supplies that model's rate for the cost metric.

    "anthropic": ("claude-opus-5", 5.00, 25.00),
    "gemini": ("gemini-2.5-flash", 0.30, 2.50),
    "grok": ("grok-4-fast-non-reasoning", 0.20, 0.50),
}


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader - avoids a dependency and never overwrites a real env var."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v and not os.environ.get(k):
            os.environ[k] = v


load_dotenv()

# A half-filled AWS credential is worse than none: boto3 sees an access key id
# with no secret and fails outright instead of falling back to the working
# ~/.aws profile. Drop the partial pair rather than let it break the run.
if os.environ.get("AWS_ACCESS_KEY_ID") and not os.environ.get("AWS_SECRET_ACCESS_KEY"):
    os.environ.pop("AWS_ACCESS_KEY_ID", None)
    print("[llm] AWS_ACCESS_KEY_ID is set but AWS_SECRET_ACCESS_KEY is empty - "
          "ignoring both and falling back to the ~/.aws profile.")

PROVIDER = os.environ.get("ARTIFACT_TRIAGE_PROVIDER", "gemini").strip().lower()
if PROVIDER not in PROVIDERS:
    raise SystemExit(f"ARTIFACT_TRIAGE_PROVIDER must be one of {list(PROVIDERS)}")
_default_model, USD_IN, USD_OUT = PROVIDERS[PROVIDER]
MODEL = os.environ.get("ARTIFACT_TRIAGE_MODEL", "").strip() or _default_model

# USD per 1M tokens (input, output) for models we may select on Bedrock. Needed
# so "cost per task" in the report reflects the model actually used.
PRICE_OVERRIDES = {
    "us.amazon.nova-2-lite-v1:0": (0.06, 0.24),
    "us.amazon.nova-pro-v1:0": (0.80, 3.20),
    "us.amazon.nova-premier-v1:0": (2.50, 12.50),
    "us.meta.llama3-3-70b-instruct-v1:0": (0.72, 0.72),
    "us.mistral.mistral-large-2402-v1:0": (4.00, 12.00),
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": (3.00, 15.00),
}
if MODEL in PRICE_OVERRIDES:
    USD_IN, USD_OUT = PRICE_OVERRIDES[MODEL]


@dataclass
class Answer:
    tier: str | None
    confidence: float
    reasons: list[str]
    input_tokens: int
    output_tokens: int
    error: str | None = None


def _scan_json_objects(raw: str):
    """Yield every balanced top-level {...} block, in order.

    A greedy `\{.*\}` spans from the first brace to the last, which is invalid
    whenever a response contains more than one object - and some models emit the
    schema before the answer.
    """
    depth, start, in_str, esc = 0, None, False, False
    for i, ch in enumerate(raw):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                yield raw[start:i + 1]
                start = None


def _first_answer_object(raw: str):
    """The first object that actually looks like an answer, not a schema.

    Llama 3.3 echoes the JSON schema before its answer. Taking the first brace
    match returned the schema - which has no `tier` value - and the run was
    recorded as an unparseable failure. That made a model look 10x worse than it
    is, and I nearly published it as a cross-model limitation.
    """
    try:
        whole = json.loads(raw)
        if isinstance(whole, dict) and "tier" in whole:
            return whole
    except json.JSONDecodeError:
        pass
    for block in _scan_json_objects(raw):
        try:
            obj = json.loads(block)
        except json.JSONDecodeError:
            continue
        # A schema has "properties"/"type"; an answer has a tier value.
        if isinstance(obj, dict) and isinstance(obj.get("tier"), str):
            return obj
    return None


def _parse(text: str, tin: int, tout: int) -> Answer:
    """Providers vary in how cleanly they emit JSON; recover the object if wrapped."""
    if not text:
        return Answer(None, 0.0, [], tin, tout, "empty response")
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?|```$", "", raw).strip()
    data = _first_answer_object(raw)
    if data is None:
        return Answer(None, 0.0, [], tin, tout, "unparseable response")
    tier = data.get("tier")
    if tier not in TIERS:
        tier = next((t for t in TIERS if str(tier).lower() == t.lower()), None)
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return Answer(tier, max(0.0, min(1.0, conf)),
                  [str(r) for r in (data.get("reasons") or [])][:6], tin, tout)


class _Bedrock:
    def __init__(self) -> None:
        import boto3
        from botocore.config import Config
        region = os.environ.get("AWS_REGION") or os.environ.get(
            "AWS_DEFAULT_REGION") or "us-east-1"
        self.cl = boto3.client(
            "bedrock-runtime", region_name=region,
            # Adaptive retry is the documented remedy for Bedrock throttling.
            config=Config(retries={"max_attempts": 6, "mode": "adaptive"},
                          read_timeout=120))

    def ask(self, system: str, user: str) -> Answer:
        r = self.cl.converse(
            modelId=MODEL,
            system=[{"text": system + "\n\nRespond with a single JSON object "
                                      "and no other text, matching: "
                     + json.dumps(SCHEMA)}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            # maxTokens is ALWAYS explicit: leaving it unset reserves the model
            # maximum against the account quota and causes spurious throttling.
            inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0},
        )
        text = "".join(b.get("text", "") for b in r["output"]["message"]["content"])
        u = r.get("usage", {})
        return _parse(text, u.get("inputTokens", 0), u.get("outputTokens", 0))


class _Anthropic:
    def __init__(self) -> None:
        import anthropic
        self.mod = anthropic
        self.cl = anthropic.Anthropic()

    def ask(self, system: str, user: str) -> Answer:
        r = self.cl.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": "high",
                           "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": user}],
        )
        text = next((b.text for b in r.content if b.type == "text"), "")
        return _parse(text, r.usage.input_tokens, r.usage.output_tokens)


class _Gemini:
    def __init__(self) -> None:
        from google import genai
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise SystemExit("GEMINI_API_KEY is not set (put it in .env)")
        self.cl = genai.Client(api_key=key)

    def ask(self, system: str, user: str) -> Answer:
        r = self.cl.models.generate_content(
            model=MODEL,
            contents=user,
            config={
                "system_instruction": system,
                "response_mime_type": "application/json",
                "max_output_tokens": MAX_TOKENS,
                "temperature": 0,
            },
        )
        u = getattr(r, "usage_metadata", None)
        return _parse(r.text or "",
                      getattr(u, "prompt_token_count", 0) or 0,
                      getattr(u, "candidates_token_count", 0) or 0)


class _Grok:
    def __init__(self) -> None:
        from openai import OpenAI
        key = os.environ.get("XAI_API_KEY")
        if not key:
            raise SystemExit("XAI_API_KEY is not set (put it in .env)")
        self.cl = OpenAI(api_key=key, base_url="https://api.x.ai/v1")

    def ask(self, system: str, user: str) -> Answer:
        r = self.cl.chat.completions.create(
            model=MODEL, max_tokens=MAX_TOKENS, temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        u = r.usage
        return _parse(r.choices[0].message.content or "",
                      getattr(u, "prompt_tokens", 0) or 0,
                      getattr(u, "completion_tokens", 0) or 0)


_BACKENDS = {"bedrock": _Bedrock, "anthropic": _Anthropic,
             "gemini": _Gemini, "grok": _Grok}


# A budget is only a budget if something enforces it. Set to 0 to disable.
BUDGET_GUARD = float(os.environ.get("ARTIFACT_TRIAGE_BUDGET_USD", "5.0"))


def budget_check(need_usd: float = 0.0) -> None:
    """Refuse to start a run that would exceed the ceiling.

    The tracker under-reported by 2.2x once already. A guard that only warns is
    worth nothing at 3am, so this raises.
    """
    if BUDGET_GUARD <= 0:
        return
    try:
        from artifact_triage.common.ledger import total
        spent = total()
    except Exception:
        return
    if spent + need_usd >= BUDGET_GUARD:
        raise SystemExit(
            f"BUDGET STOP: ${spent:.2f} already spent of ${BUDGET_GUARD:.2f}"
            f"{f' and this run needs ~${need_usd:.2f}' if need_usd else ''}.\n"
            f"Everything deterministic still runs for free: make test, verify, "
            f"control, subtle, ablation, pinning, portability, prevalence, "
            f"dataset, dashboard.")


def client():
    budget_check()
    return _BACKENDS[PROVIDER]()


def _meter(answer: "Answer", attempt: int, failed: bool = False) -> None:
    """Record EVERY call at the moment it is made.

    The first ledger counted only calls whose results were kept. Retries,
    probes and smoke tests all consumed billed tokens and were invisible, so the
    tracker reported $1.12 against a true $2.39 - wrong by 2.2x, and wrong in
    the direction that reaches a hard budget without warning.

    A retry is a call you were charged for. So is a probe. Metering the success
    path only means the meter misses everything you discarded, which during
    development is most of what you spend.
    """
    try:
        from artifact_triage.common.ledger import record
        usd = (answer.input_tokens * USD_IN
               + answer.output_tokens * USD_OUT) / 1e6
        record("call" if not failed else "call-failed", usd, 1, MODEL,
               f"attempt {attempt + 1}")
    except Exception:
        pass  # metering must never break a run


def ask(cl, system: str, user: str, retries: int = 5) -> Answer:
    """Free tiers rate-limit aggressively; back off rather than lose the row."""
    delay = 4.0
    last = "unknown error"
    for attempt in range(retries):
        try:
            a = cl.ask(system, user)
            _meter(a, attempt)
            return a
        except Exception as exc:  # provider SDKs raise different types
            last = f"{type(exc).__name__}: {str(exc)[:180]}"
            # A failed attempt may still have been billed. Tokens are unknown,
            # so record the call with a conservative typical cost rather than
            # zero - an unknown charge is not a free one.
            _meter(Answer(None, 0.0, [], 2300, 100), attempt, failed=True)
            transient = any(s in str(exc).lower() for s in
                            ("429", "rate", "quota", "overload", "503", "500",
                             "timeout", "unavailable", "exhausted"))
            if not transient or attempt == retries - 1:
                break
            time.sleep(delay)
            delay *= 2
    return Answer(None, 0.0, [], 0, 0, last)
