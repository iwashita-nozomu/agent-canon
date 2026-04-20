# エージェント運用の入口

この文書は repo 運用から見た agent 運用の薄い入口です。

## 正本

- [agents/README.md](../agents/README.md)
- [agents/canonical/README.md](../agents/canonical/README.md)
- [agents/agents_config.json](../agents/agents_config.json)
- [agents/TASK_WORKFLOWS.md](../agents/TASK_WORKFLOWS.md)
- [agents/COMMUNICATION_PROTOCOL.md](../agents/COMMUNICATION_PROTOCOL.md)
- [agents/canonical/ARTIFACT_PLACEMENT.md](../agents/canonical/ARTIFACT_PLACEMENT.md)
- [agents/canonical/CLI_ENTRYPOINTS.md](../agents/canonical/CLI_ENTRYPOINTS.md)
- [agents/canonical/CODEX_WORKFLOW.md](../agents/canonical/CODEX_WORKFLOW.md)
- [agents/canonical/CODEX_SUBAGENTS.md](../agents/canonical/CODEX_SUBAGENTS.md)
- [agents/skills/README.md](../agents/skills/README.md)
- [agents/skills/catalog.yaml](../agents/skills/catalog.yaml)

## Runtime Entry Points

- [AGENTS.md](../AGENTS.md)
- [CLAUDE.md](../CLAUDE.md)
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

## Skills

- Canonical path: `.agents/skills/`
- Claude compatibility: `.claude/skills/` (generated from `.agents/skills/`)

## 実行入口

標準の run bundle を作るときは次を使います。

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "short task summary" \
      --task-id T1 \
      --owner "codex-or-human" \
      --workspace-root "$PWD"

研究・実験つき変更:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "research-backed change" \
      --task-id T4 \
      --owner "codex" \
      --workspace-root "$PWD"

環境変更:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "platform or environment change" \
      --task-id T8 \
      --owner "codex" \
      --workspace-root "$PWD"

学術文章:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "academic writing task" \
      --task-id T10 \
      --owner "codex" \
      --workspace-root "$PWD"

包括的開発:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "comprehensive development pass" \
      --task-id T12 \
      --owner "codex" \
      --workspace-root "$PWD"

`experimenter` が有効な run では `experiment_change_loop.md`、`infra_steward` が有効な run では `environment_change_proposal.md` も bundle に含めます。
環境変更 run では `infra_steward` が requirements/plan/design の前に `triggering code requirement`、`blocked command`、`source-of-truth surface` を proposal に固定してから handoff します。
`notation_definition_reviewer` と `logic_gap_reviewer` が有効な run では、学術文章の記号定義と論理飛躍を別 reviewer で閉じます。
`citation_evidence_reviewer` が有効な run では、論文 draft の major claim が citation、figure、table、derivation、appendix、result に辿れるかを別 reviewer で閉じます。
code change を含む run では `test_designer` が `test_plan.md` を作り、worker はそれを test 実装へ落とします。
包括的開発では bundle に加えて `project_reviewer` を parent が read-only で立て、必要なら `docs_workflow_steward`、`python_reviewer`、`cpp_reviewer` を追加します。
`--task-id` は task catalog の default specialist と default review pack をそのまま bundle に反映します。

Codex parent session では、planning を含む場合に plan-mode command を使って構いません。official Codex CLI では `/plan` です。
runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない runtime では `.codex/agents/*.toml` を正本にします。

artifact-only role や review role の write scope を確認するときは、`validate_role_write_scope.py` を使います。

    python3 tools/agent_tools/validate_role_write_scope.py \
      --report-dir reports/agents/<run-id> \
      --workspace-root "$PWD" \
      --report-snapshot-out /tmp/agent-report-before.json \
      --workspace-snapshot-out /tmp/agent-workspace-before.json

    python3 tools/agent_tools/validate_role_write_scope.py \
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
- 論文 draft では `citation_evidence_reviewer` も兼務させません。
- `implementer` 以外が repo ファイルを直接編集する運用を正本にしません。
- 包括的開発では、同一 worktree の writer を `implementer` 1 人に固定します。
- 複数 writer が必要な場合は、同一 worktree ではなく複数 worktree に分けます。
- run 固有の artifact は `reports/agents/<run-id>/` に寄せ、repo-wide の正本と混ぜません。
