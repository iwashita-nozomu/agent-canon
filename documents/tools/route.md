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
