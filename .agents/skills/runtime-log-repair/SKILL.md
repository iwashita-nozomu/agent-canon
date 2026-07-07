---
name: runtime-log-repair
description: Use when AgentCanon runtime dashboard evidence should be turned into owner-routed repair work, including dashboard next actions, repair failing hook evidence, hook entries status=fail, missing actual wave rows, workflow attribution gaps, consulted source URLs, reference missing URLs, AGENT_RUNTIME_DASHBOARD_WAVE_MISSING_ACTUAL, AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_MISSING, or AGENT_RUNTIME_DASHBOARD_REFERENCE_MISSING_URLS.
---
<!--
@dependency-start
contract skill
responsibility Documents Runtime Log Repair for this repository.
upstream design ../../../agents/skills/runtime-log-repair.md documents the human-facing skill
upstream design ../../../agents/skills/agent-log-analysis.md structured dashboard analysis and finding route packets
upstream design ../../../agents/skills/agent-eval-accumulation.md accumulated eval repair loop
upstream design ../../../agents/skills/result-artifact-writeout.md durable raw and summary artifact writeout
upstream design ../../../agents/skills/issue-finding-report.md durable issue candidate writing
upstream implementation ../../../tools/agent_tools/generate_agent_runtime_dashboard.py owns dashboard API fields
@dependency-end
-->

# Runtime Log Repair

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill runtime-log-repair --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/runtime-log-repair.md`.
1. Start from `$agent-log-analysis` dashboard artifacts:
   `reports/agent-runtime-dashboard/agent-log-analysis-api.json` and
   `reports/agent-runtime-dashboard/agent-log-analysis-compact.md`. If they are
   missing or stale for the request, run `$agent-log-analysis` first.
1. Do not read raw JSONL broadly for normal repair routing; raw event drilldown
   stays with `$agent-log-analysis` tool development, schema debugging, or an
   API-named drilldown path.
1. Build a Runtime Log Repair Packet with `repair_class`,
   `dashboard_evidence`, `owner_surface`, `repair_route`, `required_input`,
   `non_goals`, and `closeout_gate` before editing or launching repair work.
1. Route repairs to owners: eval gaps to `$agent-eval-accumulation`, durable
   artifacts to `$result-artifact-writeout`, issue candidates to
   `$issue-finding-report`, wave mechanics to `$subagent-bootstrap`,
   prompt/config or selection repair to `$task-routing` plus the affected owner,
   and recurrence learning to `$agent-learning`.
1. Keep boundaries explicit: this skill does not own raw log analysis,
   dashboard schema, eval producer loops, artifact placement, durable issue
   writing, subagent launch mechanics, prompt/config review, hook
   implementation details, or reference extraction internals.
1. Verify closeout with the owner-selected gate. Rerun a full dashboard only
   when the owner gate needs accumulated post-change evidence.
1. If the owner-selected gate fails, add `failing_contract`,
   `observation_level`, `cause_classification`, `intent_preservation`, and
   `evidence` to the Runtime Log Repair Packet before changing repair
   intent, simplifying to pass, reverting, deleting intended behavior/tests,
   weakening an oracle, or downscoping validation. Preserve owner intent for
   implementation bugs and route oracle/spec, fixture/environment/stale
   artifact, unrelated, and approved-design/user-request conflicts to owner
   repair, residual, or escalation.
