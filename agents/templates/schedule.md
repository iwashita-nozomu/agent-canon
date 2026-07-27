<!--
@dependency-start
contract template
responsibility Documents Schedule for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md artifact placement contract
upstream design ../skills/agent-orchestration.md execution-time-aware work-conservation owner
@dependency-end
-->

# Schedule


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Stage Plan

| Stage | Owner Agent | Review Agent | Inputs | Exit Criteria | Status |
| ----- | ----------- | ------------ | ------ | ------------- | ------ |

## Execution-Time-Aware Plan

<!-- Project the canonical owner below; do not restate its scheduling policy or add duration cutoffs. -->

- Owner contract: `agents/skills/agent-orchestration.md#Execution-Time-Aware Work-Conservation Contract`
- Executable scheduling fields: `dependency_dag`, `makespan_objective`, `responsibility_completeness`, `correctness`, `critical_path`, `ready_set`, `context_reuse`, `affected_evidence_invalidation`.
- Dependency DAG / closure:
- Makespan objective:
- Responsibility completeness:
- Correctness:
- Critical path:
- Ready set:
- Useful ready set:
- Dispatch batch:
- Wait reason (only when the useful ready set is empty):
- Context reuse:
- Affected evidence invalidation:

| DAG Node | Depends On | Conflict Scope | Status | Evidence |
| -------- | ---------- | -------------- | ------ | -------- |

## Clause Coverage

| Clause ID | Covered By Stage | Review Gate | Status |
| --------- | ---------------- | ----------- | ------ |

## Planned Work Units

<!-- This table is the canonical task TODO surface. Keep concrete work units and statuses here until closeout. -->

| Unit ID | Clause IDs | Owner | Completion Evidence | Next Gate | Status |
| ------- | ---------- | ----- | ------------------- | --------- | ------ |

## Task Completion Boundary

<!-- Define what must be true before user-facing completion: all active clauses resolved, selected work units complete, one selected owning review gate adjudicated, mechanical completion loop complete, validation complete, closeout gate unlocked, commit and push done. Candidate review packs and rejected hypotheses do not create work; a chunk, slice, checkpoint, or subpass is internal progress only. -->

## Explicit Subagents

<!-- Record the concrete Codex subagents or permanent team roles used for each stage. -->

## Agent Wave Ledger

<!-- This is the authoritative fanout ledger when a wave route is selected. Intake Responsibility Wave is an intake responsibility slice rather than a total cap; do not create an intake row merely because the catalog lists it. Add rows only for selected or actually skipped/delegated waves. If a planned row has no actual event, classify the row in Status or Skipped Roles / Rationale as exactly one of `overplanning`, `logging_gap`, or `unresolved`; overplanning/unresolved rows are not backfilled, while logging_gap remains a validation blocker. On any mid-task user addition, classify it as `same_active_task_delta`, `scope_or_contract_change`, or `new_task` and prefer `python3 tools/agent_tools/workflow_monitor.py --mid-task-user-input ...` when durable coordination/resumption evidence is needed. Keep `Delegated Policy Ref` pointing at `team_manifest.yaml#run.delegated_spawn_policy` or `team_manifest.yaml#run.subagent_lifecycle_policy`. -->

| Wave ID | Parent Or Delegate | Spawn Authority | Trigger | Budget Before | Budget After | Runtime Max Threads | Runtime Max Depth | Spawned Roles | Role Instances | Skipped Roles / Rationale | Allowed Paths | Do Not Read | Write Scope | Validation Route | Review Gate | Handoff Artifacts | Delegated Policy Ref | Status |
| ------- | ------------------ | --------------- | ------- | ------------- | ------------ | ------------------- | ----------------- | ------------- | -------------- | ------------------------- | ------------- | ----------- | ----------- | ---------------- | ----------- | ----------------- | -------------------- | ------ |

## Reuse And Continuity Constraints

<!-- Record which existing code, naming, APIs, tests, and docs style must be followed. -->

## Risks

<!-- Note sequencing risks, merge risks, or verification risks. -->
