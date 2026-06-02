<!--
@dependency-start
responsibility Defines the external GitHub archive for AgentCanon runtime hook and eval logs.
upstream design coding-conventions-logging.md JSONL logging convention
upstream design result-log-retention-and-visualization.md retention and visualization policy
downstream implementation ../tools/agent_tools/runtime_log_paths.py resolves archive paths
downstream implementation ../tools/agent_tools/runtime_log_archive_git.py manages clone, branch, status, and push operations
downstream design runtime-log-archive-migration.md documents in-tree hook JSONL migration into the archive
downstream implementation ../.codex/hooks/log_archive_mount_warning.py warns when the archive mount is absent
downstream implementation ../.codex/hooks/runtime_log_auto_sync.py runs best-effort Stop-time archive sync
downstream implementation ../.codex/hooks/hook_event_log.py writes hook JSONL into the archive
downstream implementation ../tools/agent_tools/eval_accumulation_check.py validates archive JSONL and eval reports when mounted
downstream implementation ../tools/agent_tools/generate_agent_improvement_guide.py reads mounted archive JSONL and eval reports
downstream implementation ../tools/agent_tools/generate_agent_runtime_dashboard.py displays mounted archive evidence
downstream implementation ../tools/agent_tools/export_codex_runtime_summary.py exports bounded Codex runtime summaries
@dependency-end
-->

# Runtime Log Archive

This document owns archive location, branch policy, mount behavior, and push
rules. Retention classes for general reports and experiment artifacts belong to
`documents/result-log-retention-and-visualization.md`. The one-time migration
procedure for old in-tree logs belongs to
`documents/runtime-log-archive-migration.md`.

AgentCanon runtime hook JSONL, accumulated eval reports, Codex runtime
summaries, and archived agent run bundles are stored in the separate GitHub
repository `git@github.com:iwashita-nozomu/agent-canon-log.git`, mounted
locally at:

```text
.agent-canon/log-archive/
```

The mount is intentionally ignored by AgentCanon Git. It is not a submodule and
does not create a gitlink that can dirty AgentCanon source branches or parent
repo AgentCanon pins.

## Layout

Normal hook writers use:

```text
.agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/<hook-name>.jsonl
```

Normal eval writers use:

```text
.agent-canon/log-archive/eval-results/<family>/<eval-run-id>-<status>*.md
```

For required PR / CI eval family coverage, use the mechanical producer entry:

```bash
python3 tools/agent_tools/run_accumulated_agent_evals.py --run-id <run-id>
python3 tools/agent_tools/eval_accumulation_check.py
```

That command runs each registered eval producer with `--accumulate` and
captures producer stdout/stderr under `reports/agent-eval-runs/<run-id>/`.
Agents do not hand-author accumulated eval reports.

Agent report archive snapshots use:

```text
.agent-canon/log-archive/agent-reports/<repo-key>/<run-id>/<snapshot-id>/
.agent-canon/log-archive/agent-reports/<repo-key>/index.jsonl
```

Codex runtime summary exporters use:

```text
.agent-canon/log-archive/codex-runtime/<repo-key>/<thread-id>.jsonl
```

Agent run reports use:

```text
.agent-canon/log-archive/agent-reports/<repo-key>/<run-id>/
```

`<repo-key>` is derived from the source repository root name plus a short hash.
`<runtime-namespace>` is derived from `AGENT_CANON_HOOK_RUN_NAMESPACE`,
devcontainer/Compose metadata, or the existing host/repo fallback.

The initial import from the former in-tree log surface is preserved under:

```text
legacy-import/hook-runs/
legacy-import/eval-results/
```

## Branch Policy

- `main` stores archive-level policy, merge attributes, and one-time imports.
- Normal runtime writes use `logs/<repo-key>` branches.
- Source repos do not update AgentCanon source branches or template submodule
  pins when runtime logs change.
- JSONL files are append-only. The log repo uses `*.jsonl merge=union` so
  independent append lines can be kept during rebase conflict repair.

## Mount

```bash
python3 tools/agent_tools/runtime_log_archive_git.py ensure
```

