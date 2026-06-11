---
name: task-routing
description: Use when choosing short AgentCanon tool, skill, profile, check, runtime, closeout, or evidence routes from long candidate names or broad workflow text.
---

<!--
@dependency-start
responsibility Documents Task Routing skill shim.
upstream design ../../../agents/skills/task-routing.md human-facing task routing skill
upstream implementation ../../../tools/agent_tools/route.py selects short routing areas
@dependency-end
-->

# Task Routing

1. Read `agents/skills/task-routing.md`.
1. Use `python3 tools/agent_tools/route.py --name <candidate>` to resolve a long proposed tool or skill name before creating any new public surface.
1. Use `agent-canon local-llm route-skill --prompt "<user request>" --format json` when a broad request needs deterministic public skill routing. Treat `ACTIVE_SKILLS` as current-wave skill guidance and `DEFERRED_SKILLS` as later wave triggers. `python3 tools/agent_tools/route.py --prompt ...` is the Python compatibility mirror.
1. Use `python3 tools/agent_tools/route.py --area <area> --changed <paths...>` to select the compact route for surface, profile, checks, environment, remote, AgentCanon update, MCP, goal, runtime, token, skill, agent, closeout, dependency, convention, docs, logs, or tool catalog decisions.
1. Prefer the returned short `COMMANDS` and `NEXT_ACTION` over reading or repeating long workflow prose.
1. Create a new tool or skill only when the candidate is unknown and cannot fit an existing route area.
