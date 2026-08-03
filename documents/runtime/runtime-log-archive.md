<!--
@dependency-start
contract reference
responsibility Defines the external GitHub archive for AgentCanon runtime hook and eval logs.
upstream design ../conventions/coding-conventions-logging.md JSONL logging convention
upstream design ../experiments/result-log-retention-and-visualization.md retention and visualization policy
downstream implementation ../../tools/agent_tools/runtime_log_paths.py resolves archive paths
downstream implementation ../../tools/agent_tools/runtime_log_archive_git.py manages clone, branch, status, and push operations
downstream design runtime-log-archive-migration.md documents in-tree hook JSONL migration into the archive
downstream design ../../.codex/hooks/hook_dispatcher.py records the active fingerprint-only local spool contract
downstream implementation ../../tools/agent_tools/runtime_log_archive_git.py owns explicit mount checks and archive checkpoints
downstream implementation ../../.codex/hooks/hook_event_log.py writes atomic per-event files into the repository-owned spool
downstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates archive JSONL and eval reports when mounted
downstream implementation ../../tools/agent_tools/generate_agent_improvement_guide.py reads mounted archive JSONL and eval reports
downstream implementation ../../tools/agent_tools/generate_agent_runtime_dashboard.py displays mounted archive evidence
downstream implementation ../../tools/agent_tools/export_codex_runtime_summary.py exports bounded Codex runtime summaries
@dependency-end
-->

# Runtime Log Archive

This document owns archive location, branch policy, mount behavior, and push
rules. Retention classes for general reports and experiment artifacts belong to
`documents/experiments/result-log-retention-and-visualization.md`. The one-time migration
procedure for old in-tree logs belongs to
`documents/runtime/runtime-log-archive-migration.md`.

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

