---
name: save-experiment-results
description: "Save and publish experiment run results with branch-safe retention. Use when Codex needs to preserve experiments/<topic>/result/<run_name>, create or verify experiment result manifests, write experiment reader reports, publish to experiment-results/<topic>, prevent overwrites, or keep failed/partial experiment runs as durable evidence."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:save-experiment-results -->
<!-- canonical: agents/skills/save-experiment-results.md sha256=f45d464220f67b69367d8f130a18ad4dfd0cd33e2070c0450e5038ea55a10661 -->
<!-- route: agents/skills/catalog.yaml#skill:save-experiment-results.routing digest=e7e6280de33c4d5de334534d96aafeba109d07e8d74a991011280cd421cb98c5 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:save-experiment-results digest=539cd7169bf4ed079238078c3fa60d4cdde46f613832f05a11281d4b04febd40 -->
<!-- commands: agents/skills/catalog.yaml#skill:save-experiment-results.tool_commands digest=3b7d68ab11f3857ac007f05495e6c8ceef43c45ce2938b65b6e3c5c2c216091e -->
<!-- host-config: path=../.agents/skills/save-experiment-results/SKILL.md index=22 order=22 enabled=true digest=44afdd56a8d415ba86aea58a5b08d20afb04c233878620703787d344e1a167ea -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=18adbd8a330ec51c25c3d749538ab42a5d12b438fb2a7be10f319fe5631f5a09 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/save-experiment-results.md
@dependency-end
-->

# save-experiment-results

## Canonical Skill

Canonical workflow and policy: [save-experiment-results](../../../agents/skills/save-experiment-results.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill save-experiment-results --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
