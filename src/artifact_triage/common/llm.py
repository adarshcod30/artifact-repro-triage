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

PROVIDER = os.environ.get("ARTIFACT_TRIAGE_PROVIDER", "gemini").strip().lower()
if PROVIDER not in PROVIDERS:
    raise SystemExit(f"ARTIFACT_TRIAGE_PROVIDER must be one of {list(PROVIDERS)}")
_default_model, USD_IN, USD_OUT = PROVIDERS[PROVIDER]
MODEL = os.environ.get("ARTIFACT_TRIAGE_MODEL", "").strip() or _default_model


@dataclass
class Answer:
    tier: str | None
    confidence: float
    reasons: list[str]
    input_tokens: int
    output_tokens: int
    error: str | None = None


def _parse(text: str, tin: int, tout: int) -> Answer:
    """Providers vary in how cleanly they emit JSON; recover the object if wrapped."""
    if not text:
        return Answer(None, 0.0, [], tin, tout, "empty response")
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?|```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return Answer(None, 0.0, [], tin, tout, "unparseable response")
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
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


def client():
    return _BACKENDS[PROVIDER]()


def ask(cl, system: str, user: str, retries: int = 5) -> Answer:
    """Free tiers rate-limit aggressively; back off rather than lose the row."""
    delay = 4.0
    last = "unknown error"
    for attempt in range(retries):
        try:
            return cl.ask(system, user)
        except Exception as exc:  # provider SDKs raise different types
            last = f"{type(exc).__name__}: {str(exc)[:180]}"
            transient = any(s in str(exc).lower() for s in
                            ("429", "rate", "quota", "overload", "503", "500",
                             "timeout", "unavailable", "exhausted"))
            if not transient or attempt == retries - 1:
                break
            time.sleep(delay)
            delay *= 2
    return Answer(None, 0.0, [], 0, 0, last)
