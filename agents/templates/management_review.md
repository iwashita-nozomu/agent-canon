# Management Review
<!--
@dependency-start
responsibility Documents Management Review for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Scope Review

<!-- Check whether user intent, acceptance criteria, and scope are concrete enough. -->

## User Request Coverage Review

<!-- Check whether user_request_contract.md captures every must-do, must-not-do, and completion-evidence clause without silent drops. -->

## Source Bucket Review

<!-- Check whether each clause is labeled as current_request, durable_user_preference, repo_or_code_precedent, domain_or_external_constraint, or unknown_or_open_question, and whether durable preferences are not silently converted into task requirements. -->

## Accumulated Context Resolution Review

<!-- Check whether open questions were first resolved against memory, notes/themes, notes/guardrails, notes/knowledge, notes/failures, documents, prior logs, local code, tests, and external constraints if needed. Return revise if the agent asked the user or left unknowns without this sweep. -->

## Unknown Handling Review

<!-- Check whether unknown_or_open_question appears only in deferred or escalation entries, not in active must-do, must-not-do, or completion-evidence clauses. Return escalate only when accumulated context cannot resolve a scope-changing unknown. -->

## Routing Review

<!-- Check whether workflow=<family>, skills=<...>, review=<...> are declared and whether the right specialist roles and explicit stage subagents were enabled. -->

## Context And Library Sweep Review

<!-- Check whether the required document sweep, dependency/library sweep, and existing-implementation sweep were actually performed before planning, and whether the artifacts record what was inspected. -->

## Reuse-First Review

<!-- Check whether the intake package identifies existing code, docs, and installed libraries that implementation must follow, and whether it records why reuse or extension is insufficient before any new path is proposed. -->

## Decision

<!-- Record approve, revise, or escalate. -->
