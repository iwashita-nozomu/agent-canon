---
name: experiment-lifecycle
description: Use this skill when preparing, running, or validating experiments.
---
<!--
@dependency-start
responsibility Documents Experiment Lifecycle for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Experiment Lifecycle

1. Read `agents/skills/experiment-lifecycle.md`.
1. Keep execution steps, result paths, and report locations consistent with the canonical experiment workflow.
1. Treat `experiments/registry.toml` as the canonical topic registry for entrypoints and registered smoke/formal commands.
1. For formal or server-side runs, use `tools/experiments/run_managed_experiment.py` so `run_manifest.json` and `run.log` are captured automatically.
1. Require experiment settings to be exported as a JSON-object/dict artifact, normally `result/<run_name>/config.json`; registered commands must consume `{config_path}`.
1. Use `$result-artifact-writeout` for result/report generation so raw run output, Markdown summary, manifest, run name, and overwrite policy are recorded separately.
1. If code changes must iterate with explicit decision states, also use `experiment-change-loop`.