The stable-branch and retention policy consumed by this contract is recorded in
[agent-canon-log PR #4](https://github.com/iwashita-nozomu/agent-canon-log/pull/4).
This document owns the AgentCanon consumer, mount, and publication behavior; it
does not duplicate the policy repository's schema or retention authority.

## Reader Map

Use this document to answer where runtime hook logs, accumulated evals, Codex
summaries, and archived agent run bundles are retained outside the source tree.
Read Source-Bound Runtime Event Materialization for the prepared-artifact and
outcome-receipt boundary, then Layout for path selection and Branch Policy,
Mount, and Push for operational handling. The final sections cover legacy
in-tree migration and agent report archiving boundaries.

## Source-Bound Runtime Event Materialization

`tools/agent_tools/runtime_log_archive_git.py` owns the complete source-bound
runtime-evidence handoff. First, the explicit checkpoint command
`append-context-discovery` reads native `session_meta` and selected
`event_msg` / `task_complete` records from the finite Codex rollout source and
publishes exactly one immutable
`context_discovery.<certificate-id>.json` certificate in the active run bundle.
Then `materialize-runtime-event` reads exactly one certificate, selects one
fixed result family (`requirements`, `design`, `review`, `validation`, or
`lifecycle`), verifies the certificate's repository, rollout, native-record,
and hash identities, and prepares one canonical `runtime_event.<unit-id>.json`
artifact. Neither command modifies hook serializers, runtime summaries,
accumulated-family registries, or pull-request adapters.

The prepared artifact has schema `agent_canon.runtime_event.v1`. Its ordered top-level
fields are `schema`, `materialization_id`, `result_family`, `gate`,
`source_event`, `result_artifact`, `target_identities`, `source_snapshot`,
`publication_intent`, and `artifact_sha256`. The nested record preserves the rollout
path and bytes, certified native byte range, source record hash, exact result-artifact
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

The producer requires a matching `reports/agents/.active_run`,
`--agent-context-id`, and `--turn-id`; the materializer requires the resulting
single context certificate, the fixed result artifact, and a valid
`--base-ref`. Example:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py append-context-discovery \
  --run-id <run-id> --agent-context-id <agent-context-id> --turn-id <turn-id>
python3 tools/agent_tools/runtime_log_archive_git.py materialize-runtime-event \
  --result-family review --run-id <run-id> --gate-id change-review \
  --base-ref <base-ref>
```

When an active runtime pointer exists and its run contains one prepared runtime
event, the Rust graph command consumes the prepared artifact plus the latest
confirmed committed receipt during one `graph build`. Its v2 persisted
runtime-evidence snapshot retains the exact artifact/receipt bytes, their
hashes, the live source identity fingerprint, and the validated observation.
An active pointer whose run contains no prepared runtime event is an
observability-incomplete closeout condition; the deterministic graph still
publishes source facts and completeness diagnostics without a runtime producer
snapshot, and the selected workflow closeout owns reporting that condition.
When a prepared event exists, duplicate, malformed, uncertain, missing, or
mismatched certificates/receipts remain fail-closed. Without an active runtime
pointer, the same builder publishes the source facts and completeness
diagnostics without a runtime producer snapshot. `graph status`, `graph query`,
`graph context`, and dependency-review consumers reuse that one snapshot and
perform only one bounded freshness probe per command. They never rerun the
runtime producer.
Nonempty source completeness diagnostics produce `incomplete` rather than
`fresh`; status remains inspectable, while query and context refuse to
authorize evidence until the diagnostic sets are empty.
Once a runtime pointer is present, missing, uncertain, invalid, stale, or
mismatched runtime evidence remains unavailable or stale instead of being
regenerated.

## Layout

Use this table first when deciding where a report is kept:

| Purpose | Source During Work | Durable Location | Command |
| --- | --- | --- | --- |
| Current task run bundle | `<source-repo>/reports/agents/<run-id>/` | none until archived | `bootstrap_agent_run.py` / task tools create it |
| Normal accumulated agent reports | `<source-repo>/reports/agents/` | `.agent-canon/log-archive/agent-reports/<stable-source-repository-id>/<run-id>/<snapshot-id>/` plus append-only `index.jsonl` on the stable branch | `python3 tools/agent_tools/runtime_log_archive_git.py sync` |
| Immutable run-bundle snapshot | `<source-repo>/reports/agents/<run-id>/` | `.agent-canon/log-archive/agent-reports/<stable-source-repository-id>/<run-id>/<snapshot-id>/` plus `index.jsonl` on the stable branch | `archive-agent-report --report-dir reports/agents/<run-id>` then `push` |
| Hook chronology | `<source-repo>/.agent-canon/runtime-event-spool/hook-events/<stable-source-repository-id>/` | `.agent-canon/log-archive/hook-runs/<stable-source-repository-id>/<runtime-namespace>/<hook-name>-<agent-canon-commit>.jsonl` on the stable branch | hooks publish per-event files; explicit `sync` checkpoints them |
| Accumulated eval reports | eval producer output | `.agent-canon/log-archive/eval-results/<family>/<eval-run-id>-<status>*.md` | `run_accumulated_agent_evals.py --run-id <run-id>` |
| Codex runtime summaries | local Codex runtime state | `.agent-canon/log-archive/codex-runtime/<stable-source-repository-id>/chats/<conversation-id>/summary-<agent-canon-commit>.jsonl` | `export_codex_runtime_summary.py` then `sync` |

In short: work in `reports/agents/<run-id>/`; retain across runs in
`.agent-canon/log-archive/` on `logs/<stable-source-repository-id>`.
`runtime_log_archive_git.py status` prints the resolved
`RUNTIME_LOG_ARCHIVE_REPORTS_RUN_LOCAL`,
`RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_BRANCH`, and
`RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_DIR` values for the current source repo.
The branch key is the stable source repository ID derived from the normalized
Git remote. SSH / HTTPS, optional `.git`, host case, and repository case are
normalized by the log repository policy. Chat/session trace values remain in
metadata and paths but never affect branch identity.

Projected hook JSONL filenames and Codex runtime summary filenames carry the
AgentCanon checkout commit key, not the source repo commit. Hot-path event bytes
do not inspect or claim a Git head; the explicit checkpoint uses the AgentCanon
commit key only in publication placement. Codex runtime summaries and immutable
run-bundle manifests continue to record `agent_canon_git_head` when readable.
Existing trace metadata remains available through `codex_trace_key` and
`codex_thread_id` when the Codex runtime exposes it.

Normal hook writers use one independent file per event:

```text
<source-repo>/.agent-canon/runtime-event-spool/hook-events/<stable-source-repository-id>/<runtime-namespace>/<hook-name>/<hook-run-id>.json
```

The explicit checkpoint projects those immutable event bytes to:

```text
.agent-canon/log-archive/hook-runs/<stable-source-repository-id>/<runtime-namespace>/<hook-name>-<agent-canon-commit>.jsonl
.agent-canon/log-archive/hook-runs/<stable-source-repository-id>/.spool-index.jsonl
.agent-canon/log-archive/hook-runs/<stable-source-repository-id>/.spool-cursor.json
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
.agent-canon/log-archive/agent-reports/<stable-source-repository-id>/<run-id>/<snapshot-id>/
.agent-canon/log-archive/agent-reports/<stable-source-repository-id>/index.jsonl
```

Codex runtime summary exporters use per-chat summary files plus one
cross-chat index:

```text
.agent-canon/log-archive/codex-runtime/<stable-source-repository-id>/chats/<conversation-id>/summary-<agent-canon-commit>.jsonl
.agent-canon/log-archive/codex-runtime/<stable-source-repository-id>/index.jsonl
```

Normal `sync` / `archive-agent-reports` snapshots of agent run reports use:

```text
.agent-canon/log-archive/agent-reports/<stable-source-repository-id>/<run-id>/<snapshot-id>/
.agent-canon/log-archive/agent-reports/<stable-source-repository-id>/index.jsonl
```

`<stable-source-repository-id>` is derived from the normalized source Git
remote by the `agent-canon-log` policy repository.
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

The active hook dispatcher reuses the source-root context for this resolution:
the derived parent repository is the active root, while standalone AgentCanon
uses its own repository root. A derived invocation keeps the parent active root
even when its current directory is inside `vendor/agent-canon`. A typed
source-root resolution failure disables report projection and leaves the event
spool-only; `SOURCE_ROOT` is not a report fallback. The workflow-monitor report
target precedence is
`AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR`, the active root's
`reports/agents/.active_run`, and standalone `.active_run`; an absent target
leaves the hook spool-only. Pointer values must be relative, resolve to an
existing directory strictly below the active root's `reports/agents`, and stay
contained after symlink resolution; traversal, absolute, missing, and escaping
targets resolve to no report. The explicit environment target is a separate
authority route that may be outside `reports/agents`, but it must already be a
directory. Projection is emitted only after a `spooled` append for an assembled
behavior event, and no source-root `workflow_monitoring.md` fallback is
permitted. These reads and the local projection remain on the hook hot path
without archive sync, Git, or network operations.

The initial import from the former in-tree log surface is preserved under:

```text
legacy-import/hook-runs/
legacy-import/eval-results/
```

## Branch Policy

- `main` stores archive-level policy, merge attributes, and preserved
  legacy-import data.
- Normal runtime writes use exactly one stable branch per normalized source
  remote: `logs/<stable-source-repository-id>`.
- Stable source identity is owned by the `agent-canon-log` policy repository;
  filesystem paths and chat/session IDs are metadata only.
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

`status` returns typed nonzero `archive_branch_mismatch` when the mounted clone
is not on the policy-selected stable branch. All write routes check the branch
before staging or mutating archive data; they do not silently switch branches.

Set `AGENT_CANON_HOOK_EVENT_SPOOL_DIR` to select another container-visible
spool root. `AGENT_CANON_HOOK_RESULTS_DIR` maps to its `.event-spool/` child.
An explicit legacy `*.jsonl` hook override maps to sibling directory
`<override>.events/`; the hot path never appends a shared JSONL file and never
falls back to host `~/.codex` state.

`python3 tools/agent_tools/runtime_log_archive_git.py ensure` is the explicit
mount check for an archive checkpoint. The active dispatcher only writes
bounded fingerprint events to the local spool and never inspects or mounts an
archive.

## Push

```bash
python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
python3 tools/agent_tools/runtime_log_archive_git.py push
python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain
```

Do not copy raw hook JSONL or accumulated eval reports back into AgentCanon
source. Do not copy or rewrite agent run bundles into mutable source-tree mirror
reports for retention; `sync` and `archive-agent-report` use immutable
content-addressed snapshots and append-only indexes.
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

`sync` acquires the nonblocking source lock, checks the policy-selected branch,
snapshots the fixed spool set, validates canonical bytes, updates the hook
projection, dedup index, and cursor, copies requested agent reports, and then
stages/commits/compares/pushes once. Concurrent writers fetch the expected
remote head, rebase bounded append-only changes without force, and read back
the exact remote ref. It reads back the exact commit, tree, index,
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
are associated keys for the same stable source branch and do not count as foreign dirty
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
RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_BRANCH=logs/<stable-source-repository-id>
RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_DIR=<agent-canon>/.agent-canon/log-archive/agent-reports/<stable-source-repository-id>
```

Run `python3 tools/agent_tools/runtime_log_archive_git.py sync` from the
administrative checkpoint owner when an explicit archive checkpoint is due.
The active dispatcher has no archive, Git, network, SSH, or auto-sync
dependency.

## Legacy in-tree migration

`agent-canon-log` owns the read-only legacy inventory, source-to-stable mapping,
future migration authority, and retention policy. The AgentCanon producer does
not migrate, delete, merge, or rewrite legacy branches. It preserves all
legacy `logs/*` branches and `main` legacy-import data, and consumes only a
policy-owner manifest for any future administrative operation.

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
