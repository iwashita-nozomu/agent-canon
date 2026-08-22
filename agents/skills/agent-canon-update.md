# AgentCanon Update Skill

<!--
@dependency-start
contract workflow
responsibility Owns editing, publishing, and consuming AgentCanon as a standalone source repository.
upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared runtime design
upstream design ../../documents/runtime/bootstrap-runtime.md user lifecycle contract
upstream design ../workflows/agent-canon-pr-workflow.md standalone source PR route
upstream implementation ../../bootstrap.sh Host lifecycle entrypoint
downstream design ../../documents/runtime/runtime-log-archive.md eval archive owner
@dependency-end
-->

## Purpose

Use this skill when a task changes AgentCanon source, its shared tool runtime,
bootstrap image, skills, workflow contracts, or the parent-to-AgentCanon update
route. The goal is one source repository, one reviewed source change, one
published AgentCanon revision, and a parent that consumes that revision without
vendoring or copying AgentCanon internals.

Issue ownership must be explicit. `iwashita-nozomu/agent-canon#841` owns local
bootstrap, one shared tool container, source side-effect isolation, skill
installation, eval collection, and `agent-canon-log` publication. `#821` owns
prebuilt artifact build/distribution. Do not place local lifecycle work under
#821 or treat a distribution artifact as the lifecycle implementation.

## Source checkout and workspace

Edit the AgentCanon repository itself or a qualified development clone. For a
Template or derived parent, the clone belongs under the parent's ignored
`workspace/agent-canondevelop/<qualified-task>/agent-canon`. Do not restore a
submodule, vendor checkout, root projection, source symlink, `notes/`, or
AgentCanon test/eval directory in the parent. The clone is disposable and is
removed only after branch, PR, main readback, and archive/evidence obligations
are complete.

Keep the source checkout clean at the start. Preserve unrelated dirty state;
do not reset, clean, or delete an unknown path. Record the source remote,
current branch, HEAD, and issue/PR identity before editing.

## Runtime bootstrap

The only lifecycle entrypoint is top-level `bootstrap.sh`. It requires an
authorized parent control root and a runtime root beneath it:

```bash
ROOT=<authorized-parent-root>
RUNTIME="$ROOT/workspace/agent-canon-runtime/<installation>"
BOOTSTRAP=./bootstrap.sh
COMMON=(--control-parent-root "$ROOT" --runtime-root "$RUNTIME")

"$BOOTSTRAP" "${COMMON[@]}" install
"$BOOTSTRAP" "${COMMON[@]}" start
"$BOOTSTRAP" "${COMMON[@]}" target add --root <project-root> --mode read-only
"$BOOTSTRAP" "${COMMON[@]}" status
```

There is no implicit `$HOME`, `$HOME/.cache`, `$HOME/.local`, global
`CODEX_HOME`, source-tree `.agent-canon`, or project-local fallback. The
runtime root must not escape through a symlink. One control root uses one
shared image and at most one resident tool container; task directories and
exact target mounts provide isolation. Never create a project/task-specific
AgentCanon image, container, virtualenv, Cargo toolchain, or volume.

The container is for AgentCanon Python, Rust, and LSP tools. Project Docker,
project `test/testrunner.sh`, GPU, Git, GitHub, and Codex host launch remain in
their owning environment. Rootful/rootless Docker mode is not a branch; the
container process uses a non-root UID in either mode.

## Codex and skills

Run:

```bash
"$BOOTSTRAP" "${COMMON[@]}" codex prepare
"$BOOTSTRAP" "${COMMON[@]}" codex launch --project-root <project-root>
```

`prepare` writes only manifest-managed links beneath runtime-local isolated
`codex-home/`. It does not overwrite global skills, agents, hooks, config, or
`CODEX_HOME`. Collisions fail closed; uninstall removes only links owned by
this installation. After update, launch a new session and read back manifest,
link target, and source digest. Existing sessions do not reload links.

## Tool and compatibility route

Preserve the existing public Rust command shape. Do not add flat global Python
executables. A Python/Rust catalog entry may use:

```bash
"$BOOTSTRAP" "${COMMON[@]}" tool run --root <project-root> <verified-catalog-id> -- <args...>
```

