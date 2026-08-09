# Codex Project Setup

<!--
@dependency-start
contract agent-runtime
responsibility Documents Codex Project Setup for this repository.
upstream implementation ./config.toml project-scoped Codex settings
upstream design ../agents/task_catalog.yaml workflow family runtime budgets
upstream design ../agents/canonical/CODEX_SUBAGENTS.md subagent routing
downstream implementation ./hooks.json project-local hook declarations
downstream implementation ./hooks/hook_dispatcher.py owns the in-process active lifecycle contract
downstream implementation ../tools/agent_tools/hook_safety.py owns pure secret and destructive-Git leaves
downstream implementation ../tools/agent_tools/execution_resource_projection.py validates exact PostToolUse projection bytes
downstream design ./hooks/hook_dispatcher.py RETIRED_HOOK_ROUTES assigns former child routes to explicit owners
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
- `.codex/config.toml` の `[agents].max_threads = 27` は direct frontier `21` と nested reservation `6` から生成した requested/configured readback です。platform-effective / current-available capacity は別入力であり、27 を runtime の普遍的な cap とは扱いません
- `[agents]` は上限と timeout の設定であり、上位 runtime / developer instruction が要求する explicit subagent authorization を上書きしません。明示許可が無い session では fan-out plan と handoff packet を作り、実際の spawn は許可後に行います
- plan mode や permissions のような mode は session 単位です。official Codex CLI では `/plan`、`/model`、`/permissions` を使います
- runtime が `/agent` を提供する場合は inventory 確認に使い、使えない場合は `.codex/agents/*.toml` を直接見ます
- 最初の作業 update では `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言します
- `/goal <objective>` を使う task では、`agents/workflows/codex-goals-workflow.md` の Goal-Specified Plan-Mode Entry に従い、`/goal` 設定後に `/plan` で contract と evidence map を固定してから実装します
- token 消費を見直す場合は `agents/workflows/token-efficient-codex-workflow.md` を overlay とし、既存 session / role metric から重複 fan-out、再読、過大 tool output を特定します。task 名や見積もり規模から profile / agent mode を先に固定しません

## Goal And Plan Mode

- stable な goal 機能は Codex runtime の既定を使い、project config で feature flag を再列挙しません。
- TUI の user-facing command surface は `/goal`, `/goal <objective>`, `/goal pause`, `/goal resume`, `/goal clear` です。
- `/goal` は session view です。repo-owned durable state は top-level `goal.md`、機械 gate は `tools/agent_tools/goal_loop.py status` に置きます。
- template repo の active `goal.md` は runtime state であり、派生 repo seed に混入させません。tracked product state に入れず、必要なら `.gitignore` で ignored local file として保持します。
- goal-driven task では `/goal <objective>` の直後に `/plan <goal-driven task summary>` を使い、Plan-mode output に `Goal Contract`、`Exit Criteria Mapping`、`Source Packet`、`Reuse Survey`、`Execution Slices`、`Budget Policy` を出します。
- pre-goal subagent fan-out は active runtime の authorization に従います。明示許可がある場合は read-only wave を起動し、無い場合は `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` と handoff packet を artifact に残します。
- 上記が揃うまで implementation、subagent write handoff、closeout は開始しません。

## User-Level Token Profiles

`codex -p <profile>` reads machine-local user config, not this repository.
AgentCanon therefore does not duplicate profile values or assign profiles from
task labels. The project starts from `.codex/config.toml`; an operator may
change a user profile for a fresh session after observed token, latency, or
tool-output evidence identifies a runtime constraint. Profile changes do not
waive workflow gates and do not authorize dropping decision-relevant context.

## Runtime Capacity And Lifecycle Projection

- `.codex/config.toml` の `max_threads` は、宣言 topology の生成値を
  loader/readback した `configured_max_threads` です。現在の生成値は
  `21 + 6 = 27` であり、普遍的な ceiling ではありません。
- requested / configured / platform-effective / workflow-demand /
  write-cap / nested-reserved / available は [capacity handshake owner](../agents/canonical/CODEX_SUBAGENTS.md#capacity-and-lifecycle)
  の型付き projection に従います。effective は予約後の既知制約の最小値で、
  saturation は work を queue します。model-capacity event は thread
  saturation と別です。
- `job_max_runtime_seconds = 3600`
  - 長めの review / repo scan / validation を含む subagent job を 1 時間まで許容します
- `max_depth = 2`
  - one bounded child-subagent layer を許可します
- 同時 spawn と write frontier は宣言 topology と pairwise-disjoint write
  scope から生成されます。固定 active/write 数、task-size/count/time
  budget、または capacity probe は認可根拠になりません。
- `team_manifest.yaml` の `run.spawn_budget.active_subagents` が総同時起動 budget、`run.spawn_budget.max_write_subagents` と `run.write_scope_policy.max_write_subagents` が write-capable subagent だけの上限です。write-capable 上限は総同時起動 cap と区別します。
- same-role instance policy は `agents/task_catalog.yaml` と generated
  `team_manifest.yaml` の `run.delegated_spawn_policy` が正本です。
  `.codex/config.toml` の `[agents]` には Codex runtime が読む runtime
  limit と `[agents.<role>]` registry だけを置き、policy 文字列を置きません。
  `role_id+instance_id+agent_type` が instance key で、`max_threads` は runtime cap であり
  role cardinality の source ではありません。
- write-capable subagent instance は既定 1 体から始めます。parent が `team_manifest.yaml` の write policy と handoff で dependency order、wave plan、disjoint write scope、integration order、review gate を固定した場合だけ、同じ role type を含む複数 writer instance を spawn budget 内で並列化できます。衝突する target は禁止対象ではなく順序制約として先行 / 後続 wave に分けます。
- 各 user input は `same_active_task_delta` / `scope_or_contract_change` /
  `new_task` に分類します。owner、責務、context、write authority、validation
  route が互換なら active subagent を revised scope でも再利用します。独立
  review、disjoint write authority、incompatible owner/context、または failed
  context integrity の場合だけ fresh follow-up wave を選びます。新しい turn や
  packet 名だけでは fresh の理由になりません。coordination または resumption
  が必要な場合だけ checkpoint、updated packet path、run bundle を残します。
- `team_manifest.yaml` には選択した `run.subagent_lifecycle_policy` と fresh
  条件を出し、`fresh_subagents_required: true` と
  `reuse_for_new_task: forbidden` を一律の handoff 契約にはしません
- closeout は canonical `spawned -> active -> durable result/error -> handed
  back -> descendants closure verified -> close requested -> closed ->
  reservation released` を全 descendant で確認し、canonical `close_agent`
  ToolCall を含む CloseoutPacket を使います。

## Hook Context

- project-local hook は `.codex/hooks.json` で宣言し、project config に stable feature flag を重ねません。
- `hooks.json` は active event ごとに dispatcher を一回だけ起動し、コマンド自体に Git の root 探索や child subprocess を含めません。active events は `UserPromptSubmit`、`PreToolUse`、`PostToolUse` だけです。legacy `Stop` は dispatcher が inactive no-op として受け付けますが、`hooks.json` には登録しません。
- `HOOK_EVENT_CONTRACTS` がイベント、matcher、failure semantics、telemetry を canonical typed table として所有します。`python3 .codex/hooks/hook_dispatcher.py --contract` は active/inactive event、matcher、failure、telemetry、retired route table を readback します。
- `UserPromptSubmit` は pure owner `tools/agent_tools/hook_safety.py` の secret matcher だけを使い、高確信の private key / API key を block します。`PreToolUse` は同じ owner の destructive Git parser だけを使い、block payload の command 情報は `operation` と `command_sha256` に限定します。retired child tombstones は `tools/agent_tools/hook_retirement.py` が単独で所有します。
- `PostToolUse` は managed execution resource producer の成功した exact projection だけを in-process validator で forward します。malformed payload、validator failure、spool failure は fail-open です。
- 各 active event は `HookLogContext` を一度だけ使い、payload は fingerprint、event、bounded かつ redacted decision telemetry だけを local spool へ no-replace で書きます。prompt、command、stdout、stderr は保存せず、spool failure は安全判定を変更しません。
- 旧 log mount、cause、OOP、module、library、helper、style、notebook、review、goal、authority、role、reference、summary、auto-sync child は削除せず、`RETIRED_HOOK_ROUTES` と各 owner の explicit command / skill が移行先を示します。これらは active hook hot path ではありません。
- `bash "$(PYTHONPATH=vendor/agent-canon/tools:tools python3 -c "from pathlib import Path; from agent_tools.agent_canon_source_root import resolve_agent_canon_source_root; print((resolve_agent_canon_source_root(Path(\".\")).source_root / \"tools/sync_agent_canon.sh\").as_posix())")"` link-root は root `.codex/hooks.json` と `.codex/hooks/` を shared canon へリンクします。

## Model Settings

- `agents/model_profiles.toml` is the canonical typed authority for every
  parent and child model, reasoning, capability, context, return, checkpoint,
  and continuation field.
- `tools/agent_tools/model_profile_registry.py` materializes closed
  `.codex/agents/*.toml` and `agents/agents_config.json` generated views.
- `tools/agent_tools/check_agent_runtime_alignment.py` and
  `tools/agent_tools/evaluate_codex_agent_roles.py` validate the materialized
  agent TOML files directly.
- `agents/model_profiles.toml` が child model、reasoning、capability、context、
  return schema、continuation を所有し、canonical materializer が
  `.codex/agents/*.toml` と `agents/agents_config.json` の role projection を生成します。
  role view を手動の model authority として編集しません。
- generated view の更新後は alignment readback を確認し、load 済み session
  との不一致は手動編集せず restart して canonical projection を再読込します。
- The parent uses Sol/high and owns integration and final approval. Sol/xhigh is
  an explicit high-risk or final escalation, not a child-role default.
- mode の扱い
  - plan mode や permissions は session 単位で、per-agent TOML には書きません
  - official Codex CLI では `/plan`、`/model`、`/permissions` を使います
- `.codex/config.toml` の `[agents.<name>]` は role registration を所有し、
  model / reasoning authority は `agents/model_profiles.toml`、role TOML は
  materialized readback view です

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
- `terra`
- `worker`

## Smoke Test

subagent inventory や research perspective pack を触ったら、次で bundle と runtime surface を確認します。

```bash
python3 tools/agent_tools/smoke_test_research_perspective_pack.py
python3 tools/agent_tools/bootstrap_agent_run.py --help
python3 tools/agent_tools/doc_start.py --task "paper writing task" --kind paper --owner "codex" --dry-run
```
