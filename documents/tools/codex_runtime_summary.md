<!--
@dependency-start
contract reference
responsibility Documents the native Codex runtime summary exporter and its external archive effects.
upstream design ../runtime/runtime-log-archive.md owns archive placement and privacy policy
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/codex_runtime_summary.rs exports the summary records
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/runtime_boundary.rs validates and appends external artifacts
downstream implementation ../../tools/catalog.yaml registers the native command
downstream implementation ../../tests/agent_tools/test_export_codex_runtime_summary.py preserves raw-input behavior
@dependency-end
-->

# Codex Runtime Summary Export

`tools/bin/agent-canon export-codex-runtime-summary` exports bounded Codex
runtime summaries to the external log archive. It reads prompt history,
`logs_2.sqlite`, and optional legacy session JSONL files. Prompt contents are
never copied into summary records.

By default, the command uses `CODEX_HOME` or `~/.codex`, selects the current
`CODEX_THREAD_ID`, reads the last five days, and appends an idempotent per-chat
summary plus the cross-chat index through `RuntimeArtifactBoundary`. The
summary id ignores `recorded_at`, so repeating the same observation does not
append another record.

```bash
tools/bin/agent-canon export-codex-runtime-summary \
  --source-root <source-root> \
  --canon-root <agent-canon-root> \
  --thread-id <thread-id> \
  --history-jsonl <history.jsonl> \
  --sqlite-log <logs_2.sqlite> \
  --recent-days 5
```

Use `--all-threads` to discover threads from the selected history, SQLite, and
session inputs. Use `--session-glob <pattern>` one or more times to include
legacy session files; recursive patterns follow Python glob behavior. Use
`--all-time` to disable the recent-day filter. `--output` overrides the
per-chat path and suppresses index writes, and accepts one selected thread.
`--dry-run` reports whether the summary and index would append without writing.
`--print-json` prints the summary payload before the status lines.

The runtime root must be supplied through `AGENT_CANON_RUNTIME_ROOT` or the
existing archive mount configuration. The command uses the existing archive
layout and writer boundary; it does not write summaries into the source tree.
