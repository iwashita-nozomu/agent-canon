---
name: experiment-lifecycle
description: "Use this skill when preparing, running, or validating experiments."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:experiment-lifecycle -->
<!-- canonical: agents/skills/experiment-lifecycle.md sha256=81c9a387fcfb327b77af99fc6302e99376bbe5f1735446fa00b5cca99ded1cfe -->
<!-- route: agents/skills/catalog.yaml#skill:experiment-lifecycle.routing digest=920be5167b67012e02c6f64d6b571627479c25d3d63508cb6d088156e8427f00 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:experiment-lifecycle digest=03b4becafba4dd8a413e7c1848787007db27190f8fa70d49033f96eaeab08c94 -->
<!-- commands: agents/skills/catalog.yaml#skill:experiment-lifecycle.tool_commands digest=7742e6a4e3c0946ee9c11db194e928993d3a4376d3accb03da65509d7fa21590 -->
<!-- host-config: path=../.agents/skills/experiment-lifecycle/SKILL.md index=21 order=21 enabled=true digest=3a6ee651764f3859c6c7ee6f74fe0cfbd88f22d8530c4788be88ec06ef86b855 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=d2b00778a1b3b5776ec7012e9563fc82397244b4d57386b89700e17af172a32a -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes experiment-lifecycle for runtime discovery.
upstream design ../../../agents/skills/experiment-lifecycle.md owner
@dependency-end
-->

# experiment-lifecycle

## Canonical Skill

Canonical workflow and policy: [experiment-lifecycle](../../../agents/skills/experiment-lifecycle.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill experiment-lifecycle --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
