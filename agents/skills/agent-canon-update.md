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
directory link, per-agent, and personal `~/.codex/config.toml` links. The regular config is
migrated byte-for-byte to the ignored personal source and restored on
uninstall. Hooks, authentication, sessions, history, cache, plugins, rules,
MCP, and TUI/trust state remain outside the link set. The host shell owns
global link projection; the resident does not enumerate or validate global
skills. Uninstall removes the AgentCanon-owned skills directory link only.
After update, launch a new session.

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

1. Resolve the owning Issue and read the current remote `main`, open PRs and
   Issues, and relevant runtime documents. Record repository-qualified branch,
   HEAD, remote, and dirty-state evidence; keep #841 and #821 separate.
2. Reuse or create one Issue-qualified topic branch in the qualified
   standalone source clone. Branch reuse and creation reasons follow
   `$agent-update-branch`; the parent never becomes the source checkout.
3. Read the canonical owner, dependency-expanded callers, and selected
   validation oracle before editing.
4. For a source-free parent migration, freeze the exact management write set
   and immutable parent surfaces above before inspecting implementation.
5. Inspect the existing owner and implementation before proposing a change.
   Search beyond the first failing checker and identify source-side effects,
   impossible branches, duplicate gates, and downstream consumers.
6. Record a contract-complete design: user command family, host/container
   boundary, target mode, state roots, resource cap, failure/rollback, eval
   archive route, cleanup, and validation oracle.
7. Implement in the owning AgentCanon clone. Keep docs, manifest, code, tests,
   and dependency headers aligned. Runtime/cache/eval/test artifacts use the
   explicit external runtime root and never create source-local `.agent-canon`,
   `target`, `__pycache__`, or generated reports. Do not modify a parent
   checkout from this skill.
8. Run focused validation and then the profile selected by the changed owner.
   Preserve failure evidence by execution plane (AgentCanon tool container,
   host adapter/archive, or project execution); for runtime/container changes,
   remove task-created Docker resources at closeout and never run
   `docker system prune`.
9. Commit only the Issue-owned write set, push the topic branch, and open or
   update the AgentCanon PR through `$pr-processing`. Its body states what
   changed, why, scope, validation, cleanup, and remaining limitations; add a
   concise evidence comment to the same qualified Issue. `$pr-processing`
   owns review routing and CI; merge only after the required review and CI are
   green.
10. After merge, fetch AgentCanon `main`, verify that the fetched `main`
   contains the merge commit, and read the merge commit and resulting `main`
   tree back locally. Only then update a parent revision. A parent must not
   consume an unmerged branch or restore a vendor/submodule route.

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
- repository-qualified Issue identity, source branch, PR, merge commit, and
  local `main` readback are traceable; no exact phrase or Issue number in the
  commit message is required;
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
