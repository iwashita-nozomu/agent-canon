---
name: dependency-design
description: Define and validate the typed declarative devcontainer dependency design packet before changing mounted developer or agent tools, manifests, bootstrap, or dependency installation order.
---
<!--
@dependency-start
contract skill
responsibility Exposes the canonical dependency-design workflow to Codex runtime discovery.
upstream design ../../../agents/skills/dependency-design.md canonical dependency design packet
upstream design ../../../agents/skills/catalog.yaml public skill registry and precedence
downstream implementation ../../../tools/agent_tools/devcontainer_dependencies.py typed dependency engine
@dependency-end
-->

# Dependency Design

Read the canonical skill document at `agents/skills/dependency-design.md`, then
produce its design packet before handing the result to
`environment-maintenance`. Keep the packet scoped to mounted developer/agent
tools and the parent follow-up contract.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-design --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->