only after schema-v2 parity evidence verifies argv, cwd, stdin/stdout/stderr,
exit/signal behavior, and written paths. The dispatcher rejects shell command
strings, unknown ids, and unverified entries. Until parity is verified, keep
the legacy exact command and invoke it through its owner or:

```bash
"$BOOTSTRAP" "${COMMON[@]}" exec --root <registered-project> -- <existing-command> <args...>
```

Do not infer that every internal Python file is public. A parity failure is a
compatibility finding, not permission to silently change the command plane.

## Side-effect and eval rules

Analysis must pass with a read-only source target. A mutation operation must
declare target root, allowed paths, purpose, authority, before/after identity,
and a receipt. Runtime logs, reports, evals, dashboard output, cache, Cargo
target, SQLite, tmp, and `__pycache__` go to the external runtime root.

Use the existing eval producers and archive owner. `eval collect` writes a
versioned collection to the runtime spool and records source identity, tool
digest, family status, metrics, and source unchanged. `eval sync` sends the
spool through the typed host Git adapter to
`iwashita-nozomu/agent-canon-log`; it does not implement a second publisher.
Archive branch and retention belong to the log repository. On network/archive
failure, preserve spool and failure receipt for retry. Complete publication
requires non-force push and remote ref/tree/blob readback. Never write eval or
archive state into the AgentCanon source checkout.

## Change route

1. Resolve the owning Issue and read the current remote/main, open PRs, and
   relevant runtime documents. Keep #841 and #821 separate.
2. Inspect the existing owner and implementation before proposing a change.
   Search beyond the first failing checker and identify source-side effects,
   impossible branches, duplicate gates, and downstream consumers.
3. Record a contract-complete design: user command family, host/container
   boundary, target mode, state roots, resource cap, failure/rollback, eval
   archive route, cleanup, and validation oracle.
4. Implement in the owning AgentCanon clone. Keep docs, manifest, code, tests,
   and dependency headers aligned. Do not modify a parent checkout from this
   skill.
5. Run focused tests first. For runtime/container changes, verify exact owned
   Docker image/container IDs and remove task-created resources at closeout;
   never run `docker system prune`.
6. Run the canonical AgentCanon PR checks selected by the changed runtime
   profile. Confirm source tree unchanged by eval and archive collection, and
   confirm external artifact paths and archive readback.
7. Commit with the owning Issue reference, push the topic branch, open/update
   the AgentCanon PR, and publish a concise evidence comment to the same Issue.
   The PR body must state what changed, why, scope, validation, and remaining
   limitation.
8. After merge, fetch and read back the merge commit on AgentCanon `main`.
   Only then update a parent revision. A parent must not consume an unmerged
   branch or restore a vendor/submodule route.

## Validation and closeout

At minimum, run:

```bash
git diff --check
python3 -m pytest -q tests/bootstrap tests/tools/test_bootstrap_container_contract.py
python3 -m pytest -q tests/agent_tools/test_runtime_artifacts.py \
  tests/agent_tools/test_tool_dispatch.py
```

Select additional checks from
[Runtime Profiles And Check Matrix](../../documents/runtime/runtime-profiles-and-check-matrix.md).
For documentation-only changes, run the Markdown link/header checks and
`git diff --check`. Test output must name whether the failure belongs to the
AgentCanon tool runtime, host adapter, archive owner, or project execution
environment.

Before closeout, verify:

- source branch is clean except intended commit and its remote is pushed;
- Issue/PR are qualified as `iwashita-nozomu/agent-canon#...`;
- new bootstrap session uses the explicit control/runtime roots;
- only one owned resident container exists and its limits/readback match;
- source, parent, global `$CODEX_HOME`, and pre-existing Docker resources are
  unchanged;
- eval collection is in the external spool and archive publication has remote
  readback, or its failure receipt and pending spool are intentionally kept;
- stop/gc/uninstall removed only exact task-owned resources;
- a new Codex session read back isolated skills/agents/hooks/config.

## References

- [Standalone Bootstrap And Shared Tool Runtime](../../documents/runtime/bootstrap-runtime.md)
- [Container Operations](../../CONTAINER_OPERATIONS.md)
- [Runtime Log Archive](../../documents/runtime/runtime-log-archive.md)
- [AgentCanon PR workflow](../workflows/agent-canon-pr-workflow.md)
