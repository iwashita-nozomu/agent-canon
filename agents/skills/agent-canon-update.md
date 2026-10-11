# AgentCanon Update Skill

<!--
@dependency-start
contract workflow
responsibility Owns editing, publishing, and consuming AgentCanon as a standalone source repository.
upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared runtime design
upstream design ../../documents/runtime/bootstrap-runtime.md user lifecycle contract
upstream implementation ../../bootstrap.sh Host lifecycle entrypoint
downstream design ../../documents/runtime/runtime-log-archive.md eval archive owner
@dependency-end
-->

## Purpose

Use this skill when a task changes AgentCanon source, its shared tool runtime,
bootstrap image, skills, workflow contracts, or the parent-to-AgentCanon update
route. The source deliverable is one reviewed change and its published PR.
When parent adoption is also requested, the parent consumes the selected revision
through its own update contract, without vendoring or copying AgentCanon internals.

Issue ownership must be explicit. `iwashita-nozomu/agent-canon#841` owns local
bootstrap, one shared tool container, source side-effect isolation, skill
installation, eval collection, and `agent-canon-log` publication. `#821` owns
prebuilt artifact build/distribution. Do not place local lifecycle work under
#821 or treat a distribution artifact as the lifecycle implementation.

## Source checkout and workspace

Edit the AgentCanon repository itself or a repository-topic checkout prepared by
the canonical lifecycle. For a Template or derived parent, use
`<anchor>/workspace/<topic>/agent-canon`; select `linked-worktree` for a
parent/same-repository branch and `independent-clone` for a dependency
repository. Do not restore a submodule, vendor checkout, root projection,
source symlink, `notes/`, or AgentCanon test/eval directory in the parent. The
prepared checkout is task-owned. Remove it once no active work needs it and
the selected publication/evidence obligations preserve its state; do not retain
it solely to wait for an unrequested merge or runtime update.

Keep the source checkout clean at the start. Preserve unrelated dirty state;
do not reset, clean, or delete an unknown path. Record the source remote,
current branch, HEAD, and issue/PR identity before editing.

## Source-Free Parent Migration Boundary

A request to remove a parent repository's vendored/live AgentCanon integration
authorizes migration of AgentCanon management edges only. It does not authorize
a parent environment, product runtime, numerical stack, test, permission,
mount, GPU, dependency, or CI semantics refactor merely because those surfaces
refer to AgentCanon.

Before any parent edit, add this bounded readback to the existing task scope
update. It is not a new schema or durable packet:

```text
source_free_parent_issue=<repository-qualified Issue>
management_write_set=<exact path + operation + AgentCanon edge + owner evidence, one row per path>
immutable_parent_surfaces=<matched parent-owned paths or semantics>
mixed_file_limit=<exact AgentCanon dispatch/reference span only>
migration_status=unresolved|ready|parent_owner_handoff_required
```

Every write-set row names one existing exact path and, for a mixed file, the
exact dispatch/reference span. Placeholders, directory-wide globs, and
unresolved paths are not write authority. Keep `migration_status=unresolved`
and perform no parent mutation until every proposed row is exact.
Do not place an unresolved candidate in `management_write_set` even with a
"no authority" annotation; report it only as an unresolved item in the task
update.

The management write set may contain only evidenced operations from this list:

- remove an AgentCanon gitlink/submodule and its matching `.gitmodules` entry;
- remove AgentCanon-owned root projections, source symlinks, or updater state;
- remove or replace the exact AgentCanon dispatch edge in a mixed parent-owned
  entrypoint, preserving the existing parent command and behavior;
- update parent instructions/docs only to describe the source-free boundary,
  qualified ignored development clone, and external bootstrap route.

Treat `docker/**`, `.devcontainer/**`, product/numerical tests and code,
UID/GID/sudo/`safe.directory`, bind mounts and rootless policy, GPU behavior,
product dependencies/runtime semantics, parent acceptance criteria, and parent
CI other than an exact AgentCanon dispatch edge as immutable by default. A
reference from one of these surfaces to AgentCanon permits removal of that
dispatch/reference span only; it does not transfer ownership of the containing
surface.

If the migration cannot complete without another change, stop before that edit
and hand the exact path, required operation, owner, and validation route to the
parent owner under a separate Issue/approval. Do not widen
`management_write_set` to absorb the blocker.

Report two separate validation results: `source_free_boundary` proves every
changed path/hunk belongs to the management write set and immutable surfaces
are unchanged; `parent_product_validation` is selected and interpreted only by
the parent owner. A parent product test result cannot authorize an out-of-scope
migration edit, and a source-free boundary pass cannot claim product behavior.

## Runtime bootstrap

The only lifecycle entrypoint is top-level `bootstrap.sh`. It requires an
authorized parent control root; the default runtime is the ignored,
reconstructible `<install-root>/.runtime/`:

```bash
ROOT=<authorized-parent-root>
BOOTSTRAP=./bootstrap.sh
COMMON=(--control-parent-root "$ROOT")

"$BOOTSTRAP" "${COMMON[@]}" install
"$BOOTSTRAP" "${COMMON[@]}" start
"$BOOTSTRAP" "${COMMON[@]}" target add --root <project-root> --mode read-only
"$BOOTSTRAP" "${COMMON[@]}" status
```

There is no implicit `$HOME`, `$HOME/.cache`, `$HOME/.local`, global
`CODEX_HOME`, source-tree general artifact directory, or project-local fallback.
Only bootstrap-owned `.runtime/` is permitted under the install source; other
runtime roots must not escape through a symlink. One control root uses one
shared image and at most one resident tool container; task directories and
exact target mounts provide isolation. Never create a project/task-specific
AgentCanon image, container, virtualenv, Cargo toolchain, or volume.

