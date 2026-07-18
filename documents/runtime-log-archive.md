<!--
@dependency-start
contract reference
responsibility Defines the external GitHub archive for AgentCanon runtime hook and eval logs.
upstream design coding-conventions-logging.md JSONL logging convention
upstream design result-log-retention-and-visualization.md retention and visualization policy
downstream implementation ../tools/agent_tools/runtime_log_paths.py resolves archive paths
downstream implementation ../tools/agent_tools/runtime_log_archive_git.py manages clone, branch, status, and push operations
downstream design runtime-log-archive-migration.md documents in-tree hook JSONL migration into the archive
downstream implementation ../.codex/hooks/log_archive_mount_warning.py warns when the archive mount is absent
downstream implementation ../.codex/hooks/runtime_log_auto_sync.py runs best-effort Stop-time archive sync
downstream implementation ../.codex/hooks/hook_event_log.py writes atomic per-event files into the repository-owned spool
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

## Reader Map

Use this document to answer where runtime hook logs, accumulated evals, Codex
summaries, and archived agent run bundles are retained outside the source tree.
Read Source-Bound Runtime Event Materialization for the prepared-artifact and
outcome-receipt boundary, then Layout for path selection and Branch Policy,
Mount, and Push for operational handling. The final sections cover legacy
in-tree migration and agent report archiving boundaries.

## Source-Bound Runtime Event Materialization

`tools/agent_tools/runtime_log_archive_git.py materialize-runtime-event` is the
owner of generic, source-bound runtime evidence. It reads the active run
pointer, selects one fixed result family (`requirements`, `design`, `review`,
`validation`, or `lifecycle`), joins it to one structurally identified rollout
record, and prepares one canonical `runtime_event.<unit-id>.json` artifact in
the active run bundle. It does not modify hook serializers, runtime summaries,
accumulated-family registries, or pull-request adapters.

The prepared artifact has schema `agent_canon.runtime_event.v1`. Its ordered top-level
fields are `schema`, `materialization_id`, `result_family`, `gate`,
`source_event`, `result_artifact`, `target_identities`, `source_snapshot`,
`publication_intent`, and `artifact_sha256`. The nested record preserves the rollout
path and bytes, line-872 byte range, source record hash, exact result-artifact
path/schema/hash/blob, target content/blob identities, source `HEAD`/base OIDs,
and porcelain-v1 status lines. `publication_intent` contains the deterministic
attempt ID, exact target path, and only `prepared_state=prepared`; it never
predicts an outcome.

Publication is no-replace and source-bound. Post-target evidence is first
appended as a canonical
`agent_canon.runtime_event.publication_outcome_observation.v1` file beneath
`.agent-canon/runtime-event-spool/publication-outcome/<attempt-id>/`, then
published as an immutable hash-linked
`agent_canon.runtime_event.publication_outcome_receipt.v1` sibling of the
artifact. Receipt basenames are
`runtime_event.<unit-id>.outcome.<attempt-id>.<sequence>.json`, where sequence
is `000001` or `000002`. Consumers accept only the latest confirmed
`committed` receipt.

A pre-existing identical artifact, observation, or receipt is read back
idempotently; different bytes, malformed chains, or symlink/non-regular
targets fail closed. Every pre-artifact-rename failure preserves the old
destination and emits no outcome. A post-rename fsync/readback gap appends an
`uncertain` observation and receipt when possible. If a matching artifact is
recovered without an observation, recovery first appends sequence-1
`uncertain` with `causal_gap=true`; only a later verified recovery observation
may append sequence-2 `committed`. Existing artifacts, observations, and
receipts are never rewritten during recovery.

The public transaction codes distinguish artifact preparation
(`publication_failure`, `record_collision`, `schema_invalid`,
`publication_uncertain`), observation append/confirmation
(`publication_observation_failed`, `publication_observation_uncertain`,
`publication_observation_collision`, `publication_observation_invalid`),
receipt append/confirmation (`publication_receipt_failed`,
`publication_receipt_uncertain`, `publication_receipt_collision`,
`publication_receipt_invalid`), and attempt synchronization
(`publication_attempt_busy`, `publication_attempt_lock_invalid`,
`publication_attempt_lock_release_failed`, `publication_attempt_collision`).
For a typed failure the command prints only the exact error code and
`RUNTIME_EVENT_MATERIALIZE=fail`, writes no stderr, and exits `1`.

