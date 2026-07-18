---
name: agent-orchestration
description: Mandatory routing skill for repository tasks. Use before selecting workflow family, skills, review roles, subagents, model/team policy, runtime entrypoints, or run bundles for Codex routing.
---
<!--
@dependency-start
contract skill
responsibility Routes the runtime skill entry to the canonical Agent Orchestration policy without copying that policy.
upstream design ../../../agents/skills/agent-orchestration.md owns orchestration and Decision Sufficiency policy.
upstream design ../../../agents/canonical/skills.md owns the public skill registry.
upstream implementation ../../../tools/agent_tools/agent_team.py materializes machine ToolCall route packets.
@dependency-end
-->

# Agent Orchestration

## Reader Map

- Canonical policy: `agents/skills/agent-orchestration.md`.
- Decision Sufficiency owner:
  `agents/skills/agent-orchestration.md#Decision Sufficiency Packet`.
- Runtime packet producer: `tools/agent_tools/agent_team.py`.
- Boundary: this file is a discovery shim and does not restate routing, DSV,
  ToolCall, subagent, or validation rules.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill agent-orchestration --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->

1. Read `agents/skills/agent-orchestration.md` as the sole policy owner.
1. Consume the owner-produced `DecisionSufficiencyPacket` referenced by the
   active route packet.
1. Execute the route packet's machine-readable ToolCall tokens and return their
   typed failure semantics without translating them into prose commands.
