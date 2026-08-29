# Source-Owned Dependency Validation

<!--
@dependency-start
contract design
responsibility Defines the authority boundary between tracked dependency source and optional persisted graph analysis.
upstream design dependency-manifest-design.md dependency manifest DSL, relation, and review semantics
downstream design ../../agents/canonical/CLI_ENTRYPOINTS.md public source and persisted graph command routes
downstream implementation ../../tools/analysis/dependencies/source_dependency_graph.py derives source dependency facts
downstream implementation ../../tools/analysis/dependencies/graph_client.py exposes source dependency compatibility and explicit graph runtime commands
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/dependency_manifest.rs owns the explicit graph-analysis source snapshot parser
downstream implementation ../../tools/validation/semantic/dependencies/check_dependency_headers.py validates canonical source manifests
downstream implementation ../../tools/validation/semantic/documents/check_design_doc_claims.py consumes source-derived context
downstream implementation ../../tools/validation/semantic/tools/tool_drift.py consumes source-derived dependency facts
downstream implementation ../../tools/analysis/search/vector_search.py consumes source-derived dependency facts
downstream implementation ../../tools/analysis/dependencies/run_repo_dependency_review.sh owns source review and opt-in graph preparation
downstream implementation ../../tools/validation/ci/checks/run_pr_dependency_source_gate.sh owns PR source dependency completeness
downstream implementation ../../tools/validation/ci/checks/check_agent_canon_pr.sh selects trusted source review scope
downstream implementation ../../tools/validation/ci/receipts/pr_gate_receipt.py owns the executable source/skipped receipt schema
downstream implementation ../../tools/validation/ci/runners/run_all_checks.sh consumes one validated source/skipped receipt status
downstream implementation ../../tests/agent_tools/test_graph_client_source_projection.py verifies source projection invariants
downstream implementation ../../tests/agent_tools/test_check_dependency_headers.py verifies source header regression coverage
downstream implementation ../../tests/tools/test_agent_canon_pr_dependency_source_gate.py verifies the no-runtime PR route
downstream implementation ../../tests/tools/test_agent_canon_pr_graph_gate_integration.py prevents persisted graph orchestration from returning
downstream implementation ../../tests/tools/test_pr_gate_receipt.py verifies receipt schema and binding rejection
downstream implementation ../../tests/tools/test_pr_gate_receipt_round_trip.py verifies writer/parser/consumer execution
downstream implementation https://github.com/iwashita-nozomu/agent-canon/issues/723 records implementation and validation
@dependency-end
-->

This design specializes the dependency-manifest design for authority and runtime
ownership in `tools/analysis/dependencies/source_dependency_graph.py`. It replaces the
former assumption that dependency correctness must be read from a persisted graph in `tools/analysis/dependencies/graph_client.py`. The manifest DSL, relation meanings,
bidirectional review, cycle review, and changed-path selection remain owned by
`dependency-manifest-design.md`.

## Problem

The same tracked files were used twice:

1. a graph producer parsed them into persisted graph state;
2. validators and search consumers required that persisted state to be fresh
   before accepting facts that could be derived from the tracked files directly.

This coupled source correctness to Cargo or binary availability, database state,
producer identity, profile identity, runtime evidence, and snapshot freshness.
A document-only or small source change could therefore fail because an optional
projection was unavailable even when the source contract was locally decidable.

## Mathematical Model

Let:

- $S$ be the finite set of tracked source bytes and canonical projection
  bindings selected for one repository state;
- $P(S)$ be the deterministic dependency projection obtained by parsing the
  manifest block of each selected text file;
- $R$ be persisted graph runtime state, including database bytes, producer
  identity, profile identity, and runtime-evidence identity;
- $C(S,R)$ be an optional cached or enriched graph representation;
- $V(S)$ be a source validation predicate.

For every property owned by dependency headers, source paths, contract kinds,
relation closure, or source-backed design evidence, correctness is defined as

```text
V(S)
```

and not as

```text
V(C(S, R), R).
```

