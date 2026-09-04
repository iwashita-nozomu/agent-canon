<!--
@dependency-start
contract reference
responsibility Defines the standalone AgentCanon source update boundary.
upstream design ../../documents/runtime/bootstrap-runtime.md owns the explicit control/runtime lifecycle.
upstream design ../../agents/skills/agent-canon-update.md owns source branch and PR publication.
upstream implementation ../../bootstrap.sh owns installation, validation, and cleanup.
@dependency-end
-->

# AgentCanon update route

AgentCanon is one standalone source repository. A parent project uses an
ignored qualified development clone under `workspace/agent-canondevelop/` and
consumes a merged AgentCanon `main` revision through its own workflow. This
route does not create or update a vendor checkout, Git submodule, root
projection, source symlink, or copied policy surface.

## Source update

1. Qualify the owning Issue as `iwashita-nozomu/agent-canon#<number>` and read
   the current remote `main`, open PRs, and the source clone state.
2. Create or reuse one Issue-qualified source branch in the ignored development
   clone. Keep unrelated dirty paths intact.
3. Read the owner and dependency-expanded callers before editing. Implement the
   contract-complete source change and keep dependency headers/catalogs aligned.
4. Run focused tests and the changed runtime profile. Runtime cache, reports,
   evals, Cargo output, SQLite state, and temporary files belong below the
   explicit runtime root, never in the source checkout.
5. Commit and publish the source branch, open/update the qualified AgentCanon
   PR, process review/CI, merge it, and fetch/read back the resulting `main`
   revision before changing a parent project.

For a parent source-free migration, read
[`derived-repo-bootstrap-runbook.md`](../contracts/derived-repo-bootstrap-runbook.md)
before mutation. The migration scope contains only the exact AgentCanon
management edges listed in the existing task scope update. Parent Docker,
product/numerical tests, permissions, mounts, GPU, runtime semantics, and
acceptance policy remain outside this source-update route.

## Runtime and publication boundaries

Runtime sessions use the top-level `bootstrap.sh` documented in
[`bootstrap-runtime.md`](../runtime/bootstrap-runtime.md). It owns the
explicit control and runtime roots, while source publication remains an
ordinary standalone Git topic branch and pull request. The source checkout is
never a vendor checkout, submodule worktree, root projection, or source
symlink.

For a source update, use the repository-topic-clone owner to create or reuse
the qualified clone and branch, run the source checks, then use the PR
processing owner to publish and merge the pull request. A parent repository
does not import a pin or run a source synchronization wrapper after merge.

## Evidence and closeout

The update record names the source branch/commit, qualified Issue/PR, selected
validation, runtime root, and cleanup readback. A source-invariant check must
show the source tree unchanged after status/plan inspection. Task-owned Docker
resources and runtime directories are removed by exact identity; foreign global
Codex entries and pre-existing resources are not touched. Exact
AgentCanon-managed links may be reconciled and the personal config is restored
as a regular file during uninstall.
