# Change Review
<!--
@dependency-start
contract template
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

## Semantic Responsibility Candidate Review

<!-- Inspect `semantic_index_merge_candidates_*.jsonl`, `semantic_index_thin_docs_*.jsonl`, and optional `semantic_index_search_*.jsonl` from `review_backlog_scan.sh` when present. Record same-responsibility duplicates, consolidation candidates, thin wrappers, or adjacent search hits that affect this diff. Treat semantic-index output as advisory review evidence only; confirm with dependency review, exact search, structure checks, and source inspection before requiring a merge or deletion. -->

## Cross-Doc Coverage Review

<!-- Check whether the implementer and parent used the cross-cutting packet rather than relying only on one workflow branch. Return revise if relevant review, guardrail, migration, or lifecycle docs were omitted from the implementation basis. -->

## Design-Base Implementation Review

<!-- Check the one integrated responsibility-unit diff against all four active-packet entries. Every source, generated, and deletion record must trace to the approved artifact, clause, owner, source/reuse path, dependency order, and validation evidence. Return revise for duplicate parser/writer paths, partial file-sized completion, or test-first production behavior; return escalate for design drift. -->

## Canonical Tree-Head Review

<!-- Confirm that the diff updates only the canonical implementation paths declared by the design and that no non-canonical design doc, copied implementation, backup file, snapshot tree, or alternate truth surface remains in the tracked tree. Return revise if any parallel state remains. -->

## Remaining Work Review

<!-- Check whether this is only a chunk/slice/checkpoint and whether remaining planned work units or active clauses still exist. Return revise if the implementer treats internal progress as task completion. -->

## User Request Trace Review

<!-- Record whether the diff satisfies the declared clause IDs and whether it drifted into work the user did not request. -->

## Repo-Wide Dependency Review

<!-- Explicitly build the canonical graph, then run `bash tools/agent_tools/run_repo_dependency_review.sh` against the full repository. Record fresh verified graph status, zero unresolved/ambiguous/uncovered counts, consumer residual scans, and REPO_DEPENDENCY_REVIEW=pass. A shell/parser fallback or obsolete transport fixture is a revise finding. -->

## Revision Loop

<!-- Record what the implementer must revise before the next checkpoint review. Any fix made from these findings, however small, must return through the active required review set for the risk class and changed surface on the refreshed diff. -->

## Review Rejection Response Review

<!-- Confirm that any revise / required_change / rejected diff / requested-change handling preserves the user-requested clause or approved design intent. Return revise if the response simply reverts, discards, or shrinks requested behavior. If a revert or discard is justified, record withdrawal / supersession / owner-boundary / unsafe-replacement / escalation authority and the clauses still preserved. -->

## Post-Review Fix Rerun Requirement

<!-- If this review requires any fix, state that every required review family must rerun on the updated diff before closeout, even when the implementer believes the fix is tiny. List the review artifacts that must be refreshed. -->

## Follow-Up

<!-- Record what the implementer must revise before the next chunk proceeds. -->
