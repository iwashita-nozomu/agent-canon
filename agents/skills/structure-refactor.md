# structure-refactor
<!--
@dependency-start
contract skill
responsibility Repairs and reviews repository structure with deterministic drift fast paths and reachability-scoped evidence.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
upstream design ../../documents/design/responsibility-rationale.md drift repair, review scope, and prose-diagnostic rationale
upstream design ../../documents/rule/README.md document rule canon
upstream design ../../documents/design/README.md design canon reader route
upstream design refactor-loop.md behavior-preserving refactor loop
upstream design structure-planning.md unresolved responsibility and reader-route decisions
upstream design ../../documents/conventions/common/05_docs.md document responsibility and reading-activation boundary
upstream design dependency-analysis.md dependency and change-impact packets
upstream design prose-reasoning-graph.md optional graph-backed prose diagnostics
downstream implementation ../../.codex/personal/skills/structure-refactor/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/validation/semantic/dependencies/check_dependency_headers.py validates this adapter dependency header
@dependency-end
-->

## Purpose

Use `structure-refactor` for repository path/ownership/source-view changes. Separate deterministic state reconciliation from genuinely ambiguous structure design.

## Deterministic drift fast path

When all of these are known—canonical owner, expected state, canonical repair operation, and readback—repair directly:

1. detect the drift;
2. run the canonical repair/sync operation;
3. read back the expected owner/path/view state;
4. resume the original task.

Examples include a stale generated/root view or a known missing projection with an existing sync owner. Do not require a full structure-repair packet or a negative receipt for this path.

When ownership/source is ambiguous, sources are mixed, responsibilities overlap,
multiple target layouts are plausible, or a repair would create a second source
of truth, read [structure-planning](structure-planning.md#minimal-structure-decision) for that
unresolved boundary; do not turn a known repair into a full planning exercise.

## Review scope

Default review scope is the changed subtree plus affected direct consumers/reverse edges and the owner boundary. Expand to recursive full-tree inventory only when root ownership changes, a broad move crosses scopes, or concrete evidence indicates overlap, an uncovered path, or broken reverse edges.

Unrelated stale findings do not automatically become acceptance blockers for a bounded refactor; route durable residuals to their owner.

## Overloaded documents

When a file couples independently needed responsibilities and causes unrelated
reading, apply [Document Split Decision](../../documents/conventions/common/05_docs.md#document-split-decision).
Locate the exact mixed sections and incoming reader routes, then move details to
their existing owner and remove the old copy. Update affected callers with a
condition and direct section link; do not replace one large read with mandatory
reads of every split file. Review representative applicable and inapplicable
routes, including a mid-task change of responsibility, without a full-tree audit.

## README and prose diagnostics

Routine directory README path/link/ownership-statement updates use direct review plus the normal targeted docs checks. Run `prose_reasoning_graph` only when a substantive reader-flow rewrite leaves a specific ordering/bridge hypothesis unresolved. Do not run it once per changed README, do not require an output directory per file, and do not treat graph non-execution as failure.

## Visualization

Architecture/responsibility diagrams are selected only when they materially clarify the changed ownership/dependency relation. Delegate selected diagram rendering/coverage/readback to `code-visualization`; no filtered map becomes a second canon.

## Completion

Read back the repaired/moved paths, affected ownership/source boundary, reverse consumers relevant to the change, and the selected validation result. Full-tree and prose-graph evidence appear only when their concrete activation condition was met.
