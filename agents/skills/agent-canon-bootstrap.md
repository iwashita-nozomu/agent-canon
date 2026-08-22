# AgentCanon Bootstrap
<!--
@dependency-start
contract skill
responsibility Owns the host-controlled lifecycle of the shared AgentCanon tool runtime.
upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared runtime, target, and archive boundary
upstream implementation ../../bootstrap.sh sole host bootstrap entrypoint
upstream implementation ../../tools/agent_tools/bootstrap_runtime.py typed control-plane implementation
upstream implementation ../../tools/agent_tools/tool_dispatch.py namespaced tool dispatch and parity boundary
downstream design ./agent-eval-accumulation.md eval evidence collection and archive handoff
downstream implementation ../../tests/bootstrap/test_bootstrap_runtime.py lifecycle contract tests
downstream implementation ../../tests/tools/test_bootstrap_container_contract.py image and dispatch contract tests
@dependency-end
-->

Use this skill when AgentCanon's shared Python, Rust, or language-server tool
runtime must be installed, started, inspected, targeted, updated, or removed.
It is also the owner for the user path from an explicit project target to a
namespaced `agent-canon tool run` request and for collecting the resulting eval
evidence.

## Boundary

- `bootstrap.sh` is the only host entrypoint. Always pass explicit
  `--repository-root`, `--control-parent-root`, and `--runtime-root`; the
  control root must be the authorized parent workspace and the runtime root a
  child of it. Do not fall back to the source tree or a global `$HOME` path.
- One shared, non-root AgentCanon tool container owns Python/Rust/LSP tools.
  It is not a project container, does not receive the Docker socket or
  credentials, and does not own project dependencies, builds, or tests.
- Register a project root with `target add` before using it. Target admission
  and the active generation are read back before dispatch. Concurrent target
  changes are serialized by the bootstrap lifecycle; a failed candidate keeps
  the last verified generation active.
- `tool run` is the verified namespaced route. `exec` is the explicitly
  observed bootstrap compatibility route and must not be used as an
  unverified replacement for tool parity. Never create flat host wrappers.
- Project code is tested through the project-owned `docker/` image and
  `test/testrunner.sh`/test list. Do not mount a project's tests into the
  AgentCanon tool container and do not make AgentCanon know project test names.
- Runtime state, cache, task receipts, and eval artifacts live below the
  explicit external runtime root. The AgentCanon source checkout stays free of
  runtime output, generated reports, skill links, and tool caches.
- Eval collection is append-only and is handed to the repository-qualified
  `iwashita-nozomu/agent-canon-log` archive through the host adapter. Never
  write archive output back into the AgentCanon source tree.

## User Flow

1. Resolve the task and project owner first. Use the project repository's
   normal Docker/test runner for project execution; select this skill only for
   AgentCanon tools or their lifecycle.
2. Choose task-qualified control/runtime roots under the authorized parent
   workspace, then run `status`. Install/start the shared runtime only when
   status says it is absent or stale. Keep at most one task-owned AgentCanon
   tool container and one image generation; record IDs for cleanup.
3. Add the exact project root as a read-only target, or request the explicit
   target-write capability when a tool contract genuinely requires a write.
   Read back target identity, mode, active generation, and container health.
4. Invoke the catalog-qualified command through `tool run --root <project> <catalog-id> -- ...`.
   Preserve the receipt's argv, cwd, input/output, exit/signal, written paths,
   execution plane, and responsibility owner. A failure in the tool plane is
   not a project-code failure; report the plane and exact owner separately.
5. For eval work, run the registered producers, collect the run bundle, sync
   it through the archive adapter, and verify the remote repository and commit
   readback. Use `$agent-eval-accumulation` for the producer/checker details.
6. Stop/release task leases, remove only resources created by this task, run
   scoped garbage collection, and verify the source checkout and unrelated
   Docker resources are unchanged. Keep the closeout receipt and cleanup
   evidence outside the source tree.

## Command Shape

The concrete root values are task inputs; placeholders below must never be
silently inferred:

```bash
bash bootstrap.sh \
  --repository-root . \
  --control-parent-root <authorized-parent-workspace> \
  --runtime-root <authorized-parent-workspace>/agent-canon-runtime status

bash bootstrap.sh \
  --repository-root . \
  --control-parent-root <authorized-parent-workspace> \
  --runtime-root <authorized-parent-workspace>/agent-canon-runtime \
  target add --root <project-root> --mode read-only

bash bootstrap.sh \
  --repository-root . \
  --control-parent-root <authorized-parent-workspace> \
  --runtime-root <authorized-parent-workspace>/agent-canon-runtime \
  tool run --root <project-root> <catalog-id> -- <args...>
```

Use `install`, `start`, `stop`, `rollback`, `uninstall`, and `gc --dry-run`
only with the same explicit roots and task lifecycle evidence. `eval collect`
and `eval sync --run-id <run-id>` are the only bootstrap eval routes. Any
non-zero result remains a typed failure; do not retry through a project
container, a source checkout fallback, or an unqualified legacy command.

## Closeout

Report the repository-qualified Issue/PR, source and image identities, target
and active-generation readback, execution plane, tool/project responsibility,
eval archive commit/readback, and exact task-owned cleanup. If a required
health, parity, target, archive, or cleanup readback is missing, stop with the
typed evidence instead of claiming completion.
