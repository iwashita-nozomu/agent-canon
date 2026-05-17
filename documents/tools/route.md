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

Use this tool when a task needs a short answer to "which profile, check,
runtime, skill, or closeout path applies?" Use the specialized checker or
runner only after `route.py` points to it.
