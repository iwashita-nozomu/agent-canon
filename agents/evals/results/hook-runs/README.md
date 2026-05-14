# Hook Run Results

<!--
@dependency-start
responsibility Documents accumulated hook run result naming.
upstream design ../README.md eval result accumulation contract
upstream implementation ../../../../.codex/hooks/hook_event_log.py assigns hook run ids
downstream implementation ../../../../tools/agent_tools/generate_agent_improvement_guide.py reads hook results
@dependency-end
-->

This directory stores append-only JSONL hook results owned by AgentCanon.
It is the canonical hook-result surface for normal Codex hook runs.

Runtime-local `reports/hooks/` output is temporary debug output only when a task
intentionally overrides the destination with `AGENT_CANON_HOOK_RESULTS_DIR`,
`AGENT_CANON_OOP_HOOK_LOG_PATH`, or `AGENT_CANON_SKILL_LOG_PATH`. The default
hook destination must remain this AgentCanon-owned hook result surface so
improvement-guide and eval tooling can read one durable chronology.

## Artifact Handling

Tracked JSONL in this directory is an evidence artifact, not disposable generated
scratch. A dirty AgentCanon submodule that only contains new hook-run JSONL
lines is still carrying AgentCanon-owned product evidence.

Do not stash, drop, or revert these lines merely to fast-forward the submodule.
Commit them through the AgentCanon branch / PR path, or run an explicit
retention/compaction task that preserves the chronology according to the eval
result policy. If a hook is writing unhelpful no-op events, fix the hook filter
in a follow-up change; do not silently hide already-written evidence.

## File Naming

Each hook writes one JSONL file named after the hook:

```text
<hook-name>.jsonl
```

Each line must include:

```text
hook_run_id: hook-<YYYYMMDDTHHMMSSffffffZ>-<10-char-payload-hash>-<10-char-nonce>
timestamp: ISO-8601 UTC
event: hook event name or UnknownHookEvent
payload_fingerprint: stable payload hash
status: pass|fail|skipped
```

Hook runs are never overwritten. Repeated failures are intentionally kept as
separate observations. The final nonce makes the run id unique even when two
hook calls share the same timestamp and payload hash, and `failure_fingerprint`
is used by guide-generation tools to group repeated failures without losing the
raw chronology.

Guide-generation tools also mine these JSONL lines for routing evidence:
`skill_usage.jsonl` contributes skill counts and skill/event coverage, hook
entries with `tool_name` contribute tool usage counts, and checker command
arrays contribute target file counts. Do not strip command target paths from
hook results; they are how the next repair branch can see which skill,
workflow, tool, or source file needs attention.
