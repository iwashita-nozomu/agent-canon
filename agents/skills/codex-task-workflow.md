# codex-task-workflow

## Purpose

Codex が会話コンテキストに依存せず、毎回同じ順序で task を進めるための標準フローです。

## Use When

- Codex で task を最初から最後まで進める
- 手順を固定したい
- task ごとの skill 選択を標準化したい

## Core Reference

- `agents/canonical/CODEX_WORKFLOW.md`

## Stages

1. intake
1. required context and library sweep
1. workflow selection
1. artifact placement
1. explicit subagent bootstrap
1. execution plan and plan review
1. detailed design and detailed design review
1. document flow review
1. implementation
1. validation
1. closeout

## Required Output

- 最初の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する
- repo-changing task では `python3 scripts/agent_tools/bootstrap_agent_run.py ... --task-id <T*>` から始める
