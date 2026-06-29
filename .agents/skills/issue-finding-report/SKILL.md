---
name: issue-finding-report
description: Use when converting accumulated prompt history, run bundles, hook logs, skill/tool/workflow routing evidence, eval summaries, or agent reports into durable AgentCanon skill issues; groups repeated evidence by abstract cause, shards multi-agent review by evidence partition, and writes issue candidates from structured dashboard artifacts.
---
<!--
@dependency-start
contract skill
responsibility Documents Issue Finding Report runtime skill for this repository.
upstream design ../../../agents/skills/issue-finding-report.md human-facing skill canon
upstream design ../../../agents/skills/agent-log-analysis.md structured runtime evidence analysis workflow
upstream design ../../../agents/skills/subagent-bootstrap.md multi-agent partition and handoff workflow
upstream design ../../../issues/README.md durable AgentCanon operational issue schema
upstream implementation ../../../tools/agent_tools/generate_agent_runtime_dashboard.py emits structured log evidence
upstream implementation ../../../tools/agent_tools/runtime_log_archive_git.py resolves accumulated log archive state
upstream implementation ../../../tools/agent_tools/issue_sync.py validates local issue records and GitHub mirrors
@dependency-end
-->

# Issue Finding Report

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill issue-finding-report --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/issue-finding-report.md`.
1. Generate or cite structured log evidence before reading event files:

   ```bash
   python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
   python3 tools/agent_tools/generate_agent_runtime_dashboard.py \
     --root . \
     --compact-out reports/agent-runtime-dashboard/agent-log-analysis-compact.md \
     --api-out reports/agent-runtime-dashboard/agent-log-analysis-api.json
   ```

1. Confirm the API exposes `unknown_event_count`, `status_by_hook_family`,
   `failure_by_hook_family`, `skip_by_hook_family`,
   `namespace_debt_by_hook_family`, and `oop_applicability`.
1. Build an `Issue Finding Packet` for each abstract cause cluster. Use the
   taxonomy in `agents/skills/issue-finding-report.md`; keep one primary cause
   per cluster and cite structured dashboard headings or API JSON paths.
1. For multi-agent review, shard by `repo_key`, `hook_family`, `skill_name`,
   `workflow_name`, `tool_name`, `issue_id`, or path scope. Give each subagent
   one packet, structured artifact paths, candidate affected surfaces, allowed
   issue paths, validation route, and return schema.
1. Search existing durable surfaces before writing a new issue:

   ```bash
   git grep -n "<cause keywords>" -- issues memory notes/failures documents agents
   ```

1. Expand candidate affected surfaces with dependency review and record the
   resulting `dependency_edit_scope.txt` path in the candidate issue.
1. Write `issues/open/AC-YYYYMMDD-short-slug.md` after deduplicating existing
   issues. Use the required fields from `issues/README.md`.
1. Validate issue and skill wiring:

   ```bash
   python3 tools/agent_tools/issue_sync.py --root .
   python3 tools/agent_tools/check_skill_frontmatter.py --root .
   python3 tools/agent_tools/skill_tool_commands.py check
   ```
