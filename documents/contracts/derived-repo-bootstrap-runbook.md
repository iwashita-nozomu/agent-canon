<!--
@dependency-start
contract reference
responsibility Documents the source-free parent onboarding route for standalone AgentCanon.
upstream design ../runtime/bootstrap-runtime.md owns the explicit runtime contract.
upstream design ../agent-canon/agent-canon-update-route.md owns source publication and readback.
upstream implementation ../../bootstrap.sh owns lifecycle commands.
@dependency-end
-->

# Parent project bootstrap runbook

A normal project clone is source-free. It does not initialize an AgentCanon
vendor checkout, Git submodule, source symlink, root projection, or AgentCanon
runtime. Project code and project tests remain owned by the parent repository.

## Optional AgentCanon tool runtime

When a task needs AgentCanon Python/Rust/LSP tools, start one explicit shared
runtime from the standalone AgentCanon source checkout:

```bash
ROOT=<authorized-parent-root>
COMMON=(--control-parent-root "$ROOT")

./bootstrap.sh "${COMMON[@]}" install
./bootstrap.sh "${COMMON[@]}" start
./bootstrap.sh "${COMMON[@]}" status
./bootstrap.sh "${COMMON[@]}" target add --root <project-root> --mode read-only
./bootstrap.sh "${COMMON[@]}" stop
./bootstrap.sh "${COMMON[@]}" gc
./bootstrap.sh "${COMMON[@]}" uninstall
```

The control root must be the authorized parent checkout. Runtime state is
always the bootstrap-owned ignored `.runtime/` under the source checkout;
legacy runtime arguments are migration input only and do not select a new
placement. Runtime cache,
reports, eval collections, Codex home, Cargo output, and temporary files stay
under the external runtime root.

## Source and project boundaries

AgentCanon source changes are made in an ignored qualified clone under
`workspace/agent-canondevelop/<qualified-task>/agent-canon`, published through
an Issue-qualified AgentCanon PR, and read back from merged `main`. Parent
project implementation and tests are run through the parent-owned Docker/test
entrypoint. No parent command may restore a vendor checkout or submodule as a
fallback.

## Migration write boundary

Migrating an existing parent from a vendored/live AgentCanon integration is a
management-edge removal, not a project environment refactor. Before editing,
the current task scope update lists each authorized path with its operation,
the exact AgentCanon edge being removed/replaced, and owner evidence. This
`management_write_set` is the complete migration write authority.
Every row uses an existing exact path and, for a mixed file, an exact span;
placeholders and directory globs leave `migration_status=unresolved` and grant
no edit authority.
An unresolved candidate is reported outside `management_write_set`; annotating
an inexact row as non-authoritative does not make it a valid row.

Authorized changes are limited to an evidenced AgentCanon gitlink/submodule
and `.gitmodules` entry, AgentCanon-owned root projections/source symlinks/
updater state, exact AgentCanon dispatch/reference spans in mixed parent files,
and docs/instructions that describe the new source-free/bootstrap route.

The following remain parent-owned and immutable unless their own owner and a
separate Issue/approval explicitly authorize a semantic change:

- `docker/**`, `.devcontainer/**`, image/build definitions, and dependency set;
- product/numerical code and tests;
- UID/GID, sudoers, `safe.directory`, permission, bind-mount, and rootless policy;
- GPU behavior and product runtime semantics;
- project acceptance criteria and parent CI beyond an exact AgentCanon dispatch edge.

For a mixed file, remove or reconnect only the exact AgentCanon span while
preserving the surrounding parent behavior. If another change is necessary,
set `migration_status=parent_owner_handoff_required` and stop before editing
that surface; do not expand the migration write set.

Closeout reports `source_free_boundary` and `parent_product_validation`
separately. The former proves the exact migration hunks and unchanged immutable
surfaces. The latter belongs to the parent owner and neither receipt substitutes
for the other.

## Failure triage

| Symptom | First check |
| --- | --- |
| missing or invalid runtime | verify explicit control/runtime arguments and containment |
| source becomes dirty after inspection | inspect source/runtime path ownership and stop the task |
| AgentCanon change is needed | create/update the qualified standalone source PR |
| eval/archive publication fails | preserve the external spool and failure receipt for retry |
| project test fails | classify the parent project execution plane separately |
