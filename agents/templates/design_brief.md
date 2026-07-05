# Detailed Design Brief
<!--
@dependency-start
contract template
responsibility Documents Detailed Design Brief for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md artifact placement contract
upstream design ../../documents/dependency-manifest-design.md dependency evidence contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Reader Map

This template owns the implementation-facing detailed design packet. Fill the
goal, abstract design frame, evidence ledger, reuse survey, requirement packet,
implementation source packet, side-effect map, reader path, clause mapping,
file-by-file design, trace, naming plan, validation, rollback, and risks before
handoff. After this design is written, send this exact artifact to detailed
design review before any implementation or worker handoff. The implementation
worker uses this as an approved source packet only after `design_review.md`
approves the same artifact; unresolved responsibility, naming, validation, or
API-shape gaps belong back in design review rather than local implementation
judgment.

## Design Review Handoff

<!-- Record the design artifact path, current revision or section set, required design_review.md path, document_flow_review.md path if applicable, and the fact that implementation/handoff is blocked until the latest review decision is approve. -->

- Design artifact under review:
- Required review artifact:
- Review state:
- Implementation / handoff blocker:

## Goals

<!-- Describe the design goal in implementation-facing terms. The goal is to produce the design document that implementation will follow. -->

## Abstract Design Frame

<!-- Before selecting files or patches, describe the abstract responsibility model, concept graph, non-goals, future extension layers, evaluation axes, and relationship to existing canonical surfaces. Implementation slices must be derived from this frame, not selected only from the nearest file, helper, or finding. -->

- Responsibility model:
- Concept or layer model:
- Non-goals:
- Future extension layers:
- Evaluation axes:
- Canonical-surface relationships:

## Evidence And Assumption Ledger

<!-- Tie design claims to current code, dependency headers, existing docs, and parent documents. Record first-use DSL terms, problem standard forms, normalization rules, and governing parent-doc differences before file-by-file implementation design. For design-doc claim checking, cite code paths, tool paths, dependency-header evidence, or parent documents with stable paths. -->

- Evidence sources:
- Assumptions:
- Parent-doc alignment:
- Refactor handoff:

## Existing Code And Docs To Reuse

<!-- List the local modules, helpers, tests, docs, and naming patterns that must be reused or mirrored. -->

## Upstream Requirement Packet

<!-- List the exact document paths the designer read before writing this design: user_request_contract.md, schedule.md, intent_brief.md, waterfall workflow docs, and other governing docs. Do not rely on chat-only context. -->

## Installed Libraries And Existing Implementation Survey

<!-- List the dependency surfaces, installed libraries, existing helpers/modules/tests/docs you inspected before deciding the implementation shape. Record whether each candidate is reused, extended, replaced, or rejected, and why existing libraries or existing implementation are insufficient when you add something new. -->

## Implementation Source Packet

<!-- List every artifact the worker must read before editing: user_request_contract.md, schedule.md, this design brief, design_review.md, document_flow_review.md when active, test_plan.md, repo docs, dependency surfaces, code paths, tests, and external references if any. Mark each item required or not used. -->

## Design Side-Effect Map

<!-- For each major design decision, list downstream implementation, document, workflow, prompt/config, validation, dependency-manifest, and user-facing surfaces it affects. Connect each item to the Abstract Design Frame responsibility, request clause ID, reuse precedent, owner stage, review gate, and validation or test-plan item. -->

## Canonical Tree-Head Plan

<!-- Name the only canonical design-document paths and implementation paths that may remain tracked after this task. List every non-canonical draft, snapshot, backup file, copied implementation, mirrored directory, or parallel design doc that must be deleted or must not be created. State that the durable product state is the current tree head only. -->

## Patterns And Writing Style To Mirror

<!-- Record the existing coding and documentation style that implementation must follow. -->

## Reader Path And Term Introduction

<!-- Record the intended top-down reading order, which terms must be defined before use, and where the reader must reach the key decision points. -->

## Request Clause Mapping

<!-- Record which user-request clause IDs this design satisfies and which clause IDs remain outside this pass. -->

## File-By-File Design

<!-- Describe the planned file edits, boundaries, interfaces, and expected diff shape in detail. -->

## Design-To-Implementation Trace

<!-- For each planned edit, map design section, user-request clause ID, source/reuse document or code path, test-plan item, and expected validation evidence. The worker must cite this mapping before editing. -->

## Identifier And Naming Plan

<!-- List every new or renamed variable, function, class, file, CLI flag, config key, and public API surface. For each item, record the chosen name, local precedent, rejected alternatives if relevant, and whether the name is implementation-blocking. -->

## Validation And Rollback Plan

<!-- Describe how the design will be validated and what rollback or alternate route path exists. -->

## Risks

<!-- Capture tradeoffs, known risks, and alternate route options. -->
