---
name: experiment-lifecycle
description: Use this skill when preparing, running, or validating experiments.
---
<!--
@dependency-start
contract skill
responsibility Documents Experiment Lifecycle for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/structure-planning.md defines experiment and report structure contracts
upstream design ../../../agents/skills/prose-reasoning-graph.md defines experiment-plan graph diagnostics
downstream implementation ../../../tools/agent_tools/tool_rejection_preflight.py predicts managed execution surface guardrails
@dependency-end
-->


# Experiment Lifecycle

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill experiment-lifecycle --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/experiment-lifecycle.md`.
1. Keep execution steps, result paths, and report locations consistent with the canonical experiment workflow.
1. For a new experiment topic, fix the topic name first, copy AgentCanon template path `vendor/agent-canon/experiments/_template/` to project-root `experiments/<topic>/`, then edit `run.py` `main::main`, `cases.py`, `config.yaml`, `visualize.ipynb`, and `README.md` in that order.
1. Treat project-root `experiments/registry.toml` as the project-owned topic registry for entrypoints and registered smoke/formal commands. AgentCanon owns the registry contract in `documents/experiment-registry.md`; from a template or derived repo root, read that contract as `vendor/agent-canon/documents/experiment-registry.md`. When the project registry is absent, create or update the project-root registry before formal entrypoint registration.
1. When a project registry exists, validate registry schema and registered command placeholders with `python3 tools/ci/check_experiment_registry.py` before formal execution.
1. For formal or server-side runs, use a project `Makefile` target that calls `tools/experiments/run_managed_experiment.py` so `run_manifest.json` and `run.log` are captured automatically.
1. After a formal run from the source checkout, usually `main`, publish the generated result/report artifacts with `python3 tools/experiments/publish_result_branch.py --result-dir experiments/<topic>/result/<run_name> --branch experiment-results/<topic>`, adding `--push` when remote result-branch retention is part of the run plan.
1. Keep checked-in experiment settings in `experiments/<topic>/config.yaml`; run artifacts must include `config.json` and `config_source.yaml`, and registered commands must consume `{config_path}`.
1. Require `experiments/<topic>/README.md` to describe the experiment content, question, comparison target, standard commands, config source, visualization notebook, output schema, and run_name convention before formal execution.
1. Put the visualization notebook at `experiments/<topic>/visualize.ipynb`; notebooks read run artifacts and render figures/tables, but they must not be the formal run launcher, fine-grained test surface, or config source of truth.
1. Ensure every run has `result/<run_name>/logs/`; keep the managed top-level `run.log` for wrapper output and place additional stdout, stderr, startup, tool, or diagnostic logs under `logs/`.
1. Treat `command.json`, `environment.json`, `source_snapshot.json`, `artifact_manifest.json`, `logs/startup.jsonl`, `logs/stdout.log`, and `logs/stderr.log` as standard managed run artifacts. If a run lacks them, rerun through `tools/experiments/run_managed_experiment.py` or record that the run is not fully reproducible.
1. For planned edits to managed experiment execution surfaces, run `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and resolve the `experiment_execution_surface_guard` handoff before patching. This surface includes `tools/experiments/run_managed_experiment.py`, `tools/ci/check_experiment_registry.py`, `documents/experiment-registry.md`, `agents/workflows/experiment-workflow.md`, and `experiments/registry.toml`. Pair this skill with `$test-design`; run `python3 tools/ci/check_experiment_registry.py` when project `experiments/registry.toml` exists, run `python3 -m pytest tests/tools/test_run_managed_experiment.py -q` for runner / registry checker behavior, and reserve formal experiment runs for an explicit run plan.
1. Use `$structure-planning` before experiment planning, rerun planning, result report generation, or HTML view generation when the structure is nontrivial; fix first artifact, source-to-structure map, metric contract, invalid interpretations, and validation gate before running or writing.
1. For experiment plans or reports with nontrivial paragraph order or causal/evidence transitions, ask `$structure-planning` to use `agent-canon semantic-index discourse-relations --profile experiment-report` or `--profile methods-protocol` as advisory edge evidence.
1. If a prose graph handoff is present, use hypothesis, metric, baseline, and expected-result diagnostics as advisory input to the experiment plan or rerun plan.
1. Use `$result-artifact-writeout` for result/report generation so raw run output, Markdown summary, manifest, run name, and overwrite policy are recorded separately.
1. If code changes must iterate with explicit decision states, also use `experiment-change-loop`.
