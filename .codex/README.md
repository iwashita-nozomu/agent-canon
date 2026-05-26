# Codex Project Setup

<!--
@dependency-start
responsibility Documents Codex Project Setup for this repository.
upstream implementation ./config.toml project-scoped Codex settings
upstream design ../agents/task_catalog.yaml workflow family runtime budgets
upstream design ../agents/canonical/CODEX_SUBAGENTS.md subagent routing
downstream implementation ./hooks.json project-local hook declarations
downstream implementation ./hooks/mcp_session_context.sh provides optional MCP context text
downstream implementation ./hooks/hook_dispatcher.py dispatches lifecycle events to guard scripts
downstream implementation ./hooks/log_archive_mount_warning.py warns when the shared log archive is not mounted
downstream implementation ./hooks/skill_usage_logger.py records skill usage hook events
downstream implementation ./hooks/cause_investigation_guard.py blocks code edits without cause investigation evidence
downstream implementation ./hooks/module_boundary_guard.py blocks forced module rewrites
downstream implementation ./hooks/library_implementation_guard.py blocks library implementation rewrites
downstream implementation ./hooks/helper_first_guard.py blocks helper-first implementation drift
downstream implementation ./hooks/notebook_quality_guard.py blocks notebook-as-test misuse
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
- `[agents]` は上限と timeout の設定であり、上位 runtime / developer instruction が要求する explicit subagent authorization を上書きしません。明示許可が無い session では fan-out plan と handoff packet を作り、実際の spawn は許可後に行います
- plan mode や permissions のような mode は session 単位です。official Codex CLI では `/plan`、`/model`、`/permissions` を使います
- runtime が `/agent` を提供する場合は inventory 確認に使い、使えない場合は `.codex/agents/*.toml` を直接見ます
- 最初の作業 update では `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言します
- `/goal <objective>` を使う task では、`agents/workflows/codex-goals-workflow.md` の Goal-Specified Plan-Mode Entry に従い、`/goal` 設定後に `/plan` で contract と evidence map を固定してから実装します
- token 消費を抑える task では `agents/workflows/token-efficient-codex-workflow.md` を overlay とし、parent profile と agent mode を先に宣言します

## Goal And Plan Mode

- `goals` feature は `.codex/config.toml` の `[features].goals = true` で有効にします。
- TUI の user-facing command surface は `/goal`, `/goal <objective>`, `/goal pause`, `/goal resume`, `/goal clear` です。
- `/goal` は session view です。repo-owned durable state は top-level `goal.md`、機械 gate は MCP `goal.loop_status` と `tools/agent_tools/goal_loop.py status` に置きます。
- template repo の active `goal.md` は runtime state であり、派生 repo seed に混入させません。tracked product state に入れず、必要なら `.gitignore` で ignored local file として保持します。
- goal-driven task では `/goal <objective>` の直後に `/plan <goal-driven task summary>` を使い、Plan-mode output に `Goal Contract`、`Exit Criteria Mapping`、`Source Packet`、`Reuse Survey`、`Execution Slices`、`Budget Policy` を出します。
- pre-goal subagent fan-out は active runtime の authorization に従います。明示許可がある場合は read-only wave を起動し、無い場合は `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` と handoff packet を artifact に残します。
- 上記が揃うまで implementation、subagent write handoff、closeout は開始しません。

## User-Level Token Profiles

`codex -p <profile>` uses profiles from the user-level Codex config, not this
project-local config. Keep reusable operator profiles in `~/.codex/config.toml`
or `$CODEX_HOME/config.toml`:

```toml
[profiles.token-lite]
model_reasoning_effort = "minimal"
plan_mode_reasoning_effort = "minimal"
model_verbosity = "low"
tool_output_token_limit = 2000

[profiles.token-standard]
model_reasoning_effort = "medium"
plan_mode_reasoning_effort = "medium"
model_verbosity = "medium"
tool_output_token_limit = 3000

[profiles.token-deep]
model_reasoning_effort = "high"
plan_mode_reasoning_effort = "high"
model_verbosity = "medium"
tool_output_token_limit = 6000