The materializer requires `CODEX_THREAD_ID`, a matching
`reports/agents/.active_run`, the fixed result artifact, and a valid
`--base-ref`. Example:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py materialize-runtime-event \
  --result-family review --run-id <run-id> --gate-id change-review \
  --base-ref <base-ref>
```

The Rust graph command consumes the prepared artifact plus the latest confirmed
committed receipt during one `graph build`. Its v2 persisted runtime-evidence
snapshot retains the exact artifact/receipt bytes, their hashes, the live
source identity fingerprint, and the validated observation. `graph status`,
`graph query`, `graph context`, and dependency-review consumers reuse that one
snapshot and perform only one bounded freshness probe per command. They never
rerun the runtime producer. Missing, uncertain, invalid, stale, or mismatched
runtime evidence makes the graph unavailable or stale instead of regenerating
an event.

## Layout

Use this table first when deciding where a report is kept:

| Purpose | Source During Work | Durable Location | Command |
| --- | --- | --- | --- |
| Current task run bundle | `<source-repo>/reports/agents/<run-id>/` | none until archived | `bootstrap_agent_run.py` / task tools create it |
| Normal accumulated agent reports | `<source-repo>/reports/agents/` | `.agent-canon/log-archive/agent-reports/<repo-key>/<run-id>/` on branch `logs/<environment-key>-<chat-key>` | `python3 tools/agent_tools/runtime_log_archive_git.py sync` |
| Immutable run-bundle snapshot | `<source-repo>/reports/agents/<run-id>/` | `.agent-canon/log-archive/agent-reports/<repo-key>/<run-id>/<snapshot-id>/` plus `index.jsonl` on branch `logs/<environment-key>-<chat-key>` | `archive-agent-report --report-dir reports/agents/<run-id>` then `push` |
| Hook chronology | `<source-repo>/.agent-canon/runtime-event-spool/hook-events/<repo-key>/` | `.agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/<hook-name>-<agent-canon-commit>.jsonl` on branch `logs/<environment-key>-<chat-key>` | hooks publish per-event files; explicit `sync` checkpoints them |
| Accumulated eval reports | eval producer output | `.agent-canon/log-archive/eval-results/<family>/<eval-run-id>-<status>*.md` | `run_accumulated_agent_evals.py --run-id <run-id>` |
| Codex runtime summaries | local Codex runtime state | `.agent-canon/log-archive/codex-runtime/<repo-key>/chats/<conversation-id>/summary-<agent-canon-commit>.jsonl` | `export_codex_runtime_summary.py` then `sync` |

In short: work in `reports/agents/<run-id>/`; retain across runs in
`.agent-canon/log-archive/` on `logs/<environment-key>-<chat-key>`.
`runtime_log_archive_git.py status` prints the resolved
`RUNTIME_LOG_ARCHIVE_REPORTS_RUN_LOCAL`,
`RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_BRANCH`, and
`RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_DIR` values for the current source repo.
The branch key is `<environment-key>-<chat-key>`. `<environment-key>` comes
from `AGENT_CANON_LOG_ENV`, devcontainer / Compose / Codespace metadata, or a
host fallback. `<chat-key>` comes from `CODEX_THREAD_ID`, `CODEX_SESSION_ID`,
or `CODEX_CONVERSATION_ID`; Codex lifecycle hooks also promote top-level
payload trace fields such as `session_id`, `conversation_id`, and `thread_id`
to `CODEX_THREAD_ID` before child hooks run. Non-chat CLI / CI runs use the
explicit fallback `no-chat-<repo-key>`. The source isolation key remains
`<repo-key>` inside the branch tree, so one chat branch can still separate
parent repo and standalone AgentCanon evidence by path.

Projected hook JSONL filenames and Codex runtime summary filenames carry the
AgentCanon checkout commit key, not the source repo commit. Hot-path event bytes
do not inspect or claim a Git head; the explicit checkpoint uses the AgentCanon
commit key only in publication placement. Codex runtime summaries and immutable
run-bundle manifests continue to record `agent_canon_git_head` when readable.
Existing trace metadata remains available through `codex_trace_key` and
`codex_thread_id` when the Codex runtime exposes it.

Normal hook writers use one independent file per event:

```text
<source-repo>/.agent-canon/runtime-event-spool/hook-events/<repo-key>/<runtime-namespace>/<hook-name>/<hook-run-id>.json
```

The explicit checkpoint projects those immutable event bytes to:

```text
.agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/<hook-name>-<agent-canon-commit>.jsonl
.agent-canon/log-archive/hook-runs/<repo-key>/.spool-index.jsonl
.agent-canon/log-archive/hook-runs/<repo-key>/.spool-cursor.json
```

`event_id` is exactly `hook_run_id`; `event_sha256` is the SHA-256 of canonical
sorted compact JSON plus one terminal LF. The dedup preimage is canonical
sorted compact JSON over `event_id` and `event_sha256` without that LF.
`HookLogContext.append` returns a `HookAppendResult` whose transport `status` is
exactly `spooled`, `duplicate`, or `failed`; this is separate from the hook
event's semantic `status` field. The append path writes no stdout or stderr.
Consequently, spool failure is represented only by the returned result and the
dispatcher's JSON output remains valid.

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
captures producer stdout/stderr under `reports/agent-eval-runs/<run-id>/` by
default. PR / CI wrappers pass `--log-dir` under a temp directory and then run
`generated_artifact_guard.py`; agents do not hand-author accumulated eval
reports or leave regenerated stdout/stderr captures in the source tree.

Immutable agent report archive snapshots use:

```text
.agent-canon/log-archive/agent-reports/<repo-key>/<run-id>/<snapshot-id>/
.agent-canon/log-archive/agent-reports/<repo-key>/index.jsonl
```

Codex runtime summary exporters use per-chat summary files plus one
cross-chat index:

```text
.agent-canon/log-archive/codex-runtime/<repo-key>/chats/<conversation-id>/summary-<agent-canon-commit>.jsonl
.agent-canon/log-archive/codex-runtime/<repo-key>/index.jsonl
```

Normal `sync` / `archive-agent-reports` copies of agent run reports use:

```text
.agent-canon/log-archive/agent-reports/<repo-key>/<run-id>/
```

`<repo-key>` is derived from the source repository root name plus a short hash.
`<agent-canon-commit>` is the short HEAD SHA of the AgentCanon checkout that
provided the hook or exporter code; when no AgentCanon Git HEAD is readable,
the filename uses `no-git-head`.
`<conversation-id>` is the Codex thread/session identifier normalized as one
path segment. The summary payload also records `conversation_id`, `session_id`,
and `thread_id` so chat-local raw evidence and cross-chat analysis stay
traceable without storing prompt text.
`<runtime-namespace>` is derived from `AGENT_CANON_HOOK_RUN_NAMESPACE`,
devcontainer/Compose metadata, or the existing host/repo alternate route.
When AgentCanon runs as `vendor/agent-canon` inside a template or derived repo,
hook workflow-monitor evidence resolves the parent repo
`reports/agents/.active_run` before any submodule-local pointer. That prevents
submodule hook calls from writing active-task evidence into stale AgentCanon
source report bundles.

The initial import from the former in-tree log surface is preserved under:

```text
legacy-import/hook-runs/
legacy-import/eval-results/
```

## Branch Policy

- `main` stores archive-level policy, merge attributes, and one-time imports.
- Normal runtime writes use `logs/<environment-key>-<chat-key>` branches.
- Non-chat CLI / CI runtime writes use
  `logs/<environment-key>-no-chat-<repo-key>` branches.
- Source repos do not update AgentCanon source branches or template submodule
  pins when runtime logs change.
- JSONL files are append-only. The log repo uses `*.jsonl merge=union` so
  independent append lines can be kept during rebase conflict repair.

## Mount

```bash
python3 tools/agent_tools/runtime_log_archive_git.py ensure
```

`ensure` is an explicit administrative operation. PostToolUse does not invoke
it or inspect the archive. Hook writers publish only to the fixed-depth local
spool under the source repository, so an absent archive, a different archive
branch, or a held Git index cannot block hook completion.

Set `AGENT_CANON_HOOK_EVENT_SPOOL_DIR` to select another container-visible
spool root. `AGENT_CANON_HOOK_RESULTS_DIR` maps to its `.event-spool/` child.
An explicit legacy `*.jsonl` hook override maps to sibling directory
`<override>.events/`; the hot path never appends a shared JSONL file and never
falls back to host `~/.codex` state.

`hooks/log_archive_mount_warning.py` runs at prompt and pre-tool boundaries. It
does not block; it emits a visible warning that asks the agent to prepare the
archive before an explicit checkpoint or accumulated eval write when the mount
is missing or not a Git clone. Local hook spooling remains available.

## Push

```bash
python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
python3 tools/agent_tools/runtime_log_archive_git.py push
python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain
```

Do not copy raw hook JSONL or accumulated eval reports back into AgentCanon
source. Do not copy or rewrite agent run bundles into source-tree mirror reports
for retention; use `archive-agent-report --report-dir reports/agents/<run-id>`.
Analysis artifacts such as SQLite caches and dashboards belong to each source
repo's ignored `reports/.cache/` or `reports/agent-runtime-dashboard/` paths.

Codex runtime summaries are derived from the local Codex runtime state
(`history.jsonl`, `logs_2.sqlite`, and optional legacy session JSONL). They
store bounded counters, token observations, and runtime attribution only; prompt
text and raw tool output stay out of the archive. Raw local Codex files may
remain in Codex-owned storage, but AgentCanon accumulation stores chat-scoped
summaries and a minimal `index.jsonl` rather than mixing all chat evidence into
one flat summary stream.

Normal unattended operation uses one command:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py sync
```

