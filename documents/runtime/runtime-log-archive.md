<!--
@dependency-start
contract agent-runtime
responsibility Defines external AgentCanon hook, eval, runtime-summary, and report archive publication.
upstream design bootstrap-runtime.md shared runtime boundary
upstream implementation ../../tools/agent_tools/runtime_log_paths.py external path resolver
upstream implementation ../../tools/agent_tools/runtime_log_archive_git.py canonical archive publisher
upstream implementation ../../tools/agent_tools/eval_accumulation_check.py eval completeness gate
downstream design runtime-log-archive-migration.md archive migration route
@dependency-end
-->

# Runtime Log Archive

AgentCanon runtime evidence is runtime state. Hook events and pending
collection inputs use the bootstrap-owned ignored `<install-root>/.runtime/`
spool/control paths; accumulated evals, Codex runtime summaries, and archived
task bundles are published to the separate
[`iwashita-nozomu/agent-canon-log`](https://github.com/iwashita-nozomu/agent-canon-log)
repository. Outside that exact `.runtime/` directory, they are not written to
the AgentCanon source checkout, a parent repository, a vendor directory, or a
source-local `.agent-canon` fallback.

The general `RuntimeArtifactBoundary` remains source-local-output-safe. The
archive transaction has one explicitly named `runtime_spool_boundary` for the
bootstrap-owned exact `<source-root>/.runtime` path or an external runtime
root; it admits only `locks/` and `spool/` descendants for transaction control
and pending inputs. Archive and report output always uses the explicit external
`context.archive_root`.
In particular, the transaction never creates `.runtime/archive/`, and another
source child, runtime root, or symlink cannot use this exception.

The log repository owns its branch, append-only layout, retention, and legacy
import policy. AgentCanon owns only the local spool, archive checkout lease,
typed publication request, receipt, and readback needed by its runtime. This
document does not duplicate policy owned by the log repository.

## Reader map and paths

Start with [Standalone Bootstrap And Shared Tool Runtime](bootstrap-runtime.md)
for the command family and lifecycle. Use
`runtime_log_paths.py` for path resolution and
`runtime_log_archive_git.py` for archive state, clone, commit, push, and
readback. Use `eval_accumulation_check.py` to validate the external archive.

Given:

```text
ROOT=<authorized-parent-root>
INSTALL_ROOT=/path/to/agent-canon
RUNTIME=$INSTALL_ROOT/.runtime
```

the runtime-local layout is:

```text
$RUNTIME/
  spool/<run-id>/                 # pending eval/event/archive inputs
  tasks/<task-id>/                # logs, reports, locks, receipts
  codex-home/                     # managed isolated Codex surfaces

$INSTALL_ROOT_PARENT/agent-canon-log/  # host-owned operational archive checkout
```

IssueWorker publication receipts use the same private archive checkout and
host shell sync route. They are written under
`feedback/issue-packets/published/<owner>/<repository>/<number>.json`; the
stable path contains only the repository, Issue number/URL/state, operation,
responsibility and occurrence locators, source finding kind, and timestamp.
Issue/private bodies, digests, fingerprints, credentials, and generated IDs do
not enter the receipt. A publisher reads the GitHub result back first, writes
and reads back this receipt, and only then removes a pending packet. Failed or
uncertain publication retains the pending packet. `runtime_log_archive_git.py
sync` stages this published namespace with the existing private archive
families so the host shell remains the Git publisher. The publisher injects a
resident writer and invokes `bootstrap.sh ... tool run/exec issue-sync --
--stage-publication-receipt`; its runtime/spool route is a precondition for
GitHub mutation and its sync request is consumed by the existing
private-feedback host synchronization path.

The receipt ToolCall keeps the AgentCanon source root (the owner of
`bootstrap.sh` and the resident image) separate from the registered product
target root taken from `checkout_identity.git_root`; the generated command uses
`<agentcanon_source_root>/bootstrap.sh ... tool run --root <target_root>
issue-sync ...`.

The durable archive layout and its operational checkout are owned by
`agent-canon-log`; consumers should use its current branch contract rather
than hard-code a second local layout. Bootstrap eval publication passes this
checkout explicitly to the host archive adapter. The resident container sees
only the external spool and never creates an archive clone under `$RUNTIME`.
All report manifests and snapshots use paths relative to that same explicit
archive checkout (`agent-reports/<repo-key>/...`); `$RUNTIME` is only the
producer spool and staging boundary.

## Collection contract

`eval collect` runs existing producers in the shared tool container and writes
an `agent_canon.eval_collection.v1` bundle and receipt under the runtime spool.
The producer definitions, role/config surfaces, and eval manifests are part of
the image-owned AgentCanon snapshot. The registered repository is a separate
read-only observation target and does not need AgentCanon source files.
The bundle records at least:

- run and task id;
- source repository identity and source HEAD/fingerprint;
- AgentCanon commit and tool/image digest;
- eval family status and metrics;
- timestamp and `source_tree_unchanged` result.

Hook and runtime producers use the same external boundary. They append immutable
records or content-addressed files; they do not rewrite a prior result. A
producer must be able to run with its source target read-only. Intentional
source mutation is a separately authorized operation, not an artifact route.

Do not record secrets, authorization headers, SSH paths, raw embedding payloads,
or credential values in a collection, receipt, log, or report. Host adapters
record only credential mode, provider/remote digest, byte counts, exit status,
and the resulting artifact identity.

## Publication sequence

The supported user route is:

```bash
./bootstrap.sh --control-parent-root <root> \
  eval collect --root <project-root> --run-id <run-id>
./bootstrap.sh --control-parent-root <root> \
  eval sync --run-id <run-id>
```

The typed host Git adapter performs the following bounded sequence:

```text
runtime spool
  -> validate schema, owner, digest, and run identity
  -> acquire archive checkout lease
  -> clone/fetch the log repository on its owned branch
  -> append the immutable collection/report/index entry
  -> commit with no source checkout writes
  -> non-force push
  -> fetch and read back remote ref, tree, and blob digests
  -> finalize publication receipt
```

The archive publisher does not run arbitrary shell, accept an arbitrary remote,
or use an untyped upload path. Network and credential access stay in the host
adapter; the resident tool container remains `network=none`.

Publication is complete only after remote readback. A network, authentication,
branch, collision, or readback failure leaves the original spool and a typed
failure receipt in place. Retrying the same bytes is idempotent; different
bytes at an occupied identity fail closed. A pending spool is not silently
deleted and is not counted as successful publication.

## Branch and retention ownership

AgentCanon must not invent or silently switch archive branches. The log
repository's branch/retention contract is read before a publication and its
branch/ref is recorded in the receipt. Existing legacy branches and imported
data remain under the log repository's policy. AgentCanon may report status and
request a typed sync, but it does not migrate, prune, rewrite, or merge archive
history as a side effect of tool execution.

## Report and eval migration

Existing tracked or ignored report files are classified before removal:

1. canonical design evidence stays in a canonical AgentCanon document;
2. runtime-generated evidence is copied to the external archive and verified by
   source SHA, archive commit, and remote blob readback;
3. only after that evidence is durable may an owning change remove the old
   generated source path.

The source tree must not regain generated `reports/agent-eval-runs/`, dashboard,
improvement-guide, hook spool, or runtime-summary outputs. CI and PR wrappers
must pass an explicit external log directory or runtime root and must assert
source cleanliness after the producer exits.

## Local bare-remote end-to-end test

The focused E2E fixture uses a local bare Git remote and verifies:

```text
collect -> spool -> clone -> append/commit -> push -> fetch/readback
  -> duplicate no-op -> conflicting-bytes failure
```

The fixture must use a task temporary directory outside the source checkout,
restore the source fingerprint before and after collection, and remove only
its own clone, refs, and temporary runtime paths. It must not run a broad
Docker/Git cleanup command.

## Status and recovery

`runtime_log_archive_git.py status` and the bootstrap `status` operation show
the resolved runtime root, archive branch/lease, pending spool, and latest
publication receipt without generating a new report. A held lease or an
archive branch mismatch fails closed. Resolve the owning lease or branch
explicitly, then retry `eval sync`; do not silently fall back to source-local
storage.

Bootstrap `eval sync` supplies a repository-qualified source identity.
`archive-eval` selects that stable branch while holding the archive transaction
lock, so one shared runtime can publish sequentially for multiple registered
repositories. Branch selection still fetches first and reuses the clean/
managed-dirty reconciliation owner; foreign dirty state, an active lease,
conflicts, or failed remote readback remain fail-closed and retain the spool.
A branch mismatch outside this transaction-owned eval route still requires
explicit owner resolution.

At closeout, choose one state explicitly:

- `published`: remote ref/tree/blob readback passed;
- `pending`: spool and failure receipt retained for an authorized retry;
- `not-required`: no producer was part of the selected profile, with evidence.

Do not claim `published` from a local commit alone.

## Ownership

[Issue #841](https://github.com/iwashita-nozomu/agent-canon/issues/841) owns this
local collection, source-side-effect boundary, and publication lifecycle.
[Issue #821](https://github.com/iwashita-nozomu/agent-canon/issues/821) owns
prebuilt artifact distribution and does not own runtime archive semantics.
