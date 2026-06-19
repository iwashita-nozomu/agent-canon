# Search Tool Discoverability Needs Routing

<!--
@dependency-start
contract issue
responsibility Records the operational finding that repo search tooling is difficult to discover without prior tool-name knowledge.
upstream design ../README.md defines AgentCanon operational issue conventions.
upstream design ../../documents/dependency-manifest-design.md defines search-to-edit-scope evidence.
upstream design ../../tools/README.md documents shared tool entrypoints.
upstream implementation ../../tools/agent_tools/vector_search.py provides text-surface vector search.
downstream design ../../documents/tools/README.md should document user-facing tool discovery routes.
downstream implementation ../../tools/agent_tools/route.py should expose a search route.
downstream implementation ../../tools/agent_tools/search.py should expose purpose-based coordinated search.
downstream implementation ../../tools/agent_tools/search_index.py should build local semantic search cards.
downstream implementation ../../tools/catalog.yaml should catalog the search route and related tools.
downstream implementation ../../tests/agent_tools/test_route.py should verify the route output.
downstream implementation ../../tests/agent_tools/test_search.py should verify coordinated provider output.
downstream implementation ../../tests/agent_tools/test_search_index.py should verify search index generation.
downstream implementation ../../tests/agent_tools/test_vector_search.py should verify search index behavior.
@dependency-end
-->

issue_id: AC-20260517-search-discoverability-routing
status: resolved
source: user
severity: S2
evidence: tools/agent_tools/search.py
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/257
affected_surfaces: tools/agent_tools/route.py, tools/agent_tools/search.py, tools/agent_tools/search_index.py, tools/agent_tools/vector_search.py, tools/README.md, documents/tools/README.md, documents/search-coordination.md, tools/catalog.yaml, tests/agent_tools/test_route.py, tests/agent_tools/test_search.py, tests/agent_tools/test_search_index.py, tests/agent_tools/test_vector_search.py
edit_scope: reports/agents/20260518-010710-add-coordinated-text-llm-vector-tool-cod/
required_action: Add an obvious AgentCanon route and documentation path for searching tools, documents, agents, and dependency-expanded edit scopes without knowing `vector_search.py` by name.
close_condition: `route.py --area search`, tool docs, catalog entries, and tests expose vector search plus dependency-expanded search usage, and validation passes.
resolved_by: reports/agents/20260518-010710-add-coordinated-text-llm-vector-tool-cod/
resolved_at: 2026-05-18

## Finding

AgentCanon has `tools/agent_tools/vector_search.py`, but an agent currently has
to know the file name or run broad `rg` searches to discover it. That makes
tool, document, and agent-surface search feel like hidden knowledge instead of
an advertised workflow entrypoint.

The missing route is especially visible when the desired behavior is not only
plain text search but a two-step flow:

- search tool, document, and agent surfaces with `vector_search.py`
- expand hits through dependency manifests with
  `check_dependency_graph.sh --edit-scope` or
  `run_repo_dependency_review.sh --search-hits-file`

## Required Fix

- Add a search area to `tools/agent_tools/route.py`, for example
  `python3 tools/agent_tools/route.py --area search`.
- Document the command in `tools/README.md` and `documents/tools/README.md`.
- Include examples for searching `tools`, `documents`, `agents`, `.agents`,
  and `vendor/agent-canon` roots.
- Show how to persist search hits and expand edit scope through dependency
  manifests.
- Add focused tests so the route and docs do not regress silently.

## Evidence

Durable-surface search was run with:

```bash
rg -l "vector_search|search discoverability|dependency-expanded search|search_hits|edit-scope|route.py --area search|tool search" \
  issues memory notes/failures documents agents tools tests \
  > /workspace/reports/dependency-review/search-discoverability-20260517/search_hits.txt
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir /workspace/reports/dependency-review/search-discoverability-20260517 \
  --search-hits-file /workspace/reports/dependency-review/search-discoverability-20260517/search_hits.txt
```

The review produced `REPO_DEPENDENCY_REVIEW=pass` and
`DEPENDENCY_EDIT_SCOPE_PATHS=1690`. The directly actionable surfaces are
`tools/agent_tools/route.py`, `tools/agent_tools/vector_search.py`,
`tools/README.md`, `documents/tools/README.md`, `tools/catalog.yaml`,
`tests/agent_tools/test_route.py`, and
`tests/agent_tools/test_vector_search.py`.

## Resolution

AgentCanon now has `tools/agent_tools/search.py` as the purpose-based
coordinator for text, LLM semantic cards, vector search, tool catalog,
dependency-header edges, and Python code facts. `tools/agent_tools/search_index.py`
builds the ignored repo-local `.agent-canon/search-index/` semantic-card index.

`tools/agent_tools/route.py --area search` exposes the search entrypoint without
requiring agents to know `vector_search.py` by name. Tool docs and
`documents/search-coordination.md` describe when to use exact `rg`, coordinated
search, and index rebuilds. Focused route/search/index tests cover the exposed
command surface.
