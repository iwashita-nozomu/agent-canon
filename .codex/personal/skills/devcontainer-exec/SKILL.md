---
name: devcontainer-exec
description: "Use only when an explicitly selected existing project Dev Container needs a targeted command through devcontainer exec; AgentCanon's shared tools and LSPs use agent-canon-bootstrap, and project tests use the project Docker/test runner."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"1fa96202ce04273fa8bb44f50ad2850e7d6c6459f89f09fd52fd49240e244783"} -->

<!--
@dependency-start
contract skill
responsibility Exposes devcontainer-exec for runtime discovery.
upstream design ../../../../agents/skills/devcontainer-exec.md owner
@dependency-end
-->

# devcontainer-exec

## Canonical Skill

Canonical workflow and policy: [devcontainer-exec](../../../../agents/skills/devcontainer-exec.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill devcontainer-exec --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
