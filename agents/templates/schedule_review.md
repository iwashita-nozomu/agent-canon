# Schedule Review
<!--
@dependency-start
contract template
responsibility Documents Schedule Review for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Stage Order Review

<!-- Check stage ordering, dependency realism, and rollback points. -->

## Reviewer Separation Review

<!-- Check that plan review, detailed design review, and document flow review are assigned to different agents. -->

## Subagent Adequacy Review

<!-- Check that the chosen subagents are appropriate for requirements, research, planning, design, and implementation. Return revise if any Agent Wave Ledger row lacks spawn_budget, allowed_paths, do_not_read, write_scope, review_gate, or closeout evidence path. -->

## Completion Boundary Review

<!-- Check that the schedule separates task-level completion from chunks, slices, checkpoints, and subpasses. Return revise if user-facing completion can unlock before all active clauses and planned work units are resolved. -->

## Risks

<!-- Note schedule risks or sequencing issues. -->

## Revision Loop

<!-- Record which stage the planner must revisit, what must change, and what blocks approval. -->

{{>decision_approve_revise_escalate}}
