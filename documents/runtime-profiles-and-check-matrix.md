<!--
@dependency-start
contract reference
responsibility Defines AgentCanon runtime profiles and risk-based validation routing.
upstream design ../ROOT_AGENTS.md root runtime entrypoint and closeout model
upstream design ./SHARED_RUNTIME_SURFACES.md shared runtime surface ownership policy
downstream design ../agents/canonical/CODEX_WORKFLOW.md Codex execution workflow
downstream design ./agent-canon-parent-repo-latest-checklist.md parent repo latest-state checklist
downstream implementation ../tools/ci/run_all_checks.sh repo check runner
downstream implementation ../tools/catalog.yaml structured tool catalog
@dependency-end
-->

# Runtime Profiles And Check Matrix

Source of truth: [runtime-profiles-and-check-matrix.json](runtime-profiles-and-check-matrix.json).

AgentCanon ships broad shared surfaces, but not every surface is mandatory for
every repository task. Treat root views and tools as installed capability, then
activate only the profile required by the current change.

## Profile Classes

| Profile | Activates | Required when |
| --- | --- | --- |
| Base project | `README.md`, `QUICK_START.md`, `documents/README.md`, project code and tests | Every template or derived repo |
| Agent runtime | `AGENTS.md`, `agents/`, `.agents/`, `.codex/`, shared `tools/` | An agent performs or reviews repo work |
| Devcontainer | `.devcontainer/`, shared post-create helpers | VS Code devcontainer or agent ergonomics are used |
| Docker runtime | root `docker/`, runtime packs | Dockerfile, image, pack, Jupyter, or container setup changes |
| GitHub automation | `.github/`, PR templates, Actions helpers | GitHub Actions, PR automation, or GitHub path-constrained copies change |
| Experiment | `experiments/`, experiment registry, managed runner tools | Experiment topics, formal runs, result summaries, or research workflows change |
| C++ | `CMakeLists.txt`, `cmake/`, `src/`, `include/`, `lib/`, C++ OOP checks | C or C++ code, build layout, or native artifacts change |
| Memory and learning | `memory/`, notes promotion, learning workflows | User asks to persist memory, feedback/retrospective is observed, or agent-learning is in scope |
| Maintenance | inventories, review backlog scan, improvement guide, catalog drift tools | AgentCanon maintenance, repo-wide audit, or scheduled cleanup work |

Compatibility surfaces such as legacy subtree routes may remain documented, but
only under the matching compatibility profile. They are not the default path for
GitHub/submodule-first repositories.


## Risk Classes

| Risk | Examples | Required validation |
| --- | --- | --- |
| Routine docs | Link/text edits in project-local docs with no source contract change | docs check for touched docs and changed-file dependency header checks |
| Focused code | Narrow Python or shell edit with local tests | changed-file dependency checks, targeted tests, ruff/pyright when Python changes |
| Profile change | Docker, GitHub, experiment, C++, devcontainer, MCP, or memory surface change | profile-specific checker plus targeted tests |
| Shared canon | `vendor/agent-canon/`, root shared views, skills, workflows, hooks, tools | `make agent-canon-pr-check` or equivalent AgentCanon PR gate |
| Large delivery | repo-wide rewrite, workflow redesign, broad policy change, or user-requested comprehensive run | run bundle, dependency review, focused and full validation gates, independent review |

Static analysis and reading evidence are the primary validation evidence for
AgentCanon tasks. `make ci` remains the full local confidence gate, but it is
not the default or only acceptable evidence for every owner-bounded change. Use
operation checks, smoke runs, full CI, long test suites, benchmarks, experiments,
and other broad execution as supplemental evidence when runtime behavior,
integration risk, or unresolved static/read findings require them. The selected
validation must match the changed paths, owner surface, and risk class, and the
PR or run bundle must state why that set is sufficient.
Prompt-only or prose-only edits use the surface-specific docs, prompt, eval,
and dependency checks selected by the active profile; they do not automatically
escalate to full `make ci`.

## Validation Failure Response

After any validation test/check failure, do not simplify, revert, delete intended behavior/tests, weaken the oracle, or downscope required validation just to pass.
First record the five machine fields: `failing_contract`, `observation_level`, `cause_classification`, `intent_preservation`, and `evidence`.
This runtime-profile inventory JSON is the canonical validation-failure-response taxonomy owner. `documents/runtime-profiles-and-check-matrix.md` is the generated reader projection, while `agents/canonical/CODEX_WORKFLOW.md`, `agents/canonical/CODEX_SUBAGENTS.md`, `agents/TASK_WORKFLOWS.md`, and `documents/REVIEW_PROCESS.md` are workflow, handoff, reader-map, or checklist projections that must cite this inventory instead of defining separate slug lists.
Repair with approved intent preserved or escalate before intent change.

Required machine fields:

- `failing_contract`
- `observation_level`
- `cause_classification`
- `intent_preservation`
- `evidence`

Valid `cause_classification` values are:

- `implementation_bug`
- `test_oracle_spec_mismatch`
- `fixture_environment_issue`
- `stale_generated_artifact`
- `pre_existing_unrelated_failure`
- `approved_design_user_request_conflict`

Valid `intent_preservation` values are:

- `repair_same_intent`
- `redesign_same_intent`
- `escalate_design_conflict`

Intent preservation routes:

- repair_same_intent: repair the owning code, config, docs, workflow, fixture, environment, generated artifact, test oracle, or residual evidence route while preserving approved intent
- redesign_same_intent: return to design/test planning while preserving the same approved intent
- escalate_design_conflict: escalate approved-design/user-request conflict before any intent change

## Check Matrix

| Changed surface | Required check |
| --- | --- |
| Markdown docs only | `tools/bin/agent-canon docs check`; changed-file dependency header checks |
| Python code/tests | targeted `pytest`; `python3 -m pyright`; `python3 -m ruff check ...` |
| AgentCanon docs/workflows/skills/tools/hooks | `make agent-canon-pr-check`; shared-surface sync; workflow/PR checks; dependency review; docs check; generated-artifact guard; broad quick CI with already-run docs/workflow gates skipped |
| Root shared views or submodule pin | `bash tools/sync_agent_canon.sh check`; `git submodule status vendor/agent-canon` evidence |
| Docker/devcontainer/runtime pack | `bash tools/docker_dependency_validator.sh`; `make docker-build-check` when build behavior changes |
| GitHub workflow/PR | `python3 tools/ci/check_github_workflows.py`; relevant GitHub Actions evidence when available |
| Experiments | `make experiment-check`; managed run evidence for formal experiment changes |
| C/C++ | project-native configure/build/test and C++ reviewer/checker where applicable |
| Memory/eval/hook logging | append-only artifact evidence and improvement guide/eval checks when prompts or logging fields change |

## Closeout Rule

Do not turn optional profiles into hidden mandatory work. If a profile is not
activated by the changed paths, user request, or risk class, record it as
`not_applicable` instead of running or explaining its checks.
