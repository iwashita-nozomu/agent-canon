# エージェント運用の入口

この文書は repo 運用から見た agent 運用の薄い入口です。

## 正本

- [agents/README.md](/mnt/l/workspace/project_template/agents/README.md)
- [agents/canonical/README.md](/mnt/l/workspace/project_template/agents/canonical/README.md)
- [agents/agents_config.json](/mnt/l/workspace/project_template/agents/agents_config.json)
- [agents/TASK_WORKFLOWS.md](/mnt/l/workspace/project_template/agents/TASK_WORKFLOWS.md)
- [agents/COMMUNICATION_PROTOCOL.md](/mnt/l/workspace/project_template/agents/COMMUNICATION_PROTOCOL.md)
- [agents/canonical/ARTIFACT_PLACEMENT.md](/mnt/l/workspace/project_template/agents/canonical/ARTIFACT_PLACEMENT.md)
- [agents/canonical/CLI_ENTRYPOINTS.md](/mnt/l/workspace/project_template/agents/canonical/CLI_ENTRYPOINTS.md)
- [agents/canonical/CODEX_WORKFLOW.md](/mnt/l/workspace/project_template/agents/canonical/CODEX_WORKFLOW.md)
- [agents/canonical/CODEX_SUBAGENTS.md](/mnt/l/workspace/project_template/agents/canonical/CODEX_SUBAGENTS.md)
- [agents/skills/README.md](/mnt/l/workspace/project_template/agents/skills/README.md)
- [agents/skills/catalog.yaml](/mnt/l/workspace/project_template/agents/skills/catalog.yaml)

## Runtime Entry Points

- [AGENTS.md](/mnt/l/workspace/project_template/AGENTS.md)
- [CLAUDE.md](/mnt/l/workspace/project_template/CLAUDE.md)
- [.github/copilot-instructions.md](/mnt/l/workspace/project_template/.github/copilot-instructions.md)

## Skills

- Canonical path: `.agents/skills/`
- Claude compatibility: `.claude/skills/` (generated from `.agents/skills/`)

## 実行入口

標準の run bundle を作るときは次を使います。

    python3 scripts/agent_tools/bootstrap_agent_run.py \
      --task "short task summary" \
      --owner "codex-or-human"

`experimenter` が有効な run では `experiment_change_loop.md`、`infra_steward` が有効な run では `environment_change_proposal.md` も bundle に含めます。

artifact-only role や review role の write scope を確認するときは、`validate_role_write_scope.py` を使います。

    python3 scripts/agent_tools/validate_role_write_scope.py \
      --report-dir reports/agents/<run-id> \
      --workspace-root "$PWD" \
      --report-snapshot-out /tmp/agent-report-before.json \
      --workspace-snapshot-out /tmp/agent-workspace-before.json

    python3 scripts/agent_tools/validate_role_write_scope.py \
      --role change_reviewer \
      --report-dir reports/agents/<run-id> \
      --report-snapshot-in /tmp/agent-report-before.json \
      --workspace-snapshot-in /tmp/agent-workspace-before.json \
      --workspace-root "$PWD"

## repo 側の運用ルール

- role 定義と write policy は `agents/agents_config.json` を正本にします。
- handoff、review、response、escalation の書式は `agents/COMMUNICATION_PROTOCOL.md` を正本にします。
- 共通 workflow と skill routing は `agents/` 側で保守し、runtime entrypoint へ role 一覧を重複記載しません。
- `implementer` 以外が repo ファイルを直接編集する運用を正本にしません。
- run 固有の artifact は `reports/agents/<run-id>/` に寄せ、repo-wide の正本と混ぜません。
