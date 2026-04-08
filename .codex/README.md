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
- plan mode や permissions のような mode は session 単位です。official Codex CLI では `/plan`、`/model`、`/permissions` を使います
- runtime が `/agent` を提供する場合は inventory 確認に使い、使えない場合は `.codex/agents/*.toml` を直接見ます
- 最初の作業 update では `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言します

## Model Policy

- `gpt-5.4` + `high`
  - `requirements_organizer`
  - `execution_planner`
  - `detailed_designer`
  - `long_form_writer`
  - `notation_definition_reviewer`
  - `logic_gap_reviewer`
  - `literature_researcher`
  - `docs_workflow_steward`
  - `reviewer`
  - `plan_reviewer`
  - `detailed_design_reviewer`
  - `document_flow_reviewer`
  - `project_reviewer`
  - `report_reviewer`
  - perspective reviewer 全般
- `gpt-5.3-codex` + `high`
  - `explorer`
  - `worker`
  - `python_reviewer`
  - `cpp_reviewer`
- manual coding override
  - `gpt-5.3-codex-spark`
    - 極端に狭い低遅延 edit loop だけ
- repo default は `high`
  - `xhigh` は parent が必要と判断したときだけ manual escalation として使う
- mode の扱い
  - plan mode や permissions は session 単位で、per-agent TOML には書きません
  - official Codex CLI では `/plan`、`/model`、`/permissions` を使います

## Current Agents

- `requirements_organizer`
- `execution_planner`
- `plan_reviewer`
- `detailed_designer`
- `long_form_writer`
- `detailed_design_reviewer`
- `document_flow_reviewer`
- `notation_definition_reviewer`
- `logic_gap_reviewer`
- `explorer`
- `reviewer`
- `worker`
- `docs_workflow_steward`
- `project_reviewer`
- `literature_researcher`
- `python_reviewer`
- `cpp_reviewer`
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
python3 scripts/agent_tools/task_start.py --task "scoped change" --task-id T1 --owner "codex" --dry-run
```
