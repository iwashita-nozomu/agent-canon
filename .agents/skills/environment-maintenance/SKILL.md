---
name: environment-maintenance
description: Use when touching Docker, CI, dependencies, runtime compatibility, or repository-level development environment instructions.
---
<!--
@dependency-start
contract skill
responsibility Documents Environment Maintenance for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../CONTAINER_OPERATIONS.md canonical container and devcontainer ownership boundary
@dependency-end
-->


# Environment Maintenance

## Tool Commands

<!-- skill-tool-commands:start -->
この skill の workflow を適用する前に、次の command packet を使用してください。

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill environment-maintenance --format text
```

論理コマンドは、実行前に AgentCanon source root を基準として解決します。各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、fallback-only skill を含む script entry の script path は絶対 path にします。

packet が出力した必須 command と、task に該当する conditional command を実行してください。
<!-- skill-tool-commands:end -->


1. Treat `CONTAINER_OPERATIONS.md` as the source of truth for Dockerfile, `docker/`, `.devcontainer/`, validator, and Makefile target ownership. This skill is only the routing checklist.
1. Update `docker/packs/*.toml`, `docker/codex-container-profiles.toml`, and `docker/python-execution-rules.toml` when runtime selection behavior changes.
1. When the main server host assumptions change, update `documents/contracts/server-host-contract.md` and the server layout templates in the same change.
1. Start from `templates/agents/environment_change_proposal.md` when proposing a new repo-wide tool or dependency.
1. Update dependency definitions and related docs in the same change.
1. Check CI and local validation commands together.
1. Use `CONTAINER_OPERATIONS.md`, `documents/conventions/coding-conventions-project.md`, `documents/contracts/github-first-module-and-devcontainer-policy.md`, `documents/tools/README.md`, `documents/contracts/server-host-contract.md`, and `docker/README.md`.
1. Do not canonize host-global installs as the repository default.
1. Follow `CONTAINER_OPERATIONS.md` when deciding whether a tool belongs in repo-local Dockerfile / `docker/` or AgentCanon-owned `.devcontainer/`.
1. Update mechanical enforcement in `tools/docker_dependency_validator.sh` when the boundary changes.
1. When environment or CI validation failure drives a repair, record the
   validation-failure-response packet (`failing_contract`, `observation_level`,
   `cause_classification`, `intent_preservation`, and `evidence`) before
   downscoping validation or weakening an oracle.
