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
  --owner "codex" \
  --workspace-root "$PWD" \
  --enable scheduler \
  --enable schedule_reviewer
```

研究・実験つき変更:

```bash
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
```

環境変更:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "platform or environment change" \
  --owner "codex" \
  --workspace-root "$PWD" \
  --enable scheduler \
  --enable schedule_reviewer \
  --enable infra_steward \
  --enable infra_reviewer
```

学術文章:

```bash
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
```

repo-changing task では、always-on role に加えて最低でも `scheduler` と `schedule_reviewer` を explicit に有効化します。
調査が必要なら `researcher` と `research_reviewer`、環境変更なら `infra_steward` と `infra_reviewer` を追加します。
学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` を必ず explicit に追加します。
Codex で planning を含む parent session では、可能なら `/collab` の `Plan` mode を先に使います。
runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を見ます。
計画レビュー agent、詳細設計レビュー agent、文書通読レビュー agent は、同じ instance を使い回しません。
学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` も別 instance を使います。
