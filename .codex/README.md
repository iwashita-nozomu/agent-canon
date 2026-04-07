# Codex Project Setup

このディレクトリは、Codex を primary runtime として使うための project-scoped 設定置き場です。

## Layout

- `config.toml`
  - Codex の project 設定
- `agents/*.toml`
  - Codex 用 subagent 定義

## Shared Canon

- 共通入口は `AGENTS.md`
- workflow と skill の正本は `agents/`
- Codex-specific routing は `agents/canonical/CODEX_WORKFLOW.md` と `agents/canonical/CODEX_SUBAGENTS.md`

## Model Policy

- `gpt-5.4` + `xhigh`
  - `requirements_organizer`
  - `execution_planner`
  - `detailed_designer`
  - `long_form_writer`
  - `literature_researcher`
  - `docs_workflow_steward`
  - 全 reviewer 系 role
- `gpt-5.4-mini` + `xhigh`
  - `explorer`
  - `worker`
- manual worker overrides
  - `gpt-5.3-codex`
    - terminal-heavy な実装や coding-specialist 挙動を明示的に使いたいとき
  - `gpt-5.3-codex-spark`
    - 極端に狭い低遅延 edit loop だけ
- `Plan` collaboration mode
  - interactive Codex で要件整理と実行計画立案を行う parent session に対して使う
  - session 単位の設定なので、per-agent TOML ではなく Codex canon 側で管理する

## Current Agents

- `requirements_organizer`
- `execution_planner`
- `plan_reviewer`
- `detailed_designer`
- `long_form_writer`
- `detailed_design_reviewer`
- `document_flow_reviewer`
- `explorer`
- `reviewer`
- `worker`
- `docs_workflow_steward`
- `project_reviewer`
- `literature_researcher`
- `python_reviewer`
- `report_reviewer`
- `reproducibility_reviewer`
- `scientific_computing_reviewer`
- `benchmark_reviewer`
- `artifact_reviewer`
- `fair_data_reviewer`
- `ml_science_reviewer`

## Smoke Test

subagent inventory や research perspective pack を触ったら、次で bundle と runtime surface を確認します。

```bash
python3 scripts/agent_tools/smoke_test_research_perspective_pack.py
```
