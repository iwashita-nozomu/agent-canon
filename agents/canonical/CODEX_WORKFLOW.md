<!--
@dependency-start
responsibility Documents Codex Workflow for this repository.
upstream design ../../ROOT_AGENTS.md root runtime entrypoint
upstream design ./CODEX_SUBAGENTS.md subagent routing contract
upstream design ../workflows/derived-agent-canon-diff-workflow.md shared canon diff workflow
downstream design ../templates/closeout_gate.md closeout gate contract
upstream design ../../documents/dependency-manifest-design.md dependency manifest design
downstream implementation ../../tools/agent_tools/task_close.py enforces closeout keys
@dependency-end
-->

# Codex Workflow

この文書は、Codex でこの repo を扱うときの標準フローです。
会話の過去文脈に依存せず、毎回同じ順序で進められるようにします。

## Start Here

1. `AGENTS.md` を読む
1. clean worktree なら `make agent-canon-ensure-latest` を実行し、dirty なら未実行理由を最初の作業 update に書く
1. Base Runtime Packet を読む
1. Cross-Cutting Packet を読む
1. `agents/skills/README.md` と `$agent-orchestration` skill を読み、routing mode と skill set を先に決める
1. `agents/TASK_WORKFLOWS.md` で task family を決める
1. 実装を伴う task では `agents/workflows/implementation-waterfall-workflow.md` を読む
1. subagent を使う task では `agents/canonical/CODEX_SUBAGENTS.md` を読む
1. `agents/canonical/ARTIFACT_PLACEMENT.md` で文書の置き場を決める
1. 必要なら `.agents/skills/` から該当 skill を読む

Base Runtime Packet:

- `README.md`
- `agents/workflows/README.md`
- `agents/README.md`
- `agents/TASK_WORKFLOWS.md`
- `agents/canonical/CODEX_WORKFLOW.md`

Cross-Cutting Packet:

- `documents/REVIEW_PROCESS.md`
- `documents/AGENTS_COORDINATION.md`
- `documents/coding-conventions-python.md`
- `documents/notes-lifecycle.md`
- `agents/workflows/agent-learning-workflow.md`
- `documents/agent-canon-subtree-migration.md`
- `notes/guardrails/README.md`
- `notes/guardrails/engineering_avoidances.md`
- `docker/README.md`
- `memory/USER_PREFERENCES.md`
- `memory/AGENT_PHILOSOPHY.md`

## Required Intake Sweep

### Agent Canon Freshness

task 開始時は、local snapshot の `vendor/agent-canon/` を upstream `agent-canon` に合わせます。

- clean worktree では `make agent-canon-ensure-latest` を実行します
- dirty worktree では `bash tools/sync_agent_canon.sh ensure-latest` が stale 判定時に止まるため、未実行理由を最初の作業 update に書き、commit / stash 後に再実行します
- `ensure-latest` は `git subtree split --prefix=vendor/agent-canon HEAD` と upstream `agent-canon/<branch>` を比較し、必要なときだけ subtree pull を行います
- upstream より local shared canon が進んでいて remote history が local split の祖先なら pull せず、closeout で `bash tools/sync_agent_canon.sh push` を自然な次手として実行します。external block や user stop がある場合だけ未実行理由を残します
- local shared canon history が upstream `main` と diverge している場合は `ensure-latest` を fail-closed で停止し、`agents/workflows/derived-agent-canon-diff-workflow.md` に従って proposal branch push、maintainer merge、派生 repo snapshot 再同期を完了してから実装へ戻ります

### Context Sweep

実装、設計変更、文書改訂、実験計画の前に、会話だけを根拠に進めません。
次を topic keyword で探索し、該当 file を読んでから着手します。

- `documents/`
- `memory/`
- `notes/knowledge/`
- `notes/guardrails/`
- `notes/failures/`
- `notes/themes/`
- `notes/branches/`
- `notes/worktrees/`
- `notes/experiments/`
- `references/`

user の durable preference を見落とさないため、`memory/USER_PREFERENCES.md` は毎回読む固定 note にします。
agent の作業哲学と対話から得た学習を見落とさないため、`memory/AGENT_PHILOSOPHY.md` も毎回読む固定 note にします。

### Missing File Or Path Triage

file や path の欠落を見つけたときは、再作成、削除済み判定、repo-local 例外扱いの前に template と shared canon を確認します。

