---
name: task-routing
description: Use when choosing short AgentCanon tool, skill, profile, check, runtime, closeout, or evidence routes from long candidate names, broad workflow text, routing misses, over-constrained related-skill candidates, public/system skill delegation, skill splitting, or skill/tool routing refactors.
---

<!--
@dependency-start
contract skill
responsibility Documents Task Routing skill shim.
upstream design ../../../agents/skills/task-routing.md human-facing task routing skill
upstream implementation ../../../tools/agent_tools/route.py selects short routing areas
@dependency-end
-->

# Task Routing

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill task-routing --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/task-routing.md`.
1. Use `python3 tools/agent_tools/route.py --name <candidate>` to resolve a long proposed tool or skill name before creating any new public surface.
1. Use `python3 tools/agent_tools/route.py --prompt "<user request>" --format json` when a broad request needs deterministic public skill routing. Treat `ACTIVE_SKILLS` as current-wave skill guidance, `DEFERRED_SKILLS` as selected later wave triggers, and `RELATED_SKILL_CANDIDATES` as evidence-gated candidates for later stages.
1. When a user reports that skills are missed, called late, or that related skills are over-constrained, use prompt routing first, then route observable evidence to `$agent-log-analysis`, durable issue candidates to `$issue-finding-report`, and recurrence feedback to `$agent-learning`.
1. Route host-provided system-skill work to `$openai-docs`, `$skill-creator`, `$skill-installer`, `$imagegen`, or `$plugin-creator`; keep AgentCanon changes to local routing, evidence, and owner-surface contracts.
1. Use `python3 tools/agent_tools/route.py --area <area> --changed <paths...>` to select the structured route for surface, profile, checks, environment, remote, AgentCanon update, MCP, goal, runtime, token, skill, agent, closeout, dependency, convention, docs, logs, or tool catalog decisions.
1. Prefer the returned short `COMMANDS` and `NEXT_ACTION` over reading or repeating long workflow prose.
1. When `task_start.py` or `bootstrap_agent_run.py` has emitted `run.repo_tool_routing_policy`, execute the selected skill tool route in manifest order: `show_skill_packet`, `required_commands`, task-matching conditional commands, then validation commands. If a related skill becomes active later, regenerate that skill packet before handoff.
1. Create a new tool or skill only when the candidate is unknown and cannot fit an existing route area.
