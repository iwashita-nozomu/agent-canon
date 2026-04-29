# Change Review
<!--
@dependency-start
responsibility Documents Change Review for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md artifact placement contract
upstream design ../../documents/dependency-manifest-design.md dependency review policy
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Chunk Findings

| Chunk | Finding | Severity | Status |
| ----- | ------- | -------- | ------ |

## Reuse And Style Findings

<!-- Record whether the implementation follows the detailed design document and mirrors existing code, naming, tests, and docs style. -->

## Cross-Doc Coverage Review

<!-- Check whether the implementer and parent used the cross-cutting packet rather than relying only on one workflow branch. Return revise if relevant review, guardrail, migration, or lifecycle docs were omitted from the implementation basis. -->

## Design-Base Implementation Review

<!-- Check whether each changed slice cites an approved design artifact path and section, user-request clause ID, source/reuse document or code path, and test-plan item. Return revise for missing citations. Return escalate for design drift or design gaps. -->

## Canonical Tree-Head Review

<!-- Confirm that the diff updates only the canonical implementation paths declared by the design and that no non-canonical design doc, copied implementation, backup file, snapshot tree, or alternate truth surface remains in the tracked tree. Return revise if any parallel state remains. -->

## Remaining Work Review

<!-- Check whether this is only a chunk/slice/checkpoint and whether remaining planned work units or active clauses still exist. Return revise if the implementer treats internal progress as task completion. -->

## User Request Trace Review

<!-- Record whether the diff satisfies the declared clause IDs and whether it drifted into work the user did not request. -->

## Repo-Wide Dependency Review

<!-- Run `bash tools/agent_tools/run_repo_dependency_review.sh` against the full repository, not only changed files. Record REPO_DEPENDENCY_REVIEW=pass or list fix-now findings for missing headers, invalid manifests, self references, isolated manifests, or graph cycles. -->

## Revision Loop

<!-- Record what the implementer must revise before the next checkpoint review. Any fix made from these findings, however small, must return through the full required review set on the refreshed diff. -->

## Post-Review Fix Rerun Requirement

<!-- If this review requires any fix, state that every required review family must rerun on the updated diff before closeout, even when the implementer believes the fix is tiny. List the review artifacts that must be refreshed. -->

## Follow-Up

<!-- Record what the implementer must revise before the next chunk proceeds. -->
