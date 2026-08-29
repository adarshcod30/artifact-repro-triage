"""Budget policy, kept OUT of the inference path on purpose.

WHY THIS IS ITS OWN MODULE
--------------------------
The provenance checker fingerprints whole files: if a file that can influence a
result changes, results produced by the old version are marked stale. `llm.py`
is such a file, and it used to hold two unrelated concerns - the inference path,
which genuinely changes model output, and budget enforcement, which cannot
change a single token.

So every budget fix marked `baseline` and `solution` stale and pressed for a
paid re-run that could not possibly have produced a different answer. A
staleness detector that cries wolf trains you to ignore it, which is worse than
the wasted spend.

The fix is not a looser fingerprint - a detector with a blind spot is worse than
none, as this project learned when `fetch.py` was missing from the influencer
list. The fix is files with coherent single responsibilities, so that file-level
hashing is *accurate*. This module can be edited freely without invalidating any
recorded result, because nothing here can affect one.
"""
from __future__ import annotations

import os

# A budget is only a budget if something enforces it. Set to 0 to disable.
GUARD_USD = float(os.environ.get("ARTIFACT_TRIAGE_BUDGET_USD", "5.50"))

# Spend already on the ledger when this process started, plus what this process
# has added. Tracked so the per-call guard costs no file I/O.
_BASE_USD: float | None = None
_SESSION_USD = 0.0


def _ledger_total() -> float:
    try:
        from artifact_triage.common.ledger import total
        return total()
    except Exception:
        return 0.0


def spent() -> float:
    global _BASE_USD
    if _BASE_USD is None:
        _BASE_USD = _ledger_total()
    return _BASE_USD + _SESSION_USD


def reset() -> None:
    """Forget cached session accounting. For tests only."""
    global _BASE_USD, _SESSION_USD
    _BASE_USD, _SESSION_USD = None, 0.0


def check(need_usd: float = 0.0) -> None:
    """Refuse to START a run that would exceed the ceiling.

    The tracker under-reported by 2.2x once already. A guard that only warns is
    worth nothing at 3am, so this raises.
    """
    global _BASE_USD
    if GUARD_USD <= 0:
        return
    _BASE_USD = _ledger_total()
    if _BASE_USD + need_usd >= GUARD_USD:
        raise SystemExit(
            f"BUDGET STOP: ${_BASE_USD:.2f} already spent of ${GUARD_USD:.2f}"
            f"{f' and this run needs ~${need_usd:.2f}' if need_usd else ''}.\n"
            f"Everything deterministic still runs for free: make test, verify, "
            f"control, subtle, ablation, pinning, portability, prevalence, "
            f"dataset, dashboard.")


def enforce(usd: float) -> None:
    """Enforce the ceiling PER CALL, not once per run.

    `check()` runs inside `client()`, which is called once. A run that started
    at $4.95 passed that check and could then make hundreds of billed calls
    with nothing watching - a ceiling enforced at run granularity rather than
    spend granularity, which is no ceiling at all for any run big enough to
    matter.

    Raising mid-run is safe because every long experiment checkpoints its
    completed work before continuing, so nothing already paid for is lost.
    """
    global _SESSION_USD
    _SESSION_USD += usd
    if GUARD_USD > 0 and spent() >= GUARD_USD:
        raise SystemExit(
            f"BUDGET STOP mid-run: ${spent():.2f} of ${GUARD_USD:.2f} spent. "
            f"Completed work is already checkpointed; nothing paid for is "
            f"lost. Everything deterministic still runs for free.")
