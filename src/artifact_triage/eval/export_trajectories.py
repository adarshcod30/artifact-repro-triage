"""Render readable agent trajectories from the recorded runs.

The challenge asks for representative trajectories for every agent used, followed
from the agent's instructions through to its final result, including how tools
responded and what shaped the next step.

Two kinds of agent are involved and both are exported:

  1. PRODUCT AGENTS - the baseline and solution that ship in this repository.
     Their trajectories are reconstructed from `results/*.json` plus the same
     deterministic verifier the live run used, so what you read is what ran.

  2. THE BUILD AGENT - Claude Code, which wrote this repository. Exported
     separately by `scripts/export_build_trajectory.py`.

Every trajectory is passed through the badge scrubber before writing, so no
redaction depends on remembering to do it by hand.
"""
from __future__ import annotations

import json
from pathlib import Path

from artifact_triage.baseline.run import prompt_for as baseline_prompt
from artifact_triage.common.rubric import RUBRIC
from artifact_triage.solution.run import prompt_for as solution_prompt
from artifact_triage.solution.verify import verify

OUT = Path("trajectories")
# Chosen to show contrast, not to flatter: one artifact the verifier flags
# heavily, one it finds clean, one where the two systems disagree.
REPRESENTATIVE = [
    "zhangxiaosa__LPR",                 # 15 of 17 README paths missing
    "QuentinMaz__MDPFuzz_Replicability_Study_Artifact",  # clean, well-formed
    "THU-WingTecher__DeepConstr",       # partial breakage, large repo
]


def _fence(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text.rstrip()}\n```"


def render(fixture: dict, baseline_row: dict | None,
           solution_row: dict | None) -> str:
    ev = verify(fixture)
    aid = fixture["artifact_id"]
    L: list[str] = []
    L.append(f"# Trajectory — `{aid}`\n")
    L.append(f"- **Paper**: {fixture['paper_title']}")
    L.append(f"- **Pinned commit**: `{fixture['commit']}`")
    L.append(f"- **Files in repository**: {fixture['n_files']:,}")
    L.append(f"- **Expert badge (held out from both agents)**: "
             f"`{fixture['_label']['badge']}`\n")
    L.append("---\n")

    L.append("## Step 0 — Shared agent instructions\n")
    L.append("Both agents receive this verbatim. The task definition is held "
             "constant; only the evidence differs.\n")
    L.append(_fence(RUBRIC))
    L.append("")

    L.append("## Step 1 — Input preparation (both agents)\n")
    hits = fixture["readme_scrub"]["hits"]
    if fixture["readme_scrub"]["leaked"]:
        L.append(f"The README **disclosed its own badge tier**. Redacted before "
                 f"either agent saw it: `{hits}`\n")
    else:
        L.append("Scrubber found no badge self-disclosure in this README.\n")

    L.append("## Step 2 — Tool call: deterministic claim verification\n")
    L.append("*Solution only. No model involved — ordinary Python over the "
             "repository's real file tree.*\n")
    L.append(f"**Tool input**: {ev.claims_total} candidate paths extracted from "
             f"the README.\n")
    L.append("**Tool response**:\n")
    L.append(_fence(ev.as_prompt_block()))
    L.append("")
    if ev.broken_paths:
        L.append(f"> This is the feedback that shapes the next step. "
                 f"{ev.claims_broken} of {ev.claims_total} referenced paths do "
                 f"not exist, and each is citable by name — the model reasons "
                 f"over these facts instead of over the README's prose.\n")

    for name, row, builder in (("BASELINE", baseline_row, baseline_prompt),
                               ("SOLUTION", solution_row, solution_prompt)):
        L.append(f"## Step 3 — {name} agent\n")
        prompt = builder(fixture)
        L.append(f"**Prompt** ({len(prompt):,} chars; README truncated here for "
                 f"readability):\n")
        head = prompt[:1400]
        L.append(_fence(head + ("\n… README continues …" if len(prompt) > 1400 else "")))
        if row is None:
            L.append("\n*(no recorded result)*\n")
            continue
        L.append("\n**Final answer**:\n")
        L.append(_fence(json.dumps(
            {"tier": row.get("tier"), "confidence": row.get("confidence"),
             "reasons": row.get("reasons"),
             "escalated_to_human": row.get("escalated", False)}, indent=2), "json"))
        if row.get("escalated"):
            # NOT a confidence threshold. `decide()` never reads confidence -
            # that gate was removed for being anti-calibrated - so this line
            # narrated a mechanism the code does not have, under rows whose
            # recorded confidence was 0.9.
            L.append("\n> **Human checkpoint.** An evidence-based rule fired, "
                     "so this artifact is routed to a "
                     "qualified reviewer rather than recorded as a guess.\n")
        L.append("")

    L.append("## Step 4 — Outcome\n")
    truth = fixture["_label"]["badge"]
    for name, row in (("baseline", baseline_row), ("solution", solution_row)):
        if row:
            L.append(f"- **{name}**: predicted `{row.get('tier')}`, "
                     f"expert badge `{truth}`")
    L.append("\nSee `results/falsified_run.json` for the same agents run against "
             "this artifact's falsified twin, which is the reported experiment.\n")
    return "\n".join(L)


def main() -> None:
    OUT.mkdir(exist_ok=True)

    def index(path: str) -> dict:
        try:
            raw = json.loads(Path(path).read_text()).get("raw", [])
        except FileNotFoundError:
            return {}
        return {r["artifact_id"]: r for r in raw}

    base = index("results/baseline.json")
    sol = index("results/solution.json")

    written = []
    for stem in REPRESENTATIVE:
        p = Path("data/fixtures") / f"{stem}.json"
        if not p.exists():
            print(f"  skip (missing fixture): {stem}")
            continue
        fx = json.loads(p.read_text())
        aid = fx["artifact_id"]
        md = render(fx, base.get(aid), sol.get(aid))
        dest = OUT / f"product-agent__{stem}.md"
        dest.write_text(md)
        written.append(dest)
        print(f"  wrote {dest}  ({len(md):,} chars)")

    readme = [
        "# Agent Trajectories\n",
        "Representative trajectories for every agent used in this project.\n",
        "## Product agents (ship in this repository)\n",
        "Each file follows one artifact from the shared agent instructions, "
        "through the deterministic verification tool call and its response, to "
        "each agent's final answer — including any human checkpoint.\n",
    ]
    readme += [f"- [`{d.name}`]({d.name})" for d in written]
    readme += [
        "\nThe three artifacts were chosen to show contrast rather than to "
        "flatter: one the verifier flags heavily, one it finds clean, and one "
        "with partial breakage in a large repository.\n",
        "## Build agent (wrote this repository)\n",
        "Claude Code (Opus) authored this project. Its session transcript is "
        "exported by:\n",
        "```bash\npython scripts/export_build_trajectory.py\n```\n",
        "The exporter redacts secrets before writing. See "
        "[`build-agent.md`](build-agent.md).\n",
    ]
    (OUT / "README.md").write_text("\n".join(readme))
    print(f"  wrote {OUT}/README.md")


if __name__ == "__main__":
    main()
