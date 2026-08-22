# AgentCanon CLI Entrypoints

<!--
@dependency-start
contract reference
responsibility Defines the sole Host entrypoint and typed command routes for the standalone AgentCanon runtime.
upstream implementation ../../bootstrap.sh owns Host lifecycle admission
upstream design ../../documents/runtime/bootstrap-runtime.md owns runtime, target, eval, and cleanup semantics
downstream implementation ../../tools/agent_tools/bootstrap_runtime.py implements the command family
downstream design ./CODEX_WORKFLOW.md consumes task and closeout routes
@dependency-end
-->

## Host entrypoint

`bootstrap.sh` is the only supported Host entrypoint. Do not call Python/Rust
tools through a copied tree, a `tools/agent-canon` alias, a vendor checkout, or
the global Host environment.

```bash
BOOTSTRAP=/path/to/agent-canon/bootstrap.sh
CONTROL=<authorized-parent-root>
RUNTIME="$CONTROL/workspace/agent-canon-runtime/<installation>"
TARGET=<selected-source-or-project-root>
COMMON=(--control-parent-root "$CONTROL" --runtime-root "$RUNTIME")

"$BOOTSTRAP" "${COMMON[@]}" install
"$BOOTSTRAP" "${COMMON[@]}" start
"$BOOTSTRAP" "${COMMON[@]}" target add --root "$TARGET" --mode read-only
```

The control root and runtime root are explicit on every call. A target is not
discovered by scanning the parent workspace.

## Tool commands

Use a catalog ID when parity is verified:

```bash
"$BOOTSTRAP" "${COMMON[@]}" tool run --root "$TARGET" route -- --list
```

Use the retained argv-only compatibility route for a catalog entry that is
still classified as `legacy-route`. The command runs inside the resident tool
container with the target as its working directory:

```bash
"$BOOTSTRAP" "${COMMON[@]}" exec --root "$TARGET" -- \
  agent-canon graph build --root . --profile default --format json
```

No route accepts a shell command string. Python tools use their image path or
a catalog ID; they do not gain flat global executable names.

## Task and Codex routes

Task admission and release are explicit:

```bash
"$BOOTSTRAP" "${COMMON[@]}" task admit --task-id <task-id> --root "$TARGET"
"$BOOTSTRAP" "${COMMON[@]}" task release --task-id <task-id> --outcome completed
```

`codex prepare` creates an isolated runtime-local Codex home. `codex launch`
sets `CODEX_HOME` only for the launched child:

```bash
"$BOOTSTRAP" "${COMMON[@]}" codex prepare
"$BOOTSTRAP" "${COMMON[@]}" codex launch --project-root "$TARGET"
```

## Evaluation and archive

```bash
"$BOOTSTRAP" "${COMMON[@]}" eval collect --root "$TARGET" --run-id <run-id>
"$BOOTSTRAP" "${COMMON[@]}" eval sync --run-id <run-id>
```

Collection runs the registered producers inside the tool image. Sync is the
Host Git publication adapter and completes only after remote ref/tree/blob
readback from `agent-canon-log`.

## Closeout

```bash
"$BOOTSTRAP" "${COMMON[@]}" status
"$BOOTSTRAP" "${COMMON[@]}" stop
"$BOOTSTRAP" "${COMMON[@]}" gc
"$BOOTSTRAP" "${COMMON[@]}" uninstall
```

After absence readback, remove the exact task-owned runtime directory. Never
use `docker system prune`; never remove a resource that is not bound to the
installation's recorded ID and ownership labels.

Project builds, tests, GPU selection, and application dependencies remain
project-owned and do not run through this tool container.
