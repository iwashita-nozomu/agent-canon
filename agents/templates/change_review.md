# Change Review
<!--
@dependency-start
contract template
responsibility Documents Change Review for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md artifact placement contract
upstream design ../../documents/design/dependency-manifest-design.md dependency review policy
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Chunk Findings

| Chunk | Finding | Severity | Status |
| ----- | ------- | -------- | ------ |

## Hypothesis Adjudication

| Hypothesis | Snapshot Ref | Reachable Input / Control Path | Contract Ref | Witness / Static Proof | Adjudication | Reason Code | Evidence Ref | Opens Rework Wave |
| ---------- | ------------ | ----------------------------- | ------------ | ---------------------- | ------------ | ----------- | ------------ | ----------------- |

<!-- Reviewer output is hypothesis input. Parent / integration owner accepts only a current-snapshot, reachable-path, contract, and witness/static-proof-backed hypothesis that changes behavior, owner/design boundary, correctness, validation, or publication state. Rejected rows use reason_code and evidence_ref and do not authorize edit, revert, rollback, publication, or a new wave. -->

## Reuse And Style Findings

<!-- Record whether the implementation follows the detailed design document and mirrors existing code, naming, tests, and docs style. -->

## Semantic Responsibility Candidate Review

<!-- Inspect `semantic_index_merge_candidates_*.jsonl`, `semantic_index_thin_docs_*.jsonl`, and optional `semantic_index_search_*.jsonl` from `review_backlog_scan.sh` when present. Record same-responsibility duplicates, consolidation candidates, thin wrappers, or adjacent search hits that affect this diff. Treat semantic-index output as advisory review evidence only; confirm with dependency review, exact search, structure checks, and source inspection before requiring a merge or deletion. -->

## Cross-Doc Coverage Review

<!-- Check whether the implementer and parent used the cross-cutting packet rather than relying only on one workflow branch. Return revise if relevant review, guardrail, migration, or lifecycle docs were omitted from the implementation basis. -->

## Design-Base Implementation Review

<!-- Check the one integrated responsibility-unit diff against all four active-packet entries, including the Abstract Design Frame and Implementation Source Packet. Confirm that every changed slice traces to the approved design section, Design Side-Effect Map item, user-request clause ID, source/reuse document or code path, and test-plan item only when test design was activated. Confirm that scope came from the approved responsibility model rather than the nearest file, helper, or current finding. Every source, generated, and deletion record must trace to the approved artifact, clause, owner, source/reuse path, dependency order, and validation evidence. Return revise for duplicate parser/writer paths, partial file-sized completion, or test-first production behavior; return escalate for design drift or design gaps. -->

## Canonical Tree-Head Review

<!-- Confirm that the diff updates only the canonical implementation paths declared by the design and that no non-canonical design doc, copied implementation, backup file, snapshot tree, or alternate truth surface remains in the tracked tree. Return revise if any parallel state remains. -->

## Remaining Work Review

<!-- Check whether this is only a chunk/slice/checkpoint and whether remaining planned work units or active clauses still exist. Return revise if the implementer treats internal progress as task completion. -->

## User Request Trace Review

<!-- Record whether the diff satisfies the declared clause IDs and whether it drifted into work the user did not request. -->

## Repo-Wide Dependency Review

<!-- Run static and targeted checks first. Run `bash tools/agent_tools/run_repo_dependency_review.sh` against the full repository only when the selected final candidate contract requires it; otherwise record the targeted route and why the broad check was not selected. -->

## Revision Loop

<!-- Record only accepted findings that change behavior, owner/design boundary, correctness, validation, or publication state. Rejected hypotheses retain reason_code/evidence_ref and do not create a new review wave. -->

## Review Rejection Response Review

<!-- Confirm that any revise / required_change / rejected diff / requested-change handling preserves the user-requested clause or approved design intent. Return revise if the response simply reverts, discards, or shrinks requested behavior. If a revert or discard is justified, record withdrawal / supersession / owner-boundary / unsafe-replacement / escalation authority and the clauses still preserved. -->

## Post-Review Fix Rerun Requirement

<!-- If the parent adjudicates an accepted finding that changes behavior, owner/design boundary, correctness, validation, or publication state, record the selected owning gate rerun on the updated diff. Duplicate, stylistic, already-covered, evidence-free, unreachable, stale, private/incidental, out-of-scope, or unproven design-conflict hypotheses receive reason_code and evidence_ref and do not open a wave or rollback. -->

## Follow-Up

<!-- Record what the implementer must revise before the next chunk proceeds. -->
