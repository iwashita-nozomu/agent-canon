<!--
@dependency-start
contract reference
responsibility Documents tool and skill routing refactor policy.
upstream design README.md AgentCanon documentation index
downstream implementation ../tools/agent_tools/route.py selects short tool and skill routes
downstream design ../agents/skills/task-routing.md public skill for route decisions
downstream design tools/route.md route tool reader documentation
@dependency-end
-->

# Tool And Skill Routing Refactor

The 500 tool-skillization candidates should not become 500 new public tools or
dozens of long `$skill-name` entries. Long names such as
`profile_surface_resolver.py`, `workflow_step_router.py`, and
`$runtime-capability-routing` describe internal mechanisms, not good operator
interfaces.

This policy was derived from the parent-repo audit artifact
`template_agent_canon_tool_skillization_500_candidates.md`; that source is run
evidence, not an AgentCanon product dependency.

## Reader Map

- Owns the policy for keeping public tool and skill routing short while
  retaining compatibility aliases.
- Main path: Naming Rule, Canonical Short Surface, Refactor Boundary, and
  Ownership Layout.
- Read this before renaming tools, adding route helpers, or exposing new public
  skill names.
- Boundary: it is routing/refactor policy, not a full skill catalog or runtime
  workflow definition.

## Naming Rule

- Public tool names stay short: one or two words before `.py` when possible.
- Public skill names describe the user action, not the implementation pattern.
- Long candidate names are compatibility aliases, not new files.
- Repeated routing decisions go through `route.py --area <area>`.
- Prompt-derived public skill selection goes through
  `python3 tools/agent_tools/route.py --prompt <text>` so candidate evidence,
  current-wave `ACTIVE_SKILLS`, and later-wave `DEFERRED_SKILLS` are produced
  by the fast deterministic harness. Routing rules and stage policy live in
  `agents/skills/catalog.yaml` under `skill_families[].routing`.
- Host-provided system skills such as `$openai-docs`, `$skill-creator`,
  `$skill-installer`, `$imagegen`, and `$plugin-creator` stay outside the
  AgentCanon public catalog. AgentCanon routes to those names and keeps local
  owner-surface contracts.
- Japanese or English prompts about unnecessary numerical tests, heavy tests,
  brittle tests, tolerance-based tests, or test-design gaps route to
  `$test-design`; they are not handled by ad hoc worker judgment.
- The public skill for this family is `$task-routing`.

## Canonical Short Surface

| Area | Short Command | Skill | Replaces Long Candidates |
| ---- | ------------- | ----- | ------------------------ |
| `surface` | `route.py --area surface` | `$task-routing` | `profile_surface_resolver.py`, `$runtime-surface-minimize` |
| `profile` | `route.py --area profile` | `$task-routing` | `optional_profile_matrix.py`, `$profile-selection` |
| `checks` | `route.py --area checks` | `$task-routing` | `workflow_step_router.py`, `$workflow-lite-routing`, `validation_min_set.py` |
| `env` | `route.py --area env` | `$task-routing` | `environment_profile_detect.py`, `$environment-profile` |
| `read` | `route.py --area read` | `$task-routing` | `read_order_compactor.py`, `$onboarding-lite` |
| `remote` | `route.py --area remote` | `$task-routing` | `remote_policy_router.py`, `$remote-policy-cleanup` |
| `canon` | `route.py --area canon` | `$task-routing` | `submodule_state_router.py`, `$submodule-routing` |
| `mcp` | `route.py --area mcp` | `$task-routing` | `mcp_optional_preflight.py`, `$mcp-profile` |
| `goal` | `route.py --area goal` | `$task-routing` | `goal_contract_router.py`, `$goal-lite` |
| `runtime` | `route.py --area runtime` | `$task-routing` | `runtime_capability_probe.py`, `$runtime-capability-routing` |
| `tokens` | `route.py --area tokens` | `$task-routing` | `token_budget_gate.py`, `$token-lite` |
| `skills` | `route.py --area skills` | `$task-routing` | `skill_workflow_mapper.py`, `$routing-single-source` |
| `agents` | `route.py --area agents` | `$task-routing` | `multi_agent_mode_selector.py`, `$agent-mode` |
| `closeout` | `route.py --area closeout` | `$task-routing` | `closeout_profile_gate.py`, `$closeout-lite` |
| `deps` | `route.py --area deps` | `$task-routing` | `dependency_manifest_scope.py`, `$dependency-manifest-lite` |
| `conventions` | `route.py --area conventions` | `$task-routing` | `convention_subcheck_router.py`, `$convention-gate-lite` |
| `docs` | `route.py --area docs` | `$task-routing` | `canon_doc_router.py`, `$doc-canon-flex` |
| `logs` | `route.py --area logs` | `$task-routing` | `log_retention_decider.py`, `$log-retention-lite` |
| `tools` | `route.py --area tools` | `$task-routing` | `tool_catalog_summarizer.py`, `$tool-selection` |

## Refactor Boundary

This pass adds the routing surface and alias map. It does not delete existing
specialized checkers. Existing tools remain canonical when they perform real
validation or repair. `route.py` only decides which specialized path to use and
prints compact `ROUTE`, `AREA`, `NEXT_ACTION`, `COMMANDS`, and `EVIDENCE`
tokens.

## Ownership Layout

- Deterministic prompt-to-skill routing lives in
  `tools/agent_tools/route.py --prompt` and reads
  `agents/skills/catalog.yaml`.
- `agents/skills/catalog.yaml` remains the skill registry for id, purpose,
  doc/shim paths, prompt trigger groups, and stage policy. Routing metadata
  changes include the runtime-alignment schema check and route.py tests in the
  same diff.
- Codex CLI capabilities are not mirrored into AgentCanon routing docs. Runtime
  capability belongs in a probe or route output, and skill routing should name
  only the current task's core AgentCanon functions.

For broad user prompts, `python3 tools/agent_tools/route.py --prompt "<request>"`
prints `ROUTE=skill-selection`, `MODE`, `SKILLS`, `ACTIVE_SKILLS`,
`DEFERRED_SKILLS`, `MATCHED_SKILLS`, `REASONS`, and `EVIDENCE`. The returned
`SKILLS` is the full selected set, while `ACTIVE_SKILLS` is the current-stage
skill declaration and `DEFERRED_SKILLS` is the dynamic wave trigger set.
