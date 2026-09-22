# AgentCanon Bootstrap
<!--
@dependency-start
contract skill
responsibility Owns the host-controlled lifecycle of the shared AgentCanon tool runtime.
upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared runtime, target, and archive boundary
upstream implementation ../../bootstrap.sh sole host bootstrap entrypoint
upstream implementation ../../tools/runtime/container/bootstrap_runtime.py typed control-plane implementation
upstream implementation ../../tools/runtime/dispatch/tool_dispatch.py namespaced tool dispatch and parity boundary
downstream design ./agent-eval-accumulation.md eval evidence collection and archive handoff
downstream implementation ../../tests/bootstrap/test_bootstrap_runtime.py lifecycle contract tests
downstream implementation ../../tests/agent_tools/test_execution_route_order.py command order regression
downstream implementation ../../tests/tools/test_bootstrap_container_contract.py image and dispatch contract tests
@dependency-end
-->

Use this skill when AgentCanon's shared Python, Rust, or language-server tool
runtime must be installed, started, inspected, targeted, updated, or removed.
It is also the owner for the user path from an explicit project target to a
namespaced `agent-canon tool run` request and for collecting the resulting eval
evidence.

## Boundary

- `bootstrap.sh` is the only host entrypoint. The host adapter invokes no
  AgentCanon Python; it builds/adopts the image and starts exactly one resident
  container before using `docker exec` for the controller. Always pass explicit
  `--repository-root` and `--control-parent-root`; the effective runtime is
  always the bootstrap-owned, ignored `<repository-root>/.runtime/`.
  `--control-parent-root` authorizes access but never selects runtime or log
  placement. The historical `--runtime-root` value is accepted only as a
  migration-compatible input and cannot create new state at that path.
- Host pre-container values are the fixed bootstrap constants in
  `bootstrap/host/lifecycle/entrypoint.sh` (install/runtime paths, image/container limits,
  and mount destinations). Do not add a generic TOML parser or duplicate the
  structured catalog/state policy in shell.
- One shared AgentCanon tool container owns Python/Rust/LSP tools and the
  container-side TOML/JSON/state/eval controller. Docker
  command availability is assumed; container process identity and UID/GID
  mapping remain host/caller policy and are not validated here.
  It is not a project container, does not receive the Docker socket or
  credentials, and does not own project dependencies, builds, or tests. The
  host owns the complete Docker lifecycle transaction; the controller has no
  Docker RPC or package fallback path. Target additions/removals update the
  strict runtime `mounts.tsv` manifest; the host applies only its validated
  target rows when replacing the resident.
- The dispatcher owns required target admission and active-generation checks.
  Invoke the prescribed tool command first; do not prepend a separate target or
  health preflight. After a target-related rejection, use the existing target
  owner to diagnose and, when authorized, register the exact root. Concurrent
  target changes remain serialized; a failed candidate keeps the last verified
  generation active.
- `tool run` is the verified namespaced route. Internal Python/Rust/LSP tools
  are not exposed as host commands or compatibility choices. Never create flat
  host wrappers.
- Project code is tested through the project-owned `docker/` image and
  `test/testrunner.sh`/test list. Do not mount a project's tests into the
  AgentCanon tool container and do not make AgentCanon know project test names.
- Bootstrap lifecycle state and cache live in the ignored, reconstructible
  `<repository-root>/.runtime/`. The private `agent-canon-log` checkout is the
  sibling `<repository-root>/../agent-canon-log`, independent of the control
  root. General eval/report/SQLite/log/
  analysis artifacts remain outside the source checkout; the artifact output
  boundary does not permit `.runtime` as a source-local exception.
- When the explicit control root is `$HOME`, install/update manage one
  `~/.agents/skills` directory link, `~/.codex/agents/<role>.toml`, and
  `~/.codex/config.toml` links. The last points to the ignored personal config
  source under the AgentCanon checkout; existing regular config bytes and mode
  are migrated losslessly and restored on uninstall. Project hooks and
  authentication, session, history, cache, plugins, rules, MCP, and TUI/trust
  state remain outside this link set. `codex prepare` remains runtime-local.
