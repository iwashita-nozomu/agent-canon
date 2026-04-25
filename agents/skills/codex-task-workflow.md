# codex-task-workflow

<!--
@dependency-start
upstream design ../canonical/CODEX_WORKFLOW.md defines the executable Codex workflow
upstream design ../../documents/dependency-manifest-design.md defines dependency manifest requirements
downstream design ../../.agents/skills/codex-task-workflow/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

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
- repo-changing task では `python3 tools/agent_tools/bootstrap_agent_run.py ... --task-id <T*>` から始める
- repo-changing task では `$agent-orchestration` を先頭に置き、`$subagent-bootstrap` を併用する
- 実装前に `IMPLEMENTATION_CODEX_AGENTS` を確認し、`spark_worker,worker` なら design-traced narrow slice は `spark_worker` を先に使う
- 変更対象の `Dependency Manifest Plan` を設計で固定し、編集前に upstream、編集後に downstream を読む
- closeout 前に `check_dependency_headers.py --changed`、`scan_dependency_headers.sh --changed --fail-missing`、`check_dependency_header_format.sh --changed --require-header` を通す
- dependency edge を変更した場合は `check_dependency_graph.sh --print-edges` の結果、または移行中 baseline と今回差分で新規 graph error を増やしていない evidence を残す
