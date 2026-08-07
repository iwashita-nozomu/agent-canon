---
name: save-experiment-results
description: "Save and publish experiment run results with branch-safe retention. Use when Codex needs to preserve experiments/<topic>/result/<run_name>, create or verify experiment result manifests, write experiment reader reports, publish to experiment-results/<topic>, prevent overwrites, or keep failed/partial experiment runs as durable evidence."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"9d0a87474c976f70af1db7aba79573a8e3e0ef3a80a49d58912bbd7c5a4e1eaf"} -->

<!--
@dependency-start
contract skill
responsibility Exposes save-experiment-results for runtime discovery.
upstream design ../../../agents/skills/save-experiment-results.md owner
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
