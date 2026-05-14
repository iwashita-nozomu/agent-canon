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
Normal local runtime hook output goes to ignored `reports/hooks/` so ordinary
tool checks do not dirty tracked AgentCanon files.

Durable hook evidence belongs here only when a task intentionally enables
accumulation with `AGENT_CANON_DURABLE_HOOK_RESULTS=1`, sets
`AGENT_CANON_HOOK_RESULTS_DIR`, or sets a hook-specific path such as
`AGENT_CANON_OOP_HOOK_LOG_PATH` or `AGENT_CANON_SKILL_LOG_PATH`.

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
