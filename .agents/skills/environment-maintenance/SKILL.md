---
name: environment-maintenance
description: Use when touching Docker, CI, dependencies, runtime compatibility, or repository-level development environment instructions.
---
<!--
@dependency-start
@dependency-end
-->


# Environment Maintenance

1. Treat `docker/` as the shared environment canon.
1. Update `docker/packs/*.toml`, `docker/codex-container-profiles.toml`, and `docker/python-execution-rules.toml` when runtime selection behavior changes.
1. When the main server host assumptions change, update `documents/server-host-contract.md` and the server layout templates in the same change.
1. Start from `agents/templates/environment_change_proposal.md` when proposing a new repo-wide tool or dependency.
1. Update dependency definitions and related docs in the same change.
1. Check CI and local validation commands together.
1. Use `documents/coding-conventions-project.md`, `documents/tools/README.md`, `documents/server-host-contract.md`, and `docker/README.md`.
1. Do not canonize host-global installs as the repository default.
1. Keep canonical `safe.directory` policy in the Docker image itself rather than a runtime-only entrypoint hack.
1. Prefer a container-wide git config mechanism that still works when the runtime remaps `uid:gid` or `HOME`.