[profiles.review]
model = "gpt-5.5"
model_reasoning_effort = "high"
sandbox_mode = "read-only"
approval_policy = "never"
```

Use `codex -p token-lite` for narrow diagnosis, `codex -p token-standard` for
normal staged repo work, and `codex -p token-deep` for architecture, research,
or high-risk review. Profiles do not waive workflow gates.

## Runtime Spawn Limits

- `max_threads = 24`
  - runtime hard ceiling として使います
- `job_max_runtime_seconds = 3600`
  - 長めの review / repo scan / validation を含む subagent job を 1 時間まで許容します
- `max_depth = 1`
  - recursive fan-out は既定で止めます
- 同時 spawn の既定 budget は workflow family 側で決めます
  - `Scoped Change Lite`: 4
  - `Scoped Change`: 8
  - `Large Delivery` / `Platform And Environment`: 10
  - `Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop`: 12
- write-capable subagent は既定 1 体です。parent が `team_manifest.yaml` の write policy と handoff で dependency order、wave plan、disjoint write scope、integration order、review gate を固定した場合だけ、spawn budget 内で複数 writer を並列化できます。衝突する target は禁止対象ではなく順序制約として先行 / 後続 wave に分けます。
- 新規 user request では前 task の subagent を使い回さず、run bundle ごとに fresh subagent を起こします
- `team_manifest.yaml` には `run.subagent_lifecycle_policy` を出し、`fresh_subagents_required: true` と `reuse_for_new_task: forbidden` を handoff prompt に含めます
- closeout 前に run-local subagent を閉じ、`closeout_gate.md` の `subagents_closed=yes` と `Subagent Lifecycle Evidence` を揃えます

## MCP Inventory

- `repo_mcp_server` は [config.toml](config.toml) の `[mcp_servers.repo_mcp_server]` を正本にします。
- launcher は host-global `repo_mcp_server` command ではなく、repo-local `bash mcp/repo_mcp_server.sh` を使います。
- `cwd = "."` を設定し、launcher 側でも `CODEX_WORKSPACE_ROOT` を repo root に固定します。Goal / resume 後の restart で current working directory が揺れても、MCP は同じ repo root を見ます。
- root `mcp/` は `vendor/agent-canon/mcp/` への runtime view で、`tools/sync_agent_canon.sh link-root` が復元します。
- AgentCanon-owned surface は `mcp/repo_mcp_server.sh`、`mcp/repo_mcp_server.py`、および [../mcp/README.md](../mcp/README.md) の repo MCP tool contract です。
- Codex-owned surface は `[mcp_servers.repo_mcp_server]` の registration、project trust、hook wiring、apps / external connectors / tool availability です。
- AgentCanon repo MCP は repo context / goal loop status / goal plan 専用です。file edit、GitHub 操作、shell 実行、web access、Codex apps の代替を `repo_mcp_server` に実装しません。
- MCP server startup timeout は 20 秒、tool call timeout は 300 秒にします。repo-local graph / status 系 tool が少し重くても、即 timeout で落とさないためです。
- 普通の相談、壁打ち、routing-only advice、説明だけの turn は repository task ではありません。その場合は repo state 確認、MCP inventory、repo MCP tool、shell / GitHub check を走らせず、会話だけで応答します。
- repository task へ切り替えるのは、ユーザーが local repo state 確認、file edit、validation、PR / issue mutation、local CI 実行、または実装作業を求めた場合です。GitHub Actions run、PR check、GitHub Issue を読むだけの GitHub-only read inspection は repository task に昇格させず、repo MCP preflight を走らせません。
- 判断が曖昧な場合、または task が MCP surface を変更する場合は Rust CLI で `agent-canon mcp-preflight-policy --request-kind <kind>` を使います。`github-actions-read`、`github-read`、`pr-read`、`issue-read` は `MCP_PREFLIGHT_DECISION=skip`、`repo-read`、`implementation`、`validation`、`pr-mutation`、`issue-sync` は `required` です。
- repository task で MCP evidence が workflow 上必要な場合、または `.codex/config.toml`、`mcp/`、repo MCP tools、MCP-dependent goal-loop gate を編集する場合だけ、`agent-canon mcp-inventory --root . --require repo_mcp_server --session-cache` を実行します。Python 互換入口の `python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server` は run bundle の `workflow_monitoring.md` へ evidence を追記する必要がある場合に使います。
- Rust CLI または local Cargo が AgentCanon の lockfile を読めない場合は `mcp_preflight_unavailable=<reason>` を work log、run bundle、または user-facing update に残し、MCP runtime behavior そのものが task scope でない限り既存 Python / shell gate で検証を続けます。
- `--session-cache` は `reports/agents/.mcp_inventory_cache.json` に pass evidence を保存します。`.codex/config.toml`、`mcp/`、`rust/agent-canon/src/mcp_inventory.rs`、`tools/agent_tools/check_mcp_inventory.py` が変わった場合、cache は無効化されます。
- inventory が pass した task では、repo root / status / goal loop status / goal plan / MCP-covered context checks で repo MCP tools を優先候補にします。
- current `repo_mcp_server` は repo root / status / goal.loop_status / goal.plan / context check 専用で、file edit tool は提供しません。
- MCP が pass している通常作業では、この制限を user update で毎回説明しません。MCP startup / inventory / tool mismatch が作業判断に影響する場合、または user が編集手段を質問した場合だけ説明します。
- `repo_mcp_server` が configured inventory に無い場合は fail closed とし、bridge-local process の暗黙起動で代替しません。
- `.codex/config.toml` が `repo_mcp_server` を宣言しているのに `codex mcp list --json` が空の場合は、project trust または Codex project-config loading を先に修復します。
- `check_mcp_inventory.py` は inventory だけでなく launcher command と repo-local script の存在も検査します。

## Hook Context

- `config.toml` の `[features].hooks = true` で project-local hook を有効にします。
- `hooks.json` は active lifecycle event ごとに `hooks/hook_dispatcher.py` を 1 回だけ起動し、dispatcher が既存 guard scripts を順番に実行します。これにより hook 設定は少数の event entry に保ちつつ、個別 guard の責務、ログ、環境変数 override は維持します。
- dispatcher は `GitStatus` tool、read-only な file / Git inspection、AgentCanon plan/status/latest-check を含む既知の validation command では child guard を起動しません。読み取りや検証のために `hooks.json` を退避したり hook 設定を一時無効化したりしてはいけません。
- `hooks.json` は `SessionStart` で MCP context hook を起動しません。MCP preflight は hook ではなく、workflow が evidence を必要とする場合、または MCP surface 自体を変更する場合に明示的に実行します。
- `hooks/mcp_session_context.sh` は互換用の手動 context helper として残します。通常の Codex session startup / resume では呼び出しません。
- `UserPromptSubmit` と `PreToolUse` は `hooks/log_archive_mount_warning.py` で `.agent-canon/archive/<env-key>/` が mounted Git clone として見えるか確認します。missing / invalid の場合も block せず、先に `python3 tools/agent_tools/runtime_log_archive_git.py ensure` を実行してから hook / eval logs を蓄積するよう促す警告だけを返します。
- `UserPromptSubmit` は `hooks/prompt_secret_guard.py` も起動し、明らかな API key / private key を含む prompt を block します。
- `UserPromptSubmit` と `Stop` は `hooks/skill_usage_logger.py` で `$skill-name`、`skills=...`、`skill_invocation=...` を検出し、さらに入力 prompt から candidate skill / workflow / tool と human feedback label を分類します。`PostToolUse` では同じ logger が `tool_name`、tool input shape、command verb を記録します。既定では mounted runtime log archive `.agent-canon/archive/<env-key>/hook-runs/<repo-key>/<runtime-namespace>/skill_usage.jsonl` に `hook_run_id` 付き JSONL として追記します。User prompt は secret-like value を redaction した bounded excerpt と fingerprint を保存し、tool input は key / fingerprint / command verb だけを保存します。`AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR` が設定されている run では、明示 skill は `workflow_monitor.py --behavior-event`、人間 feedback は `workflow_monitor.py --runtime-feedback` 経由で run bundle にも記録します。
- `PreToolUse` は `hooks/cause_investigation_guard.py` で、`apply_patch` や編集系 shell / python が code path を触る直前だけ cause investigation evidence を要求します。普通の相談、read-only search、validation command では block しません。code edit 前に `reports/agents/<run-id>/cause_investigation.md`、issue、または design note へ `Observation:`、`Hypothesis:` / `Root Cause:`、`Expected Fix Surface:` / `Selected Surface:`、`Validation Before Edit:` / `Support Evidence:` を残します。hook log には `code_paths`、`cause_evidence_status`、`cause_evidence_files` を残し、後続の prompt / skill eval に使います。
- `PostToolUse` は `hooks/oop_readability_guard.py` で、source 編集後の Python / C++ 変更に OOP readability checker を即時実行し、既存 finding を含む current finding があれば中間作業でも block します。実装ミスにつながるため、closeout まで先送りしません。
- `PostToolUse` は `hooks/module_boundary_guard.py` で、changed Python module に `import_responsibility.py` を即時実行し、未使用 import、wildcard import、責務外 local import を block します。さらに public surface 変更や大きな module rewrite が test / docs / issue / responsibility-scope などの boundary evidence なしで出た場合も block します。
- `PostToolUse` は `hooks/library_implementation_guard.py` で、`vendor/**`、`site-packages`、`node_modules`、`responsibility-scope.toml` の `external_dependency` scope などの library implementation 既存ファイルを直接書き換えた場合に block します。dependency の変更は wrapper / adapter、fork / upstream patch、または manifest-backed vendor import として扱い、library 内部をその場で直しません。
- `PostToolUse` は `hooks/helper_first_guard.py` で、changed Python file に helper-like function 追加があり、test / docs / issue / responsibility-scope などの ownership evidence が無い場合を block します。hook log には accepted / blocked の両方を分析できるように `helper_candidate_records` と blocking subset の `helper_first_records`、role、candidate / judgment rule、incoming count、specialization を残し、後続の prompt / skill 改善 eval に使います。
- `PostToolUse` は `hooks/style_checker_guard.py` で、changed Python / C++ / notebook / Markdown file に対応する体裁 checker を自動選択します。Python は `ruff check`、C++ は C++ readability、notebook は notebook quality、Markdown は lint / math notation を実行し、checker が選択されなかった changed file も `unchecked_files` として hook log に残します。
- `PostToolUse` は `hooks/notebook_quality_guard.py` でも changed notebook を確認し、細かい assertion / pytest / unittest / `test_` helper / stored error output を含む notebook、または visualization を持たない notebook を block します。notebook は部分実行できる実用 demo として保ち、細かい検証は `tests/` へ置きます。
- `Stop` は `hooks/goal_completion_guard.py` で、`goal.md` が `NEXT_ACTION=run_next_iteration` のまま完了報告しそうな turn を継続させます。
- `Stop` でも `hooks/oop_readability_guard.py`、`hooks/module_boundary_guard.py`、`hooks/library_implementation_guard.py`、`hooks/helper_first_guard.py`、`hooks/style_checker_guard.py`、`hooks/notebook_quality_guard.py` を再実行し、hook を迂回した変更が残っていれば completion を block します。
- OOP hook の既定 mode は `full` です。ユーザーが明示的に差分だけを見たい場合だけ `AGENT_CANON_OOP_HOOK_MODE=diff` を設定し、必要に応じて `AGENT_CANON_OOP_HOOK_BASELINE_REF` で比較 ref を指定します。未指定時の diff baseline は `HEAD` です。
- dispatcher は元の stdin payload を各 child hook に渡し、block payload があっても後続 hook を実行してログ機会を保ちます。Codex に返す出力は、元の順序で最初の `decision=block`、block がなければ最初の non-block JSON / stdout です。
- `hooks/cause_investigation_guard.py`、`hooks/oop_readability_guard.py`、`hooks/module_boundary_guard.py`、`hooks/library_implementation_guard.py`、`hooks/helper_first_guard.py`、`hooks/style_checker_guard.py`、`hooks/notebook_quality_guard.py` は実行ごとに mounted runtime log archive 配下へ `hook_run_id`、`source_repo_key`、`hook_log_namespace`、`payload_fingerprint`、status fields 付き JSONL を追記します。`<runtime-namespace>` は `AGENT_CANON_HOOK_RUN_NAMESPACE`、`DEVCONTAINER_PROJECT_NAME`、`COMPOSE_PROJECT_NAME`、generated Compose `name:`、host/repo hash fallback の順で決まります。OOP score threshold は analyzer の `tools/oop/shared/readability_core.py` を正本にします。`AGENT_CANON_HOOK_ARCHIVE_DIR` で archive root を、`AGENT_CANON_HOOK_RESULTS_DIR` / `AGENT_CANON_CAUSE_INVESTIGATION_HOOK_LOG_PATH` / `AGENT_CANON_OOP_HOOK_LOG_PATH` / `AGENT_CANON_MODULE_BOUNDARY_HOOK_LOG_PATH` / `AGENT_CANON_LIBRARY_IMPLEMENTATION_HOOK_LOG_PATH` / `AGENT_CANON_HELPER_FIRST_HOOK_LOG_PATH` / `AGENT_CANON_STYLE_CHECKER_HOOK_LOG_PATH` / `AGENT_CANON_NOTEBOOK_QUALITY_HOOK_LOG_PATH` / `AGENT_CANON_SKILL_LOG_PATH` でテスト・debug 用の出力先を差し替えられます。
- hook の役割は「MCP preflight が必要な workflow、または MCP surface を変更する task では inventory を明示実行する」ことを session 開始時に思い出させることです。普通の相談、壁打ち、routing-only advice、説明だけの turn や GitHub-only read inspection を repo task に変換してはいけません。local Cargo が lockfile を読めない環境では `mcp_preflight_unavailable=<reason>` を記録し、MCP runtime behavior が scope でない限り Python / shell gate で検証を続けます。完了 gate は `agent-canon mcp-inventory --root . --require repo_mcp_server --session-cache`、または run bundle evidence が必要な場合の `python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server --report-dir <run>` で判定します。
- hook context は `repo_mcp_server` の canonical launcher を `.codex/config.toml` -> `bash mcp/repo_mcp_server.sh` に固定し、ad hoc local process への silent fallback を禁止します。
- hook context は編集手段の毎回説明を要求しません。編集手段の既定は `agents/canonical/CODEX_WORKFLOW.md` の `Edit Execution Surface` に従います。
- `tools/sync_agent_canon.sh link-root` は root `.codex/hooks.json` と `.codex/hooks/` を shared canon へリンクします。

## Model Policy

- `gpt-5.5` + `high`: frontier-required planning, synthesis, broad implementation, and ship decision
  - `requirements_organizer`
  - `manager_reviewer`
  - `execution_planner`
  - `detailed_designer`
  - `long_form_writer`
  - `literature_researcher`
  - `worker`
  - `reviewer`
  - `plan_reviewer`
  - `detailed_design_reviewer`
  - `citation_evidence_reviewer`
  - `notation_definition_reviewer`
  - `logic_gap_reviewer`
  - `project_reviewer`
  - `ship_reviewer`
- `gpt-5.4-mini` + `medium`: conditional specialist review
  - `document_flow_reviewer`
  - `docs_workflow_steward`
  - `report_reviewer`
  - `reproducibility_reviewer`
  - `scientific_computing_reviewer`
  - `benchmark_reviewer`
  - `artifact_reviewer`
  - `fair_data_reviewer`
  - `ml_science_reviewer`
  - `oop_readability_reviewer`
- `gpt-5.3-codex-spark` + `low`: cheap-first survey, test, diff review, and execution-only work
  - `explorer`
  - `test_designer`
  - `python_reviewer`
  - `cpp_reviewer`
  - `diff_triage_reviewer`
  - `spark_worker`
  - `experiment_runner`
- code-reading and narrow implementation roles use `gpt-5.3-codex-spark` with `low` reasoning effort to keep output bounded
- repo default は `high`
  - `xhigh` は parent が必要と判断したときだけ manual escalation として使う
- mode の扱い
  - plan mode や permissions は session 単位で、per-agent TOML には書きません
  - official Codex CLI では `/plan`、`/model`、`/permissions` を使います
- `.codex/config.toml` の `[agents.<name>]` が role registry、`.codex/agents/*.toml` が role behavior と model override の正本です

## Current Agents

- `artifact_reviewer`
- `benchmark_reviewer`
- `citation_evidence_reviewer`
- `cpp_reviewer`
- `detailed_design_reviewer`
- `detailed_designer`
- `diff_triage_reviewer`
- `docs_workflow_steward`
- `document_flow_reviewer`
- `execution_planner`
- `experiment_runner`
- `explorer`
- `fair_data_reviewer`
- `literature_researcher`
- `logic_gap_reviewer`
- `long_form_writer`
- `manager_reviewer`
- `ml_science_reviewer`
- `notation_definition_reviewer`
- `oop_readability_reviewer`
- `plan_reviewer`
- `project_reviewer`
- `python_reviewer`
- `report_reviewer`
- `reproducibility_reviewer`
- `requirements_organizer`
- `reviewer`
- `scientific_computing_reviewer`
- `ship_reviewer`
- `spark_worker`
- `test_designer`
- `worker`

## Smoke Test

subagent inventory や research perspective pack を触ったら、次で bundle と runtime surface を確認します。

```bash
python3 tools/agent_tools/smoke_test_research_perspective_pack.py
python3 tools/agent_tools/task_start.py --task "scoped change" --task-id T1 --owner "codex" --dry-run
python3 tools/agent_tools/doc_start.py --task "paper writing task" --kind paper --owner "codex" --dry-run
```