The optional graph may satisfy $C(S,R)=P(S)+E(S,R)$ for additional relations or
runtime evidence $E$, but it is not an authority for facts already determined by
$S$. Deleting, staling, or never creating $R$ therefore cannot change the result
of $V(S)$.

## Authority Invariants

### Source is the sole correctness authority

Tracked source plus canonical parent-view bindings owns dependency facts through `tools/analysis/dependencies/source_dependency_graph.py`. Dependency query/context
consumers used by validation, drift checks, and bounded search read those bytes directly through `tools/analysis/dependencies/graph_client.py`. A persisted snapshot is never consulted as a
fallback or tie-breaker.

### Parsing fails closed

The source projection rejects malformed dependency lines, unsupported direction
or kind values, incomplete markers, repository-root escape, unreadable canonical
source, and inconsistent projection bindings. Runtime unavailability cannot turn
one of these findings into success.

### Projection is deterministic

For a fixed $S$, normalized paths, edge order, node IDs, fact IDs, context
closure, source hashes, and projection fingerprints are deterministic. Ordering
is lexical after path normalization. Stable IDs are SHA-256 hashes of canonical
record tuples, not process-local counters or database row IDs.

### Canonical path containment

Every relative target is resolved from the canonical source file in
`tools/analysis/dependencies/source_dependency_graph.py`. The resolved path must remain
below the selected repository root. Parent views are mapped by

### Cache and runtime state are non-authoritative

Persisted graph state may accelerate explicit analysis or carry relations that
cannot be obtained from dependency headers alone. It may be stale, incomplete,
or unavailable without changing source validation. No source consumer silently
falls back from a parse error to cached facts.

## Consumer Routing

| Consumer | Authority | Persisted graph required |
| --- | --- | --- |
| changed-file dependency header check | canonical tracked source | no |
| design-document claim evidence closure | canonical tracked source | no |
| tool/convention drift links | canonical tracked source | no |
| vector-search dependency context | canonical tracked source | no |
| repository dependency review and TSV/DOT rendering | canonical tracked source | no |
| PR dependency completeness | trusted base/head path packet plus canonical tracked source | no |
| explicit `graph build` / `graph status` | persisted graph runtime | yes |
| non-dependency graph relations and token graph context | persisted graph runtime | yes |

`GraphClient` remains a compatibility boundary while callers migrate. Its
full-repository dependency query and tokenless path context are source-derived.
`build`, `status`, non-dependency relation queries, and token context remain
explicit persisted-graph operations. This split prevents broad caller churn
without making graph runtime state implicit.

## PR Gate Contract

The PR selector `tools/validation/ci/checks/agent_canon_pr_graph_selector.py` still owns trusted
comparison-base acquisition, changed-path packet construction, profile
validation in `tools/validation/ci/checks/agent_canon_pr_graph_selector.py`, and the decision to run full dependency review or header scan only.
Selection does not authorize a graph build in `tools/validation/ci/checks/check_agent_canon_pr.sh`.

When full review is selected, `run_pr_dependency_source_gate.sh` runs:

1. standalone tool-drift checks where applicable;
2. strict header scan and format validation;
3. source relation, cycle, and edit-scope review;
4. source-derived Markdown, TSV, and DOT projection generation.

When the selected change is outside declared dependency surfaces, the same gate
`tools/validation/ci/checks/run_pr_dependency_source_gate.sh` runs the trusted changed-path header
scan only. The receipt records `source` or
`skipped`; it does not record graph freshness as source correctness evidence.

`tools/validation/ci/receipts/pr_gate_receipt.py` is the sole receipt schema owner. Its status enum
contains exactly `source` and `skipped`; `strict_dependency` and `graph` are
compatibility fields that must carry the same one of those two values in `tools/validation/ci/receipts/pr_gate_receipt.py`. The
writer in `tools/validation/ci/checks/check_agent_canon_pr.sh` serializes and validates the
complete owner/root/PID/status/selector
record before the parent-boundary write. `tools/validation/ci/runners/run_all_checks.sh` invokes the same
module once for read-back and consumes only its `status=...` output in `tools/validation/ci/runners/run_all_checks.sh`. `prepared`
and `scoped` are retired persisted-graph states and fail closed at writer,
parser, and consumer boundaries.

