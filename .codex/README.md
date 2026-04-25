# Codex Project Setup

<!--
@dependency-start
upstream implementation ./config.toml project-scoped Codex settings
upstream design ../agents/task_catalog.yaml workflow family runtime budgets
upstream design ../agents/canonical/CODEX_SUBAGENTS.md subagent routing
downstream implementation ../tools/agent_tools/check_mcp_inventory.py MCP inventory preflight
@dependency-end
-->

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
- runtime cap は `.codex/config.toml` の `[agents].max_threads = 24` を使い、spawn は depth ではなく bounded concurrency で制御します
- plan mode や permissions のような mode は session 単位です。official Codex CLI では `/plan`、`/model`、`/permissions` を使います
- runtime が `/agent` を提供する場合は inventory 確認に使い、使えない場合は `.codex/agents/*.toml` を直接見ます
- 最初の作業 update では `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言します

## Runtime Spawn Limits

- `max_threads = 24`
  - runtime hard ceiling として使います
- depth は repo config で固定しません
- 同時 spawn の既定 budget は workflow family 側で決めます
  - `Scoped Change`: 8
  - `Large Delivery` / `Platform And Environment`: 10
  - `Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop`: 12
- 同時 write-capable subagent は常に 1 体までです

## MCP Inventory

- `repo_mcp_server` は [config.toml](config.toml) の `[mcp_servers.repo_mcp_server]` を正本にします。
- MCP 前提の task では、local process を手で起動する前に `python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server` を実行します。
- `repo_mcp_server` が configured inventory に無い場合は fail closed とし、bridge-local process の暗黙起動で代替しません。
- host 側に `repo_mcp_server` command が無い場合は、inventory entry は見えても runtime startup は失敗し得ます。その場合は host setup issue として記録します。

## Model Policy

- `gpt-5.5` + `high`
  - `requirements_organizer`
  - `manager_reviewer`
  - `execution_planner`
  - `detailed_designer`
  - `long_form_writer`
  - `notation_definition_reviewer`
  - `logic_gap_reviewer`
  - `literature_researcher`
  - `docs_workflow_steward`
  - `worker`
  - `reviewer`
  - `plan_reviewer`
  - `detailed_design_reviewer`
  - `document_flow_reviewer`
  - `project_reviewer`
  - `report_reviewer`
  - perspective reviewer 全般
- `gpt-5.3-codex` + `high`
  - `explorer`
  - `test_designer`
  - `python_reviewer`
  - `cpp_reviewer`
- design-traced narrow implementation default
  - `gpt-5.3-codex-spark`
    - `spark_worker`
- broad or ambiguous implementation fallback
  - `gpt-5.5`
    - `worker`
    - 設計解釈、conflict resolution、architecture-sensitive edit
- repo default は `high`
  - `xhigh` は parent が必要と判断したときだけ manual escalation として使う
- mode の扱い
  - plan mode や permissions は session 単位で、per-agent TOML には書きません
  - official Codex CLI では `/plan`、`/model`、`/permissions` を使います

## Current Agents

- `requirements_organizer`
- `manager_reviewer`
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
- `spark_worker`
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
python3 tools/agent_tools/smoke_test_research_perspective_pack.py
python3 tools/agent_tools/task_start.py --task "scoped change" --task-id T1 --owner "codex" --dry-run
python3 tools/agent_tools/doc_start.py --task "paper writing task" --kind paper --owner "codex" --dry-run
```
