# Codex Project Setup

<!--
@dependency-start
contract agent-runtime
responsibility Documents Codex Project Setup for this repository.
upstream implementation ./config.toml project-scoped Codex settings
upstream design ../agents/task_catalog.yaml workflow family runtime budgets
upstream design ../agents/canonical/CODEX_SUBAGENTS.md subagent routing
downstream implementation ./hooks.json project-local hook declarations
downstream implementation ./hooks/hook_dispatcher.py dispatches lifecycle events to guard scripts
downstream implementation ./hooks/log_archive_mount_warning.py warns when the shared log archive is not mounted
downstream implementation ./hooks/branch_worktree_guard.py blocks unconfirmed branch and worktree creation
downstream implementation ./hooks/direct_rg_context_guard.py warns on context-polluting direct rg usage
downstream implementation ./hooks/skill_usage_logger.py records skill usage hook events
downstream implementation ./hooks/cause_investigation_guard.py warns on code edits without cause investigation evidence
downstream implementation ./hooks/module_boundary_guard.py warns on forced module rewrites
downstream implementation ./hooks/library_implementation_guard.py warns on library implementation rewrites
downstream implementation ./hooks/helper_first_guard.py warns on helper-first implementation drift
downstream implementation ./hooks/notebook_quality_guard.py warns on notebook-as-test misuse
@dependency-end
-->

このディレクトリは、Codex を primary runtime として使うための project-scoped 設定置き場です。

## この文書の読み方

- この文書は、`.codex/` の project-scoped 設定、subagent 定義、hook、runtime cap、model 設定の入口です。
- `Layout` と `Shared Canon` で設定 file と shared canon への接続を確認し、goal、token profile、spawn limit、hook context、agents、smoke test は目的別に読みます。
- Codex runtime の設定確認、hook や subagent inventory の確認、project-local Codex smoke test の前に読みます。

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
- `/goal` は session view です。repo-owned durable state は top-level `goal.md`、機械 gate は `tools/agent_tools/goal_loop.py status` に置きます。
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

Use `codex -p token-lite` for bounded diagnosis, `codex -p token-standard` for
normal staged repo work, and `codex -p token-deep` for architecture, research,
or high-risk review. Profiles do not waive workflow gates.

## Runtime Spawn Limits

- `max_threads = 24`
  - runtime hard ceiling として使います
- `job_max_runtime_seconds = 3600`
  - 長めの review / repo scan / validation を含む subagent job を 1 時間まで許容します
- `max_depth = 2`
  - one bounded child-subagent layer を許可します
- 同時 spawn の既定 budget は workflow family 側で決めます
  - `Owner-Bounded Change`: 4
  - `Scoped Change`: 8
  - `Large Delivery` / `Platform And Environment`: 10
  - `Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop`: 12
- `team_manifest.yaml` の `run.spawn_budget.active_subagents` が総同時起動 budget、`run.spawn_budget.max_write_subagents` と `run.write_scope_policy.max_write_subagents` が write-capable subagent だけの上限です。`max_write_subagents: 3` は総同時起動 cap ではありません。
- same-role instance policy は `agents/task_catalog.yaml` と generated
  `team_manifest.yaml` の `run.delegated_spawn_policy` が正本です。
  `.codex/config.toml` の `[agents]` には Codex runtime が読む runtime
  limit と `[agents.<role>]` registry だけを置き、policy 文字列を置きません。
  `role_type+instance_id` が instance key で、`max_threads` は runtime cap であり
  role cardinality の source ではありません。