1. current repo で、欠落している path が root symlink view、synced root copy、shared workflow / skill / tool / memory surface、または template 由来の scaffold かを確認する
1. template root または登録された template remote / snapshot で同じ path の有無と現在の正本形を確認する
1. `vendor/agent-canon/` と standalone `agent-canon` で同じ path の有無、rename、移動、sync 対象からの除外理由を確認する
1. canon-owned surface なら `documents/SHARED_RUNTIME_SURFACES.md` と `tools/sync_agent_canon.sh` の surface list に従い、`link-root`、vendor update、standalone canon update、または意図的削除のどれかに分類する
1. template と canon のどちらにも無く、task 固有に必要な file だけを新規作成候補にし、既存実装・文書で足りない理由を run bundle に残す

欠落を見つけた agent は、handoff や review artifact に `missing_file_triage` として確認した template path、canon path、分類、次 action を記録します。
「無いから作る」「無いから無視する」は、template / canon 確認前の有効な判断ではありません。

### MCP Surface Preflight

MCP tool や `repo_mcp_server` が必要な task では、configured MCP inventory を先に確認します。

```bash
python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server
```

- `repo_mcp_server` の正本 launcher は `.codex/config.toml` の `[mcp_servers.repo_mcp_server]` です。
- template / derived repo では host-global command ではなく root `mcp/` から `vendor/agent-canon/mcp/` の repo-local launcher を起動します。
- `.codex/hooks.json` の `SessionStart` / `UserPromptSubmit` hook は MCP preflight context を session に注入します。これは注意喚起と routing 補助であり、checker 実行と run bundle evidence の代替ではありません。
- configured inventory に無い server を、parent や worker が bridge-local process として暗黙に起動して代替してはいけません。
- inventory にあるが startup に失敗する場合は、`mcp/` symlink view、launcher path、または host の base command availability の問題として run bundle に記録し、MCP 前提作業を続けません。
- contract 確定前の preflight 記録は `work_log.py --allow-missing-request-clause-id --missing-request-clause-reason "<reason>"` で run bundle に残します。

### Library And Reuse Sweep

新しい code path、module、helper、test、script を足す前に、導入済みライブラリと既存の再利用候補を探索します。
dependency surface は task に応じて次を見ます。

- `docker/requirements.txt`
- `pyproject.toml`
- lockfile
- build file
- package manager file
- 必要なら `pipdeptree` / `deptry`

既存実装の探索対象は task に応じて次です。

- `python/`
- `tests/`
- `src/`
- `include/`
- `lib/`
- `scripts/`

既存実装があるのに別名の重複 module を新設しません。
既存ライブラリや既存実装で足りない理由を言えない限り、新規追加を選びません。

### File Dependency Manifest

新規作成・編集する human-authored text file では、ファイル冒頭に `@dependency-start` / `@dependency-end` marker を持つ dependency manifest block を置きます。
設計正本は `documents/dependency-manifest-design.md` です。
旧 `Dependency Files:` block は新規・変更 file では使いません。

- manifest の内部 DSL は `<direction> <kind> <relative-path> <reason...>` です
- `direction` は `upstream` または `downstream` です
- `kind` は `design`、`implementation`、`environment` です
- path は manifest を持つ file から見た相対 path です
- 依存として書くのは、その file を理解・実行・検証するために読むべき repo 内の正本 file です。単なる同一 directory の全列挙や推測 dependency を水増ししません
- upstream は「編集前に読む file」、downstream は「編集後に影響確認する file」として分けます
- 依存が無い direction は行を置きません。`none` placeholder は置きません
- Markdown は title 直後、Python / shell / TOML / YAML など comment 可能な file は shebang / encoding marker 直後、C-like file は先頭 comment block に置きます
- line comment しかない format では `# @dependency-start` のように line comment wrapping を使います
- commentless format や generated / binary / vendored external file は scan tool の分類に従い、必要なら同じ変更の design / manifest / README に理由を残します

編集 workflow:

1. 変更対象 file の manifest を先に読み、upstream edge の target を編集前 context として読む
1. manifest が無い checkable file を編集する場合は、同じ差分の最初に `@dependency-start` block を追加する
1. downstream edge を持つ file を編集した場合は、差分後に downstream target を確認する
1. 新しい dependency edge を足す場合は、同じ変更で reverse edge も足すか、migration 中で足せない理由を review artifact に記録する
1. subagent handoff には `dependency_manifest_plan` を含め、編集対象ごとの upstream / downstream edge と読む順序を固定する

