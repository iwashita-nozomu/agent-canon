# subagent-bootstrap

## Purpose

specialist delegation が必要な task で、run bundle、役割分担、write-scope を崩さずに起動します。

## Use When

- run artifact を残したい
- specialist を使う
- reviewer / implementer の責務を分けたい
- 計画レビュー agent、詳細設計レビュー agent、文書通読レビュー agent を分けたい

## Core References

- `agents/TASK_WORKFLOWS.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `scripts/agent_tools/bootstrap_agent_run.py`

## Standard Command

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "repo-changing task" \
  --task-id T1 \
  --owner "codex" \
  --workspace-root "$PWD"
```

研究・実験つき変更:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "research-backed change" \
  --task-id T4 \
  --owner "codex" \
  --workspace-root "$PWD"
```

環境変更:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "platform or environment change" \
  --task-id T8 \
  --owner "codex" \
  --workspace-root "$PWD"
```

学術文章:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "academic writing task" \
  --task-id T10 \
  --owner "codex" \
  --workspace-root "$PWD"
```

包括的開発:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

repo-changing task では、`--task-id` を使って task catalog の default specialist と default review pack をそのまま有効化します。
調査、環境変更、学術文章、包括的開発の強い review coverage は task catalog 側の default として管理します。
code change では `test_designer` を実装前に立て、nasty case を `test_plan.md` に残します。
包括的開発では bundle に加えて `project_reviewer`、`docs_workflow_steward`、`python_reviewer`、必要に応じて `cpp_reviewer` を固定で立てます。
Codex で planning を含む parent session では、plan-mode command を先に使います。official Codex CLI では `/plan` です。
runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を見ます。
計画レビュー agent、詳細設計レビュー agent、文書通読レビュー agent は、同じ instance を使い回しません。
学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` も別 instance を使います。
包括的開発では、同一 worktree の writer を `worker` 1 人に固定します。複数 writer が必要な場合は worktree を分けます。
