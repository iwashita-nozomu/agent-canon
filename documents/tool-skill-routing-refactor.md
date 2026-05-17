<!--
@dependency-start
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

## Naming Rule

- Public tool names stay short: one or two words before `.py` when possible.
- Public skill names describe the user action, not the implementation pattern.
- Long candidate names are compatibility aliases, not new files.
- Repeated routing decisions go through `route.py --area <area>`.
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
