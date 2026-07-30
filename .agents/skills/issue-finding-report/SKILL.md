---
name: issue-finding-report
description: "Use when converting accumulated prompt history, run bundles, hook logs, skill/tool/workflow routing evidence, eval summaries, or agent reports into durable AgentCanon skill issues; groups repeated evidence by abstract cause, shards multi-agent review by evidence partition, and writes issue candidates from structured dashboard artifacts."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:issue-finding-report -->
<!-- canonical: agents/skills/issue-finding-report.md sha256=60ebacc27cfa660c7320c86d72e6fdbd10ea1a45c1544413da139e4e125d0041 -->
<!-- route: agents/skills/catalog.yaml#skill:issue-finding-report.routing digest=d01425d3348c8a4cc2c977fc5c7ca5d33f22bf8dcccf1265643bf080af8cd324 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:issue-finding-report digest=1099d4384784263924e56b8198ee072577339839fb7b3ea5652b2ba1fc752efc -->
<!-- commands: agents/skills/catalog.yaml#skill:issue-finding-report.tool_commands digest=fde0aaf989f1e64f7ec012226431203d110793513d150367475b1a7828787115 -->
<!-- host-config: path=../.agents/skills/issue-finding-report/SKILL.md index=30 order=30 enabled=true digest=96d9fc1a22351541f3f828f8b304de9bd26447e3acd102a4ff760baf6763c069 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=7f5930b88194879e9411ab5d75f88f5aaa5dedffe166ea05d75e14c4aee97d4b -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes issue-finding-report as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/issue-finding-report.md canonical skill owner
@dependency-end
-->

# issue-finding-report

## Canonical Skill

Canonical workflow and policy: [issue-finding-report](../../../agents/skills/issue-finding-report.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill issue-finding-report --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
