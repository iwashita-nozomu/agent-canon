<!--
@dependency-start
contract reference
responsibility Defines AgentCanon runtime profiles and risk-based validation routing.
upstream design ../../ROOT_AGENTS.md root runtime entrypoint and closeout model
upstream design ./SHARED_RUNTIME_SURFACES.md shared runtime surface ownership policy
downstream design ../../agents/canonical/CODEX_WORKFLOW.md Codex execution workflow
downstream design ../agent-canon/agent-canon-parent-repo-latest-checklist.md parent repo latest-state checklist
downstream implementation ../../tools/ci/run_all_checks.sh repo check runner
downstream implementation ../../tools/ci/agent_canon_pr_graph_selector.py selects strict parent graph requirement from canonical profile IDs
downstream implementation ../../tools/catalog.yaml structured tool catalog
@dependency-end
-->

# Runtime Profiles And Check Matrix

Source of truth: [runtime-profiles-and-check-matrix.json](runtime-profiles-and-check-matrix.json).

AgentCanon ships broad shared surfaces, but not every surface is mandatory for
every repository task. Treat root views and tools as installed capability, then
activate only the profile required by the current change.
Each profile ID and strict_dependency_graph_required value is canonical input
for parent AgentCanon PR graph selection; unknown IDs fail selection.

## Profile Classes

| Profile ID | Profile | Activates | Required when | Strict dependency graph |
| --- | --- | --- | --- | --- |
| bootstrap | Bootstrap | `bootstrap.sh`, `bootstrap/`, lifecycle parser and state | AgentCanon installation, start/stop, target, or lifecycle state changes | no |
| tool-runtime | Tool runtime | Python/Rust tool dispatch, catalog, LSP | Shared AgentCanon analysis tools or language servers change | no |
| container | Container | Dockerfile, entrypoint, manifest limits | The shared AgentCanon tool image or container contract changes | no |
| mount-generation | Mount generation | target registry, generations, rollback | Target admission, mount generation, rollback, or concurrent lifecycle changes | no |
| codex-surfaces | Codex surfaces | isolated skills, agents, hooks, runtime-local `CODEX_HOME` | Codex preparation, isolated runtime configuration, or owned-link cleanup changes | no |
| eval-archive | Eval archive | eval producer, external spool, archive Git adapter | Eval collection, source-unchanged evidence, or agent-canon-log publication changes | no |
| docs | Docs | README, guides, runtime contracts | User-facing AgentCanon command, owner, migration, or runtime documentation changes | no |
| source | Source | policy, workflow, skills, canonical tools | AgentCanon source policy, workflow, skill, hook, or canonical tool changes | yes |
| project | Project | project Docker, project test runner, project GPU | A parent project execution environment changes; never for AgentCanon internal tests | no |

Profiles may be combined, but every changed path must have one owner and one
primary check route. Do not select `project` merely because a tool was invoked
against a project target.


## Risk Classes

| Risk | Examples | Required validation |
| --- | --- | --- |
| boundary | new mount, path default, write location, credential route | source before/after fingerprint, resolved paths, negative escape test |
| compatibility | CLI rename, catalog entry, execution-plane change | schema-v2 parity fixture for argv/cwd/streams/exit/signal/writes |
| lifecycle | install/start/stop/gc/uninstall, image/container ownership | exact IDs, labels, limits, health and absence readback |
| concurrency | target add, rollback, task admission | lock trace, active count, candidate/old generation evidence |
| archive | collect/sync, branch, push, readback | local spool, remote ref/tree/blob digest, duplicate/conflict result |
| docs | user route, owner, migration, issue reference | link/header check and clean command examples |

If a focused command is unavailable in a fresh checkout, report the missing
owner/route; do not create a fallback that writes into source. Use one task
temporary directory outside the source checkout and one shared tool image at
most. Track any image/container created for validation and remove that exact
resource after evidence is captured.

## Validation Failure Response

After any validation test/check failure, do not simplify, revert, delete intended behavior/tests, weaken the oracle, or downscope required validation just to pass.
First record the five machine fields: `failing_contract`, `observation_level`, `cause_classification`, `intent_preservation`, and `evidence`.
This runtime-profile inventory JSON is the canonical validation-failure-response taxonomy owner. `documents/runtime/runtime-profiles-and-check-matrix.md` is the generated reader projection, while `agents/canonical/CODEX_WORKFLOW.md`, `agents/canonical/CODEX_SUBAGENTS.md`, `agents/TASK_WORKFLOWS.md`, and `documents/conventions/REVIEW_PROCESS.md` are workflow, handoff, reader-map, or checklist projections that must cite this inventory instead of defining separate slug lists.
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
| AgentCanon docs/workflows/skills/tools/hooks | `make agent-canon-pr-check`; shared-surface sync; workflow/PR checks; strict dependency review as the dependency-header/graph judgment owner; standalone-source tool_drift coverage once; docs check; generated-artifact guard; standalone-source prompt/accumulated evals remain in the existing static-gates owner; derived shared gates exclude AgentCanon development prompt/accumulated eval producers and parent-owned diagnostics; standalone shared gates remain the existing static-gates owner and add no repository-wide project-quality job; derived parent workflows expose the canonical project-quality owner marker and `make ci` command; job names are not an authority; no repository-wide project-quality runner is added to the shared gate |
| Root bootstrap or runtime lifecycle | `install -> start -> target add -> status -> codex prepare -> tool/exec`; `eval collect -> eval sync` or an explicit pending receipt; `stop -> gc -> uninstall -> resource absence readback` |
| Python/Rust tool runtime or LSP | targeted tool-dispatch and runtime-artifact tests; schema-v2 parity evidence for argv/cwd/streams/exit/signal/writes |
| Docker image or shared container | container contract tests; one labeled shared image build when Docker is available; non-root, read-only source, bounded resource and LSP readback |
| Target mount or generation | target registry and generation tests; lock, active-task, candidate-health, rollback and atomic-switch evidence |
| Codex isolated surfaces | bootstrap Codex tests and manifest readback; runtime-local `CODEX_HOME` isolation; collision and foreign-link negative cases |
| Eval collection or archive publication | runtime artifact/archive tests; local bare-remote E2E; source unchanged, pending spool, branch and remote readback evidence |
| Project execution environment | project-owned Dockerfile and `test/testrunner.sh`; project test/GPU evidence; never AgentCanon internal test knowledge |

## Closeout Rule

Do not turn optional profiles into hidden mandatory work. If a profile is not
activated by the changed paths, user request, or risk class, record it as
`not_applicable` instead of running or explaining its checks.