- write-capable subagent instance は既定 1 体から始めます。parent が `team_manifest.yaml` の write policy と handoff で dependency order、wave plan、disjoint write scope、integration order、review gate を固定した場合だけ、同じ role type を含む複数 writer instance を spawn budget 内で並列化できます。衝突する target は禁止対象ではなく順序制約として先行 / 後続 wave に分けます。
- 新規 user request では前 task の subagent を使い回さず、run bundle ごとに fresh subagent を起こします
- active task の途中追加指示は parent が `same_active_task_delta` / `scope_or_contract_change` / `new_task` に分類し、same-task delta は run bundle checkpoint と updated packet path を残してから run-local subagent へ再配送し、scope 変更は fresh follow-up wave にします
- `team_manifest.yaml` には `run.subagent_lifecycle_policy` を出し、`fresh_subagents_required: true` と `reuse_for_new_task: forbidden` を handoff prompt に含めます
- closeout 前に run-local subagent を閉じ、`closeout_gate.md` の `subagents_closed=yes` と `Subagent Lifecycle Evidence` を揃えます

## Hook Context

- `config.toml` の `[features].hooks = true` で project-local hook を有効にします。
- `hooks.json` は active lifecycle event ごとに `hooks/hook_dispatcher.py` を 1 回だけ起動し、dispatcher が既存 guard scripts を順番に実行します。これにより hook 設定は少数の event entry に保ちつつ、個別 guard の責務、ログ、環境変数 override は維持します。
- dispatcher は `GitStatus` tool、read-only な file / Git inspection、AgentCanon plan/status/latest-check を含む既知の validation command では child guard を起動しません。読み取りや検証のために `hooks.json` を退避したり hook 設定を一時無効化したりしてはいけません。
- dispatcher は `GitPush` tool、単純な `git push`、安全な `gh pr` inspection / create / edit / checks / comment、`python3 tools/agent_tools/github_publish.py ...` でも child guard を起動しません。GitHub publish / PR evidence は publish tool と PR gate の責務であり、非重大 hook finding で止めません。
- dispatcher は fail-open が既定です。子 hook の `decision=block` はログと修復 context として保持しますが、prompt secret など `CRITICAL_BLOCKING_CHILD_HOOKS` に入った高確信の公開事故だけを runtime block として維持します。明示的な hook 開発・強制検証では `AGENT_CANON_HOOK_STRICT_BLOCKS=1` または `AGENT_CANON_HOOK_STRICT_FAILURES=1` を設定できます。
- process / search / reuse / planning / review completeness の規律は、hook blocker ではなく warning、run bundle evidence、closeout gate、または reviewer finding として扱います。hook finding は closeout 前に直すべき evidence ですが、通常の read-only 調査、validation、修復作業を止めません。
- `UserPromptSubmit` と `PreToolUse` は `hooks/log_archive_mount_warning.py` で `.agent-canon/log-archive/` が mounted Git clone として見えるか確認します。missing / invalid の場合も block せず、先に `python3 tools/agent_tools/runtime_log_archive_git.py ensure` を実行してから hook / eval logs を蓄積するよう促す警告だけを返します。
- `UserPromptSubmit` は `hooks/prompt_secret_guard.py` も起動し、明らかな API key / private key を含む prompt を block します。
- `UserPromptSubmit` と `Stop` は `hooks/skill_usage_logger.py` で `$skill-name`、`skills=...`、`skill_invocation=...` を検出し、さらに入力 prompt から candidate skill / workflow / tool と human feedback label を分類します。`PostToolUse` では同じ logger が `tool_name`、tool input shape、command verb を記録します。既定では mounted runtime log archive `.agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/skill_usage.jsonl` に `hook_run_id` 付き JSONL として追記します。User prompt は secret-like value を redaction した bounded excerpt と fingerprint を保存し、tool input は key / fingerprint / command verb だけを保存します。`AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR` が設定されている run では、明示 skill は `workflow_monitor.py --behavior-event`、人間 feedback は `workflow_monitor.py --runtime-feedback` 経由で run bundle にも記録します。
- `Stop` は `hooks/codex_runtime_summary_logger.py` で bounded runtime summary を書いた後、`hooks/runtime_log_auto_sync.py` で `runtime_log_archive_git.py sync` を best-effort 実行します。これにより hook JSONL、eval report、Codex runtime summary、`reports/agents/` run bundle は通常 agent の手動 push なしで log archive の `logs/<repo-key>` branch に集約されます。network / SSH / archive 不在の失敗は fail-open で作業を止めません。
- `PreToolUse` は `hooks/direct_rg_context_guard.py` で、repo root や broad scope への direct `rg -n` を `DIRECT_RG_CONTEXT_RISK=warn` として警告します。`rg --files`、`rg -l "<pattern>" <bounded dirs>`、specific file / bounded dir への `rg -n`、`--max-count` 付き検索、または `.agent-canon/log-archive/**`、`reports/**`、`*.jsonl` を除外した検索は通常 quiet です。この warning は block ではなく、context 汚染を closeout 前の修復 / 記録対象にするための機械 gate です。
- `PreToolUse` は `hooks/cause_investigation_guard.py` で、`apply_patch` や編集系 shell / python が code path を触る直前だけ cause investigation evidence を確認します。普通の相談、read-only search、validation command では child guard を起動しません。code edit 前に `reports/agents/<run-id>/cause_investigation.md`、issue、または design note へ `Observation:`、`Hypothesis:` / `Root Cause:`、`Expected Fix Surface:` / `Selected Surface:`、`Validation Before Edit:` / `Support Evidence:` を残します。hook log には `code_paths`、`cause_evidence_status`、`cause_evidence_files` を残し、後続の prompt / skill eval に使います。
- `PostToolUse` は `hooks/oop_readability_guard.py` で、source 編集後の Python / C++ 変更に OOP readability checker を即時実行します。current finding は warning context と hook log に残し、closeout 前の修復対象にします。
- `PostToolUse` は `hooks/module_boundary_guard.py` で、changed Python module に `import_responsibility.py` を即時実行し、未使用 import、wildcard import、責務外 local import、public surface 変更、大きな module rewrite と boundary evidence の関係を記録します。finding は通常 warning context とし、closeout gate または明示 validation で修復します。
- `PostToolUse` は `hooks/library_implementation_guard.py` で、`vendor/**`、`site-packages`、`node_modules`、`responsibility-scope.toml` の `external_dependency` scope などの library implementation 既存ファイルを直接書き換えた場合に finding を出します。dependency の変更は wrapper / adapter、fork / upstream patch、または manifest-backed vendor import として扱い、library 内部をその場で直しません。
- `PostToolUse` は `hooks/helper_first_guard.py` で、changed Python file に helper-like function 追加があり、test / docs / issue / responsibility-scope などの ownership evidence が無い場合を finding として記録します。hook log には accepted / flagged の両方を分析できるように `helper_candidate_records` と flagged subset の `helper_first_records`、role、candidate / judgment rule、incoming count、specialization を残し、後続の prompt / skill 改善 eval に使います。
- `PostToolUse` は `hooks/helper_inventory_guard.py` で、repo-local `helper_inventory_guard_policy.json` に従い、`needs_user_judgment`、tool rule gap、role/action name gap を domain 別 count として記録します。`name_gap` は `helper_function_inventory.py` の `searchable_name` / `name_search_rule` から集計します。
- `PostToolUse` は `hooks/style_checker_guard.py` で、changed Python / C++ / notebook / Markdown file に対応する体裁 checker を自動選択します。Python は `ruff check`、C++ は C++ readability、notebook は notebook quality、Markdown は lint / math notation を実行し、checker が選択されなかった changed file も `unchecked_files` として hook log に残します。
- `PostToolUse` は `hooks/notebook_quality_guard.py` でも changed notebook を確認し、細かい assertion / pytest / unittest / `test_` helper / stored error output を含む notebook、または visualization を持たない notebook を finding として記録します。notebook は部分実行できる実用 demo として保ち、細かい検証は `tests/` へ置きます。
- `Stop` は `hooks/goal_completion_guard.py` で、`goal.md` が `NEXT_ACTION=run_next_iteration` のまま完了報告しそうな turn を continuation context として返します。
- `Stop` でも `hooks/oop_readability_guard.py`、`hooks/module_boundary_guard.py`、`hooks/library_implementation_guard.py`、`hooks/helper_first_guard.py`、`hooks/style_checker_guard.py`、`hooks/notebook_quality_guard.py` を再実行し、hook を迂回した変更が残っていれば closeout repair context を返します。
- OOP hook の既定 mode は `full` です。ユーザーが明示的に差分だけを見たい場合だけ `AGENT_CANON_OOP_HOOK_MODE=diff` を設定し、必要に応じて `AGENT_CANON_OOP_HOOK_BASELINE_REF` で比較 ref を指定します。未指定時の diff baseline は `HEAD` です。
- dispatcher は元の stdin payload を各 child hook に渡し、child hook が finding を出しても後続 hook を実行してログ機会を保ちます。Codex に返す出力は、critical block があればその block、それ以外は公式 hook output の `systemMessage` / `hookSpecificOutput.additionalContext` に正規化した warning context です。`PostToolUse` は runtime の post-tool output schema を壊さないため、非 blocking finding や child failure を stdout に返さず、hook log、明示 validation、closeout evidence の対象にします。
- `hooks/cause_investigation_guard.py`、`hooks/oop_readability_guard.py`、`hooks/module_boundary_guard.py`、`hooks/library_implementation_guard.py`、`hooks/helper_first_guard.py`、`hooks/style_checker_guard.py`、`hooks/notebook_quality_guard.py` は実行ごとに mounted runtime log archive 配下へ `hook_run_id`、`source_repo_key`、`hook_log_namespace`、`payload_fingerprint`、status fields 付き JSONL を追記します。`<runtime-namespace>` は `AGENT_CANON_HOOK_RUN_NAMESPACE`、`DEVCONTAINER_PROJECT_NAME`、`COMPOSE_PROJECT_NAME`、generated Compose `name:` のいずれかで明示されます。OOP score threshold は analyzer の `tools/oop/shared/readability_core.py` を正本にします。`AGENT_CANON_HOOK_ARCHIVE_DIR` で archive root を、`AGENT_CANON_HOOK_RESULTS_DIR` / `AGENT_CANON_CAUSE_INVESTIGATION_HOOK_LOG_PATH` / `AGENT_CANON_OOP_HOOK_LOG_PATH` / `AGENT_CANON_MODULE_BOUNDARY_HOOK_LOG_PATH` / `AGENT_CANON_LIBRARY_IMPLEMENTATION_HOOK_LOG_PATH` / `AGENT_CANON_HELPER_FIRST_HOOK_LOG_PATH` / `AGENT_CANON_STYLE_CHECKER_HOOK_LOG_PATH` / `AGENT_CANON_NOTEBOOK_QUALITY_HOOK_LOG_PATH` / `AGENT_CANON_SKILL_LOG_PATH` でテスト・debug 用の出力先を差し替えられます。
- hook context は編集手段の毎回説明を要求しません。編集手段の既定は `agents/canonical/CODEX_WORKFLOW.md` の `Edit Execution Surface` に従います。
- `tools/sync_agent_canon.sh link-root` は root `.codex/hooks.json` と `.codex/hooks/` を shared canon へリンクします。

## Model Settings

- `.codex/agents/*.toml` is the source of truth for each Codex subagent's
  `model` and `model_reasoning_effort`.
- `.codex/config.toml` owns project features, runtime limits,
  skill registration, and the agent registry only; it does not carry a second
  model settings table.
- `tools/agent_tools/check_agent_runtime_alignment.py` and
  `tools/agent_tools/evaluate_codex_agent_roles.py` validate the materialized
  agent TOML files directly.
- Review, quality-check, diff review, bounded review, and test-design roles use
  frontier reviewer TOML files; repo inventory, tool-drift, machine-report
  summary, and execution-only log roles stay on mini helper TOML files; broad
  design, implementation, and ship-decision roles use frontier TOML files.
- `xhigh` is a manual session escalation, not a project-wide default.
- mode の扱い
  - plan mode や permissions は session 単位で、per-agent TOML には書きません
  - official Codex CLI では `/plan`、`/model`、`/permissions` を使います
- `.codex/config.toml` の `[agents.<name>]` が role registry、`.codex/agents/*.toml` が role behavior と model / reasoning 設定の正本です

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
