<!--
@dependency-start
responsibility Documents route tool usage.
upstream implementation ../../tools/agent_tools/route.py selects short tool and skill routes
upstream design ../tool-skill-routing-refactor.md defines short naming policy
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

Prompt routing output returns the minimal public skill set for a task-shaped
request. It always starts with `$agent-orchestration`, adds
`$codex-task-workflow` for repo-changing prompts, and then appends matched
task-shape skills such as `$result-artifact-writeout`, `$agent-learning`, or
`$oop-readability-check`.

Routing miss, selection gap, ToolCall, SkillCall, or coverage prompts are
log-analysis tasks. `route.py --prompt ... --format json` should include
`$agent-log-analysis` for those requests so the agent reads compact runtime
dashboard evidence before editing prompt, hook, skill, or workflow surfaces.

Use this tool when a task needs a short answer to "which profile, check,
runtime, skill, or closeout path applies?" Use the specialized checker or
runner only after `route.py` points to it.
