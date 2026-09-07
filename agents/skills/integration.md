# integration
<!--
@dependency-start
contract skill
responsibility Integrates a prepared local branch into its selected base and closes conflict/tree readback.
upstream design ../canonical/CODEX_WORKFLOW.md authorized branch and commit lifecycle
upstream design ../../documents/operations/BRANCH_SCOPE.md commit correctness and integration scope
upstream design ./worktree-health.md checkout health and cleanup readback
upstream design ./pr-processing.md GitHub Issue/PR publication boundary
downstream implementation ../../.codex/personal/skills/integration/SKILL.md runtime discovery shim
@dependency-end
-->

## Purpose

Integrate a prepared local branch into its selected local base while preserving
the branch's complete tree and the intent of its changes. This skill owns the
local merge, conflict handling, and post-merge readback. It does not publish or
merge GitHub pull requests.

## Use When

- a topic or integration branch must be merged into a local base branch;
- a move, rename, delete, symlink, or other structural change must survive
  integration;
- a local merge conflict needs resolution against the source responsibility and
  the target contract.

Do not select this skill for GitHub Issue/PR inventory, publication, approval, or
remote merge; use `pr-processing`. Use `worktree-health` for checkout drift,
stale workspaces, and cleanup.

## Integration Contract

Before the merge, the caller supplies the source and base identities, the
authorized integration checkout, the source validation result, and the changed
path/owner scope. Preserve unexplained dirty or untracked state; it is not a
merge input until `worktree-health` classifies it.

The integration unit is the Git merge and its readback. Do not reconstruct a
structural change with file copy, `git checkout <path>`, ad-hoc cherry-pick, or
manual recreation of deleted content. Keep the source tree shape, including
renames, deletions, file types, and links, unless a conflict decision is backed
by the owning contract.

Run the merge in the current authorized integration checkout. This skill does
not create a new `git worktree`. `--no-ff` is not a default acceptance rule:
use it only when the selected branch/commit contract requires a merge commit;
otherwise the repository's normal fast-forward or merge route is sufficient.

For a structural source diff, the changed-scope tree comparison is the
semantic readback: compare every source-side path involved in an add, delete,
rename, symlink, or file-type change with the same path at the integration
commit. The comparison proves that the source tree shape survived integration;
it does not prove behavior or replace the changed owner validation.

## Route

1. Read the checkout identity and selected source/base refs once at the
   transition into integration. Run `worktree-health` when checkout drift,
   carry-over, or cleanup is in scope.
2. Confirm the source branch's selected validation and changed-path scope. Do
   not repeat checks already closed by the source owner merely because a merge
   is starting.
3. On the authorized integration checkout, merge the source branch into the
   selected base using the repository's normal Git route. Keep the merge
   conflict visible; do not reset, discard, or narrow the source diff to make
   the command pass.
4. For each conflict, read the competing blocks and their callers/consumers or
   path owners. Resolve according to the source contract, target contract, and
   intended tree shape. If the contracts disagree, return a typed conflict to
   the owning design/review route instead of inventing a compatibility path.
5. After the merge, read back only the changed structural paths and their direct
   owner/consumer edges. Confirm that required additions, renames, deletions,
   file types, and links match the source integration intent and that no
   conflict markers remain. When the source diff contains structural paths,
   the existing targeted owner check may provide this comparison:

   ```bash
   python3 tools/validation/ci/checks/check_merge_structure.py \
     --source <source-ref> \
     --target <base-ref> \
     --compare-commit <integration-commit> \
     --repo-root <checkout-root>
   ```

   Do not run this command for a content-only merge, turn it into a full-tree
   scan, or add a second checker.
6. Run the selected post-merge validation once at the owning unit boundary.
   The selected owner decides whether a behavioral check is needed; this skill
   does not add a generic full suite, tree checker, or convention gate.
7. Return the source ref, base ref, merge result, resolved conflict paths,
   changed-tree readback, validation command/result, and unresolved blockers to
   the caller. GitHub publication remains a separate `pr-processing` operation.

## Failure Semantics

An unresolved conflict, missing source evidence, dirty carry-over, or failed
post-merge validation is a typed incomplete state. Preserve the checkout and
the evidence, classify the owning cause, and route it back to the relevant
owner. Do not delete the source branch, weaken the contract, drop a rename or
deletion, or replace the merge with a smaller patch.

## Boundary

- `worktree-health` owns checkout identity, drift, stale workspace, and cleanup
  diagnosis.
- `pr-processing` owns GitHub Issue/PR lifecycle and remote merge/publication.
- `codex-task-workflow` owns task transport and overall closeout.
- The changed code/document owner owns behavior validation; this skill only
  executes the selected post-merge route and records its readback.

## Expected Output

```text
integration=complete|blocked
source=<ref>
base=<ref>
merge=<sha-or-unresolved>
conflicts=<none-or-paths>
tree_readback=<changed-paths-and-state>
validation=<command-and-result>
unresolved=<none-or-owner-routed-blocker>
```
