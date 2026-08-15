<!--
@dependency-start
contract issue
responsibility Tracks removal of persisted graph runtime as a prerequisite for dependency correctness.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
upstream design ../../documents/design/source-owned-dependency-validation.md source and runtime authority boundary
downstream implementation ../../tools/agent_tools/source_dependency_graph.py source-derived dependency projection
downstream implementation ../../tools/agent_tools/graph_client.py compatibility and explicit graph runtime boundary
downstream implementation ../../tools/agent_tools/check_dependency_headers.py canonical source validation
downstream implementation ../../tools/agent_tools/run_repo_dependency_review.sh source-owned repository review
downstream implementation ../../tools/ci/run_pr_dependency_source_gate.sh source-owned PR dependency gate
downstream implementation ../../tools/ci/check_agent_canon_pr.sh PR routing consumer
downstream implementation ../../tests/agent_tools/test_graph_client_source_projection.py source projection regression
downstream implementation ../../tests/tools/test_agent_canon_pr_dependency_source_gate.py no-runtime PR fixture
downstream implementation ../../tests/tools/test_agent_canon_pr_graph_gate_integration.py persisted orchestration boundary regression
@dependency-end
-->

# [Runtime簡素化] dependency検証を永続graph snapshotから分離する

issue_id: AC-20260815-decouple-graph-runtime
status: in_progress
source: user
severity: S2
problem: tracked sourceから決定論的に導出できるdependency correctnessが、Rust graph executable、persisted database、producer/profile identity、runtime evidence、snapshot freshnessへ依存している。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/723
done: dependency query/context、header/design/tool/search consumer、repository review、PR gateがpersisted graph stateなしでsource correctnessを検証し、graph runtimeは明示的analysis capabilityだけに限定される。
affected_surfaces: documents/design/, agents/canonical/CLI_ENTRYPOINTS.md, tools/agent_tools/, tools/ci/, tests/agent_tools/, tests/tools/
edit_scope: owner-bounded
required_action: tracked sourceを唯一のcorrectness authorityとするpure projectionを追加し、通常consumerとPR gateをsource-directへ切り替え、explicit graph build/status/non-dependency queryは維持する。
close_condition: focused no-runtime testsとrepository-owned required checksがpassし、Issueからbranch、PR、validationを追跡できる。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/723

## Current snapshot

- Base: `main@3a472410da41b8a2f46dcde2fdd580a75cd43e6a`.
- Active branch: `canon/decouple-graph-runtime-723`.
- Existing behavior: dependency consumers required a fresh persisted graph query or
  context response even when their facts were fully determined by tracked source.
- PR behavior: standalone AgentCanon PRs always built the Rust graph; selected parent
  PRs also entered build/status/query and incomplete-graph acceptance paths.
- Target behavior: source-owned correctness runs without Cargo, graph executable,
  `.agent-canon/knowledge-graph`, or snapshot freshness. Explicit graph analysis remains.

## Root cause

The repository treated a derived projection as the authority for its own source.
For tracked source state $S$, dependency projection $P(S)$, runtime state $R$, and
validation $V$, the implementation required a form of `V(P(S), R)` even though
`V(S)` was sufficient. This introduced false blockers from runtime availability,
staleness, profile identity, or persisted evidence that did not alter source
semantics.

## Target ownership

`documents/design/source-owned-dependency-validation.md` owns the authority split:

- tracked source and canonical parent-view bindings own dependency facts;
- malformed source and root escape fail closed;
- source query/context payloads are deterministic projections;
- persisted graph state is non-authoritative cache/enrichment;
- explicit graph build/status and non-dependency analysis retain Runtime ownership.

The existing dependency-manifest design continues to own DSL syntax, direction,
kind, bidirectional relation, cycle, and changed-scope semantics.

## Implementation scope

- add a pure `source_dependency_graph.py` projection;
- route full dependency query and tokenless path context through tracked source;
- validate changed-file headers from canonical source rather than graph status;
- let design claims, tool drift, and vector-search context consume source-derived
  typed facts through the compatibility boundary;
- make repository dependency review source-owned by default and reserve
  `--ensure-graph` for explicit preparation;
- replace PR graph build/status/query orchestration with
  `run_pr_dependency_source_gate.sh`;
- preserve trusted base/head changed-path selection without treating selection as
  authorization to build a graph;
- replace the former persisted incomplete-graph integration fixture with boundary
  regressions that forbid graph orchestration in the PR path;
- document the authority model and CLI routing.

## Non-goals

- removing the Rust graph implementation, SQLite schema, or visualizations;
- changing dependency manifest semantics;
- introducing a second source manifest or mirror database;
- weakening malformed/unresolved source findings;
- changing runtime archive/event semantics;
- renaming all graph-related compatibility symbols in the same PR.

## Validation plan

Focused tests:

```bash
python3 -m unittest tests.agent_tools.test_graph_client_source_projection
python3 -m unittest tests.tools.test_agent_canon_pr_dependency_source_gate
python3 -m unittest tests.tools.test_agent_canon_pr_graph_gate_integration
python3 -m unittest tests.agent_tools.test_check_dependency_headers
python3 -m unittest tests.agent_tools.test_check_design_doc_claims
python3 -m unittest tests.agent_tools.test_tool_drift
python3 -m unittest tests.agent_tools.test_vector_search
python3 -m unittest tests.agent_tools.test_dependency_manifest_tools
```

Static checks:

```bash
bash -n tools/agent_tools/run_repo_dependency_review.sh
bash -n tools/ci/run_pr_dependency_source_gate.sh
bash -n tools/ci/check_agent_canon_pr.sh
python3 tools/agent_tools/check_dependency_headers.py --root .
python3 tools/agent_tools/tool_drift.py --root .
```

Required GitHub checks:

- `static-gates`
- `dashboard`
- `issue-mirror-check`

## Acceptance criteria

- dependency query/context used by core consumers succeeds without graph executable
  or persisted graph state;
- explicit graph runtime operations remain explicit and fail when Runtime is absent;
- source parse, path containment, and target errors fail without cache fallback;
- repository dependency review does not invoke graph status/build by default;
- PR dependency gate does not invoke graph build/status/query or inspect SQLite;
- required and skipped PR routes retain trusted changed-path evidence;
- source-derived review artifacts remain deterministic;
- `main` drift is reconciled before review;
- Issue #723 contains branch, PR, validation, and remaining-risk evidence;
- status moves from `in progress` to `ready for review` when the branch is handoff-ready.

## Validation snapshot

Completed on the active branch before PR creation:

- source projection fixture: 5 focused cases passed;
- PR source gate fixture: 3 focused cases passed;
- shell syntax for the changed repository-review and PR-gate scripts passed;
- current `main` remained at the branch base SHA during the latest drift check.

Repository-wide and GitHub-hosted checks remain to be executed against the PR head.
