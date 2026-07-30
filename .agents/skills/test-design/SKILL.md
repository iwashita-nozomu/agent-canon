---
name: test-design
description: "Use after the owning implementation mechanism exists to proactively design a logically minimal test set; classify unresolved oracle, specification, regression, and failure-mode risk before adding cases."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:test-design -->
<!-- canonical: agents/skills/test-design.md sha256=e4c3ac2dd202624abdf6536ce6dc360862d3aa7572212842291e4730227d71e6 -->
<!-- route: agents/skills/catalog.yaml#skill:test-design.routing digest=49dd312bd2d10ce4758f4d5adb13180c50c2a60f73d4880b0538dc3a47f651d3 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:test-design digest=ab8ae849289317fe7c67f4fe4b20109754d2b80aa7603cf6dc5b33da4bd26cbe -->
<!-- commands: agents/skills/catalog.yaml#skill:test-design.tool_commands digest=a152f74773f241b740a7ee0dbf8adeada0150a21cbbd6104e80a069ab53f9523 -->
<!-- host-config: path=../.agents/skills/test-design/SKILL.md index=53 order=53 enabled=true digest=91079aa77cf92012bdc204fe02e5fb6331ff8deeb15528378023c6d2f39fdbae -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=580846b9f4bb7dd34bddf794dbc0ac386e62c48f17064f465cedb7f3f4b92dd5 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/test-design.md
@dependency-end
-->

# test-design

## Canonical Skill

Canonical workflow and policy: [test-design](../../../agents/skills/test-design.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill test-design --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
