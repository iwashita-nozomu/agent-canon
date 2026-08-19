---
name: experiment-lifecycle
description: "Use this skill when preparing, running, or validating experiments."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"8788e4e9ebc45e63a58c1f6d6b40bc6dacf3f6937e4420329aea2b210ea01dec"} -->

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

## Topic Preparation

新規 topic の準備は canonical owner の `Topic Preparation` を読み、次の creator route に入ります。

```bash
python3 tools/experiments/create_experiment_topic.py <topic>
```

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill experiment-lifecycle --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