`sync` acquires the nonblocking source lock, ensures the archive exactly once,
snapshots the fixed spool set, validates canonical bytes, updates the hook
projection, dedup index, and cursor, copies requested agent reports, and then
stages/commits/pulls/pushes once. It reads back the exact commit, tree, index,
cursor, and projection identities before deleting only the covered spool
files. Concurrent hook writers publish independent files and events outside
the captured snapshot remain for the next checkpoint. It skips
`.active_run`, cache files, Python cache directories, and oversized single
files. The source repo's ignored `reports/agents/` directory remains run-local
working evidence; the log archive is the durable accumulated store.

The lock is
`<source-repo>/.agent-canon/runtime-event-spool/.archive-transaction.lock`.
A held lock fails immediately as `archive_transaction_busy`. `sync --no-push`
reports `partial_retained`; malformed input, archive failure, failed or
uncertain publication, and readback mismatch retain every source event.

The static hot-path contract is checked without resolving repository or archive
context:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py check-hook-hot-path
```

Its AST graph closes over hook-local calls and the imported `repo_log_key`,
`hook_event_spool_root`, and `codex_trace_key` definitions in
`runtime_log_paths.py`; those helpers are not trusted as opaque leaves.
For current task closeout, prefer the immutable snapshot path:
`archive-agent-report --report-dir reports/agents/<run-id>` followed by `push`.
Use broad `sync` when intentionally collecting accumulated runtime families,
not as a substitute for archiving the active run bundle.

Before task closeout, run:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain
```

`check-clean` must report `RUNTIME_LOG_ARCHIVE_CLEAN=yes`,
`RUNTIME_LOG_ARCHIVE_BRANCH_MATCH=yes`, `RUNTIME_LOG_ARCHIVE_DIRTY=no`, and
`RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no`. It must also report
`RUNTIME_LOG_ARCHIVE_FOREIGN_TREE=no`; that line catches already committed
unrelated repo-key directories, not only uncommitted dirt. The source repo key,
the AgentCanon repo key, and the source repo key of the AgentCanon superproject
are associated keys for the same chat branch and do not count as foreign dirty
or foreign tree entries. A foreign dirty or foreign tree finding means logs for
an unrelated `<repo-key>` were written while the archive worktree was on the
current runtime branch. Treat that as a log repository operation blocker:
migrate the listed foreign key to the correct runtime branch before unlocking
the run bundle.

To print the resolved placement without writing anything, run:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py status
```

Read these lines first:

```text
RUNTIME_LOG_ARCHIVE_REPORTS_RUN_LOCAL=<source-repo>/reports/agents
RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_BRANCH=logs/<environment-key>-<chat-key>
RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_DIR=<agent-canon>/.agent-canon/log-archive/agent-reports/<repo-key>
```

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
