---
name: owner-bounded-routing
description: "Use for owner-bounded repository edits after routing evidence shows a bounded owner, replaceable unit, targeted validation route, and no public behavior/schema expansion; also use for typo/link/format-only edits and Owner-Bounded Change work where Codex should run existing tools directly, record owner/tool/validation evidence, keep validation targeted, and avoid escalating to broad workflow prose."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:owner-bounded-routing -->
<!-- canonical: agents/skills/owner-bounded-routing.md sha256=b91114a26c3137132d728630460fb861ef5772632c327d0ce0917f304db0653e -->
<!-- route: agents/skills/catalog.yaml#skill:owner-bounded-routing.routing digest=f7a555da339b2fd491fcd1139f994324d489d9f17e2352d20efcd8cd0201f0b6 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:owner-bounded-routing digest=78734376c281b296991698dabce3c5ff736e7714e8024ed05981d8aa2fd90f27 -->
<!-- commands: agents/skills/catalog.yaml#skill:owner-bounded-routing.tool_commands digest=5ecf0a08a0ba1467d27c1269eeb201c2348707be0a9157dff584ed578213d5a1 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/owner-bounded-routing.md
@dependency-end
-->

# owner-bounded-routing

## Canonical Skill

Canonical workflow and policy: [owner-bounded-routing](../../../agents/skills/owner-bounded-routing.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill owner-bounded-routing --format text`; schema `skill_tool_commands.v2`, digest: `5ecf0a08a0ba1467d27c1269eeb201c2348707be0a9157dff584ed578213d5a1`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
