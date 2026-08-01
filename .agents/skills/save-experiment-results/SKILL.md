---
name: save-experiment-results
description: "Save and publish experiment run results with branch-safe retention. Use when Codex needs to preserve experiments/<topic>/result/<run_name>, create or verify experiment result manifests, write experiment reader reports, publish to experiment-results/<topic>, prevent overwrites, or keep failed/partial experiment runs as durable evidence."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"9485d66f1e837f4806cae9819df79739700f4b8623317d1ab429465301af9a78"} -->

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
