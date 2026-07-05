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
downstream implementation ../../../tools/agent_tools/tool_rejection_preflight.py predicts experiment execution surface guardrails
upstream implementation ../../../tools/experiments/create_experiment_topic.py creates registered experiment topics from the shared template
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
1. For a new experiment topic, fix the topic name first, run `python3 tools/experiments/create_experiment_topic.py <topic>` to copy `vendor/agent-canon/experiments/_template/` into project-root `experiments/<topic>/` and append the project registry entry, then edit `run.py` `main::main`, `cases.py`, `config.yaml`, `visualize.ipynb`, and `README.md` in that order.
1. Treat project-root `experiments/registry.toml` as the project-owned topic registry for entrypoints and registered smoke/formal commands. AgentCanon source owns the registry contract in `documents/experiment-registry.md`; from a template or derived repo root, read that contract as `vendor/agent-canon/documents/experiment-registry.md`.
1. When a project registry exists, validate registry schema and registered command placeholders with `python3 tools/ci/check_experiment_registry.py` before formal execution.
1. Treat `/usr/bin/python experiments/<topic>/run.py` with no CLI options as the canonical experiment entrypoint. The topic `run.py` owns run directory creation, config snapshotting, artifact writing, and notebook execution.
1. After a canonical run from the source checkout, usually `main`, use
   `$save-experiment-results` before publishing generated result/report
   artifacts. The dedicated save skill owns retention plan, dirty-source
   formal-status, overwrite policy, and result-branch evidence before
   `python3 tools/experiments/publish_result_branch.py --result-dir experiments/<topic>/result/<run_name> --branch experiment-results/<topic>` runs, adding `--push` only when remote result-branch retention is part of the run plan.
1. Keep GPU/JAX execution-environment ownership in the scheduler or caller environment. Experiment topic code and checked-in configs stay free of hard-coded per-run environment assignment such as GPU visibility, JAX platform, allocator, or preallocation overrides unless the task is explicitly an environment-contract change.
1. Preserve available GPU parallelism by default. Do not force a topic to single-GPU or serial execution by adding `max_workers: 1`, GPU visibility filters, single-device JAX platform settings, or equivalent throttles unless the user explicitly requests serial debugging or the run plan records a concrete environment limit. `gpu_max_slots: 1` means one worker slot per GPU; it must not be used as a substitute for reducing the visible GPU set.
1. When a Python process remains after an interrupted or failed experiment, identify the parent `run.py`, child worker, process group, and elapsed time before calling it residual. Treat active parent/worker processes as a still-running experiment and stop them only when the user asks for abort or cleanup.
1. If the user restricts validation, distinguish non-persistent static checks from checks that leave artifacts. Static checks that do not create durable outputs are allowed. Experiment runs, notebook execution, smoke checks, report generators, or any validation that writes result/log/report artifacts must not be run unless the user asks for them; when such a command is run and creates transient artifacts, delete those artifacts immediately after the run and report the cleanup.
1. Keep checked-in experiment settings in `experiments/<topic>/config.yaml`; run artifacts must include a topic config snapshot, commonly `config_snapshot.json`, written by `run.py`.
1. Require `experiments/<topic>/README.md` to describe the experiment content, question, comparison target, standard commands, config source, visualization notebook, output schema, and run_name convention before formal execution.
1. Require each nontrivial experiment README to include an implementation source map that lists the reused `python/` files, classes, and functions by name, plus a separate object-flow section that shows which objects each step creates, mutates, passes downstream, and writes as artifacts. If an experiment compares variants, identify the single shared execution path and the exact factory/function boundary where variants differ.
1. Put the visualization notebook at `experiments/<topic>/visualize.ipynb`; notebooks read run artifacts and render figures/tables, but they must not be the formal run launcher, fine-grained test surface, or config source of truth.
1. For each notebook visualization item, add a Markdown cell immediately above the code cell in Japanese explaining the input artifact, the plotted quantity, and how to read the figure in one or two sentences.
1. When reviewing an experiment topic, add `$experiment-review` and check direct `run.py` execution, GPU/JAX environment ownership, artifact schema, and notebook readiness.
1. Ensure every run has `result/<run_name>/`; put additional stdout, stderr, startup, tool, or diagnostic logs under `result/<run_name>/logs/` when the topic emits them.
1. Treat `summary.json`, `cases.jsonl`, the topic config snapshot, case artifacts, and `visualize_executed.ipynb` as standard topic run artifacts. If a run lacks them, rerun `/usr/bin/python experiments/<topic>/run.py` or record that the run is not fully reproducible.
1. For planned edits to experiment execution surfaces, run `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and resolve the `experiment_execution_surface_guard` handoff before patching. This surface includes `tools/ci/check_experiment_registry.py`, `documents/experiment-registry.md`, `agents/workflows/experiment-workflow.md`, `experiments/registry.toml`, and topic `run.py` entrypoints. Pair this skill with `$test-design`; run `python3 tools/ci/check_experiment_registry.py` when project `experiments/registry.toml` exists, use `python3 -m pytest tests/tools/test_run_managed_experiment.py -q` for runner or registry checker behavior changes, and reserve long experiment runs for an explicit run plan.
1. Use `$structure-planning` before experiment planning, rerun planning, result report generation, or HTML view generation when the structure is nontrivial; fix first artifact, source-to-structure map, OOP structure contract, metric contract, invalid interpretations, and validation gate before running or writing.
1. For experiment plans and reports, require the OOP structure contract to list reused modules/classes/functions/protocols, objects created/mutated/passed/written by each step, the factory/function boundary where variants differ, and dependency direction across orchestration, domain logic, metrics, visualization, and artifact I/O before section order is drafted.
1. For experiment plans or reports with nontrivial paragraph order or causal/evidence transitions, ask `$structure-planning` to use `agent-canon semantic-index discourse-relations --profile experiment-report` or `--profile methods-protocol` as advisory edge evidence.
1. If a prose graph handoff is present, use hypothesis, metric, baseline, and expected-result diagnostics as advisory input to the experiment plan or rerun plan.
1. Use `$save-experiment-results` with `$result-artifact-writeout` for
   experiment result/report generation so raw run output, Markdown summary,
   manifest, run name, overwrite policy, branch reason, and formal-status are
   recorded separately.
1. If code changes must iterate with explicit decision states, also use `experiment-change-loop`.