- `sync` acquires `replacement.lock` once, runs exactly `git -C
  <install-root> pull --ff-only origin main`, publishes
  `.runtime/source-sync/source-sync.json`, and selects the shared
  `:env-<key>` image through `bootstrap/container/image/digest.sh`.
  An exact local image and resident with current source/cache mounts are
  reused; otherwise the image is pulled or built once and the resident is
  replaced. Detached and shallow checkouts are accepted when Git accepts the
  pull. No remote-ref comparison, candidate checkout, Git rollback, or
  secondary source-sync lock is allowed. Source-mounted Rust tools are then
  compiled by the container's generic `tools/**/Cargo.toml` scan into cache/bin.
  For caller compatibility, sync also accepts and ignores historical
  `--remote` and `--branch` arguments; the operation always uses `origin main`.
- Eval collection is append-only and is handed to the repository-qualified
  `iwashita-nozomu/agent-canon-log` archive through the host adapter. Never
  write archive output back into the AgentCanon source tree.

## User Flow

1. Resolve the task and project owner first. Use the project repository's
   normal Docker/test runner for project execution; select this skill only for
   AgentCanon tools or their lifecycle.
2. Reuse the source install root and authorized control root, then invoke the
   catalog-qualified `tool run --root <project> <catalog-id> -- ...` directly.
   Preserve argv, cwd, input/output, exit/signal, written paths, execution plane,
   and responsibility owner from the result. Success needs no route preflight.
3. Only after failure, diagnose the relevant route. Use `status` for an unresolved
   runtime failure or target readback for a target rejection; do not scan every
   surface or infer a project-code failure from a tool-plane rejection.
4. Install/start or `target add` only for an explicit lifecycle request or an
   authorized repair of that failure. Default new targets to read-only; writes
   require the existing target-write authority. Read back the changed target or
   generation, then retry only when allowed. Preserve the one-container/image
   limit and record task-created resource IDs for cleanup.
5. For eval work, run the registered producers, collect the run bundle, sync
   it through the archive adapter, and verify the remote repository and commit
   readback. Producer definitions and manifests come from the image-owned
   AgentCanon snapshot; the registered project remains only the observed,
   read-only target. Use `$agent-eval-accumulation` for the producer/checker
   details.
6. Stop/release task leases, remove only resources created by this task, run
   scoped garbage collection, and verify the source checkout and unrelated
   Docker resources are unchanged. Keep the closeout receipt and cleanup
   evidence outside the source tree.

The host records the exact resident `Config.Image` reference and immutable ID
in `host-state/active-image.tsv` after install/update/rollback readback.
All ordinary routes consume that record; only candidate-producing install,
update, and sync paths derive a new image reference.

## Command Shape

The control root is a task input; the effective runtime is always the fixed
bootstrap path `<repository-root>/.runtime`:

```bash
bash bootstrap.sh \
  --repository-root . \
  --control-parent-root <authorized-parent-workspace> \
  tool run --root <project-root> <catalog-id> -- <args...>
```

After a relevant failure, `status` or target readback uses the same roots.
Use `target add --root <project-root> --mode read-only`, `install`, `update`,
`start`, `stop`, `rollback`, `uninstall`, or `gc --dry-run` only for the selected
lifecycle operation, not as a checklist before ordinary execution. `eval collect`
and `eval sync --run-id <run-id>` are the only bootstrap eval routes. Any
non-zero result remains a typed failure; do not retry through a project
container, a source checkout fallback, or an unqualified legacy command.
Successful target add/remove operations materialize the same strict rollback
plan from the resident generation snapshot. `rollback` therefore restores a
target-only generation without rebuilding the image and rewrites the plan for
the opposite generation so a second rollback can toggle back.

`codex launch` first runs `codex prepare` in the resident and then invokes the
host Codex executable with the managed runtime `CODEX_HOME` and project root;
the host Codex binary is never dispatched into the network-disabled resident.
The resident validates the image-owned canonical skill/agent/config bytes, but
the runtime-local `CODEX_HOME` links target the corresponding live
`<install-root>/.codex/...` paths on the host. The config link is directly at
`CODEX_HOME/config.toml`, so the host Codex process can read it without a HOME
mount.
`eval sync` is a two-plane route: resident Python validates the collection and
writes only a strict body-free request, while the host shell resolves the
registered target mount and invokes the credentialed archive Git adapter.
Successful `exec` feedback/knowledge sync uses the same request handoff; the
resident never imports or calls the archive publisher.

## Closeout

Report the repository-qualified Issue/PR, exact command/result, execution plane,
and tool/project responsibility. Use identities and generation evidence already
returned by execution; ordinary success does not require separate health probes.
For selected lifecycle/eval work, report its required target, archive, and exact
task-owned cleanup readback. Missing evidence remains unverified, not complete.
