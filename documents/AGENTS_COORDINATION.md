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
      --owner "codex-or-human" \
      --workspace-root "$PWD" \
      --enable scheduler \
      --enable schedule_reviewer

研究・実験つき変更:

    python3 scripts/agent_tools/bootstrap_agent_run.py \
      --task "research-backed change" \
      --owner "codex" \
      --workspace-root "$PWD" \
      --enable scheduler \
      --enable schedule_reviewer \
      --enable researcher \
      --enable research_reviewer \
      --enable experimenter \
      --enable experiment_reviewer

環境変更:

    python3 scripts/agent_tools/bootstrap_agent_run.py \
      --task "platform or environment change" \
      --owner "codex" \
      --workspace-root "$PWD" \
      --enable scheduler \
      --enable schedule_reviewer \
      --enable infra_steward \
      --enable infra_reviewer

学術文章:

    python3 scripts/agent_tools/bootstrap_agent_run.py \
      --task "academic writing task" \
      --owner "codex" \
      --workspace-root "$PWD" \
      --enable scheduler \
      --enable schedule_reviewer \
      --enable researcher \
      --enable research_reviewer \
      --enable notation_definition_reviewer \
      --enable logic_gap_reviewer

包括的開発:

    python3 scripts/agent_tools/bootstrap_agent_run.py \
      --task "comprehensive development pass" \
      --owner "codex" \
      --workspace-root "$PWD" \
      --enable scheduler \
      --enable schedule_reviewer \
      --enable researcher \
      --enable research_reviewer \
      --enable infra_steward \
      --enable infra_reviewer \
      --enable critical_guardian

`experimenter` が有効な run では `experiment_change_loop.md`、`infra_steward` が有効な run では `environment_change_proposal.md` も bundle に含めます。
`notation_definition_reviewer` と `logic_gap_reviewer` が有効な run では、学術文章の記号定義と論理飛躍を別 reviewer で閉じます。
包括的開発では bundle に加えて `project_reviewer` を parent が read-only で立て、必要なら `docs_workflow_steward` と `python_reviewer` を追加します。

Codex parent session では、planning を含む場合に `/collab` の `Plan` mode を使って構いません。
runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない runtime では `.codex/agents/*.toml` を正本にします。

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
- 会話だけを根拠に実装へ進めず、`documents/`、`notes/`、`references/` と local library の sweep を先に行います。
- 最初の作業 update では `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言します。
- review feedback は、直前の execution role が反映してから次段へ handoff します。
- 学術文章では `document_flow_reviewer`、`notation_definition_reviewer`、`logic_gap_reviewer`、completeness reviewer を兼務させません。
- `implementer` 以外が repo ファイルを直接編集する運用を正本にしません。
- same file を複数の write-capable role / subagent に同時に割り当てません。
- same directory の parallel write は、file 単位の disjoint write scope を artifact に残せる場合だけ許可します。
- run 固有の artifact は `reports/agents/<run-id>/` に寄せ、repo-wide の正本と混ぜません。
