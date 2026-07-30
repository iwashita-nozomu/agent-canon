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
<!-- host-config: path=../.agents/skills/owner-bounded-routing/SKILL.md index=47 order=47 enabled=true digest=40cfe1d93973989cebb3cd40d230250738c41f82e3c12a0c38a076ebd4750c30 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=77d682cb34fdc8d4184ba664f58ae748d1f112659a08a4c1645fef7db05057dd -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes owner-bounded-routing for runtime discovery.
upstream design ../../../agents/skills/owner-bounded-routing.md owner
@dependency-end
-->

# owner-bounded-routing

## Canonical Skill

Canonical workflow and policy: [owner-bounded-routing](../../../agents/skills/owner-bounded-routing.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill owner-bounded-routing --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
