# Detailed Design Review
<!--
@dependency-start
contract template
responsibility Documents Detailed Design Review for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md artifact placement contract
upstream design ../../documents/dependency-manifest-design.md dependency evidence contract
upstream implementation ../../tools/agent_tools/check_design_doc_claims.py verifies design-doc evidence claims
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

{{>findings_area_table}}

## Reader Map

This template owns review of the detailed design artifact itself before
implementation. Record the exact design artifact under review, then work
through document completeness, reuse/style, cross-doc coverage, upstream
requirements, abstract design frame, evidence, assumptions, parent-doc
alignment, source packet, side effects, canonical tree head, naming,
design-to-implementation trace, and readiness before deciding approve, revise,
or escalate. Top-down reader flow is reviewed separately by the document-flow
review artifact; this template checks whether implementation can proceed from
the reviewed design without hidden assumptions. An approve decision applies
only to the current artifact recorded below.

## Design Artifact Under Review

<!-- Name the exact design_brief.md path, revision or section set, source packet, and reviewer separation evidence. Return revise if the review target is a chat summary, implementation diff, worker summary, or stale design artifact. -->

- Design artifact path:
- Design revision or section set:
- Source packet reviewed:
- Reviewer separation:
- Review validity:

## Document Completeness Review

<!-- Check whether the design document is concrete enough for implementation without hidden assumptions. -->

## Reuse And Style Review

<!-- Check whether existing code, naming, APIs, tests, and docs style are being followed. -->

## Cross-Doc Coverage Review

<!-- Check whether the design looked beyond the parent document chain and covered relevant cross-cutting docs such as review policy, guardrails, notes lifecycle, learning workflow, and migration/integration docs. Return revise if the design stayed inside one document branch and missed adjacent governing docs. -->

## Upstream Requirement Packet Review

<!-- Check whether the design explicitly cites the upstream documented requirement packet: request contract, schedule, intent brief, waterfall docs, and other governing documents. Return revise if the design appears to rely on chat-only memory. -->

## Abstract Design Frame Review

<!-- Review the exact active-packet abstract-design-frame entry and whether the design fixes the abstract responsibility model, concept graph or layer model, non-goals, future extension layers, evaluation axes, and relationship to existing canonical surfaces. Return revise if entry references do not join or file-by-file design is not derived from this frame. -->

## Evidence Coverage Review

<!-- Check whether major design claims cite current code, dependency-header evidence, existing docs, or parent documents. For new or changed design docs, record `python3 tools/agent_tools/check_design_doc_claims.py --root . <design-doc>` and the artifact path. -->

## Assumption Definition Review

<!-- Check whether first-use DSL terms, problem standard forms, canonical forms, and normalization rules appear in the design's Evidence And Assumption Ledger before they drive implementation choices. -->

## Parent-Doc Alignment Review

<!-- Check whether differences from upstream parent documents are recorded with the governing source for the current choice. -->

## Refactor Tool Alignment Review

<!-- Check whether structure or responsibility shifts are handed to dependency-analysis and structure-refactor with dependency-expanded evidence. -->

## Implementation Source Packet Review

<!-- Review the exact implementation-source-packet entry, its dependency on abstract-design-frame, and every required read-before-edit artifact. Return revise if references do not join or the worker would need chat context or unstated assumptions. -->

## Design Side-Effect Map Review

<!-- Review the exact design-side-effect-map entry and whether each decision maps to affected implementation, document, workflow, prompt/config, validation, dependency-manifest, and user-facing surfaces. Return revise if references do not join or implementation would need to discover secondary surfaces after approval. -->

## Canonical Tree-Head Review

<!-- Check whether the design fixes the canonical design-document paths and implementation paths that may remain in the tracked tree, and whether it explicitly deletes or forbids non-canonical drafts, snapshots, mirrored directories, backup files, or copied implementations. Return revise if the task would preserve multiple truths beyond the current tree head. -->

## Identifier And Naming Review

<!-- Check whether every new or renamed identifier, path, CLI flag, config key, and public API is fixed by the design or local precedent. Return revise if the worker would need to invent any reusable or user-facing name. -->

## Design-To-Implementation Trace Review

<!-- Review the exact design-to-implementation-trace entry and its dependencies on all other packet entries. Check that every planned source, generated, and deletion record maps to a design section, request clause, source or reuse path, validation evidence, and the one responsibility unit. -->

## Implementation Readiness Review

<!-- Check whether the design is actually ready for implementation and whether it passes the most important pre-implementation gate. Top-down document readability is handled separately in document_flow_review.md. -->

## Revision Loop

<!-- Record what the designer must revise, whether the issue stays in detailed design, or whether the task must return to planning. -->

{{>decision_approve_revise_escalate}}
