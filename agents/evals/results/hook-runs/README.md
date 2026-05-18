# Hook Run Results

<!--
@dependency-start
responsibility Documents accumulated hook run result naming.
upstream design ../README.md eval result accumulation contract
downstream implementation ../../../../.codex/hooks/hook_event_log.py assigns hook run ids
downstream implementation ../../../../tools/agent_tools/generate_agent_improvement_guide.py reads hook results
downstream implementation ../../../../tools/agent_tools/generate_agent_runtime_dashboard.py displays hook results
downstream implementation ../../../../tools/agent_tools/eval_accumulation_check.py validates hook result structure
@dependency-end
-->

This directory stores append-only JSONL hook results owned by AgentCanon.
It is the canonical hook-result surface for normal Codex hook runs.

Runtime-local `reports/hooks/` output is temporary debug output only when a task
intentionally overrides the destination with `AGENT_CANON_HOOK_RESULTS_DIR`,
`AGENT_CANON_OOP_HOOK_LOG_PATH`, `AGENT_CANON_STYLE_CHECKER_HOOK_LOG_PATH`,
or `AGENT_CANON_SKILL_LOG_PATH`. The default
hook destination must remain this AgentCanon-owned hook result surface so
improvement-guide and eval tooling can read one durable chronology.

OOP hook entries include a `mode` field. The default mode is `full`, which blocks
all current findings in changed source files. `diff` mode is opt-in for tasks
where the user explicitly asked to ignore baseline findings; those entries also
record the `baseline_ref` used for comparison.

Style checker hook entries include `selected_checkers`, `checked_files`, and
`unchecked_files`. `unchecked_files` is the durable signal that a changed file
had no automatic Python / C++ / notebook / Markdown style checker selected.

Reference capture hook entries include `urls`, `registered_urls`,
`missing_urls`, `reference_files`, and `decision`. UserPromptSubmit entries are
measurement-only, while PostToolUse and Stop entries may block when a consulted
PDF or HTML URL has not been materialized as Markdown under `references/`.

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

Each hook writes one JSONL file named after the hook inside a runtime namespace:

```text
<runtime-namespace>/<hook-name>.jsonl
```

The namespace is derived from `AGENT_CANON_HOOK_RUN_NAMESPACE`,
`DEVCONTAINER_PROJECT_NAME`, `COMPOSE_PROJECT_NAME`, generated devcontainer
Compose `name:`, or a host/repo hash fallback. This prevents shared
AgentCanon-owned hook result files such as `oop_readability_guard.jsonl` from
becoming one conflicting append target across multiple containers or clones.
Legacy direct files at `hook-runs/<hook-name>.jsonl` may remain readable, but
new default hook writes must use a namespace directory.

Each line must include:

```text
hook_run_id: hook-<YYYYMMDDTHHMMSSffffffZ>-<10-char-payload-hash>-<10-char-nonce>
hook_log_namespace: runtime namespace used for the JSONL path
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
`skill_usage.jsonl` contributes explicit skill counts, candidate skill /
workflow / tool counts inferred from prompt text, human feedback labels and
targets, prompt fingerprints, bounded redacted prompt excerpts, and skill/event
coverage. `PostToolUse` entries in that same file contribute chosen tool names,
tool input fingerprints, input key names, and command verbs. Hook entries with
`tool_name` contribute tool usage counts, and checker command arrays contribute
target file counts. Do not strip command target paths from hook results; they
are how the next repair branch can see which skill, workflow, tool, or source
file needs attention.

Prompt-intake logs must not store unbounded raw prompt text. Store only
`prompt_excerpt_redacted`, `prompt_fingerprint`, `prompt_char_count`, and
`prompt_excerpt_truncated`. If a prompt contains secret-like values, redact them
before writing the excerpt. If later analysis cannot answer which prompt shape,
tool selection, or workflow attribution caused a failure, that is evidence that
the hook log schema is still too weak and should be extended deliberately.

Before editing `.codex/hooks.json` or `.codex/hooks/*`, run
`python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>`.
The predicted `codex_hook_runtime_alignment` and `log_surface_inventory_guard`
gates are part of the hook change contract: update hook wiring, quiet-pass
tests, durable JSONL fields, and `documents/log-surface-inventory.json` together
instead of letting the PostToolUse/Stop hook discover the mismatch after the
edit.