If the mount is absent, hooks fall back to a local state directory outside the
repository tree. Set `AGENT_CANON_HOOK_ARCHIVE_DIR` to route logs to another
archive root. Existing `AGENT_CANON_HOOK_RESULTS_DIR` and per-hook
`*_HOOK_LOG_PATH` variables remain explicit test/debug overrides.

`hooks/log_archive_mount_warning.py` runs at prompt and pre-tool boundaries. It
does not block; it emits a visible warning that asks the agent to run the
`ensure` command before accumulating hook or eval logs when the mount is missing
or not a Git clone.

## Push

```bash
python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
python3 tools/agent_tools/runtime_log_archive_git.py push
```

Do not copy raw hook JSONL or accumulated eval reports back into AgentCanon
source. Do not copy or rewrite agent run bundles into source-tree mirror reports
for retention; use `archive-agent-report --report-dir reports/agents/<run-id>`.
Analysis artifacts such as SQLite caches and dashboards belong to each source
repo's ignored `reports/.cache/` or `reports/agent-runtime-dashboard/` paths.

Codex runtime summaries are derived from the local Codex runtime state
(`history.jsonl`, `logs_2.sqlite`, and optional legacy session JSONL). They
store bounded counters, token observations, and runtime attribution only; prompt
text and raw tool output stay out of the archive.

Normal unattended operation uses one command:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py sync
```

`sync` ensures the archive clone, copies current `reports/agents/` run bundles
to `agent-reports/<repo-key>/`, stages hook JSONL, eval reports, Codex runtime
summaries, and agent reports, then commits and pushes the source repository's
`logs/<repo-key>` branch. It skips `.active_run`, cache files, Python cache
directories, and oversized single files. The source repo's ignored
`reports/agents/` directory remains run-local working evidence; the log archive
is the durable accumulated store.

`hooks/runtime_log_auto_sync.py` runs the same `sync` path from the Codex Stop
hook on a best-effort, fail-open basis. It emits no output on success and does
not block repository work on network, SSH, or archive availability failures.
Use `AGENT_CANON_DISABLE_RUNTIME_LOG_AUTO_SYNC=1` to disable it for explicit
hook-development tests, or `AGENT_CANON_RUNTIME_LOG_AUTO_SYNC_NO_PUSH=1` to copy
artifacts locally without pushing.

## Legacy In-Tree Migration

If `agents/evals/results/hook-runs/` contains old `*.jsonl`, migrate it with
`documents/runtime-log-archive-migration.md`. The normal command is:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py import-legacy --delete-source
python3 tools/agent_tools/runtime_log_archive_git.py push \
  --message "Import legacy AgentCanon hook logs"
```

The AgentCanon source tree must not keep hook JSONL or eval report artifacts.
Raw hook streams move to `legacy-import/hook-runs/` in the log archive.

If `agents/evals/results/` contains old accumulated eval reports, migrate them
with:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py import-eval-results --delete-source
python3 tools/agent_tools/runtime_log_archive_git.py push \
  --message "Import legacy AgentCanon eval results"
```

The AgentCanon source tree keeps no `agents/evals/results/` tree. Accumulated
eval report families move to `legacy-import/eval-results/` in the log archive.

When invoking the helper from a wrapper repository, keep the AgentCanon
submodule as the working directory and let the tool derive the superproject
source root. For unusual layouts, pass `--source-root <repo>` and
`--canon-root <agent-canon>` explicitly.

## Agent Report Archiving

Run-local `reports/agents/<run-id>/` bundles remain local task evidence while
the task is active. At closeout or PR evidence publication, archive the bundle
mechanically instead of hand-copying summaries:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py ensure
python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report \
  --report-dir reports/agents/<run-id>
python3 tools/agent_tools/runtime_log_archive_git.py push \
  --message "Archive <run-id> agent report"
```

The archive command copies the bundle into a content-addressed snapshot
directory and appends one JSONL index entry. Re-running it with identical
content is idempotent; re-running it after the run bundle changes creates a new
snapshot. Agents should not generate a separate archive report by prose. Eval,
hook, runtime summary, and run-bundle archive entries must be created by tools
that write the archive paths directly.