The PR gate `tools/validation/ci/checks/check_agent_canon_pr.sh` must not invoke `graph build`, `graph status`, `graph query`, inspect
`graph.sqlite`, or evaluate persisted incomplete-graph diagnostics. Explicit
graph-analysis workflows may still do so outside this correctness path.

## Repository Review Contract

`tools/analysis/dependencies/run_repo_dependency_review.sh` is source-owned by default. Its normal route
uses source scan, format, relation/cycle, TSV/DOT, and edit-scope projections in `tools/analysis/dependencies/run_repo_dependency_review.sh`;
it does not require a graph executable, persisted database, or graph status in `tools/analysis/dependencies/run_repo_dependency_review.sh`. `--ensure-graph` is a separate opt-in operation that performs
persisted graph status/build preparation and exits before source review. It is
mutually exclusive with `--header-scan-only`, preventing one invocation from
presenting optional graph preparation as dependency correctness evidence.

## Compatibility Boundary

Existing output schemas and typed fact objects are retained where practical so
source consumers do not need a simultaneous rewrite. Compatibility applies only
to response shape. It does not preserve the previous authority of persisted
snapshots.

The names `GraphClient` and `tools/validation/ci/checks/agent_canon_pr_graph_selector.py` may remain during
this focused change because they also own explicit graph operations and trusted `tools/validation/ci/checks/agent_canon_pr_graph_selector.py` scope selection. Renaming them is a separate responsibility and must not be
combined with the authority correction.

## Non-Goals

- removing the Rust graph CLI, SQLite schema, or graph visualization;
- replacing dependency headers with another manifest or mirror database;
- making malformed source warnings non-blocking;
- changing dependency direction, kind, cycle, or bidirectional semantics;
- changing runtime-event archive semantics;
- adding an alternate fallback parser for persisted graph consumers;
- renaming every graph-related symbol in the same change.

## Evidence And Assumption Ledger

- `DSL` assumption: relation syntax and registered kinds are owned by
  `documents/design/dependency-manifest-design.md` and parsed by
  `tools/analysis/dependencies/source_dependency_graph.py`.
- `normalization` assumption: canonical path and surface binding normalization
  is owned by `tools/analysis/dependencies/source_dependency_graph.py` and
- Evidence sources: source projection, receipt lifecycle, and regression tests
  are `tools/analysis/dependencies/source_dependency_graph.py`,
  `tools/validation/ci/receipts/pr_gate_receipt.py`, and
  `tests/tools/test_pr_gate_receipt_round_trip.py`.
- Parent-doc alignment: relation and runtime authority remain governed by
  `documents/design/dependency-manifest-design.md`.

## Validation

The focused validation set in `tests/tools/test_pr_gate_receipt_round_trip.py` must demonstrate both positive and negative
properties:

- dependency query and path context succeed without an executable or
  `.agent-canon` graph state;
- explicit persisted graph commands still fail when their runtime is absent;
- malformed and escaping source fails without runtime fallback;
- PR source-gate required and skipped routes in `tests/tools/test_agent_canon_pr_dependency_source_gate.py` work without graph state;
- the production PR shell contains no persisted dependency graph build/status/
  query orchestration;
- repository dependency review in `tools/analysis/dependencies/run_repo_dependency_review.sh` remains stable across repeated source-only runs;
- full repository static gates and required GitHub checks pass.

## Migration Result

After this change, graph runtime is an explicit analysis capability rather than
a prerequisite for dependency correctness. The architecture preserves the graph
feature while restoring the dependency direction:

```text
tracked source -> optional graph projection
```

and forbids the inverse authority relation:

```text
persisted graph runtime -/-> tracked-source correctness
```
