---
name: agent-log-analysis
description: Use when analyzing accumulated AgentCanon skill/tool/workflow/hook/eval logs, routing misses, weak skills, or selection gaps; first convert raw logs into a token-light compact summary with generate_agent_runtime_dashboard.py before reading or interpreting evidence.
---
<!--
@dependency-start
responsibility Documents Agent Log Analysis for this repository.
upstream design ../../../agents/skills/agent-log-analysis.md documents the human-facing skill
upstream design ../../../documents/runtime-log-archive.md defines the external log archive mount
upstream implementation ../../../tools/agent_tools/runtime_log_archive_git.py resolves the mounted log archive
@dependency-end
-->


# Agent Log Analysis

1. Read `agents/skills/agent-log-analysis.md`.
1. Do not broad-search raw accumulated logs with `rg -n`.
1. Use the external log archive API first. Resolve or mount the archive:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py ensure
python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
python3 tools/agent_tools/runtime_log_archive_git.py sync
python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain
```

1. Do not complete log analysis or task closeout while `check-clean` reports `RUNTIME_LOG_ARCHIVE_CLEAN=no`. If it reports `RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=yes`, resolve the listed foreign repo-key logs before returning to the user.
1. Call the log archive repository tool, not raw JSONL. Replace `<archive-root>` with `RUNTIME_LOG_ARCHIVE_ROOT` from `status --porcelain` or `check-clean --porcelain`:

```bash
python3 <archive-root>/tools/runtime_log_dashboard.py \
  --root <archive-root> \
  --profile log-analysis \
  --output reports/agent-runtime-dashboard/agent-log-analysis-compact.md \
  --api-output reports/agent-runtime-dashboard/agent-log-analysis-api.json
```

1. Read the API JSON or compact Markdown as the default analysis input. The log archive repo owns aggregation, moving averages, and manuscript-structure evidence cells.
1. If `<archive-root>/tools/runtime_log_dashboard.py` is missing, stop with `log_archive_api_missing`; do not fall back to raw JSONL.
1. If the compact report lacks enough context for a specific claim, extend the log archive repository API/report profile and rerun it instead of opening raw JSONL.
1. Treat raw JSONL as tool-development or corruption-audit input only; record an explicit rationale before reading it.
1. Do not answer token-use questions from lifetime totals alone; use the API token coverage/moving-average fields. If token status is missing, say token claims are unsupported.
1. Report observations separately from interpretation, repair target, and unknowns.
1. If the analysis drives a prompt, skill, workflow, or tool change, add the responsible skill such as `$agent-learning`, `$md-style-check`, or the target skill before editing.
1. If the user asks for a durable report, pair this skill with `$result-artifact-writeout`.
