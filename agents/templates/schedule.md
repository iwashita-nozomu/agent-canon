<!--
@dependency-start
contract template
responsibility Documents Schedule for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->

# Schedule


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Stage Plan

| Stage | Owner Agent | Review Agent | Inputs | Exit Criteria | Status |
| ----- | ----------- | ------------ | ------ | ------------- | ------ |

## Clause Coverage

| Clause ID | Covered By Stage | Review Gate | Status |
| --------- | ---------------- | ----------- | ------ |

## Planned Work Units

<!-- This table is the canonical task TODO surface. Keep concrete work units and statuses here until closeout. -->

| Unit ID | Clause IDs | Owner | Completion Evidence | Next Gate | Status |
| ------- | ---------- | ----- | ------------------- | --------- | ------ |

## Task Completion Boundary

<!-- Define what must be true before user-facing completion: all active clauses resolved, all planned work units complete, final review approved, mechanical completion loop complete, read-only diff-check agent approval recorded in a run-local artifact, validation complete, closeout gate unlocked, commit and push done. A chunk, slice, checkpoint, or subpass is internal progress only. -->

## Explicit Subagents

<!-- Record the concrete Codex subagents or permanent team roles used for each stage. -->

## Agent Wave Ledger

<!-- This is the authoritative fanout ledger. Intake Responsibility Wave is an intake responsibility slice rather than a total cap. Add one row for the intake wave and one row for every mid-task expansion, skipped wave, or delegated child wave. On any mid-task user addition, classify it as `same_active_task_delta`, `scope_or_contract_change`, or `new_task` and prefer `python3 tools/agent_tools/workflow_monitor.py --mid-task-user-input ...` so this table and workflow_monitoring.md stay synchronized. Keep `Delegated Policy Ref` pointing at `team_manifest.yaml#run.delegated_spawn_policy` or `team_manifest.yaml#run.subagent_lifecycle_policy`. -->

| Wave ID | Parent Or Delegate | Spawn Authority | Trigger | Budget Before | Budget After | Runtime Max Threads | Runtime Max Depth | Spawned Roles | Role Instances | Skipped Roles / Rationale | Allowed Paths | Do Not Read | Write Scope | Validation Route | Review Gate | Handoff Artifacts | Delegated Policy Ref | Status |
| ------- | ------------------ | --------------- | ------- | ------------- | ------------ | ------------------- | ----------------- | ------------- | -------------- | ------------------------- | ------------- | ----------- | ----------- | ---------------- | ----------- | ----------------- | -------------------- | ------ |

## Reuse And Continuity Constraints

<!-- Record which existing code, naming, APIs, tests, and docs style must be followed. -->

## Risks

<!-- Note sequencing risks, merge risks, or verification risks. -->
