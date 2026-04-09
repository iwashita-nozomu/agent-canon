---
name: experiment-lifecycle
description: Use this skill when preparing, running, or validating experiments.
---

# Experiment Lifecycle

1. Read `agents/skills/experiment-lifecycle.md`.
1. Keep execution steps, result paths, and report locations consistent with the canonical experiment workflow.
1. Treat `experiments/registry.toml` as the canonical topic registry for entrypoints and registered smoke/formal commands.
1. For formal or server-side runs, use `scripts/experiments/run_managed_experiment.py` so `run_manifest.json` and `run.log` are captured automatically.
1. If code changes must iterate with explicit decision states, also use `experiment-change-loop`.
