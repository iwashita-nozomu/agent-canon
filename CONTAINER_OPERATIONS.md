# Container Operations Rulebook

<!--
@dependency-start
contract agent-runtime
responsibility Defines the standalone shared AgentCanon tool container and its host boundary.
upstream design documents/design/agent-canon-bootstrap-tool-runtime.md shared runtime design
upstream design documents/runtime/bootstrap-runtime.md user lifecycle contract
upstream implementation bootstrap/container/Dockerfile shared tool image
upstream implementation tools/agent_tools/bootstrap_runtime.py Host lifecycle owner
downstream implementation tests/bootstrap/test_bootstrap_runtime.py lifecycle validation
@dependency-end
-->

This rulebook applies to the standalone AgentCanon tool runtime. It does not
define a project's product image, test image, GPU policy, or development
environment. Project repositories own those surfaces and run their tests with
their own Docker/test runner.

## Operating boundary

The only supported lifecycle entrypoint is top-level `bootstrap.sh`:

```bash
./bootstrap.sh \
  --control-parent-root <authorized-parent-root> \
  --runtime-root <authorized-parent-root>/workspace/agent-canon-runtime/<id> \
  <operation>
```

The control root is an authorized parent repository. The runtime root must be
inside that root after realpath resolution, with no symlink escape. Do not use
the AgentCanon source tree, an implicit current-directory state directory,
`$HOME/.cache`, `$HOME/.local`, global `$CODEX_HOME`, or a whole workspace/home
mount as a runtime fallback.

The host owns Docker, Git, GitHub, Codex launch, credentials, project builds,
and project tests. The resident container owns only AgentCanon Python, Rust,
and language-server tools. It receives exact allowlisted target mounts and a
task-scoped exchange directory; it does not receive a Docker socket, SSH agent,
GitHub token, host home, arbitrary Git state, or a general network.

The Docker daemon can be rootful or rootless. Bootstrap does not detect or
branch on daemon mode. The image starts its tool process with a non-root UID;
if the host effective UID is 0, the image still uses its configured safe
non-zero UID. Rootfulness of the daemon is not a permission model for tools.

## Shared image and resident container

`bootstrap/container/Dockerfile` is the sole AgentCanon tool image definition.
It reuses dependency planning and installs the configured Python, Rust, and
LSP tools once. It does not contain editor post-create behavior, project
dependencies, project tests, GPU setup, or a Compose workspace lifecycle.

`install` builds or verifies a manifest-owned image generation and records its
digest. `start` creates or starts at most one resident container per effective
owner and control-root digest. Docker labels and manifest readback prevent a
second bootstrap installation from adopting or deleting another installation.
The runtime uses one image/container across registered projects; task
separation is provided by exact target mounts and runtime-root task directories.

The default limits are:

| Resource | Limit |
| --- | --- |
| resident containers | 1 |
| admitted tasks | 2 |
| CPU | 2 |
| memory | 4 GiB |
| PIDs | 512 |
| task timeout | 30 minutes |
| termination grace | 10 seconds |
| network | disabled |
| root filesystem | read-only |
| Linux capabilities | all dropped |
| privilege escalation | `no-new-privileges` |

`/tmp` is a task-local writable tmpfs. Runtime, cache, task-state, log, and
archive-lease quotas are recorded in `bootstrap/manifest.toml`. At 80% of a
quota, `gc` may remove completed and unpinned owned state using LRU order.
Active tasks, current and rollback generations, unpublished spool, and
pre-existing Docker resources are retained.

Do not use `docker system prune`. Stop/remove only exact image and container
IDs recorded as owned by this installation. Before and after an operation,
read back labels, digest, limits, mounts, health, and resource absence.

## Build and installation

Build context is the AgentCanon source repository. The image build must be
single-purpose and bounded; do not create a project image or a per-task image.
The container image has no host credentials and has no network at runtime.
Dependency downloads occur during the explicit image installation route and
are represented by the dependency manifest and image receipt.

The image's final process is non-root and the final root filesystem is
read-only. The runtime exchange is the only writable bind mount. It contains
sanitized task requests/responses and task I/O, with owner/mode/nonce/deadline
validation. Control manifests, credentials, Git metadata, and archive state
are host-owned and stay outside the exchange.

## Target and mount rules

Register each exact project root before execution:

```bash
./bootstrap.sh --control-parent-root <root> \
  --runtime-root <root>/workspace/agent-canon-runtime/<id> \
  target add --root <project-root> --mode read-only
```

