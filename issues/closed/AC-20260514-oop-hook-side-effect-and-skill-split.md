# OOP Hook Side Effect And Skill Split

<!--
@dependency-start
contract issue
responsibility Records the workflow defect where a simple OOP tool run expanded into hook side effects, report overproduction, and unclear timing attribution.
upstream design ../README.md defines durable AgentCanon operational issue storage.
upstream implementation ../../.codex/hooks/oop_readability_guard.py appends OOP hook evidence during source edits.
upstream implementation ../../tools/oop/shared/readability_core.py provides OOP readability report mechanics.
upstream implementation ../../tools/agent_tools/workflow_monitor.py records workflow behavior events.
downstream design ../../.agents/skills/oop-readability-check/SKILL.md keeps mechanical OOP output and agent analysis in one skill with separate modes.
@dependency-end
-->

issue_id: AC-20260514-oop-hook-side-effect-and-skill-split
status: resolved
source: user
severity: S1
evidence: reports/hooks/oop_readability_guard.jsonl, vendor/agent-canon/agents/evals/results/hook-runs/oop_readability_guard.jsonl, reports/agents/20260514-012429-oop-readability-report/oop_readability_report.md
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/250
affected_surfaces: .codex/hooks/oop_readability_guard.py, .codex/hooks/hook_event_log.py, documents/runtime-log-archive.md, tools/agent_tools/workflow_monitor.py, tools/agent_tools/review_backlog_scan.sh, .agents/skills/oop-readability-check/SKILL.md
edit_scope: .codex/hooks/oop_readability_guard.py, .codex/hooks/hook_event_log.py, documents/runtime-log-archive.md, tools/agent_tools/workflow_monitor.py, tools/agent_tools/review_backlog_scan.sh, agents/templates/workflow_monitoring.md, agents/skills/catalog.yaml, agents/skills/README.md, .agents/skills/oop-readability-check/SKILL.md
required_action: Keep OOP tool execution and agent analysis in one public skill while preventing hook evidence writes from making simple tool checks look like broad repo-changing work.
close_condition: A simple user request for OOP checking can invoke one narrow skill, choose mechanical-only/analyze-existing/run-and-analyze mode, record duration tokens when a run bundle exists, and append hook evidence to the AgentCanon-owned hook result chronology.
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/31
resolved_at: 2026-05-14
resolution_summary: OOP readability checks append run-bundle timing tokens with tool_call, duration_ms, status, scope, and output_path. Follow-up correction restores AgentCanon-owned `agents/evals/results/hook-runs/` as the default hook JSONL source of truth; `reports/hooks/` is override-only temporary output.

## Finding

A user asked for an OOP tool check and report, but the agent response expanded
the work into a broad workflow-shaped action:

- MCP and goal-loop preflight were run as required by runtime policy.
- Agent orchestration material was loaded even though the requested operation was
  a narrow tool invocation.
- The OOP readability tool was run against both AgentCanon full tree and PR
  source-diff scopes, and in both Markdown and JSON forms.
- A Markdown report was hand-built from the mechanical output.
- Runtime hooks appended JSONL evidence under the vendored AgentCanon tree,
  making `vendor/agent-canon` dirty after otherwise read-only commands.
- The dirty hook evidence then required repeated status checks and restore
  commands before the next operation.

The user's follow-up correctly identified that the elapsed time was not caused
by OOP tool performance. It was caused by surrounding workflow expansion,
report overproduction, and hook-log side effects.

## Observed Failure Mode

The core failure was a boundary collapse between three distinct activities:

1. **Mechanical OOP check**
   - Run the OOP readability tool on the requested paths.
   - Let the tool decide the language when possible.
   - Return deterministic status, counts, hotspot rows, and command evidence.
   - Do not interpret whether findings are true design problems.

2. **Mechanical report rendering**
   - Convert tool output into tables only when the user asks for a report.
   - Preserve raw metrics and findings without adding agent judgment.
   - Avoid running extra formats unless needed for the requested artifact.

3. **Agent analysis**
   - Read an existing mechanical report or raw tool output.
   - Explain likely false positives, priority, and next investigation targets.
   - Decide whether additional code reading is needed.
   - Keep judgments separate from the mechanical check result.

Because there was no explicit skill for the first two operations, the agent
treated a simple tool request as a small repository task. The result was more
careful than necessary, slower than necessary, and harder for the user to
control.

## Hook Side Effect

The hook behavior made the situation worse. OOP hook evidence is useful for
AgentCanon improvement loops, and the default tracked write path is intentional:
`agents/evals/results/hook-runs/*.jsonl` is an AgentCanon-owned evidence
artifact surface. The failure was not that the tracked JSONL changed; the
failure was that the surrounding workflow treated hook evidence churn as an
unclear side effect instead of routing it through the AgentCanon artifact and PR
path.

