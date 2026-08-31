<!--
@dependency-start
contract agent-runtime
responsibility Describes the standalone AgentCanon bootstrap and shared tool-runtime user contract.
upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared runtime design
upstream implementation ../../bootstrap.sh Host entrypoint
upstream implementation ../../tools/runtime/container/bootstrap_runtime.py lifecycle owner
downstream design runtime-profiles-and-check-matrix.md validation profiles
downstream design runtime-log-archive.md archive publication
@dependency-end
-->

# Standalone Bootstrap And Shared Tool Runtime

`agent-canon` is a source repository and a reusable tool runtime. It is not a
project dependency directory. The supported user path is a host bootstrap
which adopts one shared, bounded tool container from the published
multi-architecture GHCR image and then
launches tools against explicitly registered targets.

The bootstrap owns only shell/Docker/Git adapters. The container owns Python,
Rust, and language-server tools. Project builds, product tests, GPU access,
GitHub actions, and arbitrary host commands remain owned by the project or
host workflow. No project-specific AgentCanon image, container, virtualenv,
Cargo toolchain, volume, or source checkout is created.

The published image uses a digest-pinned
`node-provider -> runtime-base -> builder -> runtime` pipeline. The reusable
runtime-base installs the retained Ubuntu closure and exact `clangd-18` once,
then removes its key, source list, apt indexes, and transient installers. The
disposable builder adds build-essential, curl, gnupg, ninja, pipx,
npm/corepack, rustup-init, and Cargo build support; system pip is unnecessary.
The final runtime receives only declared Python/Rust/LSP artifacts, pipx venvs,
and build receipts/plan. It has no pipx package or command and excludes pytest,
pip, ninja, build-essential, curl, gnupg, clang-format, package-manager caches,
and Cargo registry/git/target caches. No Docker cache mounts are used.

## Host/container activation boundary

`bootstrap.sh` and `bootstrap/host/lifecycle/entrypoint.sh` are executable by a host that
has Docker and Git but no Python package environment. They never import or
execute AgentCanon Python directly. Lifecycle and tool operations first build
or adopt the image, create/start exactly one resident container with
`--network none`, then invoke the Python controller through `docker exec`.

The controller never issues Docker operations. The host shell owns the fixed
Docker lifecycle transaction and invokes the controller only after the
resident is healthy. Target sources are exported by the controller as a strict
`mounts.tsv` manifest and are validated by the shell before each create. No Docker socket, host `$HOME`,
Git credentials, or network capability is mounted into the resident. The
credential-free `container-state` subtree is the only runtime state mount;
host-only Docker config and archive credentials remain outside it. Systemd
units and source synchronization remain host shell/Git operations. Sync stages
a full-history candidate under `.runtime/source-staging/` and replaces the
resident only after candidate image health; live source fast-forward happens
afterward and failure restores the old resident. Product
code verification remains in the project's own Docker test runner.

## One command family

Every command starts with the install root and explicit control root. The
persistent runtime defaults to the install root's ignored `.runtime/`:

```bash
BOOTSTRAP=./bootstrap.sh
ROOT=<authorized-parent-root>
COMMON=(--control-parent-root "$ROOT")
```

`--control-parent-root` is the authorized parent repository root. It authorizes
access but does not select storage. The effective runtime is always the
bootstrap-owned `<install-root>/.runtime/`; the private log checkout is its
sibling `<install-root-parent>/agent-canon-log`. Both are ignored or external
to the source checkout as appropriate. Eval, report, SQLite, log, and analysis output
remains under its declared external artifact root. There is no implicit
`$HOME`, `$HOME/.cache`, or `$HOME/.local` fallback.

The command family is:

```bash
"$BOOTSTRAP" "${COMMON[@]}" install
"$BOOTSTRAP" "${COMMON[@]}" update
"$BOOTSTRAP" "${COMMON[@]}" sync --install-root "$HOME/agent-canon" --remote origin --branch main
"$BOOTSTRAP" "${COMMON[@]}" scheduler enable
"$BOOTSTRAP" "${COMMON[@]}" scheduler status
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

The invocation cwd is informational only; it is not used to select runtime
state and no cwd warning is emitted. The flow is `cwd -> bootstrap.sh ->
install root -> control root -> <install-root>/.runtime/ -> resident
container`. `install` creates the verified image and resident, `update`
reconciles the current checkout in that resident, and `status` reads back the
active image and resident health from `.runtime/`. `gc --dry-run` follows the
same identity and ownership reads without preparing or changing `.runtime/`;
`gc` performs the exact owned Docker cleanup under the replacement lock and
includes the resident controller's state/cache/lease GC receipt.

`target add` is explicit because the shared runtime never scans a workspace
or mounts a whole home directory. `read-only` is the default and is required
for analysis. `explicit-target-write` is available only for an operation whose
documented mutation capability names its target and allowed paths.

`install` is a clean reconstruction transition. After SourceSync has selected
the current source generation, it resets the reconstructible lifecycle state
and target projection before creating the resident; the new install therefore
starts with no prior target or rollback generation. Receipts, pending spool,
archive, and cache evidence remain available. `update` and `target add` may
remove only syntactically valid, derived target registry entries whose host
source is missing, not a directory, or a symlink; all other live target
entries remain unchanged. `target add` applies the same stale entry cleanup
before adding the requested mapping and returns an unchanged receipt when
that mapping and the resident are already current. `start`, `exec`, and
`tool` never prune the registry: a missing registered target is a terminal
error in those execution paths.

The command emits a typed JSON receipt. Keep receipts under the selected
runtime root; they are operational evidence, not source files. A failed
operation returns a stable error code and preserves the previous state where
the operation has a generation or ownership boundary.

The host creates the canonical `.runtime/source-sync.json` record before any
resident container is created and mounts that file read-only at
`/var/lib/agent-canon/source-sync.json`. The host shell is the only source-sync
state writer. Resident status and dashboard readers consume this mounted file;
`container-state/source-sync.json` is not a state surface.

The source-sync record uses schema `agent-canon.source-sync.v1` and contains
`status`, `code`, `updated_at`, `source_root`, `remote`, `remote_url`, `branch`,
`source_head`, and `source_tree`. A `failed` record additionally contains
`failure`; a `success` record does not. Shell status and resident dashboard
readers accept only this complete shape. Legacy, incomplete, or wrongly typed
records are reported as unavailable and are replaced only by the next atomic
host sync transition.

### Install source transition

The public install path has one SourceSync admission transition after argument
and path parsing but before Docker command discovery, host runtime
initialization, image build, or resident reconciliation. It fetches
`refs/heads/main` explicitly into `refs/remotes/origin/main` and admits the
checkout only when `git rev-parse HEAD` is exactly equal to
`git rev-parse refs/remotes/origin/main`. Fetch and commit-read failures remain
typed operational failures. The transition never switches branches, inspects
working-tree cleanliness, expands shallow history, or reads a source tree for
admission; tree identity in the host source-sync receipt is telemetry only.

After the commit match, install deletes the exact AgentCanon-owned resident
and reconstructible runtime projection, then builds and starts the new
resident. Old `mounts.tsv`, target paths, rollback files, resident layout or
security configuration, and UID/rootless details are not install inputs.
Foreign or unlabeled Docker resources remain untouched. A failure in source
admission, owned-state deletion, build, or start is terminal for that
invocation; target registration and tool execution remain separate operations.

## What is installed and where

`install` creates the runtime state directories and adopts the published GHCR
image when the source was installed by the distribution route. Development
and CI checkouts may still use the ordinary Docker build from
`bootstrap/container/image/Dockerfile`; live `sync` never builds locally. The image
is one OCI index for `linux/amd64` and `linux/arm64`; Docker selects the native
variant without a user platform selector. `start` creates or starts at most
one manifest-owned container. The image contains the Rust CLI, Python tools,
configured LSP servers, and the AgentCanon-owned eval definitions/configuration
needed to evaluate a source-free target. Container process identity and
UID/GID mapping are owned by the host/caller environment; AgentCanon does not
create a user, pass `--user`, or validate that policy. A matching pre-existing
image tag is adopted by exact ID without overwrite; an unowned pre-existing
image remains outside uninstall.

After install, update, or rollback readback, `host-state/active-image.tsv`
atomically records the exact resident `Config.Image` reference and immutable
image ID. Ordinary `start`, `status`, `target`, `tool`, and Codex routes consume
that record; they do not recompute a source-derived image tag. Candidate image
selection is limited to install/update/sync, and rollback may persist the
immutable ID used to recreate the resident.

`update` reads only the current AgentCanon checkout. It never fetches,
checks out, merges, rebases, resets, or pulls Git state. Without `--image-ref`
it performs one ordinary Docker build; with an immutable `--image-ref` it
adopts only an already-pulled registry image. A handled build or health
failure restores the existing v2 generation, container, and image.
`sync` is the one-shot source/update route. It uses `git ls-remote` for
`origin/main`, treats equal HEAD as a no-op, clones a fresh full-history
checkout under runtime staging, pulls `:sha-<full-commit>`, verifies the OCI
revision, RepoDigest, and native platform, then atomically swaps the full
checkout transactionally while preserving the bootstrap-owned `.runtime/`, then runs
`update --image-ref`, `start`, and `codex prepare`. A pull,
health, or candidate bootstrap failure restores the previous checkout and
runtime; the source checkout's commit history remains available for logs and
diagnostics.
`main` and `latest` are discovery labels only and are never runtime identity.

On Linux and WSL with a usable systemd user manager, `install` enables the
one-shot `agent-canon-sync.timer`; its service exits after one sync. The timer
is owned by `scheduler enable`, `disable`, `status`, and `uninstall`. Hosts
without systemd user support, macOS, and native Windows remain one-shot-only;
no daemon, webhook listener, cron route, or `loginctl enable-linger` is added.
`install` and `update` converge the explicit control-root Codex views into split
per-entry links. With `$HOME` as control root, these are
`~/.agents/skills/<skill>` to the ignored source view, `~/.codex/agents/<role>.toml`
to the tracked role file, and `~/.codex/config.toml` to the ignored personal
source under the AgentCanon checkout. An existing regular Codex config is moved
byte-for-byte (including mode) before linking; update preserves it and uninstall
restores a regular file. Foreign entries and foreign symlinks are preserved or
reported as collisions. Project hooks and user authentication, session,
history, cache, plugins, rules, MCP, and TUI/trust settings are outside this
projection. `codex prepare` remains the separate runtime-local isolated home
route.

The container is bounded by the manifest: two CPUs, 4 GiB memory, 512 PIDs,
network disabled, read-only root filesystem, all Linux capabilities dropped,
no-new-privileges, and a writable `/tmp` tmpfs. The default maximum is two
admitted tasks, one shared resident container, and a 30-minute task timeout
with a 10-second termination grace period. Runtime, task, cache, and archive
lease quotas are checked before garbage collection.

`codex prepare` creates a manifest-managed, isolated `codex-home/` beneath the
selected runtime root and `codex launch` sets `CODEX_HOME` only for the launched
process. Separately, with `$HOME` as explicit control root, install/update own
split global skill and role links plus the one personal `~/.codex/config.toml`
link described above. Existing conflicting paths fail closed; only links
recorded in the strict runtime `global-links.tsv` manifest can be removed by
`uninstall`, which restores the regular personal config. Foreign links are not
scanned or removed. Start a new Codex session after an install or update and
read back both global links and runtime-local targets.

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
`gc` removes only exact stale Docker container IDs and image tag references or
IDs carrying both the AgentCanon runtime label and the current control-root
label. It keeps the live resident, its `Config.Image`, active image state,
rollback identity, and images of kept containers. It never uses `docker system
prune`, prefix matching, or foreign/other-control resources. The resident
controller's existing GC continues to enforce completed, unpinned,
manifest-owned task/cache/archive semantics; an unpublished spool retains its
archive cache. `uninstall` removes only this installation's image,
container, and managed links after checking that no task is active. It retains
the external state, owner record, and receipts for absence readback; after that
readback the installation runtime directory may be removed as the final
task-owned cleanup. Foreign global Codex entries remain untouched; exact
AgentCanon-managed links are removed or restored as described above.

## Tool routes and compatibility

Rust first-class commands keep their existing public shape, for example
`agent-canon docs check` and `agent-canon semantic-index`. Python tools do not
gain flat global executables. A catalog entry is runnable through
`tool run` only after its versioned schema-v2 parity record verifies argv,
cwd, standard streams, exit/signal behavior, and written paths. The
dispatcher rejects shell command strings and unknown catalog entries.

Until parity is verified, an internal Python file is not exposed through the
public bootstrap command family. Do not infer that an internal Python file is
a public catalog command.

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
`agents/`, `.codex/`, or `eval/`. Producer failure is recorded
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
  -> tool run -> template export / eval collect -> eval sync -> stop -> gc -> uninstall
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
