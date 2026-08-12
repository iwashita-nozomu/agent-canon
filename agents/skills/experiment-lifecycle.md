# experiment-lifecycle
<!--
@dependency-start
contract skill
responsibility Owns experiment run identity, lifecycle state, reproducibility core, and rerun/publication decisions without re-owning artifact files or report prose.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/design/responsibility-rationale.md experiment lifecycle and artifact ownership rationale
downstream implementation ../../tools/experiments/create_experiment_topic.py creates registered topics
downstream implementation ../../tools/experiments/run_managed_experiment.py owns managed run execution
downstream implementation ../../tools/experiments/publish_result_branch.py explicitly publishes selected result directories
downstream implementation ../../tools/ci/check_experiment_registry.py validates the project registry
downstream design result-artifact-writeout.md owns file/checksum/role artifact manifests
downstream design report-writing.md owns reader-facing interpretation when requested
@dependency-end
-->

## Purpose

Own one experiment run from preparation through terminal status. The canonical run record answers: which source/config/command/environment produced the run, what status it reached, which artifact owner wrote outputs, and whether an explicit rerun or publication action followed.

## Activation

Use this skill for a new experiment topic, managed experiment execution, rerun decisions, run status/provenance, or explicit result-branch publication. Saving already-produced files alone routes to `result-artifact-writeout`; writing interpretation routes to `report-writing`; rendering HTML routes to `html-output`.

## Canonical ownership

- Topic registration and runnable scaffold: `tools/experiments/create_experiment_topic.py` plus project `experiments/registry.toml`.
- Managed execution: `tools/experiments/run_managed_experiment.py --topic <topic> --variant <variant> -- <inner-command>`.
- Run identity/state: this skill and the managed-run record. A second save-result state machine is forbidden.
- Physical artifacts, checksum, and semantic role: `result-artifact-writeout`.
- Reader claims and limitations: `report-writing` only when requested.
- HTML artifact correctness: `html-output` only when HTML is requested.
- Result-branch publication: explicit `tools/experiments/publish_result_branch.py`; saving a run does not imply publication.

## Reproducibility core

A formal run must retain enough information to reproduce and compare the executed computation. The required semantic core is:

1. source identity or exact source-state evidence;
2. effective configuration or a config snapshot/reference sufficient to reconstruct it;
3. executed command/protocol identity;
4. material environment/runtime identity relevant to the result;
5. terminal status, including failed/partial states truthfully;
6. references to the artifacts that actually exist, delegated to `result-artifact-writeout`.

No universal filename inventory follows from this contract. `summary.json`, `cases.jsonl`, notebooks, startup logs, plots, and case files are producer-specific outputs: require them only when the selected producer/protocol declares them. A run that never produces an optional artifact does not need a synthetic missing-artifact limitation.

## Topic contract

A registered topic uses `experiments/<topic>/` and keeps its checked-in configuration in the topic-owned source chosen by the project, commonly `config.yaml`. `README.md` records the question, comparison/baseline, standard managed command, configuration source, output schema, and `run_name` rule when those are part of the topic.

`run.py` is an inner entrypoint called by the managed runner. It may create the run directory, snapshot effective configuration, and call domain code, but it does not become scheduler/environment policy. GPU visibility, JAX/XLA allocation, allocator/preallocation, and other per-run resource assignment remain scheduler/caller responsibilities unless the task explicitly changes that environment contract.

A visualization notebook, when the producer uses one, reads existing run artifacts; it is not the formal launcher or configuration source of truth.

## Lifecycle

1. Fix the topic and protocol. Create missing topics with `python3 tools/experiments/create_experiment_topic.py <topic>` rather than copying a template directory manually.
2. When a project registry exists, run `python3 tools/ci/check_experiment_registry.py` before formal execution.
3. Execute through the managed runner. Preserve source/config/command/environment identity before interpreting results.
4. Record terminal status even for failed/partial runs. Do not overwrite an existing run identity to make a rerun look like the original run.
5. Delegate every file that actually exists to `result-artifact-writeout` for role/checksum/manifest writeout.
6. Add `report-writing` only if a reader-facing synthesis is requested. Add `html-output` only for explicit HTML/browser output.
7. Rerun only when the run/protocol requires new execution evidence. A report rewrite or artifact copy does not imply rerun.
8. Publish a result branch only by explicit operation using `python3 tools/experiments/publish_result_branch.py --result-dir experiments/<topic>/result/<run_name> --branch experiment-results/<topic>`; add `--push` only when remote publication is authorized.

## Safety boundaries

For planned changes to experiment execution surfaces, run `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and resolve `experiment_execution_surface_guard` before editing. Changes to the managed runner or registry checker use focused unit tests such as `python3 -m pytest tests/tools/test_run_managed_experiment.py -q`; long experiment execution remains an explicit run-plan action.

A user restriction on validation distinguishes non-persistent static checks from commands that create run/result/report artifacts. Do not run artifact-producing experiment commands when the requested scope excludes them.

Interrupted processes are not classified as residual merely because they are long-lived. Read the parent `run.py`, worker/process-group relation, and elapsed state before cleanup; stop active experiment work only under the requested abort/cleanup authority.

## Review

Use `experiment-review` for managed-run route, environment ownership, producer-declared artifact schema, and optional notebook readiness. Use `test-design` only for an unresolved oracle/specification/regression risk rather than as an automatic companion to every experiment edit.
