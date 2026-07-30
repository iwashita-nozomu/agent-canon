---
name: cpp-review
description: "Use when C or C++ code changes need strict review for build evidence, header boundaries, ownership, and native-code behavior."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:cpp-review -->
<!-- canonical: agents/skills/cpp-review.md sha256=84fcc0adb3df46f6370937cae8a54f8d1c75e21cc9184a5feddd7f9d03d6af5b -->
<!-- route: agents/skills/catalog.yaml#skill:cpp-review.routing digest=ceaab753e28c451e305a7975b509970e1acd93904d57f6ac720895db9cfa5161 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:cpp-review digest=c3013ba138342b1334c435f9470870a3936b334cc2a31a880fe856b06a78b1ca -->
<!-- commands: agents/skills/catalog.yaml#skill:cpp-review.tool_commands digest=a2c4a873d29641038cbad39270e59266edc54c4c20c85c21def73e02afa78242 -->
<!-- host-config: path=../.agents/skills/cpp-review/SKILL.md index=15 order=15 enabled=true digest=c811737d445b2292420ff53bc7fea70346aa0d2265db7de0a81b8af6277ebc7e -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=369460ad8ed968f2860bd00983c027cbfafff8ccc8da60d9a4c311dea4a11267 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes cpp-review as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/cpp-review.md canonical skill owner
@dependency-end
-->

# cpp-review

## Canonical Skill

Canonical workflow and policy: [cpp-review](../../../agents/skills/cpp-review.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill cpp-review --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