`sync` is the automatic-update route. It acquires `replacement.lock` once and
runs `git -C <install-root> fetch origin main` followed by
`git -C <install-root> checkout --force -B main FETCH_HEAD`; this leaves the
installed checkout on local `main` at the fetched remote revision. It then
writes `.runtime/source-sync/source-sync.json`, selects the shared
`:env-<key>` image through `digest.sh`, and reuses the resident when
the environment and source/cache mounts are current. Otherwise it pulls or
builds the environment once, updates the resident, and refreshes host-owned
links and the timer. There is no candidate checkout, remote-ref comparison,
Git rollback, or second source-sync lock. A missing systemd user manager is a
warning and leaves manual `sync` available.

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
`codex-home/`; it remains separate from the global link lifecycle. When the
explicit control root is `$HOME`, install/update manage one `~/.agents/skills`
directory link, per-agent, and personal `~/.codex/config.toml` links. A regular
config is copied to the ignored personal source before the canonical
`model_context_window = 1050000` and
`model_auto_compact_token_limit = 900000` settings are applied; other personal
TOML remains intact. Uninstall restores a regular file from that source. Hooks,
authentication, sessions, history, cache, plugins, rules,
MCP, and TUI/trust state remain outside the link set. The host shell owns
global link projection; the resident does not enumerate or validate global
skills. Uninstall removes the AgentCanon-owned skills directory link only.
After update, launch a new session.

## Tool route

Preserve the existing public Rust command shape. Do not add flat global Python
executables. A catalog entry uses its typed route:

```bash
"$BOOTSTRAP" "${COMMON[@]}" tool run --root <project-root> <catalog-id> -- <args...>
```

The dispatcher validates the typed descriptor, registered target, authenticated
runtime, and requested output capability when the command runs. It rejects
shell command strings and unknown ids. For a caller-selected direct command,
use the explicit argv route:

```bash
"$BOOTSTRAP" "${COMMON[@]}" exec --root <registered-project> -- <existing-command> <args...>
```

Do not infer that every internal Python file is public, and keep Rust
first-class commands on their existing public shape.

## Side-effect and eval rules

Analysis must pass with a read-only source target. A mutation operation must
declare target root, allowed paths, purpose, authority, before/after identity,
and a receipt. Runtime logs, reports, evals, dashboard output, cache, Cargo
target, SQLite, tmp, and `__pycache__` go to the external runtime root.

Runtime, eval, and archive validation must leave the AgentCanon source status
and content unchanged. Compare the source before and after validation; any
source delta is a validation failure. Cleanup removes only transient resources
owned by the current task; persistent shared runtime and install state may
remain in place.

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

Resolve the owning Issue, current remote `main`, relevant PRs, and checkout
identity from the task. Keep #841 and #821 with their separate owners. Reuse or
create an Issue-qualified topic branch through `repository-topic-clone` in the
qualified standalone source checkout; choose checkout mode from the repository
relationship and use `$agent-update-branch` for lane selection. The parent does
not become the AgentCanon source checkout.

Read the canonical owner, the callers that can affect the selected mechanism,
and the validation oracle for the requested change. For a source-free parent
migration, freeze the exact management write set and immutable parent surfaces
before any parent edit. The design record follows the open decision: when a
cross-surface contract such as command shape, state roots, resource cap,
rollback, archive route, cleanup, or validation remains unresolved, settle it
in the existing design trace; for a bounded change with settled ownership,
carry the decision in the existing task record.

Implement in the owning AgentCanon clone, keeping affected docs, manifests,
code, tests, and dependency headers aligned. Runtime, cache, eval, and test
outputs stay under the external runtime root, not source-local `.agent-canon`,
`target`, `__pycache__`, or generated-report directories. Do not modify a parent
checkout from this skill. Choose validation from the changed owner and its
execution plane. Preserve failures and unavailable checks as observed; for
runtime/container changes, remove only task-created Docker resources and never
run `docker system prune`.

When source PR delivery is selected, commit only the Issue-owned write set, push
the topic branch, and open or update the AgentCanon PR through `$pr-processing`.
Record scope, validation, cleanup, limitations, and Issue/PR identity on both
surfaces. PR delivery does not authorize merge, parent adoption, or runtime
deployment. If merge or adoption is requested, use `$pr-processing`, then verify
the merged commit and tree in fetched `main`. Consumer-owned PR-pin validation
follows [dependency-module-change](dependency-module-change.md); it does not
restore a vendor/submodule route.

## Validation and closeout

For bootstrap/runtime implementation changes, select the applicable checks:

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

For PR handoff, verify the published source head, changed paths, selected
validation, Issue/PR references, and preservation of unrelated state. Record
missing validation as unverified, not as a passed check or an implicit request
to rebuild the environment. Merge-commit/main readback applies only after an
authorized merge.

Only when the corresponding runtime/lifecycle operation is in scope, verify:

- new bootstrap session uses the explicit control/runtime roots;
- only one owned resident container exists and its limits/readback match;
- source, parent, foreign global Codex entries, and pre-existing Docker
  resources are unchanged; only exact managed global links may change;
- eval collection is in the external spool and archive publication has remote
  readback, or its failure receipt and pending spool are intentionally kept;
- stop/gc/uninstall removed only exact task-owned resources;
- a new Codex session read back isolated skills/agents/hooks/config.

## References

- [Standalone Bootstrap And Shared Tool Runtime](../../documents/runtime/bootstrap-runtime.md)
- [Container Operations](../../CONTAINER_OPERATIONS.md)
- [Runtime Log Archive](../../documents/runtime/runtime-log-archive.md)
- [Source-free parent bootstrap runbook](../../documents/contracts/derived-repo-bootstrap-runbook.md)
