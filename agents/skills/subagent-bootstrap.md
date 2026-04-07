# subagent-bootstrap

## Purpose

specialist delegation が必要な task で、run bundle、役割分担、write-scope を崩さずに起動します。

## Use When

- run artifact を残したい
- specialist を使う
- reviewer / implementer の責務を分けたい
- 計画レビュー agent と詳細設計レビュー agent を分けたい

## Core References

- `agents/TASK_WORKFLOWS.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `scripts/agent_tools/bootstrap_agent_run.py`

## Standard Command

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "short task summary" \
  --owner "codex"
```

repo-changing task では、最低でも `scheduler`、`schedule_reviewer`、`designer`、`design_reviewer` を explicit に有効化します。
調査が必要なら `researcher` と `research_reviewer` も追加します。
計画レビュー agent と詳細設計レビュー agent は、同じ instance を使い回しません。
