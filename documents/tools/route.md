<!--
@dependency-start
contract reference
responsibility Documents route tool usage.
upstream implementation ../../tools/agent/orchestration/route.py selects short tool and skill routes
upstream implementation ../../tools/validation/semantic/tools/visualization_contract.py owns the exact typed visualization ToolCall contract
upstream design ../../agents/skills/code-visualization.md owns sole-public-owner and coverage/readback policy
upstream design ../design/tool-skill-routing-refactor.md defines short naming policy
upstream design ../../agents/skills/structure-refactor.md defines repo-refactor and personal runtime routing boundary
downstream implementation ../../tests/agent_tools/test_route.py validates route behavior
@dependency-end
-->

# route.py

`route.py` is the short AgentCanon entrypoint for task routing decisions that
would otherwise become many long one-off tools. It maps long proposal names
such as `profile_surface_resolver.py` or `$runtime-capability-routing` to one
small command surface:

```bash
python3 tools/agent/orchestration/route.py --area checks --changed README.md
python3 tools/agent/orchestration/route.py --name profile_surface_resolver.py
python3 tools/agent/orchestration/route.py --name repo_refactor_skill.py
python3 tools/agent/orchestration/route.py --prompt "fix skill routing with multi-agent evidence" --format json
python3 tools/agent/orchestration/route.py --list --format markdown
```

Text output is machine-readable and compact:

```text
ROUTE=task-routing
AREA=checks
TOOL=route.py
SKILL=task-routing
NEXT_ACTION=run_selected_checks
COMMANDS=make check-matrix
```

Prompt skill routing is owned by the Python fast path
`route.py --prompt`. It returns the full selected `SKILLS` list plus
`ACTIVE_SKILLS` for the current stage and `DEFERRED_SKILLS` for dynamic wave
triggers. It also returns `RELATED_SKILL_CANDIDATES` and `RELATED_SKILLS` from
the public skill catalog; use those as next-stage candidates after matching
evidence appears, not as extra initial reads.

Prompt routing keeps schema `agent_canon.route.skill_route.v1` and adds exactly
three singular visualization fields:

- `visualization_owner_skill`: `code-visualization` or null;
- `visualization_tool_call`: one canonical `ToolCall` or null;
- `visualization_rejection`: `missing_owner`, `invalid_tool_call`,
  `schema_mismatch`, `prose_only`, or null.

There is no parallel route ToolCall type and no plural ToolCall collection.
`visualization_tool_call`, when present, is exactly the canonical owner call:

- `schema = agent_canon.visualization_tool_call.v1`;
- `tool_id = agent_canon.visualization.coverage`;
- `argument_schema = agent_canon.visualization.arguments.coverage.v1`;
- `arguments` contains every field required by the canonical typed contract.

The route activates visualization ownership only from an explicit
`code-visualization` skill ID, explicit visualization capability ID, exact
canonical ToolID, or valid schema-bearing ToolCall. Explicit renderer-skill
aliases and adapter ToolIDs normalize to `code-visualization`; they never
become public visualization owners. Visualization prose without one of those
explicit identities does not route by keyword and returns `prose_only`.
Malformed calls reject deterministically: absent owner is `missing_owner`, an
unknown ToolID or field/type/format defect is `invalid_tool_call`, and a
ToolCall or argument-schema mismatch is `schema_mismatch`.

The six accepted ToolID/schema pairs are:

| Role | ToolID | Argument schema |
| ---- | ------ | --------------- |
| Owner | `agent_canon.visualization.coverage` | `agent_canon.visualization.arguments.coverage.v1` |
| Dependency adapter | `agent_canon.visualization.adapter.dependency_manifest` | `agent_canon.visualization.arguments.dependency_manifest.v1` |
| Algorithm adapter | `agent_canon.visualization.adapter.algorithm_flowchart` | `agent_canon.visualization.arguments.algorithm_flowchart.v1` |
| Document adapter | `agent_canon.visualization.adapter.document_mermaid` | `agent_canon.visualization.arguments.document_mermaid.v1` |
| Repository adapter | `agent_canon.visualization.adapter.repository_graph` | `agent_canon.visualization.arguments.repository_graph.v1` |
| Knowledge adapter | `agent_canon.visualization.adapter.knowledge_graph` | `agent_canon.visualization.arguments.knowledge_graph.v1` |

