<!--
@dependency-start
contract reference
responsibility Documents route tool usage.
upstream implementation ../../tools/agent_tools/route.py selects short tool and skill routes
upstream design ../tool-skill-routing-refactor.md defines short naming policy
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
python3 tools/agent_tools/route.py --area checks --changed README.md
python3 tools/agent_tools/route.py --name profile_surface_resolver.py
python3 tools/agent_tools/route.py --name repo_refactor_skill.py
python3 tools/agent_tools/route.py --prompt "fix skill routing with multi-agent evidence" --format json
python3 tools/agent_tools/route.py --list --format markdown
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

## Explicit capability routing

Capability mode is the explicit, fail-closed route for a single catalog
capability. The success command is:

```bash
python3 tools/agent_tools/route.py --capability oop_type_design --format json
```

An unknown capability is also explicit and fail-closed:

```bash
python3 tools/agent_tools/route.py --capability unknown_capability --format json
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
`related_skill_candidates`, `related_skills`, `reasons`.

`status=pass` with exit 0 is success. `status=fail` with a stable `error_code`,
empty non-applicable fields, and exit 2 is fail-closed. Related-skill
candidates are evidence for a later owner route, not automatic activation.
Text and Markdown use the same fields and ordering as the capability schema.

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
