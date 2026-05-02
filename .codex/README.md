# Codex Project Setup

<!--
@dependency-start
responsibility Documents Codex Project Setup for this repository.
upstream implementation ./config.toml project-scoped Codex settings
upstream design ../agents/task_catalog.yaml workflow family runtime budgets
upstream design ../agents/canonical/CODEX_SUBAGENTS.md subagent routing
downstream implementation ./hooks.json project-local hook declarations
downstream implementation ./hooks/mcp_session_context.sh injects MCP preflight context
downstream implementation ../tools/agent_tools/check_mcp_inventory.py MCP inventory preflight
@dependency-end
-->

このディレクトリは、Codex を primary runtime として使うための project-scoped 設定置き場です。

## Layout

- `config.toml`
  - Codex の project 設定
- `agents/*.toml`
  - Codex 用 subagent 定義
- `hooks.json`
  - Codex lifecycle hook 定義
- `hooks/*.sh`
  - repo-local hook script

## Shared Canon

- 共通入口は `AGENTS.md`
- workflow と skill の正本は `agents/`
- Codex-specific routing は `agents/canonical/CODEX_WORKFLOW.md` と `agents/canonical/CODEX_SUBAGENTS.md`
- runtime cap は `.codex/config.toml` の `[agents].max_threads = 24` を使い、spawn は depth ではなく bounded concurrency で制御します
- plan mode や permissions のような mode は session 単位です。official Codex CLI では `/plan`、`/model`、`/permissions` を使います
- runtime が `/agent` を提供する場合は inventory 確認に使い、使えない場合は `.codex/agents/*.toml` を直接見ます
- 最初の作業 update では `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言します
- `/goal <objective>` を使う task では、`agents/workflows/codex-goals-workflow.md` の Goal-Specified Plan-Mode Entry に従い、`/goal` 設定後に `/plan` で contract と evidence map を固定してから実装します
- token 消費を抑える task では `agents/workflows/token-efficient-codex-workflow.md` を overlay とし、parent profile と agent mode を先に宣言します

## Goal And Plan Mode

- `goals` feature は `.codex/config.toml` の `[features].goals = true` で有効にします。
- TUI の user-facing command surface は `/goal`, `/goal <objective>`, `/goal pause`, `/goal resume`, `/goal clear` です。
- `/goal` は session view です。repo-owned durable state は top-level `goal.md`、機械 gate は MCP `goal.loop_status` と `tools/agent_tools/goal_loop.py status` に置きます。
- goal-driven task では `/goal <objective>` の直後に `/plan <goal-driven task summary>` を使い、Plan-mode output に `Goal Contract`、`Exit Criteria Mapping`、`Source Packet`、`Reuse Survey`、`Execution Slices`、`Budget Policy` を出します。
- 上記が揃うまで implementation、subagent write handoff、closeout は開始しません。

## Token Profiles

- `token-lite`
  - `model_reasoning_effort = "low"`
  - `plan_mode_reasoning_effort = "low"`
  - `model_verbosity = "low"`
  - `tool_output_token_limit = 6000`
- `token-standard`
  - `model_reasoning_effort = "medium"`
  - `plan_mode_reasoning_effort = "medium"`
  - `model_verbosity = "medium"`
  - `tool_output_token_limit = 12000`
- `token-deep`
  - `model_reasoning_effort = "high"`
  - `plan_mode_reasoning_effort = "high"`
  - `model_verbosity = "medium"`
  - `tool_output_token_limit = 24000`

Use `codex -p token-lite` for narrow diagnosis, `codex -p token-standard` for
normal staged repo work, and `codex -p token-deep` for architecture, research,
or high-risk review. Profiles do not waive workflow gates.

## Runtime Spawn Limits

- `max_threads = 24`
  - runtime hard ceiling として使います
- `job_max_runtime_seconds = 3600`
  - 長めの review / repo scan / validation を含む subagent job を 1 時間まで許容します
- depth は repo config で固定しません
- 同時 spawn の既定 budget は workflow family 側で決めます
  - `Scoped Change`: 8
  - `Large Delivery` / `Platform And Environment`: 10
  - `Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop`: 12
- 同時 write-capable subagent は常に 1 体までです
- 新規 user request では前 task の subagent を使い回さず、run bundle ごとに fresh subagent を起こします
- `team_manifest.yaml` には `run.subagent_lifecycle_policy` を出し、`fresh_subagents_required: true` と `reuse_for_new_task: forbidden` を handoff prompt に含めます
- closeout 前に run-local subagent を閉じ、`closeout_gate.md` の `subagents_closed=yes` と `Subagent Lifecycle Evidence` を揃えます

## MCP Inventory

- `repo_mcp_server` は [config.toml](config.toml) の `[mcp_servers.repo_mcp_server]` を正本にします。
- launcher は host-global `repo_mcp_server` command ではなく、repo-local `bash mcp/repo_mcp_server.sh` を使います。
- root `mcp/` は `vendor/agent-canon/mcp/` への runtime view で、`tools/sync_agent_canon.sh link-root` が復元します。
- MCP server startup timeout は 20 秒、tool call timeout は 300 秒にします。repo-local graph / status 系 tool が少し重くても、即 timeout で落とさないためです。
- repository task では、ユーザーが MCP を明示していなくても、intake で `python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server` を実行します。
- inventory が pass した task では、repo root / status / MCP-covered context checks で repo MCP tools を優先候補にします。
- current `repo_mcp_server` は repo root / status / context check 専用で、file edit tool は提供しません。
- MCP が pass している通常作業では、この制限を user update で毎回説明しません。MCP startup / inventory / tool mismatch が作業判断に影響する場合、または user が編集手段を質問した場合だけ説明します。
- `repo_mcp_server` が configured inventory に無い場合は fail closed とし、bridge-local process の暗黙起動で代替しません。
- `.codex/config.toml` が `repo_mcp_server` を宣言しているのに `codex mcp list --json` が空の場合は、project trust または Codex project-config loading を先に修復します。
- `check_mcp_inventory.py` は inventory だけでなく launcher command と repo-local script の存在も検査します。

## MCP Hook Context

- `config.toml` の `[features].codex_hooks = true` で project-local hook を有効にします。
- `hooks.json` は `SessionStart` と `UserPromptSubmit` で `hooks/mcp_session_context.sh` を起動し、MCP preflight の追加 context を Codex に渡します。
- hook の役割は「MCP をユーザーが明示しなくても repo task の標準 preflight として扱う context 注入」です。完了 gate は引き続き `python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server` と run bundle evidence で判定します。
- hook context は `repo_mcp_server` の canonical launcher を `.codex/config.toml` -> `bash mcp/repo_mcp_server.sh` に固定し、ad hoc local process への silent fallback を禁止します。
- hook context は編集手段の毎回説明を要求しません。編集手段の既定は `agents/canonical/CODEX_WORKFLOW.md` の `Edit Execution Surface` に従います。
- `tools/sync_agent_canon.sh link-root` は root `.codex/hooks.json` と `.codex/hooks/` を shared canon へリンクします。

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
