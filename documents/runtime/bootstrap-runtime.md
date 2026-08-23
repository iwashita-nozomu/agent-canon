<!--
@dependency-start
contract agent-runtime
responsibility Describes the standalone AgentCanon bootstrap and shared tool-runtime user contract.
upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared runtime design
upstream implementation ../../bootstrap.sh Host entrypoint
upstream implementation ../../tools/agent_tools/bootstrap_runtime.py lifecycle owner
downstream design runtime-profiles-and-check-matrix.md validation profiles
downstream design runtime-log-archive.md archive publication
@dependency-end
-->

# Standalone Bootstrap And Shared Tool Runtime

`agent-canon` is a source repository and a reusable tool runtime. It is not a
project dependency directory. The supported user path is a host bootstrap
which builds or adopts one shared, bounded tool container and then
launches tools against explicitly registered targets.

The bootstrap owns lifecycle and host adapters. The container owns Python,
Rust, and language-server tools. Project builds, product tests, GPU access,
GitHub actions, and arbitrary host commands remain owned by the project or
host workflow. No project-specific AgentCanon image, container, virtualenv,
Cargo toolchain, volume, or source checkout is created.

## One command family

Every command starts with the same explicit control and runtime roots:

```bash
BOOTSTRAP=./bootstrap.sh
ROOT=<authorized-parent-root>
RUNTIME="$ROOT/workspace/agent-canon-runtime/<installation>"
COMMON=(--control-parent-root "$ROOT" --runtime-root "$RUNTIME")
```

`--control-parent-root` is the authorized parent repository root. The runtime
root must be beneath it and must not escape through a symlink. There is no
implicit `$HOME`, `$HOME/.cache`, `$HOME/.local`, current-directory, or source
tree fallback. Keep the runtime directory outside the AgentCanon checkout and
outside product source.

The command family is:

```bash
"$BOOTSTRAP" "${COMMON[@]}" install
"$BOOTSTRAP" "${COMMON[@]}" start
"$BOOTSTRAP" "${COMMON[@]}" status
"$BOOTSTRAP" "${COMMON[@]}" target add --root <project-root> --mode read-only
"$BOOTSTRAP" "${COMMON[@]}" codex prepare
"$BOOTSTRAP" "${COMMON[@]}" codex launch --project-root <project-root>
"$BOOTSTRAP" "${COMMON[@]}" tool run --root <project-root> <verified-catalog-id> -- <args...>
"$BOOTSTRAP" "${COMMON[@]}" eval collect --root <project-root> --run-id <run-id>
"$BOOTSTRAP" "${COMMON[@]}" eval sync --run-id <run-id>
"$BOOTSTRAP" "${COMMON[@]}" stop
"$BOOTSTRAP" "${COMMON[@]}" rollback
"$BOOTSTRAP" "${COMMON[@]}" gc
"$BOOTSTRAP" "${COMMON[@]}" uninstall
```

`target add` is explicit because the shared runtime never scans a workspace
or mounts a whole home directory. `read-only` is the default and is required
for analysis. `explicit-target-write` is available only for an operation whose
documented mutation capability names its target and allowed paths.

The command emits a typed JSON receipt. Keep receipts under the selected
runtime root; they are operational evidence, not source files. A failed
operation returns a stable error code and preserves the previous state where
the operation has a generation or ownership boundary.

## What is installed and where

`install` invokes the ordinary Docker build from
`bootstrap/container/Dockerfile`, records the Docker result and manifest, and
creates the runtime state directories. It does not enumerate containers,
perform a host architecture gate, or hash the full source tree before the
build. `start` creates or starts at most one manifest-owned container. The
image contains the Rust CLI, Python tools, configured LSP servers, and the
AgentCanon-owned eval definitions/configuration needed to evaluate a
source-free target. Container process identity and UID/GID mapping are owned
by the host/caller environment; AgentCanon does not create a user, pass
`--user`, or validate that policy. A matching pre-existing image tag is adopted
by exact ID without overwrite; an unowned pre-existing image remains outside
uninstall.

The container is bounded by the manifest: two CPUs, 4 GiB memory, 512 PIDs,
network disabled, read-only root filesystem, all Linux capabilities dropped,
no-new-privileges, and a writable `/tmp` tmpfs. The default maximum is two
admitted tasks, one shared resident container, and a 30-minute task timeout
with a 10-second termination grace period. Runtime, task, cache, and archive
lease quotas are checked before garbage collection.

The host owns `$CODEX_HOME`. `codex prepare` instead creates a
manifest-managed, isolated `codex-home/` beneath the selected runtime root.
`codex launch` sets `CODEX_HOME` only for the launched process and does not
overwrite global skills, agents, hooks, or configuration. Existing conflicting
paths fail closed; only links recorded as owned by this installation can be
removed by `uninstall`. Start a new Codex session after an install or update
and use `codex prepare` readback to verify the link and source digest.

## Targets, generations, and failure recovery

