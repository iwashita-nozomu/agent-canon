# API Surface Traversal Before Negative Conclusions

<!--
@dependency-start
contract issue
responsibility Records the workflow defect where an agent declared an API path impossible before following nested public configuration surfaces.
upstream design ../README.md defines durable AgentCanon operational issue conventions.
upstream design ../../agents/canonical/CODEX_WORKFLOW.md defines the executable Codex workflow.
upstream design ../../agents/workflows/implementation-waterfall-workflow.md requires installed-library and existing-API sweeps before implementation.
upstream design ../../agents/skills/codex-task-workflow.md requires dependency surface review before implementation.
upstream design ../../documents/dependency-manifest-design.md defines dependency-expanded search evidence.
downstream design ../../agents/workflows/implementation-waterfall-workflow.md should require public API traversal evidence before negative capability claims.
downstream design ../../agents/skills/codex-task-workflow.md should route API-surface misses into workflow gates.
downstream implementation ../../tools/agent_tools/route.py may expose an API-surface search route.
downstream implementation ../../tools/catalog.yaml should catalog any resulting route or checker.
downstream implementation ../../tests/agent_tools/test_route.py should cover the resulting route behavior.
@dependency-end
-->

issue_id: AC-20260518-api-surface-negative-conclusion
status: resolved
source: user
severity: S2
evidence: reports/dependency-review/api-surface-negative-conclusion-20260518/search_hits.txt
affected_surfaces: agents/canonical/CODEX_WORKFLOW.md, agents/workflows/implementation-waterfall-workflow.md, agents/skills/codex-task-workflow.md, agents/workflows/hypothesis-validation-workflow.md, documents/tools/README.md, tools/agent_tools/route.py, tools/catalog.yaml, tests/agent_tools/test_route.py, issues/open/AC-20260517-search-discoverability-routing.md, issues/open/AC-20260517-responsibility-scope-management.md
edit_scope: reports/dependency-review/api-surface-negative-conclusion-20260518/dependency_edit_scope.txt
required_action: Add an API-surface traversal gate that prevents negative capability claims until public exports, config fields, and nested public config factories have been inspected and cited.
close_condition: Workflow or tooling requires any API "cannot do" conclusion to cite the exact inspected public path, and a focused route or eval test catches the PDIPM-style nested-config miss.
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/97
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/153
resolved_at: 2026-05-31

## Finding

On 2026-05-18, the agent concluded that PDIPM preconditioner selection could
not be configured from the available public API and started reasoning toward a
library change. The user corrected the conclusion by pointing to the already
available public factory surface:

```text
pdipm.InitializeConfig
  -> kkt.InitializeConfig
    -> h_preconditioner_initialize / s_preconditioner_initialize
      -> _preconditioners.InitializeConfig.identity()
      -> _preconditioners.InitializeConfig.external()
      -> _preconditioners.InitializeConfig.dense_eigh(...)
      -> _preconditioners.InitializeConfig.lobpcg(...)
```

The failure was not that the library lacked a selector. The failure was the
search path: the agent stopped at the outer PDIPM config boundary, treated the
missing direct field as a missing capability, and did not traverse the nested
public config type that the outer API explicitly asks the caller to provide.

## Faulty Search Path

The mistaken conclusion came from this path:

1. The agent inspected the notebook and identified that it needed to configure
   the PDIPM H and S preconditioners.
1. It inspected or inferred the outer `pdipm.InitializeConfig` and
   `pdipm.SolveConfig` shape.
1. It observed that the outer config receives KKT initialize and solve configs,
   rather than a top-level field named like `preconditioner`.
1. It incorrectly treated "the desired choice is not a top-level PDIPM field"
   as evidence that selection was unavailable.
1. It shifted toward project helper or upstream library changes before
   completing the public API traversal.
1. It then overcorrected from the user's "do not touch KKT internals" feedback
   and confused a user-facing conceptual boundary with a prohibition on reading
   nested public config factories.
1. It failed to follow the type chain from `pdipm.InitializeConfig` to
   `kkt.InitializeConfig` to `_preconditioners.InitializeConfig`.
1. It therefore missed that `_preconditioners.InitializeConfig` already exposes
   `identity`, `external`, `dense_eigh`, and `lobpcg` factory methods.

## What Was Missed

The missing search move was simple and mechanical: when an outer public config
contains a typed nested public config field, the agent must inspect the nested
public config's documented or exported factory surface before claiming the
capability does not exist.

The correct distinction is:

- Do not patch or redesign the dependency unless the task explicitly assigns
  upstream library work.
- Do inspect the dependency's public export and public config surfaces needed
  to call it correctly.
- Do not read deep implementation internals as the first move when the public
  config surface is enough.
- Do not declare "cannot configure" until the exact missing public field,
  factory, or constructor path is named.

For this case, the API surface was enough. The correct caller-side change was
to build the KKT initialize/solve configs with the desired
`_preconditioners.InitializeConfig.*` and `SolveConfig.*` factories.

## Required Fix

AgentCanon should add a negative-capability discipline for dependency APIs.
Before an agent says an API cannot do something, the workflow should require a
short evidence trail:

1. Public import surface checked, including `__all__` or stable exports when
   available.
1. Outer config or function signature checked.
1. Nested public config fields followed at least to their public factory or
   constructor surface.
1. Conceptual user-facing boundary separated from implementation boundary.
1. Exact missing public selector named if the conclusion remains negative.
1. Scope decision recorded before proposing project helper code or upstream
   library edits.

This should be placed where implementation and hypothesis-validation workflows
currently require installed-library and existing-API sweeps, and should also be
discoverable through tool or route guidance for API search.

## Related Issues

- `AC-20260517-search-discoverability-routing` covers the broader problem that
  search routes are not obvious enough.
- `AC-20260517-responsibility-scope-management` covers the related boundary
  defect where an agent moved toward changing an external library before
  confirming the caller-side public API path.

This issue is narrower: it records the precise search-path error that produced
the false "cannot do it" conclusion.

## Evidence

Durable surface search and dependency expansion were run with:

```bash
rg -l "negative conclusion|cannot do|API surface|public API|InitializeConfig|preconditioner|library boundary|search path|dependency API|nested config|__all__|できない|ライブラリ" \
  vendor/agent-canon/issues vendor/agent-canon/memory vendor/agent-canon/notes/failures vendor/agent-canon/documents vendor/agent-canon/agents \
  > reports/dependency-review/api-surface-negative-conclusion-20260518/search_hits.txt
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review/api-surface-negative-conclusion-20260518 \
  --search-hits-file reports/dependency-review/api-surface-negative-conclusion-20260518/search_hits.txt
```

The review produced `REPO_DEPENDENCY_REVIEW=pass` and wrote the expanded edit
scope to
`reports/dependency-review/api-surface-negative-conclusion-20260518/dependency_edit_scope.txt`.

## Resolution

PR #153 added the API-surface traversal policy, first-party library guard, task
authority schema guard, role write policy guard, issue eval coverage, and
validation-gate parity needed to prevent the recorded negative-capability miss.
GitHub issue #97 was closed after PR #153 merged.
