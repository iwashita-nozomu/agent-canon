---
name: owner-bounded-routing
description: "Use for owner-bounded repository edits only after routing evidence shows a bounded owner, replaceable unit, targeted validation route, and `external public API/behavior/schema unchanged`; route every public-surface addition, contraction, removal, rename, restriction, deprecation, or semantic change to `scoped_change` or a broader route with dependency/consumer/migration/docs closure. Also use for typo/link/format-only edits and Owner-Bounded Change work where Codex should run existing tools directly and record owner/tool/validation evidence."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"a940358f4dddf524ef9af0ecd9b2dadc674332302bfd3bffdc740b1ac2e94451"} -->

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