closeout 前に、少なくとも次を実行します。

```bash
python3 tools/agent_tools/check_dependency_headers.py --changed
bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing
bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header
```

dependency edge を追加・変更した場合は次も実行します。

```bash
bash tools/agent_tools/check_dependency_graph.sh --print-edges
```

`check_dependency_graph.sh` は upstream graph と downstream graph を別々に扱い、自己参照、reverse edge、kind mismatch、cycle を検証します。
移行期間中に repo 全体の既存 graph failure が残る場合でも、新規・変更 file が旧形式や新規 reverse-edge 欠落を増やした状態で closeout しません。

## Task Classification

次の 6 つから 1 つ選びます。

- `Scoped Change`
- `Research-Driven Change`
- `Large Delivery`
- `Platform And Environment`
- `Comprehensive Development`
- `Adaptive Improvement Loop`

分類規則:
- code / docs / tools / runtime をまとめて rework するなら `Comprehensive Development`
- Docker / CI / dependency を触るなら `Platform And Environment`
  - `environment-maintenance` と `environment_change_proposal.md` を先に起こし、code requirement と blocked command を固定する
  - repo-local virtual environment を作らず、environment validation には `bash tools/docker_dependency_validator.sh` を使う
- 外部調査や比較実験が必要なら `Research-Driven Change`
- tuning、比較改善、探索的 protocol refinement を backlog 付きで回すなら `Adaptive Improvement Loop`
  - Agile outer loop とし、1 extension ごとに 1 waterfall run-id / 1 waterfall pass / 1 decision state へ分解する
- chunk ごとの delivery なら `Large Delivery`
- それ以外は `Scoped Change`

## Completion Bar

user-facing completion は、最小実装、1 chunk、1 slice、checkpoint pass、または一部仕様の実装ではありません。
closeout 前に reviewer と auditor は次を明示的に確認します。

- 各 must-do clause と completion-evidence clause が、実装、文書、test、command、artifact、または明示された deferred / rejected clause に対応している
- request に含まれる仕様と実際の product surface の間に未実装の gap が残っていない
- schedule、review、validation、commit / push、shared canon sync、follow-up 判断を含む今回 scope の task が 1 つも未完了で残っていない
- task が数式、擬似コード、仕様、method contract を持つ場合、runtime success だけでなく implementation alignment evidence が review artifact に残っている
- required review の `fix now` findings が実装へ反映され、どんなに小さい review-driven fix でも full required review set を最新 diff に対して最初からやり直している
- 反映しない findings は follow-up ではなく、今回の completion を阻害しない理由と escalation が artifact に記録されている

`closeout_gate.md` の `spec_product_coverage_complete=yes`、`review_findings_integrated=yes`、`post_fix_full_review_complete=yes` が揃うまで、`user_completion_report` を `unlocked` にしてはいけません。

## Mechanical Completion Loop

実装後から user-facing completion までの間は、parent の自己判断だけで閉じず、次の機械的 loop を `closeout_gate.md` に evidence として残します。

1. `user_request_contract.md` の active clause、`schedule.md` の planned work unit、直近 review findings、validation blockers、commit / push、shared canon sync、follow-up 判断を一覧化します。
1. 最新 diff と tracked / untracked state を確認し、変更対象 file の dependency manifest、downstream edge、旧参照、正本でない copy / snapshot / backup path を見ます。
1. 必要な repo-wide dependency review、静的解析、docs / tests / agent checks を実行します。差分限定 check だけでは loop を閉じません。
1. read-only の diff-check agent を起動し、run bundle、request contract、schedule、latest diff、validation evidence、dependency evidence を渡します。
1. diff-check agent の decision が `approve` 以外なら、fix-now finding を実装して loop の 1 に戻ります。`escalate` は該当する設計・計画 stage へ戻します。
1. diff-check agent が `approve` し、未完了 work unit、未解決 finding、未実行 validation、未同期 canon、未 commit / push、未判断 follow-up が無い場合だけ loop を止めます。

`closeout_gate.md` の `mechanical_completion_loop_complete=yes` と `diff_check_agent_complete=yes` が揃うまで、`user_completion_report` を `unlocked` にしてはいけません。

## Minimal Skill Set