`read-only` is the default and the required mode for analysis. A named
`explicit-target-write` operation must provide a target capability, purpose,
allowed paths, before/after identity, and receipt. Registering an entire home,
workspace, or unresolved symlink is rejected. A project test directory is not
an AgentCanon mount requirement.

Target updates run under `lifecycle.lock`:

```text
admission closed
  -> wait for active_task_count=0
  -> validate realpath, mode, collision, and registry
  -> stop old generation and read absence
  -> start candidate
  -> health check and exact mount readback
  -> atomically switch current-generation
  -> reopen admission
```

An active task returns `mount_update_blocked` and leaves the current generation
unchanged. Candidate health/readback failure quarantines the candidate and
keeps the old pointer. Failure to restore the old generation returns
`runtime_unavailable` with pointer, quarantine, and absence receipts. A
candidate and old container are never intentionally active together.

## Command compatibility

Rust first-class routes preserve their existing CLI shape. Python public tools
are exposed through `tool run --root <project> <catalog-id> -- <args...>` only when
the catalog's schema-v2 parity fixture is verified. The fixture compares argv,
cwd, standard streams, exit/signal behavior, and written paths. Shell strings,
unknown IDs, and implicit public status are rejected.

An unverified or legacy command remains on its exact owning route. Run it with
the typed host operation when appropriate:

```bash
./bootstrap.sh --control-parent-root <root> \
  --runtime-root <runtime> exec --root <registered-project> -- <existing-command> <args...>
```

There is no compatibility alias that silently changes a command's plane or
side effects. A parity failure leaves the legacy route authoritative until a
new fixture is reviewed.

## Codex surfaces

`codex prepare` creates a manifest-managed isolated `codex-home/` under the
selected runtime root. `codex launch --project-root <root>` sets
`CODEX_HOME` only in the child process. Global Codex skills, agents, hooks,
configuration, and the user's `$HOME` are not overwritten or mounted.

Colliding pre-existing paths fail closed unless their digest is the same link
already owned by this installation. `uninstall` removes only links recorded as
owned by this manifest. After install/update, launch a new Codex session and
read back the manifest, link targets, and source digests; an existing session
does not magically reload new skills.

## Evaluation and archive

Eval producers run in the tool container and write collection data to the
external runtime-root spool. `eval collect` records run/task/source identity,
source HEAD and unchanged result, AgentCanon/tool digest, family status, and
metrics. It does not write source-local reports.

`eval sync` uses the typed host Git adapter and the existing
`runtime_log_archive_git.py` owner to publish to
`iwashita-nozomu/agent-canon-log`. The log repository owns branch and retention
policy. Network/archive failure keeps the spool and failure receipt for retry.
Publication is complete only after non-force push and remote ref/tree/blob
readback. See [Runtime Log Archive](documents/runtime/runtime-log-archive.md).

## Cleanup and recovery

Use this lifecycle for a normal session:

```text
install -> start -> target add -> status -> codex prepare -> codex launch
  -> tool run or exec -> eval collect -> eval sync -> stop -> gc -> uninstall
```

`status` is the first recovery operation. `rollback` requires zero active tasks
and activates the last verified generation. `stop` removes the owned container
but retains state and spool. `gc` removes only exact eligible owned objects.
`uninstall` requires no active task and removes this installation's managed
container, image generations, links, and state while preserving user roots and
pre-existing resources. Remove the runtime directory only after pending spool,
archive lease, and rollback state have been resolved and absence has been read
back.

## Validation

For image or lifecycle changes, use the focused bootstrap/container tests and
the runtime profile matrix:

```bash
python3 -m pytest -q tests/bootstrap tests/tools/test_bootstrap_container_contract.py
python3 -m pytest -q tests/agent_tools/test_runtime_artifacts.py \
  tests/agent_tools/test_tool_dispatch.py
```

Then run the canonical checks selected by
[Runtime Profiles And Check Matrix](documents/runtime/runtime-profiles-and-check-matrix.md).
Tests must identify whether a failure belongs to the AgentCanon tool runtime,
the host adapter, or the project's own execution environment. A project test
must run from its project-owned Docker/test runner and must not require the
AgentCanon tool container.

## Ownership and issues

- [Issue #841](https://github.com/iwashita-nozomu/agent-canon/issues/841) owns the local bootstrap, shared runtime, source side-effect boundary, skill isolation, eval collection, and archive lifecycle.
- [Issue #821](https://github.com/iwashita-nozomu/agent-canon/issues/821) owns prebuilt AgentCanon artifact build/distribution only.

Keep these issue scopes distinct in commits, PR descriptions, and failure
receipts.
