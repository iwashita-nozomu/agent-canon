<!--
@dependency-start
responsibility Documents legacy jax_solver_util tool imports retained for provenance.
upstream design ../../../documents/repo-local-tool-imports.md records import disposition
downstream implementation scripts/README.md indexes the imported legacy scripts
@dependency-end
-->

# jax_solver_util Legacy Tool Imports

This directory preserves repo-local tools imported from
`/mnt/l/workspace/jax_solver_util/scripts/` during the 2026-05-05 consolidation
pass.

These files are not canonical AgentCanon defaults. They are retained so future
PRs can promote, rewrite, or delete them with provenance instead of rediscovering
them repo by repo.

Promotion requirements:

- remove project-specific `/workspace` or `jax_util` assumptions;
- add current dependency manifests;
- pass strict style/static checks for the promoted path;
- add tests or deterministic help-smoke evidence;
- update `documents/repo-local-tool-imports.md`.
