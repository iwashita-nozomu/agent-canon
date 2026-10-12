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

## Reader Map

- Use When: an observed event, routing gap, unexpected result, or repeated
  failure needs evidence-based interpretation.
- Evidence: use available conversation, tool, child, report, issue, or archive
  records; a dashboard or packet is not required. Records describe their own
  snapshots and do not establish current runtime behavior by themselves.
- Flow: compare expected and observed behavior, locate a supported cause and
  owner, then report the conclusion and limits.
- Boundary: analysis does not authorize collection, archive work, reruns,
  dashboard changes, or repairs.

## Workflow

1. Set the question and relevant source, revision, time range, or coverage;
   reuse sufficient summaries.
2. If needed, inspect a bounded source range. Missing records remain unknown,
   not zero, successful, or absent.
3. Compare expected behavior with observed operations and results. Plans,
   candidates, and manifests alone do not prove execution; separate observation
   from interpretation and cause.
4. Follow evidence to its owner. Gather more or select a repair only when the
   requested conclusion depends on it. For a selected repair, check the changed
   guarantee through its owner and report remaining uncertainty.

## Claims And Owner Boundaries

- Return the evidence and conclusion in the requested form, including limits
  from missing or stale records.
- Use evidence that actually covers a claim: event, file, line, or agent counts
  do not establish token use.
- If dashboard or archive records are involved, follow their owners for
  aggregation, collection, delivery, retention, and readback. Analysis itself
  does not sync or clean an archive.
- Missing, stale, or failed eval evidence is an observation. If collection or
  repair is selected, use [agent-eval-accumulation](agent-eval-accumulation.md).
  For selected archive work, follow the
  [runtime log archive owner](../../documents/runtime/runtime-log-archive.md).
- For a requested durable Issue, use [issue-finding-report](issue-finding-report.md).
  Claim publication only from the publisher's result and remote readback.