The practical symptoms were:

- `vendor/agent-canon` showed modified content after source-edit or report
  operations.
- The modified paths were hook-result JSONL evidence files.
- The agent incorrectly considered restoring or stashing those files instead of
  treating them as append-only AgentCanon artifacts.
- The user-facing task looked larger because status output mixed the real work
  with untriaged hook evidence churn.

Tracked hook-result JSONL is product evidence. It should be visible as evidence
when accumulated, committed through AgentCanon when retained, and only compacted
by an explicit retention pass.

## 2026-05-14 Additional Observation

During the standalone-only document surface repair, a small runtime packet path
resolver touched `tools/agent_tools/agent_team.py`. The OOP hook then blocked on
whole-file findings that already existed at `HEAD`, even though the edited
resolver did not introduce those findings. This is a distinct hook failure mode:
changed-file scope is useful, but blocking must be based on new or worsened
finding identities when a large legacy file already has recorded debt.

The first mitigation in the repair branch updates
`.codex/hooks/oop_readability_guard.py` to compare current JSON findings with
the same files at `HEAD`. The hook still blocks new files, new findings, and
worsened finding identities. Unchanged pre-existing findings are logged as
`OOP_READABILITY_BASELINE=preexisting-only` and do not block the current edit.

## Timing Attribution Gap

AgentCanon has partial observability:

- `tools/agent_tools/workflow_monitor.py` can append timestamped behavior
  events to `workflow_monitoring.md`.
- `tools/agent_tools/review_backlog_scan.sh` records command name, status, and
  output path in `review_backlog_scan_status.tsv`.
- hook JSONL files record hook timestamps and result status.

What is missing is a standard duration contract. There is no consistent
machine-readable token such as:

```text
tool_call=oop-readability-check command=tools/oop/python/readability.py duration_ms=742 status=fail scope=python
```

Without this token, the system cannot easily distinguish time spent in the tool
from time spent in orchestration, formatting, hook cleanup, or agent analysis.
That makes user feedback about latency harder to convert into an actionable
workflow fix.

## Required Product Direction

Keep one public skill:

- `$oop-readability-check`
  - Runs the OOP readability tool in `mechanical-only` or `run-and-analyze`
    mode.
  - Respects user-specified paths exactly.
  - Uses language-auto behavior, preferably through `--language all` until a
    dedicated language-auto wrapper exists.
  - Produces mechanical tables only when requested.
  - Performs agent interpretation only in an explicit `analyze-existing` or
    `run-and-analyze` mode.
  - Keeps mechanical output and `Agent Analysis` as separate sections.
  - Records timing tokens in workflow monitoring when a run bundle is active.

This lets the user be precise without needing two public triggers:

- "Run `$oop-readability-check` on `python/`" means use `mechanical-only`.
- "Use `$oop-readability-check` to interpret that report" means use
  `analyze-existing`.
- "Check and explain the result" means use `run-and-analyze`.

## Hook And Evidence Direction

The hook evidence policy should distinguish three modes:

1. **Local runtime observation**
   - Default for ordinary agent work.
   - Writes to ignored local paths or a run bundle.
   - Must not dirty tracked AgentCanon files.

2. **Run-bundle evidence**
   - Used when `AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR` or a run bundle is
     active.
   - Appends behavior and tool timing tokens to `workflow_monitoring.md`.

3. **Durable AgentCanon accumulation**
   - Used only during explicit eval / improvement workflows.
   - May write under `agents/evals/results/hook-runs/`.
   - Must be intentional and documented as a product artifact, not a hidden
     side effect of a normal tool check.

## Acceptance Criteria

- `$oop-readability-check` is discoverable in
  `.agents/skills/`, `.claude/skills/`, `agents/skills/README.md`, and
  `agents/skills/catalog.yaml`.
- Prompt/eval expected counts are updated for the single public skill surface.
- A narrow OOP check can be run with one command and no agent-authored report
  unless explicitly requested.
- A report request produces mechanical tables from one tool output, not an
  expanded full workflow unless the user asks for it.
- Agent analysis is triggered by mode and cites the mechanical evidence it
  interprets without being mixed into the mechanical result.
- Hook JSONL writes do not dirty tracked AgentCanon files during ordinary
  parent-repo OOP checks.
- Workflow monitoring can record at least `tool_call`, `duration_ms`, `status`,
  `scope`, and `output_path` for OOP checks when a run bundle exists.