Codex では、まず `$agent-orchestration` を起点にし、`agents/skills/README.md` から必要最小限の skill だけ選びます。
user が skill を明示したい場合は `$skill-name` を使います。例: `$repo-onboarding`、`$research-workflow`、`$paper-writing`
細粒度の review pass、CLI adapter、artifact placement、validation helper は public skill ではなく、`documents/REVIEW_PROCESS.md` と `agents/canonical/` に寄せます。
repo-changing task では `$agent-orchestration` と `$subagent-bootstrap` を `$codex-task-workflow` に加えます。

- workflow / runtime routing:
  - `agent-orchestration`
- repo 入口確認:
  - `repo-onboarding`
- subagent 起動:
  - `subagent-bootstrap`
- code review:
  - `change-review`
- Python diff:
  - `python-review`
- C / C++ diff:
  - `cpp-review`
- test design:
  - `test-design`
- paper writing:
  - `paper-writing`
- long-form docs:
  - `long-form-writing`
- academic docs:
  - `academic-writing`
- Markdown diff:
  - `md-style-check`
- worktree kickoff:
  - `worktree-start`
- worktree drift and cleanup:
  - `worktree-health`
- experiment inner loop:
  - `experiment-lifecycle`
- tuning / research / experiment の backlog-driven outer loop:
  - `adaptive-improvement-loop`
- literature and prior art:
  - `literature-survey`
- research outer loop:
  - `research-workflow`
- 包括的 repo-wide delivery:
  - `comprehensive-development`
- environment and tool rollout:
  - `environment-maintenance`
- preference note の整理と `AGENTS.md` 昇格:
  - `user-preference-sync`
- agent philosophy と対話学習の整理:
  - `agent-learning`

## Execution Flow

### 1. Intake

- context sweep と library sweep を先に行う
- 変更対象と acceptance criteria を短く固定する
- `user_request_contract.md` に must-do、must-not-do、completion-evidence の clause ID を書く
- repo-changing task では早い段階で `schedule.md` を TODO 正本として埋め、stage plan / clause coverage / planned work units を concrete にする
- 各 clause に source bucket を付け、`current_request`、`durable_user_preference`、`repo_or_code_precedent`、`domain_or_external_constraint`、`unknown_or_open_question` を混ぜずに扱う
- 不明点は即停止せず、notes、guardrails、documents、prior logs、local code / tests で解決できるかを `Requirements Resolution Sweep` に記録してから deferred / escalation を決める
- active な must-do、must-not-do、completion-evidence clause に `unknown_or_open_question` を残さない
- durable user preference は今回 request や repo evidence と結び付いたときだけ task requirement へ昇格する
- 最初の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する
- skill を user-facing に書くときは `$skill-name` を既定にし、`skills=<...>` でも同じ表記を維持する
- durable な user preference を観測したら、その場で `python3 tools/agent_tools/log_user_preference.py --preference "<...>" --kind provisional --source chat` を実行して `memory/USER_PREFERENCES.md` へ追記する
- agent-side の作業哲学、対話上の再発防止、task retrospective を観測したら、その場で `python3 tools/agent_tools/log_agent_learning.py --kind interaction-observation --statement "<...>" --source chat --evidence "<...>"` を実行して `memory/AGENT_PHILOSOPHY.md` へ追記する

### 2. Workflow Selection

- `agents/TASK_WORKFLOWS.md` から family を 1 つ選ぶ
- family をまたぐ場合も、主 family を 1 つ決める

### 3. Placement

- run 固有のメモは `reports/agents/<run-id>/`
- repo-wide の恒久文書は `agents/` か `documents/`
- 知見の蓄積は `notes/`
- packet 出力は tree 順ではなく、`CROSS_CUTTING_DOCUMENT_PACKET`、`DESIGN_DOCUMENT_PACKET`、`IMPLEMENTATION_DOCUMENT_PACKET`、`WORKFLOW_SUBAGENT_PROMPT_PACKET` の順で handoff に使う

### 4. Run Bootstrap

repo-changing task では bundle 作成と explicit subagent activation を既定にします。
ただし stage の具体的な責務と禁止事項は prose ではなく `.codex/agents/*.toml` を正本にします。

- repo を編集する
- specialist handoff を明示したい
- review artifact を残したい
- 長めの task で run 単位の記録が必要
- subagent と parent の責務を分けたい

