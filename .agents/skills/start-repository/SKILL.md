---
name: start-repository
description: Use when starting a new GitHub/submodule-first repository from this template after clone, including project slug/display-name setup and AgentCanon submodule validation.
---
<!--
@dependency-start
contract skill
responsibility Documents Start Repository for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Start Repository

## Tool Commands

<!-- skill-tool-commands:start -->
この skill の workflow を適用する前に、次の command packet を使用してください。

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill start-repository --format text
```

論理コマンドは、実行前に AgentCanon source root を基準として解決します。各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、fallback-only skill を含む script entry の script path は絶対 path にします。

packet が出力した必須 command と、task に該当する conditional command を実行してください。
<!-- skill-tool-commands:end -->


1. Use this skill after `git clone <template> <new-project>` when the user is turning the clone into a new repository.
1. Read `documents/contracts/template-bootstrap.md`, `scripts/README.md`, and the AgentCanon documents `documents/agent-canon/agent-canon-github-remote.md` and `documents/runtime/runtime-profiles-and-check-matrix.md`. From a template or derived repo root, resolve the AgentCanon documents as `vendor/agent-canon/documents/agent-canon/agent-canon-github-remote.md` and `vendor/agent-canon/documents/runtime/runtime-profiles-and-check-matrix.md`.
1. Prefer `bash scripts/start_repository.sh --project-slug <slug> --display-name "<name>"` for clone-time setup.
1. Treat GitHub `https://github.com/iwashita-nozomu/agent-canon.git` as the AgentCanon source of truth.
1. Treat local bare repositories only as compatibility mirrors documented by the parent repo, never as new bootstrap defaults.
1. After committing init changes, run `bash scripts/start_repository.sh --validate-only`.
1. Do not create or overwrite local AgentCanon bare repositories from this skill.
