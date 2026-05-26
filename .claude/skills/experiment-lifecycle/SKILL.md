---
name: experiment-lifecycle
description: Use this skill when preparing, running, or validating experiments.
---
<!--
@dependency-start
responsibility Documents Experiment Lifecycle for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/structure-planning.md defines experiment and report structure contracts
@dependency-end
-->


# Experiment Lifecycle

1. Read `agents/skills/experiment-lifecycle.md`.
1. Keep execution steps, result paths, and report locations consistent with the canonical experiment workflow.
1. Treat `experiments/registry.toml` as the canonical topic registry for entrypoints and registered smoke/formal commands.
1. For formal or server-side runs, use a project `Makefile` target that calls `tools/experiments/run_managed_experiment.py` so `run_manifest.json` and `run.log` are captured automatically.
1. Keep checked-in experiment settings in `experiments/<topic>/config.yaml`; run artifacts must include a `config.json` or YAML snapshot, and registered commands must consume `{config_path}`.
1. Use `$structure-planning` before experiment planning, rerun planning, result report generation, or HTML view generation when the structure is nontrivial; fix first artifact, source-to-structure map, metric contract, invalid interpretations, and validation gate before running or writing.
1. Use `$result-artifact-writeout` for result/report generation so raw run output, Markdown summary, manifest, run name, and overwrite policy are recorded separately.
1. If code changes must iterate with explicit decision states, also use `experiment-change-loop`.