とくに、`scheduler`、`schedule_reviewer`、`designer`、`design_reviewer`、`document_flow_reviewer`、`test_designer` は repo-changing task の標準構成とします。
Codex subagent では、`requirements_organizer`、`manager_reviewer`、`execution_planner`、`plan_reviewer`、`detailed_designer`、`detailed_design_reviewer`、`document_flow_reviewer`、`test_designer`、`worker` を stage ごとに明示します。
学術文章では、これに `notation_definition_reviewer` と `logic_gap_reviewer` を追加します。
論文や thesis chapter では、さらに `citation_evidence_reviewer` を追加します。
interactive Codex で要件整理と実行計画立案を行う場合は、parent session 側の plan-mode command を使ってから planning specialist を起動します。official Codex CLI では `/plan` です。
default の model split は、`gpt-5.5` が planning、writing、research、review、final judgment、broad / ambiguous implementation を担当し、`gpt-5.3-codex` が code survey、static test design、language-specific code review を担当する形です。設計packetで完全に切れる狭い実装sliceは `spark_worker` の `gpt-5.3-codex-spark` を first implementation candidate にし、設計判断、scope判断、review判断は `gpt-5.5` 側に残します。
- subagent の depth は固定値で規定しません。必要な追加層がある場合だけ parent が owner、入力 packet、write scope、review gate を明示して展開します。
- active spawn budget は workflow family に従って縛ります。機械設定の正本は `agents/task_catalog.yaml` の `workflow_families[].spawn_budget` です。現在の既定は `Scoped Change` で同時 8 体、`Large Delivery` / `Platform And Environment` で同時 10 体、`Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop` で同時 12 体までです。
- workflow family ごとの subagent prompt 正本は `agents/task_catalog.yaml` の `workflow_families[].subagent_prompt` です。
- budget を超える場合は例外扱いにし、`schedule.md` と `work_log.md` に理由、追加 role、expected output、write scope を残します。
- write-capable subagent は同時 1 体までに固定し、追加分は read-only review / research / survey role だけにします。

Codex runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を直接見ます。

最小コマンド:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "short task summary" \
      --task-id T1 \
      --owner "codex" \
      --workspace-root "$PWD"

bundle 出力には少なくとも次が含まれます。

- `CROSS_CUTTING_DOCUMENT_PACKET`
- `DESIGN_DOCUMENT_PACKET`
- `IMPLEMENTATION_DOCUMENT_PACKET`
- `WORKFLOW_SUBAGENT_PROMPT_PACKET`

parent は subagent handoff でこの packet path 群と `team_manifest.yaml` の `run.subagent_prompt_packet` / role 別 `prompt_contract` を明示入力し、文書 tree を逐次辿らせるだけの運用に戻しません。

研究・実験つき変更:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "research-backed change" \
      --task-id T4 \
      --owner "codex" \
      --workspace-root "$PWD"

環境変更:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "platform or environment change" \
      --task-id T8 \
      --owner "codex" \
      --workspace-root "$PWD"

学術文章:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "academic writing task" \
      --task-id T10 \
      --owner "codex" \
      --workspace-root "$PWD"

包括的開発:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "comprehensive development pass" \
      --task-id T12 \
      --owner "codex" \
      --workspace-root "$PWD"

反復改善:

    python3 tools/agent_tools/bootstrap_agent_run.py \
      --task "adaptive improvement loop" \
      --task-id T13 \
      --owner "codex" \
      --workspace-root "$PWD"

Adaptive Improvement Loop では、outer run の `experiment_change_loop.md` に `Extension Backlog` を持ち、各 extension で別の waterfall run-id を作ります。
次の extension へ進む前に、直前 extension の中間 `waterfall-gate-check`、final review、`task-close`、commit / push を完了させます。

`--task-id` を指定すると、`agents/task_catalog.yaml` にある task-default specialist と `default_for_tasks` review pack を自動で有効化します。cost を気にしない run では `--task-id` を基本にし、狭い例外だけ `--enable` で補います。
language-specific reviewer は task catalog に固定せず、`bootstrap_agent_run.py` が `--changed-path` か workspace の `git status --short` から自動で足します。
run bundle を起こしたら、`intent_brief.md` だけで進めず、`user_request_contract.md` を planning 前に埋めます。stage artifact、handoff、review では clause ID を明示します。
各 waterfall gate を次段へ進める前に `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate <gate>"` で中間 gate を確認します。

包括的開発の固定 Codex stack:

