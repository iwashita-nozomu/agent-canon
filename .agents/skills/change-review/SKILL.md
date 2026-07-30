---
name: change-review
description: "Use for code review, doc review, or AI-generated diff review when you need findings-first output focused on bugs, regressions, missing tests, and broken assumptions."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:change-review -->
<!-- canonical: agents/skills/change-review.md sha256=b5543d9fee9908311195b15371a958f60b20f753840c5cb6b11fade6c4bb7743 -->
<!-- route: agents/skills/catalog.yaml#skill:change-review.routing digest=1327113effd84eb563b0a06a826d764fed93f90b71f43967e8854adfe7398c68 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:change-review digest=89501841ffb49ea788f747d5c4c84e4351caeda90514ac26da003e4fe2db1a0a -->
<!-- commands: agents/skills/catalog.yaml#skill:change-review.tool_commands digest=5748d3caf86893020c645ea50f8bdbf3bfc441b711a2d788723b379479dc5f23 -->
<!-- host-config: path=../.agents/skills/change-review/SKILL.md index=11 order=11 enabled=true digest=12908be23cb800b1ff57896dfafe70281ab8e23e21b504ebc8f59f146867cb53 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=185389409b891b9b048b80d9c97bddcd51aed94049dcc897e4d5864167f8ad97 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes change-review as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/change-review.md canonical skill owner
@dependency-end
-->

# change-review

## Canonical Skill

Canonical workflow and policy: [change-review](../../../agents/skills/change-review.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill change-review --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
