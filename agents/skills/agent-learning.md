# agent-learning

## Purpose

agent の作業哲学、対話から得た学習、task retrospective を `memory/AGENT_PHILOSOPHY.md` に蓄積し、stable な項目だけを workflow や `AGENTS.md` へ昇格します。

## Use When

- user が agent の人格形成、作業哲学、対話からの継続学習を求めている
- task closeout で、次回以降の agent 行動を変える観測がある
- `USER_PREFERENCES.md` には入らない agent-side の学習を残したい
- raw chat ではなく、evidence 付きの短い observation として残したい
- self-learning と対話記録の追記を shared canon 側の責務として閉じたい

## Core References

- `documents/agent-learning-workflow.md`
- `memory/AGENT_PHILOSOPHY.md`
- `memory/USER_PREFERENCES.md`
- `notes/guardrails/engineering_avoidances.md`
- `documents/notes-lifecycle.md`
- `documents/workflow-references.md`
- `tools/agent_tools/log_agent_learning.py`

## Mandatory Checklist

- user preference と agent-side learning を分ける
- raw transcript を貼らず、短い observation に圧縮する
- source、evidence、scope、confidence を書く
- task-local な一時指示を stable philosophy にしない
- `memory/` への追記を template local artifact だけで終わらせず、shared canon update として closeout する
- promotion candidate は `AGENTS.md` へ直書きせず、periodic sweep で昇格する
- 確定した禁止事項は `engineering_avoidances.md` への昇格候補にする

## Default Commands

```bash
python3 tools/agent_tools/log_agent_learning.py \
  --kind interaction-observation \
  --statement "<agent-side learning>" \
  --source chat \
  --evidence "<short evidence>" \
  --scope repo-wide \
  --confidence tentative
```

```bash
python3 tools/agent_tools/log_agent_learning.py \
  --kind task-retrospective \
  --statement "<what should change next time>" \
  --source closeout \
  --evidence "<task/run/commit>" \
  --scope task-family \
  --confidence tentative
```

## Boundary

- user の coding preference は `user-preference-sync` を使います。
- failure として確定した禁止事項は `notes/guardrails/engineering_avoidances.md` へ移します。
- 文献調査で学習 workflow を変える場合は `literature-survey` も使います。