- `requirements_organizer`
- `manager_reviewer`
- `literature_researcher`
- `execution_planner`
- `plan_reviewer`
- `detailed_designer`
- `detailed_design_reviewer`
- `document_flow_reviewer`
- `test_designer`
- `project_reviewer`
- `docs_workflow_steward`
- `python_reviewer`
- `cpp_reviewer`
- `worker`

cost を無視して review coverage を優先する run では、research-driven change と comprehensive development は `--full-team` を許可します。

### 5. Implementation

- 実装は `agents/workflows/implementation-waterfall-workflow.md` の gate に従って進める
- Gate 1 / 4 / 6 / 7 / 8 / 9 の次段移行では `waterfall_gate_check.py` を通し、`WATERFALL_GATE_READY=yes` でない場合は指示された owner stage へ戻る
- 実装前に `design_brief.md` の `Installed Libraries And Existing Implementation Survey`、`Implementation Source Packet`、`Design-To-Implementation Trace` を読み、そこにある artifact、repo docs、dependency surface、code path、test plan を読了する
- 詳細設計前に `task_start.py` / `bootstrap_agent_run.py` の `DESIGN_DOCUMENT_PACKET` を読み、その path 群を `design_brief.md` の `Upstream Requirement Packet` に転記する
- 詳細設計では `design_brief.md` の `Canonical Tree-Head Plan` に、この task の後に tracked tree に残してよい設計文書 path と実装 path を固定し、parallel design doc、implementation copy、snapshot、backup path を残さないことを明記する
- worker は会話文脈を実装入力にせず、各 implementation slice の前に design artifact path、design section、test plan item、request clause ID を明示する
- `Installed Libraries And Existing Implementation Survey` または `Implementation Source Packet` がない、または design と現行 repo docs / code / dependency surface が矛盾する場合は実装せず Gate 5-6 へ戻る
- implementation は current tree head の canonical path だけを更新対象にし、`*_old`、`*_copy`、dated clone、parallel module、mirror directory のような別 truth surface を作らない
- `task_start.py` / `bootstrap_agent_run.py` の `IMPLEMENTATION_CODEX_AGENTS` を確認し、`spark_worker,worker` なら design trace、naming、test plan、write scope が固定済みの低リスクsliceを `spark_worker` へ先に渡す
- 実装 subagent を起動するときは `IMPLEMENTATION_DOCUMENT_PACKET` の path 群を明示入力し、chat 要約ではなく packet path を読ませる
- すべての stage subagent を起動するときは `team_manifest.yaml` の `run.subagent_prompt_packet` と該当 role の `prompt_contract` を prompt に含める
- `spark_worker` は設計判断、scope判断、review判断へ使わない
- chunk、slice、checkpoint、subpass が終わっても user-facing completion を返さず、remaining planned work units と next gate を確認してから続行する
- repo-changing task では run bundle の `work_log.md` を継続更新し、worktree では action log も同時に維持する
- worktree で作業する場合、編集前に `python3 tools/agent_tools/worktree_scope_lint.py --current` を通し、`Branch`、`Worktree path`、`Editable Directories`、`Read-Only Or Avoid Directories` が current state と一致することを確認する
- worktree では scope 更新、編集開始、テスト実行、実験開始 / 停止、carry-over 判断を action log に残し、各 entry に request clause ID を結び付ける。`WORKTREE_SCOPE.md` に contract path がある場合は `work_log.py` で run bundle `work_log.md` も同時に更新する
- `計画レビュー`、`詳細設計レビュー`、`文書通読レビュー` の分離や、implementation 着手条件は `.codex/agents/*.toml` を正本にする
- 包括的開発では `project_reviewer` を intake と closeout に追加し、repo-wide な integration risk を確認する
- 文書主体の成果物では `document_flow_reviewer` を通し、上から順に読んだときの意味の通り方を確認する
- README、workflow、guide、migration 文書のような長文では `long-form-writing` を読み、別 reviewer で `docs-completeness-review` も通す
- 論文、thesis chapter、scholarly note のような学術文章では `academic-writing` を読み、`notation_definition_reviewer`、`logic_gap_reviewer`、別 reviewer の `docs-completeness-review` を通す
- 投稿論文や thesis chapter の draft では `paper-writing` を読み、`citation_evidence_reviewer` も別 instance で通す
- code 変更では `test-design` を読み、実装前に `test_designer` で nasty case と regression case を固定する
- 研究・実験系の変更では `report_reviewer` と research perspective reviewers を default にし、optional 扱いを避ける
- JAX export / native runtime の task では、最初の implementation slice で `generic callable path`、`specialized coeff path`、`export-based generic path` のどれを触るか宣言する。generic path は `jax.export` artifact producer と consumer/runtime smoke を完了条件に含める
- cross-process export worker には live Python object reference を渡さず、serializable manifest と reconstruction recipe を渡す
- `LoadedProgram` のような runtime materialization は compile DAG node にせず、runtime vertex / lifetime scope として扱う
- まず導入済みライブラリ、既存 code path、既存 helper、既存 style を調べ、再利用と拡張を優先する
- 新規 helper や新規 module を足すときは、既存実装では足りない理由と、導入済みライブラリの設定変更や薄い wrapper で済まない理由を design packet に結び付ける
- worker は approved design または明白な局所 precedent にない variable、function、class、file、CLI flag、config key、public API identifier を発明しない
- checkpoint review は diff だけでなく approved design packet と source packet citation の一致を確認する
- role ごとの model policy は `agents/canonical/CODEX_SUBAGENTS.md` に従う
- broad worker は `gpt-5.5` で、design-traced narrow slice の first candidate は `gpt-5.3-codex-spark` とする
- same-worktree single-writer rule は `worker.toml` と planning/reviewer TOML を正本にする
- 正本は `agents/` と `documents/` から先に直す
- runtime entrypoint は薄く保つ
- skill は repo 正本を置き換えず、導線だけを担う

