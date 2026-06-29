---
name: owner-bounded-routing
description: Use for owner-bounded repository edits after routing evidence shows a bounded owner, replaceable unit, targeted validation route, and no public behavior/schema expansion; also use for typo/link/format-only edits and Owner-Bounded Change work where Codex still needs to read the selected runtime skill, record owner_bounded_skill_read evidence, keep validation targeted, and avoid escalating to broad workflow prose.
---
<!--
@dependency-start
contract skill
responsibility Documents Owner-Bounded Change Routing runtime skill for this repository.
upstream design ../../../agents/skills/owner-bounded-routing.md documents the human-facing route
upstream design ../../../agents/task_catalog.yaml owns Owner-Bounded Change workflow identity
upstream design ../../../documents/runtime-profiles-and-check-matrix.md owns Routine docs and Focused code validation profiles
downstream implementation ../../../tools/agent_tools/convention_compliance_contracts.toml declares owner-bounded marker contract
@dependency-end
-->

# Owner-Bounded Change Routing

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill owner-bounded-routing --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->

1. Read `agents/skills/owner-bounded-routing.md`.
1. Use this route after `$agent-orchestration` only when evidence already
   fixes the owner boundary, replaceable unit, targeted validation route, and
   public behavior / schema impact. Typo/link/format-only, Routine docs,
   Focused code, and `Owner-Bounded Change` may use this route when those facts
   are known. Do not select it from apparent file count alone.
1. Record `selected_runtime_skill_read` and `owner_bounded_skill_read` with the
   selected runtime `SKILL.md` path before patching.
1. Read only the selected task-shape skill and directly related owner surface.
   Add neighboring skills only when a concrete changed path, checker finding,
   or routing packet names them.
1. Run or cite `python3 tools/agent_tools/tool_rejection_preflight.py --root .
   <planned-edit-paths>` before editing, and keep predicted repair commands in
   the work log or handoff.
   Record each `responsibility_scope` line with its owner scope and protecting tools
   before choosing the implementation directory.
1. For typo/link/format-only Markdown edits, route `$md-style-check`, record
   `structure_contract=skipped` with the reason, and validate with
   `tools/bin/agent-canon docs check <changed-docs>`.
1. For bounded code edits, keep `targeted validation`: changed-file dependency
   checks, relevant static checker, and directly related tests only when the
   change adds observable behavior.
1. Escalate to the broader workflow when public behavior, dependency direction,
   section responsibility, claim grounding, schema, runtime profile, or multiple
   writers enter scope.