An executable renderer path is a command, never a ToolID. Runtime ordering is
owner ToolCall first and one task-matching adapter ToolCall second. The adapter
owns syntax/layout only and remains downstream of the canonical owner.

## Explicit capability routing

Capability mode is the explicit, fail-closed route for a single catalog
capability. The success command is:

```bash
python3 tools/agent/orchestration/route.py --capability oop_type_design --format json
```

An unknown capability is also explicit and fail-closed:

```bash
python3 tools/agent/orchestration/route.py --capability unknown_capability --format json
```

This command returns exit status 2. Capability mode accepts one exact catalog
ID and performs no natural-language inference. It rejects conflicts with
prompt, request, purpose, task, prompt-file, request-file, query-file,
prompt-stdin, request-stdin, query-stdin, name, area, list, or changed input.

`--root` accepts a repository root and defaults to the current repository
catalog. `--mode` accepts `routing-only` or `repo-changing`; `--format` accepts
`text`, `json`, or `markdown`; and `--risk focused` is the only supported risk
input in capability mode. The default root is used when `--root` is omitted.

JSON uses schema `agent_canon.route.capability_route.v1` and preserves this key
order: `schema`, `route`, `mode`, `status`, `error_code`, `capability_ids`,
`matches`, `skills`, `active_skills`, `deferred_skills`,
`related_skill_candidates`, `related_skills`, `reasons`,
`visualization_owner_skill`, `visualization_tool_call`,
`visualization_rejection`.

`status=pass` with exit 0 is success. `status=fail` with a stable `error_code`,
empty non-applicable fields, and exit 2 is fail-closed. Related-skill
candidates are evidence for a later owner route, not automatic activation.
Text and Markdown use the same fields and ordering as the capability schema.
An explicit visualization capability emits only the same canonical owner
ToolCall. Renderer selection and adapter emission remain downstream work.

## Visualization completion boundary

Routing does not authorize omission. `code-visualization` constructs the
immutable literal scope plus owner/dependency closure before renderer
selection. Renderer family, clustering, zoom, and filtering are view-only and
cannot remove serialized identities. After the downstream adapter runs, the
owning formatter is mandatory, followed by readback from the final formatted
artifact. Completion carries exact eight-kind (`identity`, `edge`, `field`,
`phase`, `branch`, `module`, `evidence`, `time`) source, rendered, and readback
count maps, the deterministic coverage digest, and final-token evidence. If a
renderer cannot retain complete coverage, return the typed renderer-capacity
blocker instead of pruning or emitting a partial fallback.

Japanese or English prompts about unnecessary numerical tests, heavy tests,
test brittleness, tolerance-based tests, or test-design gaps route to
`$test-design` so the numerical admission gate is applied before workers add
tests.

Repository-refactor and structure-review aliases such as
`repo_refactor_skill.py`, `repo/refactor`, and `structure-review`, plus personal
Codex runtime boundary prompts involving `~/.codex`, route to the `structure`
area and `$structure-refactor`. Do not add a parallel public repo-refactor or
structure-review skill unless `route.py --name <candidate>` returns
`STATUS=unknown` after the structure route has been considered.

Routing miss, selection gap, ToolCall, SkillCall, or coverage prompts are
log-analysis tasks. `route.py --prompt ... --format json` should include
`$agent-log-analysis` for those requests so the agent reads compact runtime
dashboard evidence before editing prompt, hook, skill, or workflow surfaces.

Use this tool when a task needs a short answer to "which profile, check,
runtime, skill, or closeout path applies?" Use the specialized checker or
runner only after `route.py` points to it.