### 6. Validation

- repo-changing task は差分限定ではなく全 repo 対象で `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` を通し、dependency graph、header 欠落、header format を確認する。失敗した header は修正してから再実行する
- repo-changing task は user-facing completion 前に `make ci` を通し、pytest、pyright、pydocstyle、ruff を全 repo 設定で確認する。`make ci-quick` は途中 checkpoint 用であり、final closeout の静的解析 evidence にはしない
- agent runtime / skill 変更では `make agent-checks`
- checkpoint では `make ci-quick` を使ってよいが、final closeout では `make ci` を優先する
- 必要に応じて `make ci`
- Python 変更では `pyright`、`pytest tests/`、`ruff check python tests --select D,E,F,I,UP` を確認する
- C / C++ 変更では project-native configure / build / test evidence を確認し、CMake project なら `cmake -S . -B build`、`cmake --build build`、`ctest --test-dir build` を既定候補にする
- 文書変更では markdown / link check を使う
- report を閉じる前には `documents/experiment-report-style.md` を確認する
- 研究系 task では `critical-review` と `report-review` の decision state を確認し、必要なら `research-perspective-review` を追加する

### 7. Closeout

- repo に残す差分がある task では、validation 後に commit を作る
- user が明示的に止めていなければ、final report の前に branch を push する
- user-facing final report は、`verification.txt` が `status=pass` で、`closeout_gate.md` が `auditor_status=resolved` かつ `user_completion_report=unlocked` で、`user_request_contract.md` が `all_clauses_resolved=yes` かつ `forbidden_drift_detected=no` になるまで出さない
- `closeout_gate.md` の `all_planned_chunks_complete=yes` と `overall_delivery_complete=yes` が揃うまで、chunk completion を completion report にしない
- `closeout_gate.md` の `unfinished_tasks_absent=yes` が揃うまで、予定作業、review 対応、validation、commit / push、shared canon sync、follow-up 判断が残る completion report を出さない
- `closeout_gate.md` の `dependency_headers_complete=yes` が揃うまで、作成・編集した text file の依存 file header が抜けた completion report を出さない
- `closeout_gate.md` の `repo_wide_dependency_tools_complete=yes` が揃うまで、checkpoint / final review で全 repo 対象の `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` を通し、header 修正まで完了していない completion report を出さない
- `closeout_gate.md` の `repo_wide_static_analysis_complete=yes` が揃うまで、全 repo 対象の `make ci`、または `python3 -m pyright` と `python3 -m ruff check python tests --select D,E,F,I,UP` の static analysis evidence が無い completion report を出さない
- `closeout_gate.md` の `spec_product_coverage_complete=yes` と `review_findings_integrated=yes` が揃うまで、仕様の一部だけの実装や未反映 review findings が残る completion report を出さない
- `closeout_gate.md` の `mechanical_completion_loop_complete=yes` が揃い、planned work、review findings、validation、dependency review、static analysis、commit / push、shared canon sync、follow-up 判断が構造化 loop evidence として残るまで completion report を出さない
- `closeout_gate.md` の `diff_check_agent_complete=yes` が揃い、run-local diff-check artifact が read-only independent agent、latest diff ref、`approve` decision、findings disposition を示すまで completion report を出さない
- `closeout_gate.md` の `canonical_tree_head_complete=yes` が揃うまで、正本でない設計文書、implementation copy、snapshot tree、backup path が残る completion report を出さない
- `workflow_monitoring.md` の signals / interventions / improvement decisions が埋まり、skill / config / workflow / memory の改善判断が `applied`、`recorded`、`not_applicable` のいずれかになるまで、workflow 監視が未完了の completion report を出さない
- `tools/agent_tools/evaluate_agent_run.py --report-dir reports/agents/<run-id> --write` が pass し、`closeout_gate.md` の `agent_evaluation_complete=yes` と `agent_evaluation.md` の `feedback_actions_resolved: yes` が揃うまで、agent behavior evaluation と feedback resolution が未完了の completion report を出さない
- `schedule.md` が TODO 正本として埋まっておらず、または `work_log.md` に意味のある execution trail が無い場合は completion evidence 不足として closeout を止める
- `notes/guardrails/engineering_avoidances.md` の log-derived avoid に当たる変更が残る場合、final report を出さず、修正または reviewer escalation に戻す
- user request が generic path の usable smoke を求める場合、specialized path の tuning、narrow smoke、header-only compile だけでは completion evidence にしない
- JAX export / native runtime の generic path は、`jax.export` artifact producer と consumer/runtime evidence が揃うまで completion evidence にしない
- 実験・性能改善では、spot run、debug run、smoke run、partial run、raw failure count だけを completion evidence にしない
- small toy、dense Jacobian、baseline 未比較の結果から trainer replacement、scalability、superiority、広い theorem を主張しない
- failure-onset dimension を記録せず、implementation bug と真の frontier limit を混同しない
- 実験・性能改善では、correctness evidence と performance evidence を別項目で示し、片方だけで両方を満たした扱いにしない
- final report には branch、commit、push の成否を短く残す
- push が失敗した、または意図的に skip した場合は、その理由を final report に明記する
- push が自然な完了条件に含まれる場合は、push の許可を取りに戻らず実行する
- closeout 前に `memory/USER_PREFERENCES.md` を見直し、stable になった preference があれば `user-preference-sync` で `AGENTS.md` への昇格要否を判断する
- closeout 前に `memory/AGENT_PHILOSOPHY.md` を見直し、task retrospective、interaction observation、promotion candidate を `agent-learning` で残すか判断する
- closeout 前に `agent_evaluation.md` の feedback actions を見直し、stable な失敗防止は `agent-learning` で記録し、確定した禁止事項は guardrail 昇格候補にする
- review-only task や no-change task では commit / push を要求しない