The target registry stores exact real paths and modes. A target update acquires
the lifecycle lock, closes task admission, waits for zero active tasks,
validates paths and collisions, starts a candidate generation, performs a
health check and exact mount readback, then atomically switches
`current-generation`. The old generation becomes rollback state only after
the candidate is verified. Old and candidate containers are never intentionally
run at the same time.

If active tasks do not drain, the result is `mount_update_blocked` and the
current container is unchanged. If candidate health or mount readback fails,
the candidate is quarantined and the old generation remains current. If the
old generation cannot be restored, the runtime reports `runtime_unavailable`
and preserves the pointer, quarantine receipt, and evidence for recovery.
`rollback` is allowed only with no active task and switches to the last
verified generation. `status` is the first recovery command; inspect its
generation, container, target, limits, and receipt fields before retrying.

`stop` removes the owned container but retains runtime state and spool data.
`gc` removes only completed, unpinned, manifest-owned task/cache/archive
objects after readback. An archive cache is retained whenever an unpublished
spool exists. It never uses `docker system prune` and never removes
pre-existing resources. `uninstall` removes only this installation's image,
container, and managed links after checking that no task is active. It retains
the external state, owner record, and receipts for absence readback; after that
readback the installation runtime directory may be removed as the final
task-owned cleanup. User repositories and global Codex state remain untouched.

## Tool routes and compatibility

Rust first-class commands keep their existing public shape, for example
`agent-canon docs check` and `agent-canon semantic-index`. Python tools do not
gain flat global executables. A catalog entry is runnable through
`tool run` only after its versioned schema-v2 parity record verifies argv,
cwd, standard streams, exit/signal behavior, and written paths. The
dispatcher rejects shell command strings and unknown catalog entries.

Until parity is verified, use the existing exact command through
`bootstrap ... exec --root <registered-target> -- <command...>` or its owning
workflow. Bootstrap does not silently rewrite a legacy command, and a failed
parity check leaves the legacy route authoritative. Do not infer that an
internal Python file is a public catalog command.

## Evaluation and archive route

`eval collect` runs the selected producer in the tool plane and writes a
versioned collection plus receipt to the runtime-root spool. The collection
records run and task identity, target repository and HEAD, AgentCanon/tool
digest, family status, metrics, and a source-unchanged result. Eval output,
hook events, dashboards, summaries, and task reports never default to
AgentCanon `reports/`, `.agent-canon/`, `target/`, or another source path.
Producer code, role configuration, and eval manifests resolve from the
image-owned AgentCanon snapshot. `--root <project-root>` supplies only the
observed read-only target identity; the target is not required to copy
`agents/`, `.codex/`, or `evidence/agent-evals/`. Producer failure is recorded
before export, and the Host adapter exports the pre-created output/log trees
without replacing that failure with a missing-path error.

`eval sync` hands the external spool to the existing archive owner,
`iwashita-nozomu/agent-canon-log`, through the typed host Git adapter. The
archive repository owns its branch, retention, and append-only policy.
Network or archive failure retains the spool and a failure receipt for retry;
it does not dirty AgentCanon source. Successful publication is complete only
after non-force push and remote ref/tree/blob readback. A local bare remote is
the focused end-to-end test fixture for this sequence.

The archive checkout is a runtime lease under the selected runtime root. It is
not a submodule, vendor checkout, symlink, or required source-tree directory.
Secrets, authorization headers, SSH paths, and raw embedding payloads are not
written to receipts, evals, or logs.

## Cleanup and user movement

The normal movement is:

```text
install -> start -> target add -> status -> codex prepare -> codex launch
  -> tool run / exec -> eval collect -> eval sync -> stop -> gc -> uninstall
```

Use a distinct `<installation>` or task id when an independent lifecycle is
needed, but reuse the shared image and container for projects under the same
authorized control root. Never create a second container merely to isolate a
task; task cwd, locks, temporary files, reports, logs, and receipts are
isolated below the runtime root. Before deleting a runtime root, run `stop`,
`eval sync`, `gc`, and `uninstall`, then verify `status`/resource absence and
archive readback. Remove a runtime directory only after no pending spool,
rollback generation, or archive lease remains.

For Template or another parent repository, AgentCanon development uses a
parent-owned ignored clone workspace. The parent does not vendor AgentCanon,
mount its tests, or learn its internal eval names. Project tests run from the
project's own Docker/test runner; AgentCanon's tool container is not the
project execution environment.

## Related owners

- [Bootstrap design](../design/agent-canon-bootstrap-tool-runtime.md) owns the implementation contract.
- [Runtime log archive](runtime-log-archive.md) owns archive publication and readback.
- [Runtime profiles and checks](runtime-profiles-and-check-matrix.md) selects validation by changed surface.
- [AgentCanon update skill](../../agents/skills/agent-canon-update.md) owns source/update workflow.
- [Issue #841](https://github.com/iwashita-nozomu/agent-canon/issues/841) owns local bootstrap/runtime lifecycle.
- [Issue #821](https://github.com/iwashita-nozomu/agent-canon/issues/821) owns prebuilt artifact distribution; it is not the local lifecycle owner.
