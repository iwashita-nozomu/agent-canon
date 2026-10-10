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
  always the bootstrap-owned, ignored `<control-parent-root>/.runtime/`.
  `--control-parent-root` selects the shared runtime authority while the
  private log placement remains owned by the install-root parent. The
  historical `--runtime-root` value is accepted only as a
  migration-compatible input and cannot create new state at that path.
  When the same control-root resident already exists, the host reuses that
  control-root runtime and the resident's named state volume; it does not
  infer a source-checkout runtime or create another authority.
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
  `<control-parent-root>/.runtime/`. The private `agent-canon-log` checkout is the
  sibling `<repository-root>/../agent-canon-log`, independent of the control
  root. General eval/report/SQLite/log/
  analysis artifacts remain outside the source checkout; the artifact output
  boundary does not permit `.runtime` as a source-local exception.
- When the explicit control root is `$HOME`, install/update manage one
  `~/.agents/skills` directory link, `~/.codex/agents/<role>.toml`, and
  `~/.codex/config.toml` links. The last points to the ignored personal config
  source under the AgentCanon checkout; existing regular config bytes and mode
  are migrated before the two canonical context settings are applied, while
  unrelated personal TOML remains intact. Those settings are
  `model_context_window = 1050000` and
  `model_auto_compact_token_limit = 900000`. The saved source is restored on
  uninstall. Project hooks and
  authentication, session, history, cache, plugins, rules, MCP, and TUI/trust
  state remain outside this link set. `codex prepare` remains runtime-local.
- `install` and `sync` use one source transition under `replacement.lock`:
  `git -C <install-root> fetch origin main` followed by
  `git -C <install-root> checkout --force -B main FETCH_HEAD`. It publishes
  `.runtime/source-sync/source-sync.json`; sync then selects the shared
  `:env-<key>` image through `bootstrap/container/image/digest.sh`.
  An exact local image and resident with current source/cache mounts are
  reused; otherwise the image is pulled or built once and the resident is
  replaced. No remote-ref comparison, candidate checkout, Git rollback, or
  secondary source-sync lock is allowed. Source-mounted Rust tools are then
  compiled by the container's generic `tools/**/Cargo.toml` scan into cache/bin.
  For caller compatibility, `sync` accepts and ignores `--remote` and `--branch`;
  the source remote and branch remain fixed to `origin main`.
- Eval collection is append-only and is handed to the repository-qualified
  `iwashita-nozomu/agent-canon-log` archive through the host adapter. Never
  write archive output back into the AgentCanon source tree.

## User Flow

Resolve the task and project owner before selecting this skill. Use the project
repository's normal Docker/test runner for project code, and use this runtime
only for AgentCanon tools or lifecycle operations. The installer entrypoint
comes from the installed runtime source root; pass the observed project or
worktree separately as a read-only `--root <topic>` target. Use the latest
installed/bootstrap absolute entrypoint; a topic checkout's `./bootstrap.sh`
may be stale and is only for validating lifecycle-source changes.

For an ordinary tool request, reuse the source install and authorized control
roots, then invoke the catalog-qualified `tool run --root <project> <catalog-id>
-- ...` directly.
Carry the actual argv, cwd, input/output, exit/signal, written paths, execution
plane, and owner from its result; success needs no route preflight.

If a tool fails, diagnose only the relevant route: use `status` for an unresolved
runtime failure or target readback for a target rejection. A tool-plane failure
does not establish a project-code failure. Install/start or add a target only
for an explicit lifecycle request or an authorized repair. Targets remain
read-only; authoring uses the tool's output and host publication. Read back the
changed target or generation, retry only when the owner permits it, and retain
the one-container/image limit and task-created resource IDs for cleanup.

Eval collection is its own selected branch: run registered producers, collect
the run bundle, sync through the archive adapter, and verify remote repository
and commit readback. Producer definitions and manifests come from the
image-owned AgentCanon snapshot; the registered project remains a read-only
observation target. Use `$agent-eval-accumulation` for producer/checker detail.

When a selected lifecycle operation creates leases or resources, release or
remove only those task-owned items through the existing owner. Use scoped
garbage collection for cleanup and confirm pre-existing source and unrelated
Docker state remain untouched. Routine successful tool use creates no cleanup
or health-probe requirement. Keep cleanup evidence outside the source tree.

The host records the exact resident `Config.Image` reference and immutable ID
in `host-state/active-image.tsv` after install/update/rollback readback.
All ordinary routes consume that record; only candidate-producing install,
update, and sync paths derive a new image reference.

## Command Shape

Use the absolute installed AgentCanon source root as `INSTALL_ROOT`; the
project or topic checkout is a separate `--root` target. The effective runtime
is always the fixed bootstrap path `<control-parent-root>/.runtime`:

```bash
INSTALL_ROOT=<absolute-installed-agent-canon-root>
BOOTSTRAP="$INSTALL_ROOT/bootstrap.sh"
ROOT=<authorized-parent-workspace>
COMMON=(--repository-root "$INSTALL_ROOT" --control-parent-root "$ROOT")
"$BOOTSTRAP" "${COMMON[@]}" \
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
