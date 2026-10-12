# agent-log-analysis
<!--
@dependency-start
contract skill
responsibility Documents agent-log-analysis for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/runtime/runtime-log-archive.md accumulated eval and hook result storage
upstream design ../../documents/tools/search-coordination.md coordinated search policy
upstream design ../../documents/runtime/runtime-log-archive.md defines the external log archive mount
downstream design issue-finding-report.md converts compact log findings into durable issues
upstream implementation ../../eval/producers/generate_agent_runtime_dashboard.py owns structured dashboard API fields
upstream implementation ../../tools/runtime/archive/runtime_log_archive_git.py resolves the mounted log archive
downstream implementation ../../.codex/personal/skills/agent-log-analysis/SKILL.md exposes this workflow as a runtime skill
downstream design agent-eval-accumulation.md repairs missing accumulated eval family evidence
@dependency-end
-->

The consumed stable-branch and retention policy provenance is recorded in
[agent-canon-log PR #4](https://github.com/iwashita-nozomu/agent-canon-log/pull/4).
This external evidence link is intentionally prose metadata; dependency headers
contain only repository-local owner paths.

## Reader Map

- Purpose: interpret AgentCanon logs and related tool or child results to locate
  a supported cause and its owner.
- Use When: investigating skill, tool, workflow, hook, eval, or actual
  subagent/tool-result behavior.
- Flow: set scope, read available evidence, locate a selected owner, check the
  changed guarantee, and report results and limits.
- Boundary: analysis does not itself select collection, archive maintenance,
  dashboard repair, eval reruns, or code changes.

## Purpose

Analyze accumulated logs and related execution evidence without making one
dashboard, packet, or archive state a prerequisite. Existing records describe
their recorded snapshot; they do not by themselves reproduce current runtime
behavior.

## Use When

- Investigating missed or late skill/tool/workflow selection, routing gaps, or
  repeated failures.
- Interpreting available dashboard summaries, reports, issues, conversations,
  native tool results, or child launch/completion/failure results.
- Recording missing, stale, or failing eval-family evidence.
- Preparing evidence for a selected repair or durable Issue.

## Workflow

1. Set the question and the relevant repository, artifact, snapshot or time
   range, and coverage. Reuse available summaries when they answer the question;
   a dashboard or structured summary is not required for analysis.
2. If the summary is incomplete, read the known source with a bounded path,
   time, or line range. Record why the drilldown was needed. Missing fields and
   records remain unknown, never zero or successful; do not expand raw logs
   broadly.
3. Compare expected behavior with observed operations and results when relevant:
   actual tool calls, child launch/completion/failure, prompt or tool selection,
   checker execution, and owner follow-through. Plans, candidate lists, and
   manifests alone do not prove an operation occurred. Separate observation,
   interpretation, and tentative cause.
4. Locate the canonical owner indicated by the evidence. Select further
   collection, a change, or repair only when it is needed for the requested
   claim or outcome. Use that owner's native command and authority; unavailable
   new evidence limits the claim but does not erase readable evidence.
5. For a selected change, check its changed guarantee through the owning route.
   Report the actual result and unresolved limits; analysis or Issue recording
   alone does not establish that a repair succeeded.

## Claims And Owner Boundaries

- Report the question, evidence sources and snapshot/coverage, observations,
  interpretation, selected owner/action, checks actually performed, and limits.
  Keep missing or stale evidence explicit.
- Token-use claims require token coverage or moving-average evidence. Do not
  estimate token use from event, file, line, or agent counts.
- The dashboard owner owns aggregation. The runtime log archive owner owns
  archive branches, delivery, retention, synchronization, and remote readback;
  analysis does not sync or clean an archive. Distinguish a missing producer
  record from failed delivery, and do not infer the cause from an old archive
  head.
- Stable archive branch identity follows the log repository policy and the
  normalized Git remote; filesystem paths and session IDs are metadata only.
- For selected dashboard refresh or source-bound collection, use the existing
  owner command and output boundary. Runtime session collection uses the
  container-local source root supplied by its owner, never host session paths.
- Treat eval-family missing/stale/fail as observations. Do not automatically
  rerun producers, migrate old logs, or repair the dashboard. Selected eval
  repair follows [agent-eval-accumulation](agent-eval-accumulation.md); selected
  archive work follows the [runtime log archive owner](../../documents/runtime/runtime-log-archive.md).
- When durable Issue recording is requested, use
  [issue-finding-report](issue-finding-report.md) with available evidence and
  limitations. Publication is established by the publisher's actual receipt
  and remote readback, not candidate counts or pending-state disappearance. For
  a requested durable report, use `$result-artifact-writeout`.