そのうえで、何を変えたか、何を確認したか、何を確認していないかを短く残して完了する

## Codex-Specific Rules

- `AGENTS.md` は Codex の最初の入口として保つ
- `.agents/skills/` を正規 skill path とする
- repo-changing task では、stage ごとの subagent / specialist を暗黙にせず明示する
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` は別 instance にする
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` も別 instance にする
- 論文 draft では `citation_evidence_reviewer` も別 instance にする
- 包括的開発では、同一 worktree の write role を `worker` 1 人に固定する
- 複数 writer を要する場合は、同一 worktree ではなく複数 worktree に分ける
- required review が unresolved のまま `worker` 相当の実装を始めない
- tracked repo change がある task では、required review、validation、commit、`origin` への push を経ずに完了扱いにしない
- tracked repo change で push が自然な完了条件なら、push の許可を取りに戻らず実行する。止めるのは user が明示的に止めた場合か external block がある場合だけとする
- 未完了の planned work、review finding、validation、commit / push、shared canon sync、follow-up 判断が残っている間は user-facing completion を返さない
- `verification.txt`、`closeout_gate.md`、`user_request_contract.md` が close 条件を満たすまで user-facing completion を返さない
- Codex 専用事情でも、再利用可能なルールは `agents/` に昇格する
- 会話文脈にだけ依存する運用は repo 正本にしない
