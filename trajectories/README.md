# Agent Trajectories

Representative trajectories for every agent used in this project.

## Product agents (ship in this repository)

Each file follows one artifact from the shared agent instructions, through the deterministic verification tool call and its response, to each agent's final answer — including any human checkpoint.

- [`product-agent__zhangxiaosa__LPR.md`](product-agent__zhangxiaosa__LPR.md)
- [`product-agent__QuentinMaz__MDPFuzz_Replicability_Study_Artifact.md`](product-agent__QuentinMaz__MDPFuzz_Replicability_Study_Artifact.md)
- [`product-agent__THU-WingTecher__DeepConstr.md`](product-agent__THU-WingTecher__DeepConstr.md)

The three artifacts were chosen to show contrast rather than to flatter: one the verifier flags heavily, one it finds clean, and one with partial breakage in a large repository.

## Build agent (wrote this repository)

Claude Code (Opus) authored this project. Its session transcript is exported by:

```bash
python scripts/export_build_trajectory.py
```

The exporter redacts secrets before writing. See [`build-agent.md`](build-agent.md).
