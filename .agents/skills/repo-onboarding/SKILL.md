---
name: repo-onboarding
description: "Use when entering an unfamiliar repository or subdirectory and you need the fastest safe path to the repo overview, commands, conventions, and agent canon."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:repo-onboarding -->
<!-- canonical: agents/skills/repo-onboarding.md sha256=75d59ce92962442d084dc0ce637837815b2948d14c814150f5835c91792c0486 -->
<!-- route: agents/skills/catalog.yaml#skill:repo-onboarding.routing digest=1d6e0fde0de0427d4bec430a8a7fd41fcd31f1456b967ba68a4e374f018e44f5 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:repo-onboarding digest=d367ae94b3aff8b85cf348905dcd3c2e012dbbd0c14da2b7e3ce0774a32607f9 -->
<!-- commands: agents/skills/catalog.yaml#skill:repo-onboarding.tool_commands digest=8ccf92064c07eb62f6fe93373fd5878bde2216fdbf1f0a3c9fed2b9539fe6d9e -->
<!-- host-config: path=../.agents/skills/repo-onboarding/SKILL.md index=42 order=42 enabled=true digest=16b4e5777598ec36fed8a45421ee4334dee036422e3af9823dd317b131f00b3c -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=c5e54f9e009906fbde001086a5795602aa4e2a0d265d32648d4b80552d357b17 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes repo-onboarding as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/repo-onboarding.md canonical skill owner
@dependency-end
-->

# repo-onboarding

## Canonical Skill

Canonical workflow and policy: [repo-onboarding](../../../agents/skills/repo-onboarding.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill repo-onboarding --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
