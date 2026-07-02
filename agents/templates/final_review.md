# Final Review
<!--
@dependency-start
contract template
responsibility Documents Final Review for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md artifact placement contract
upstream design ../../documents/dependency-manifest-design.md dependency review policy
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Ship Blockers

| Finding | Severity | Status |
| ------- | -------- | ------ |

## Design Trace Acceptance

<!-- Confirm that the final diff remains traceable to the Abstract Design Frame, approved design sections, user-request clause IDs, Implementation Source Packet entries, and test-plan items. Return revise if a changed slice is only justified by the nearest file, helper, current finding, or chat context instead of the abstract responsibility model. Record blockers or escalation points. -->

## Design Side-Effect Trace Acceptance

<!-- Confirm that implemented side effects match the approved Design Side-Effect Map, including documents, workflows, prompt/config, validation output, dependency manifests, and user-facing surfaces. Record any side-effect item that moved to a later stage, was escalated, or received explicit reviewer acceptance. -->

## Planned Work Completion Review

<!-- Confirm that all planned work units and active clauses are complete, that schedule.md still reflects the full TODO surface, and that work_log.md shows the meaningful execution trail. Return required_change if only a chunk, slice, checkpoint, or subpass is complete. -->

## Cross-Doc Coverage Review

<!-- Confirm that the task did not stay trapped in one document tree branch and that relevant cross-cutting packet docs were considered before acceptance. Return revise if review policy, guardrails, lifecycle docs, or migration/integration docs that affect this task were ignored. -->

## Spec-To-Product Coverage Review

<!-- For every must-do and completion-evidence clause, confirm the implemented product surface or artifact that satisfies it. Return revise if any requested spec has no corresponding implementation, doc, test, command, or explicit deferred/rejected clause. -->

## Review Finding Incorporation Review

<!-- Confirm that change review, language-specific review, docs review, final review, and required specialist findings were reflected in implementation or explicitly escalated. Return revise if fix-now findings were ignored or only recorded in review artifacts. -->

## Review Rejection Response Review

<!-- Confirm that review rejection, requested-change, revise, and required_change responses preserved the active request clauses and approved design intent. Return revise if the final diff reached green state by rolling back, discarding, or narrowing user-requested behavior without withdrawal, supersession, owner-boundary, unsafe-replacement, or escalation evidence. -->

## Semantic Search And Responsibility Evidence

<!-- Confirm whether review-time semantic-index artifacts were required for this task. If present, record how responsibility-scoped merge candidates, thin-doc candidates, and long-query search hits were accepted, fixed, or rejected. Return revise if relevant semantic candidates were ignored, or if semantic output alone was used as merge/delete authority without dependency and structure evidence. -->

## Post-Fix Full Review Rerun Review

<!-- Confirm that if any review-driven fix landed after an earlier review artifact, the active required review set for the risk class and changed surface was rerun against the latest diff. Record the refreshed review artifacts, or explicitly state that no post-review fixes occurred after the last applicable review pass. Return revise if any tiny fix skipped the rerun. -->

## Repo-Wide Dependency Review

<!-- Confirm `bash tools/agent_tools/run_repo_dependency_review.sh` was run against the full repository after the latest fix. Return revise if only --changed checks were run or if any dependency manifest issue remains. -->

## Canonical Tree-Head Acceptance

<!-- Confirm that the only durable product state left in the tracked tree is the current tree head on canonical paths. Return revise if any non-canonical design document, copied implementation, dated snapshot, backup path, or mirrored tree remains. -->

## Residual Risks

<!-- Record remaining risk, approval notes, or escalation points. -->

{{>decision_approve_revise_escalate}}
