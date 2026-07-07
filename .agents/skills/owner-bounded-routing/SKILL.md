---
name: owner-bounded-routing
description: Use for owner-bounded repository edits after routing evidence shows a bounded owner, replaceable unit, targeted validation route, and no public behavior/schema expansion; also use for typo/link/format-only edits and Owner-Bounded Change work where Codex should run existing tools directly, record owner/tool/validation evidence, keep validation targeted, and avoid escalating to broad workflow prose.
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
1. Do not make selected runtime `SKILL.md` reading a prerequisite for existing
   tool execution or patching. Run the existing tool first when it owns the
   check, then read only the owner surface or nearby lines needed to interpret
   or repair its output.
1. Record the owner boundary, existing tool route, and targeted validation
   evidence. Add neighboring skills only when a concrete changed path, checker
   finding, or routing packet names them.
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
1. If targeted validation fails, record `failing_contract`,
   `observation_level`, `cause_classification`, `intent_preservation`, and
   `evidence` before simplifying to pass, reverting, deleting intended
   behavior/tests, weakening an oracle, or downscoping validation. Repair
   implementation bugs while preserving approved intent; route oracle/spec,
   fixture/environment/stale artifact, unrelated, and approved-design/user-
   request conflicts to the owning repair, residual, or escalation path.
1. Escalate to the broader workflow when public behavior, dependency direction,
   section responsibility, claim grounding, schema, runtime profile, or multiple
   writers enter scope.
