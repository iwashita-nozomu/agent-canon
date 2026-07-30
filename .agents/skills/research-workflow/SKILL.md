---
name: research-workflow
description: "Use when a task needs external research, comparison design, iterative implementation and runs, and explicit review decisions before claims are accepted."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:research-workflow -->
<!-- canonical: agents/skills/research-workflow.md sha256=5f62bb10ed2a514ffa2b35c7f6e961b3fffbd6e6edbab51a7bf97248e6de15a2 -->
<!-- route: agents/skills/catalog.yaml#skill:research-workflow.routing digest=18f8d33e3ae6a501fce57ae7b9cc9862538ee0dc0a06879d8c4456eecd135434 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:research-workflow digest=20b0cbfb5c92228a8528791bd30c17ffdf5fae7660146f6e17e3421d2979fb84 -->
<!-- commands: agents/skills/catalog.yaml#skill:research-workflow.tool_commands digest=61cc70c7bd73b05fc6ffba8d759b999f48267823af59bf2f6c1f25cd7ff7d102 -->
<!-- host-config: path=../.agents/skills/research-workflow/SKILL.md index=44 order=44 enabled=true digest=285448f3431a0e261f2937bf9b66685a72d42782cddcc4c60b7b0029f2ef3573 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=70cf98a21add277d2dad71295bd4da11e5931766b021cebabd90b10e3d794d30 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes research-workflow as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/research-workflow.md canonical skill owner
@dependency-end
-->

# research-workflow

## Canonical Skill

Canonical workflow and policy: [research-workflow](../../../agents/skills/research-workflow.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill research-workflow --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
