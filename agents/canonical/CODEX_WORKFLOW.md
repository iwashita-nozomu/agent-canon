<!--
@dependency-start
contract agent-runtime
responsibility Documents Codex Workflow for this repository.
upstream design ../../ROOT_AGENTS.md root runtime entrypoint
upstream design ./CODEX_SUBAGENTS.md subagent routing contract
upstream design ../workflows/derived-agent-canon-diff-workflow.md shared canon diff workflow
upstream design ../../issues/README.md durable AgentCanon operational finding storage
downstream design ../workflows/token-efficient-codex-workflow.md token-aware runtime mode overlay
downstream design ../templates/closeout_gate.md closeout gate contract
upstream design ../../documents/dependency-manifest-design.md dependency manifest design
upstream design ../../documents/runtime-profiles-and-check-matrix.md runtime profile and risk-based validation routing
upstream design ../../documents/BRANCH_SCOPE.md commit correctness and push contract
upstream design ../skills/tool-finding-report.md tool finding packet and prompt feedback workflow
downstream implementation ../../tools/agent_tools/task_close.py enforces closeout keys
@dependency-end
-->

# Codex Workflow

この文書は、Codex でこの repo を扱うときの標準フローです。
毎回同じ順序と repo evidence で進められるようにします。

## Reader Map

- This document owns the Codex task execution path from intake through completion, including routing, profile selection, implementation flow, and closeout.
- The early sections define startup reads and intake sweep; the middle sections classify tasks, completion bars, skills, and execution flow; the final section captures Codex-specific runtime rules.
- Start at `## Start Here` for any task, then jump to `## Required Intake Sweep` for repo state, `## Task Classification` for workflow selection, and `## Execution Flow` before implementation.
- For chunked reading, keep this map and `## Start Here` as the anchor, then load only the active profile or rule section named by the current run bundle.

## Start Here

1. `AGENTS.md` を読む
1. `agents/skills/README.md` と `$agent-orchestration` skill を読み、routing mode と skill set を先に決める
1. `agents/TASK_WORKFLOWS.md` で task family を決める
1. Runtime profile と implementation owner がまだ固定されていない repo-changing task では、広い packet 読解より先に canonical router / semantic-index / dependency review の structured output を取る
1. AgentCanon update surface が repairable なら `make agent-canon-ensure-latest` を実行する。親 repo の無関係な dirty state は evidence として記録し、clean な submodule branch checkout と stale parent gitlink の mismatch は warning/evidence として扱い、dirty / detached / unpushed / divergent source state を fail-closed blocker にする
1. 選択された workflow/profile が必要とする Base Runtime Packet だけを読む。inactive profile の packet は `not_applicable` として記録する
1. Cross-Cutting Packet は選択 route、review gate、または structured tool finding が必要にした slice を読む
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
- `documents/runtime-profiles-and-check-matrix.md`
- `notes/guardrails/README.md`
- `notes/guardrails/engineering_avoidances.md`
- `docker/README.md`
- `memory/USER_PREFERENCES.md`
- `memory/AGENT_PHILOSOPHY.md`

## Required Intake Sweep

### Agent Canon Freshness

task 開始時は、parent repo の `vendor/agent-canon` submodule pin と submodule worktree を upstream `agent-canon` に合わせます。

- submodule repo では、`make agent-canon-ensure-latest` の判断対象を AgentCanon update surface に限定します。
- AgentCanon update surface は `vendor/agent-canon/` submodule worktree、parent gitlink、`.gitmodules`、および `link-root` が触る AgentCanon-owned root symlink / copy view です。
- clean な submodule worktree が remote main を指していて parent gitlink だけ古い場合は、gate / preflight が parent gitlink を stage または commit して検査を続行します。
- clean な submodule worktree が non-default branch を指し、その branch head が remote branch に push 済みで fetched remote main を含み、parent gitlink だけが古い場合は `deferred_branch_pr` evidence として記録し、routing / planning / review を続けます。AgentCanon PR merge 後に `make agent-canon-ensure-latest` を再実行することが closeout blocker です。
- `vendor/agent-canon/` に local commit、dirty state、remote main と diverge した history がある場合は、先に `bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty` で current branch に GitHub main を取り込み、AgentCanon PR に出します。
- local checkout branch は valid な shared-canon work surface です。local checkout に積まれた commit は消して最新化する対象ではなく、GitHub `main` を merge して conflict を解き、通常の AgentCanon PR として review / merge します。機械 evidence として `merge-main-into-current-preserve-dirty` の `agent_canon_merge_source_sha`、`agent_canon_merge_post_head`、`agent_canon_merge_remote_main_in_post_head=yes`、`agent_canon_merge_remote_main_verified=yes` を run bundle、PR body、または work log に残します。
- update surface が unsafe な場合だけ、`agents/workflows/agent-canon-pr-workflow.md` または `agents/workflows/derived-agent-canon-diff-workflow.md` に入り、AgentCanon branch / PR に出し、merge 後に template / derived repo 側で `make agent-canon-ensure-latest`、`bash tools/sync_agent_canon.sh link-root`、parent pin commit を作ります。
- AgentCanon source change、parent submodule pin change、`.gitmodules`
  change、AgentCanon-owned root runtime view / root-copy surface change、parent
  root sync PR は `agentcanon_structure_followup=required` です。template /
  derived parent root で `bash tools/sync_agent_canon.sh link-root` と
  `bash tools/sync_agent_canon.sh check` が pass した後だけ
  `agentcanon_structure_followup=pass` として closeout に使えます。
- `ensure-latest` は `.gitmodules` の URL と submodule `origin/main` を見て、parent gitlink と submodule worktree HEAD が remote main と一致するかを判定します。remote main が進んでいれば submodule を fast-forward し、parent repo の gitlink commit と root shared surface を同期します。
- local submodule commit が remote main に含まれている場合は、`bash tools/update_agent_canon.sh apply` または `make agent-canon-ensure-latest` で parent pin を remote main へ揃えます。
- local submodule history が remote main と diverge している場合は fail-closed とし、`agents/workflows/derived-agent-canon-diff-workflow.md` に従って AgentCanon branch push、AgentCanon PR / merge、派生 repo submodule pin 再同期を完了してから実装へ戻ります。
- `task_start.py` と `bootstrap_agent_run.py` の freshness preflight は script path ではなく `--workspace-root` を対象にします。template の root symlink view から起動したときに `skipped_source_canon` が出る場合は misconfiguration として扱い、workspace root、`.gitmodules`、`vendor/agent-canon` の状態を確認します。`skipped_source_canon` は standalone AgentCanon source checkout でだけ妥当です。

### Branch Reuse Default

既存 branch / PR が現在の task、追加 user instruction、または follow-up と同じ ownership surface を担える場合は、その branch / PR を継続します。branch / worktree 作成 route は、作成前に route authority と理由を記録する 1 gate に集約します。

- 通常 task の authority は、user が別 branch を明示した場合の `user_request` です。AgentCanon source update の authority は、AgentCanon branch / PR workflow と canonical update tool が owner の `agent_canon_workflow` です。
- 「fresh start」「dirty state 回避」「追記の分離」「task 途中の追加指示」「既存 PR の checklist 追記」は、既存 branch / PR 継続の理由として扱います。
- branch / worktree 作成前に run bundle、work log、または PR body へ `branch_creation_reason=<reason>` または `worktree_creation_reason=<reason>` と authority 対応箇所を記録します。shell 実行では `branch_worktree_guard.py` の PreToolUse gate に `AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=user_request` または `AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=agent_canon_workflow` と `AGENT_CANON_BRANCH_WORKTREE_REASON=<reason>` を渡します。
- AgentCanon source 変更は current `vendor/agent-canon` branch / AgentCanon PR を優先して継続します。parent repo の `canon-pin` branch は、AgentCanon PR route が確定した後に parent pin だけを隔離する場合に限ります。

### Runtime Profile And Risk Selection

Before broad context loading or validation, classify the task with
`documents/runtime-profiles-and-check-matrix.md`.

- Routine docs and Focused code still need targeted validation. When they are
  repo-changing implementation / patch / doc-edit work, write-capable
  `spark_worker` / `worker` handoff is the default; parent-direct requires a
  recorded exception rationale before editing.
- Profile changes activate only their matching checker family: Docker,
  GitHub automation, experiment, C++, devcontainer, memory/eval, or maintenance.
- Shared canon changes activate AgentCanon PR workflow and PR gate.
- Large delivery activates the full run bundle, independent review, full
  dependency review, and full validation gate.

Use only the active profile for the task. Mark inactive profiles as
`not_applicable` in the run artifact or PR body when evidence is needed.

### Context Sweep

実装、設計変更、文書改訂、実験計画の前に、repo evidence を根拠にします。
context sweep は `requested_scope` を保存したうえで work packet を作る手順です。
先に user request から要求された file、workflow、check、doc、PR state を
`requested_scope` として固定し、task topic、runtime profile、implementation
surface router、semantic-index / context-pack、dependency review の structured
output で `work_scope` を段階化します。選ばれなかった profile / document bucket
は、request に無関係である evidence がある場合だけ `not_applicable` にします。
Large delivery / Shared canon でも、bounded responsibility route は作業順序を
決める artifact です。対象範囲の正本は `requested_scope` に残します。読む
slice を選ぶ場合は、coverage map に `covered_surfaces`、`deferred_surfaces`、
`omitted_surfaces` と理由を残してから進めます。

- `documents/`
- `issues/`
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

raw text search の hit だけで編集対象を決めません。
検索 hit を修正 surface にする場合は、hit path を保存し、dependency header graph と責務 owner で edit scope を展開します。owner boundary、差し替え可能な単位、validation route、public impact boundary が evidence で閉じたら、minimal write-capable `spark_worker` / `worker` handoff を作ります。parent repository edits は `PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes` かつ `PARENT_DIRECT_WRITE_EXCEPTION=<explicit_user_approval|runtime_blocker>` を記録した場合だけ許可します。
bounded route では、existing tool の実行と patching を tool-owned evidence から開始します。runtime `SKILL.md` 読了は、対象 property を正本として持つ existing tool の実行後に必要な場合だけ使う follow-up context です。結果の解釈や修正に必要な owner surface だけを開きます。bounded route は route と validation profile の signal であり、実装 behavior は契約完全実装ポリシーから導きます。

```bash
git grep -l "topic keywords" -- <responsibility-scoped dirs> \
  | sed -n '1,200p' > reports/search_hits.txt
wc -l reports/search_hits.txt > reports/search_hits.count
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --search-hits-file reports/search_hits.txt
```

`dependency_edit_scope.txt` は path artifact として残します。会話、Issue、PR body、または run bundle の本文には、件数、主要 path、編集した file、確認した file、意図的に外した candidate だけを書きます。

### Missing File Or Path Triage

file や path の欠落を見つけたときは、再作成、削除済み判定、repo-local 例外扱いの前に template と shared canon を確認します。

1. current repo で、欠落している path が root symlink view、synced root copy、shared workflow / skill / tool / memory surface、または template 由来の scaffold かを確認する
1. template root または登録された template remote / current template main で同じ path の有無と現在の正本形を確認する
1. `vendor/agent-canon/` と standalone `agent-canon` で同じ path の有無、rename、移動、sync 対象からの除外理由を確認する
1. canon-owned surface なら `documents/shared-runtime-surfaces.toml`、`documents/SHARED_RUNTIME_SURFACES.md`、`tools/sync_agent_canon.sh` の manifest-backed ownership に従い、`link-root`、vendor update、standalone canon update、または意図的削除のどれかに分類する
1. template と canon のどちらにも無く、task 固有に必要な file だけを新規作成候補にし、既存実装・文書で足りない理由を run bundle に残す

欠落を見つけた agent は、handoff や review artifact に `missing_file_triage` として確認した template path、canon path、分類、次 action を記録します。
欠落 path の判断は、template / canon 確認後の `missing_file_triage` に基づけます。

### Repository Task Boundary

普通の相談、壁打ち、routing-only advice、説明だけの turn は conversational
turn として扱います。その場合は会話だけで応答します。

GitHub Actions run、PR check、GitHub Issue を読むだけの GitHub-only read
inspection は GitHub inspection として扱います。

local repo state 確認、file edit、validation、PR / issue mutation、local CI
実行、または実装作業へ切り替わった時点で repository task として扱い、
切り替えをユーザー向け update で明示してから通常の workflow gate に入り
ます。

### ユーザー向け言語

ユーザー向けの作業更新、最終報告、レビュー要約、handoff guidance、
reader-facing docs は日本語で書きます。機械可読の key、command、path、
role id、schema は正本表記を保ちます。

repo-changing run では `team_manifest.yaml` の
`run.user_facing_language_policy` を handoff packet に含め、subagent と reviewer
が同じ方針を参照できる状態で渡します。`task_start.py` と
`bootstrap_agent_run.py` の `USER_FACING_LANGUAGE=ja` を起動時 evidence として
扱います。

### 契約完全実装

実装 behavior は request clauses、acceptance contract、
`Implementation Source Packet`、`Design-To-Implementation Trace`、
dependency-expanded scope、validation route、review gate から導きます。
見た目の広さ、owner-bounded route、MVP、thin slice は暫定的な routing、
wave、validation profile の signal に留めます。owner boundary や impact surface が
違うと分かった時点で route を更新します。

repo-changing run では `team_manifest.yaml` の
`run.contract_complete_implementation_policy` を handoff packet に含めます。
`task_start.py` と `bootstrap_agent_run.py` の
`IMPLEMENTATION_COMPLETENESS_POLICY=contract_complete` を起動時 evidence として
扱います。contract gap、責務境界、API shape、依存方向、runtime contract の不足は
`design_issue_blocker` として Gate 5-6 に戻します。

### Design Integrity Gate

実装前の設計判断は、近い file、現在の finding、会話印象ではなく
owning responsibility model から始めます。Full staged route では `Abstract Design
Frame`、`Implementation Source Packet`、`Design Side-Effect Map`、
`Design-To-Implementation Trace` をそろえます。Parent-Direct Context Note は
routing / handoff artifact として扱い、edit authorization は別 gate で固定します。親が repo
を直接編集するには、同じ責務 model に加えて
`PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes` と
`PARENT_DIRECT_WRITE_EXCEPTION=<explicit_user_approval|runtime_blocker>` が必要です。
Gate 5 で作成された設計文書は、作成直後に Gate 6 の detailed design review を
受けます。`design_review.md` が同一の design artifact path と対象 revision /
section を `approve` した後に、その設計を implementation handoff、worker input、
または follow-up 実装判断の根拠にします。

API shape、責務境界、path layout、命名、アルゴリズム、test oracle、依存方向、
runtime contract、config surface の判断が未確定なら、実装吸収ではなく
`design_issue_blocker=<issue>` と evidence を残して Gate 5-6 へ戻ります。local
fallback、wrapper、helper、branch、compatibility route、test relaxation、docs
overwrite、implementation shortcut は Design Integrity Gate の外側です。

### Codex Goals Feature Preflight

Codex `goals` feature が有効な runtime では、`agents/workflows/codex-goals-workflow.md` を overlay として読みます。

```bash
codex features list | grep '^goals'
python3 tools/agent_tools/goal_loop.py status --goal-file goal.md
python3 tools/agent_tools/goal_loop.py plan --goal-file goal.md \
  --report-out reports/agents/<run-id>/goal_work_breakdown.md
```

- shared config は `.codex/config.toml` の `[features].goals = true` を既定にします。
- `goal.md` は durable source of truth、Codex goals は session view、`goal_loop.py status` は機械 gate です。
- `goal.md` は repo-local state として管理します。
- user が goal-driven intent を示したが exact `/goal <objective>` を渡していない場合は、parent が conservative な Objective draft を作り、`goal.md` に先に固定します。goal inference は explicit goal intent と Objective draft に基づけます。
- repo-changing goal task では `/goal` 確定前に provisional run bundle を作り、`requirements_organizer`、`explorer`、必要なら `execution_planner` と `plan_reviewer` の read-only fan-out plan を作ります。active runtime が explicit spawn authorization を持つ場合はその wave を起動し、runtime authorization が必要な場合は handoff packet と `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` を artifact に残して許可待ちにします。write-capable implementation subagent は `/goal` mirror、parseable `goal.md`、Plan-mode evidence mapping が揃った時点で起動します。
- user が `/goal <objective>` または goal-driven task を指定した場合は、`/goal` を session view に設定した直後に `/plan <goal-driven task summary>` へ入り、Plan-mode output が `Goal Contract`、`Exit Criteria Mapping`、`Goal Work Breakdown`、`Source Packet`、`Reuse Survey`、`Execution Slices`、`Budget Policy` を含む状態で実装へ進みます。
- `Goal Work Breakdown` は `goal_loop.py plan` の `GW*` rows を run bundle `schedule.md` へ移したものです。実装は objective と work breakdown の両方に基づけます。
- goal-driven task では、Codex goals と対応する `goal.md` Objective / Exit Criteria / Backlog / Loop Log を更新します。
- `goal_loop.py status` が `NEXT_ACTION=run_next_iteration` を返す場合は、次 iteration の plan / execution へ進みます。
- Codex goals と `goal.md` が食い違う場合は、repo-owned `goal.md` を正本にして session goal view を修正してから実装へ戻ります。

### Token And Agent Mode Preflight

When the user asks to reduce token usage, or when the session is already long,
read `agents/workflows/token-efficient-codex-workflow.md` before spawning
subagents or loading broad context.

Use these parent-session profiles as operator modes:

```bash
codex -p token-lite
codex -p token-standard
codex -p token-deep
```

- `token-lite` is for bounded diagnosis and low-risk changes. It keeps the
  selected required gates active.
- `token-standard` is the default staged repo-work mode.
- `token-deep` is for broad architecture, research synthesis, high-risk review,
  and repeated validation failures.

Choose one subagent mode before delegation:

- `parent-direct`: exception route for parent repository edits. Trivial or
  mechanical repo-changing edits still use a minimal write-capable
  `spark_worker` handoff by default; parent edits require
  `PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes` and
  `PARENT_DIRECT_WRITE_EXCEPTION=<explicit_user_approval|runtime_blocker>`.
- `scout-only`: read-only `explorer` / reviewer answers bounded questions.
- `spark-slice`: `spark_worker` handles approved low-risk slices derived from the Abstract Design Frame and design trace.
- `full-stage`: normal staged requirements, planning, design, review, and
  implementation agents.
- `deep-review`: additional independent read-only reviewers for high-risk work.

Token-saving changes context loading while preserving correctness gates. The
active gates are those selected by runtime profile and risk class.

### Edit Execution Surface

Repo file edits use the responsibility-preserving execution surface:

1. 手編集で責務を追える編集は patch-based edit を使います。
1. 機械生成・一括変換・format は repo 内の script / formatter / generator を使います。
この選択は編集手段の選択です。対象範囲の正本は `requested_scope` に残します。
作業 log / run bundle には、`requested_scope`、選んだ `work_scope`、外した surface
の理由を必要な粒度で残します。user update では、既定から外れる編集手段を使う場合、
tool availability が作業判断に影響する場合、または user が編集手段を質問した場合に説明します。

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

既存実装がある場合は、その module を拡張または再利用します。
新規追加は、既存ライブラリや既存実装で足りない理由を reuse survey に残してから選びます。

### File Dependency Manifest

新規作成・編集する canonical design / workflow / tool / policy / template text file では、ファイル冒頭に `@dependency-start` / `@dependency-end` marker を持つ dependency manifest block を置きます。Routine notes、generated reports、closed issue records、archive / compatibility records は scanner の classification に従います。
設計正本は `documents/dependency-manifest-design.md` です。
旧 `Dependency Files:` block は新規・変更 file では使いません。

- manifest の内部 DSL は `<direction> <kind> <relative-path> <reason...>` です
- `direction` は `upstream` または `downstream` です
- `kind` は `design`、`implementation`、`environment` です
- path は manifest を持つ file から見た相対 path です
- 依存として書くのは、その file を理解・実行・検証するために読むべき repo 内の正本 file です。dependency list は実際の責務関係に基づけます
- upstream は「編集前に読む file」、downstream は「編集後に影響確認する file」として分けます
- 依存が無い direction は行を置きません。`none` placeholder は置きません
- Markdown は title 直後、Python / shell / TOML / YAML など comment 可能な file は shebang / encoding marker 直後、C-like file は先頭 comment block に置きます
- line comment しかない format では `# @dependency-start` のように line comment wrapping を使います
- commentless format や generated / binary / vendored external file は scan tool の分類に従い、必要なら同じ変更の design / manifest / README に理由を残します

編集 workflow:

1. 変更対象 file の manifest を先に読み、upstream edge の target を編集前 context として読む
1. manifest が無い checkable file を編集する場合は、同じ差分で `@dependency-start` block を追加する
1. downstream edge を持つ file を編集した場合は、差分後に downstream target を確認する
1. 新しい dependency edge を足す場合は、同じ変更で reverse edge も足すか、migration 中で足せない理由を review artifact に記録する
1. subagent handoff には `dependency_manifest_plan` と dependency header graph の再帰展開結果を含め、編集対象ごとの upstream / downstream edge、`dependency_edit_scope.txt` / `dependency_graph.tsv`、読む順序を handoff packet に載せる

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
移行期間中に repo 全体の既存 graph failure が残る場合でも、新規・変更 file は現行形式と reverse-edge を満たして closeout します。

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
  - host runtime では repo-local virtual environment を作らず、environment validation には `bash tools/docker_dependency_validator.sh` と `python3 tools/ci/container_config.py` を使う
- 外部調査や比較実験が必要なら `Research-Driven Change`
- tuning、比較改善、探索的 protocol refinement を backlog 付きで回すなら `Adaptive Improvement Loop`
  - Agile outer loop とし、1 extension ごとに 1 waterfall run-id / 1 waterfall pass / 1 decision state へ分解する
- chunk ごとの delivery なら `Large Delivery`
- それ以外は `Scoped Change`

## Completion Bar

user-facing completion は、全 active clause、全 planned work unit、required review、validation、closeout gate が揃った状態です。
closeout 前に reviewer と auditor は次を明示的に確認します。

- 各 must-do clause と completion-evidence clause が、実装、文書、test、command、artifact、または明示された deferred / rejected clause に対応している
- request に含まれる仕様と実際の product surface の間に未実装の gap が残っていない
- schedule、review、validation、commit / push、shared canon sync、follow-up 判断を含む今回 scope の task が 1 つも未完了で残っていない
- task が数式、擬似コード、仕様、method contract を持つ場合、runtime success ではなく
  静的解析・読み取りによる implementation alignment evidence が review artifact に
  主証跡として残っている
- required review の `fix now` findings が実装へ反映され、どの review-driven fix でも risk class と changed surface に対する active required review set を最新 diff に対して最新 diff 全体に対して再実行している
- review reject、requested-change、または `required_change` への応答が、user
  request や design intent を捨てる rollback になっていない。実装 slice の
  revert / discard がある場合は、撤回、置換、owner 外、unsafe replacement、
  または escalation の authority と、保持された request clause が artifact に残っている
- deferred findings は今回の completion readiness への影響、理由、escalation を artifact に記録している

`closeout_gate.md` の `spec_product_coverage_complete=yes`、`review_findings_integrated=yes`、`post_fix_full_review_complete=yes` が揃った時点で、`user_completion_report=unlocked` にできます。

## Mechanical Completion Loop

実装後から user-facing completion までの間は、parent の自己判断だけで閉じず、次の機械的 loop を `closeout_gate.md` に evidence として残します。

1. `user_request_contract.md` の active clause、`schedule.md` の planned work unit、直近 review findings、validation blockers、commit / push、shared canon sync、follow-up 判断を一覧化します。
1. 最新 diff と tracked / untracked state を確認し、変更対象 file の dependency manifest、downstream edge、旧参照、copy / snapshot / backup path を見ます。
1. 必要な repo-wide dependency review、静的解析、読み取り確認、docs / targeted
   tests / agent checks を実行します。動作確認や broad execution だけでは loop を
   閉じません。
1. read-only の diff-check agent を起動し、run bundle、request contract、schedule、latest diff、validation evidence、dependency evidence を渡します。
1. diff-check agent の decision が `approve` 以外なら、fix-now finding を実装して loop の 1 に戻ります。`escalate` は該当する設計・計画 stage へ戻します。
   この修正 loop では、review finding への応答を、同じ意図を保つ修正、
   再設計、または authority 付き escalation / replacement として扱います。
1. diff-check agent が `approve` し、未完了 work unit、未解決 finding、未実行 validation、未同期 canon、未 commit / push、未判断 follow-up が無い場合だけ loop を止めます。

`closeout_gate.md` の `mechanical_completion_loop_complete=yes` と `diff_check_agent_complete=yes` が揃った時点で、`user_completion_report=unlocked` にできます。

## Contract-Required Skill Set

Codex では、まず `$agent-orchestration` を起点にし、`agents/skills/README.md` から current stage と contract に必要な skill を選びます。
user が skill を明示したい場合は `$skill-name` を使います。例: `$repo-onboarding`、`$research-workflow`、`$paper-writing`
細粒度の review pass、CLI adapter、artifact placement、validation helper は public skill ではなく、`documents/REVIEW_PROCESS.md` と `agents/canonical/` に寄せます。
repo-changing task では `python3 tools/agent_tools/route.py --prompt "<request>" --format json` の `ACTIVE_SKILLS` を routing declaration に使い、`$codex-task-workflow` は execution stage、`$subagent-bootstrap` は implementation / patch / doc-edit handoff が current stage に入った時点で active にします。
`task_start.py` と `bootstrap_agent_run.py` は `--task` 文面から prompt-derived
skill を追加し、選択済み skill ごとの repo tool route を
`run.repo_tool_routing_policy` に出します。repo tool route は skill ごとに
`show_skill_packet`、`required_commands`、
`task_matching_conditional_commands`、`validation_commands` の順で扱います。
後続 wave で関連 skill が active になった場合は、同じ
`skill_tool_commands.py show --skill <skill> --format text` を再生成してから
handoff に入ります。

Before a capability gap claim about an existing API, dependency, config,
or extension point, the implementation plan includes the
`documents/api-surface-traversal-policy.md` evidence trail. Helper wrappers,
native reusable API patches, and vendor/library edit proposals follow
after the public import/export/signature/nested-config/example path has been
checked and cited.

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
- general explanatory docs:
  - `long-form-writing` as the DSL-to-prose adapter when file/document responsibility is README, workflow, guide, migration, specification, or similar explanatory prose
- academic docs:
  - `academic-writing`
- Markdown diff:
  - `md-style-check`
- legacy worktree cleanup / drift diagnosis:
  - `worktree-start`
- worktree drift and cleanup:
  - `worktree-health`
- experiment inner loop:
  - `experiment-lifecycle`
- experiment review:
  - `experiment-review`
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
- 不明点は notes、guardrails、documents、prior logs、local code / tests で解決できるかを `Requirements Resolution Sweep` に記録してから deferred / escalation を決める
- active な must-do、must-not-do、completion-evidence clause に `unknown_or_open_question` を残さない
- durable user preference は今回 request や repo evidence と結び付いたときだけ task requirement へ昇格する
- 着手時の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する
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
stage の具体的な責務と実行条件は prose ではなく `.codex/agents/*.toml` を正本にします。
この文書は executable stage flow の正本です。workflow family 選定は
`agent-orchestration`、prompt / config drift 監査は `prompt_config_reviewer`
を先に通し、ここは executable stage flow に保ちます。
goal-driven task では `/goal` 確定前でも provisional bundle を作り、read-only requirements / repo survey / planning review subagent の handoff plan を先に作ります。active runtime が明示許可を要求する場合は、許可があるときだけ実際に起動します。

- repo を編集する
- specialist handoff を明示したい
- review artifact を残したい
- 長めの task で run 単位の記録が必要
- subagent と parent の責務を分けたい

full staged route では、`scheduler`、`schedule_reviewer`、`designer`、`design_reviewer`、active gate の場合の `document_flow_reviewer`、`test_designer` を標準構成とします。
owner-bounded route では、公開 API、reader-facing docs、新用語、cross-surface risk がある場合だけ full staged route へ昇格します。
Codex subagent では、`requirements_organizer`、`manager_reviewer`、`execution_planner`、`plan_reviewer`、`detailed_designer`、`detailed_design_reviewer`、`document_flow_reviewer`、`test_designer`、`spark_worker`、`worker` を workflow family に応じて stage ごとに明示します。
Agent Wave の標準順序は `計画 -> レビュー -> 編集` です。bootstrap は
`team_manifest.yaml` に `run.standard_wave_sequence` を出し、parent は
plan artifact、review gate decision、edit handoff evidence をこの順で
`schedule.md` と `workflow_monitoring.md` に記録します。
bootstrap は `run.pre_handoff_scope_policy` も出します。implementation
surface route は source packet seed であり、responsibility search、reuse
survey、stale-surface scan、dependency expansion を通してから
`allowed_paths`、`do_not_read`、`write_scope`、`validation_route`、
`review_gate` の handoff scope にします。
`task_start.py` と `bootstrap_agent_run.py` は
`run.default_quality_check_policy` も出します。この policy は active な
`test_designer`、`change_reviewer`、`docs_workflow_steward`、
`python_reviewer`、`cpp_reviewer` と、それらから展開される Codex
`agent_type`、task-default / changed-path / manual enable / review-pack
provenance、軽量 static check command を記録します。review と edit の
handoff はこの policy を含めます。
学術文章では、これに `notation_definition_reviewer` と `logic_gap_reviewer` を追加します。
論文や thesis chapter では、さらに `citation_evidence_reviewer` を追加します。
interactive Codex で要件整理と実行計画立案を行う場合は、parent session 側の plan-mode command を使ってから planning specialist を起動します。official Codex CLI では `/plan` です。
default の model / reasoning split は `.codex/agents/*.toml` を正本にします。code survey、tool drift survey、機械 report 要約、execution-only experiment / log work は mini helper role TOML に残します。設計判断、scope 判断、final judgment、broad / ambiguous implementation、static validation triage、language-specific code review、bounded review / report traceability / checklist gate は frontier role TOML に寄せます。Abstract Design Frame と design trace で完全に切れる狭い実装 slice は `spark_worker` に寄せます。
- subagent の depth は `.codex/config.toml` と active spawn budget で管理します。必要な追加層がある場合だけ parent が owner、入力 packet、write scope、review gate を明示して展開します。
- active spawn budget は workflow family に従って縛ります。機械設定の正本は `agents/task_catalog.yaml` の `workflow_families[].spawn_budget` です。現在の既定は `Owner-Bounded Change` で同時 4 体、`Scoped Change` で同時 8 体、`Large Delivery` / `Platform And Environment` で同時 10 体、`Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop` で同時 12 体までです。
- workflow family ごとの subagent prompt 正本は `agents/task_catalog.yaml` の `workflow_families[].subagent_prompt` です。
- budget を超える場合は例外扱いにし、`schedule.md` と `work_log.md` に理由、追加 role、expected output、write scope を残します。
- write-capable subagent は既定 1 体です。ただし parent が `team_manifest.yaml` の write policy と handoff で dependency order、wave plan、disjoint write scope、integration order、review gate を明示した場合は、spawn budget 内で複数体を並列化できます。衝突する target は順序制約として扱い、同じ file / canonical surface / shared root contract に触る作業は先行 wave の validation と tool rerun 後に後続 wave へ回します。安全に分離できる writer は同一 wave、追加判断が要る writer は current checkout 内の後続 wave へ直列化します。

Codex runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を直接見ます。

標準コマンド:

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
- `IMPLEMENTATION_SURFACE_ROUTE_STATUS` と route command
- `TOOL_REUSE_LEDGER_STATUS`
- `PRE_EDIT_REJECTION_PREDICTION_STATUS`
- task id / fan-out budget / active role evidence

parent は subagent handoff でこの packet path 群と `team_manifest.yaml` の `run.subagent_prompt_packet` / role 別 `prompt_contract` を明示入力し、requested scope を保持した bounded packet routing を維持します。
handoff には `allowed_paths`、`do_not_read`、context artifact path、expected output schema、
`PRIMARY_PATHS` / `FORBIDDEN_PATHS`、reuse ledger、pre-edit rejection prediction を含めます。
`cross_cutting_document_packet` は利用可能な reference list であり、role ごとの work packet を選ぶために使います。広い request では、packet に含めなかった reference を `omitted_surfaces` として理由付きで残します。

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

`--task-id` を指定すると、`agents/task_catalog.yaml` にある task-default specialist と `default_for_tasks` review pack を自動で有効化します。まず catalog default を使い、full perspective や extra reviewer は必要な根拠がある場合だけ `--enable` で補います。
language-specific reviewer は `bootstrap_agent_run.py` が `--changed-path` か workspace の `git status --short` から自動で足します。
run bundle を起こしたら、`user_request_contract.md` を planning 前に埋めます。stage artifact、handoff、review では clause ID を明示します。
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
- `prompt_config_reviewer`
- `python_reviewer`
- `cpp_reviewer`
- `worker`

cost を無視して review coverage を優先する run では、research-driven change と comprehensive development は `--full-team` を許可します。

### 5. Implementation

- 実装は `agents/workflows/implementation-waterfall-workflow.md` の gate に従って進める
- Gate 1 / 4 / 6 / 7 / 8 / 9 の次段移行では `waterfall_gate_check.py` を通し、`WATERFALL_GATE_READY=yes` でない場合は指示された owner stage へ戻る
- 実装前に `design_brief.md` の `Abstract Design Frame`、`Installed Libraries And Existing Implementation Survey`、`Implementation Source Packet`、`Design Side-Effect Map`、`Design-To-Implementation Trace` を読み、抽象責務と概念 model から実装 slice と downstream side effect が導かれていることを確認してから、そこにある artifact、repo docs、dependency surface、code path、test plan を読了する
- 実装前に `design_review.md` を読み、`Design Artifact Under Review` が
  現在の `design_brief.md` を指し、decision が `approve` であることを確認する。
  設計を修正した後は Gate 6 で現行設計の approve を取り直す
- 詳細設計 artifact がある run では、write-capable handoff と parent-direct
  exception の前に `pre_handoff_gate_status` へ `design_review.md decision=approve`
  と `waterfall-gate-check --gate design` pass evidence を記録する
- 詳細設計前に `task_start.py` / `bootstrap_agent_run.py` の `DESIGN_DOCUMENT_PACKET` を読み、その path 群を `design_brief.md` の `Upstream Requirement Packet` に転記する
- 詳細設計では `design_brief.md` の `Canonical Tree-Head Plan` に、この task の後に tracked tree に残してよい設計文書 path と実装 path を固定し、parallel design doc、implementation copy、snapshot、backup path を残さないことを明記する
- worker の実装入力は、各 implementation slice の前に明示された design artifact path、design section、test plan item、request clause ID です
- worker は docs、workflow、prompt/config、validation output、dependency manifest、user-facing surface へ波及する変更を `Design Side-Effect Map` の item として扱い、implementation summary に owner stage と review gate を残す
- `Abstract Design Frame`、`Installed Libraries And Existing Implementation Survey`、`Implementation Source Packet`、承認済み `design_review.md`、design gate check、および design と現行 repo docs / code / dependency surface の整合が揃った時点で実装へ進む。欠けた場合は Gate 5-6 へ戻る
- 実装中に design issue が見つかった場合は、`design_issue_blocker=<issue>`、evidence、候補 option を artifact に残し、Gate 5-6 へ戻す。API shape、責務境界、path layout、命名、アルゴリズム、証明対象、test oracle、依存方向、runtime contract、config surface の欠落や矛盾は設計側で解決します。run bundle が無い parent-direct task では編集を止めて user に設計判断を返す
- `design_issue_blocker` は local fallback、wrapper、helper、分岐、互換 route、test 緩和、docs 上書きではなく、Gate 5-6 の設計更新で閉じる。承認済み design と局所 precedent から一意に導ける typo、format、import、狭い機械的追従だけが同じ implementation pass で修正できる
- compatibility-preservation drift と duplicate implementation は implementation GuardRail finding として扱い、旧 route、旧 wrapper、旧 helper、config mirror は caller migration で canonical owner へ統合する
- implementation は current tree head の canonical path だけを更新対象にし、`*_old`、`*_copy`、dated clone、parallel module、duplicate directory のような別 truth surface を作らない
- `task_start.py` / `bootstrap_agent_run.py` の `IMPLEMENTATION_CODEX_AGENTS` を確認し、repo-changing implementation / patch / doc-edit work は write-capable handoff first で進める。`spark_worker,worker` なら Abstract Design Frame から導かれ、design trace、naming、test plan、dependency-expanded handoff scope が揃った低リスク slice を `spark_worker` へ先に渡す。parent-direct は explicit approval、spawn authorization blocker、または tool-gate blocker を記録した exception route です
- 新規または rename する file、function、class、theorem、artifact、CLI flag、
  config key は、implementation handoff 前に naming plan で固定する。naming plan は
  対象概念、責務語彙、既存 naming family、採用名、avoid-name list を含み、
  `documents/conventions/common/02_naming.md` と言語別規約を参照します。
  名前が未確定な場合は Gate 5-6 へ戻り、worker handoff 前に naming plan を確定します
- 明示 spawn 許可がある場合、実装前の repo inventory と tool drift survey は mini helper role TOML へ、static validation failure triage と diff-local language review は frontier review role TOML へ先に渡し、低遅延実装 slice は `spark_worker` へ渡します。parent は統合判断と次 gate 判定に集中する
- `spark_worker` に渡す実装は、Abstract Design Frame から導かれた差し替え可能な単位で、public interface 変更なし、依存追加なし、仕様解釈なし、既存 test / docs の局所更新で閉じる slice だけにする。適格性は design trace と dependency-expanded handoff scope で判断します。
- 実装 subagent を起動するときは `IMPLEMENTATION_DOCUMENT_PACKET` の path 群を明示入力し、chat 要約ではなく packet path を読ませる
- すべての stage subagent を起動するときは `team_manifest.yaml` の `run.subagent_prompt_packet` と該当 role の `prompt_contract` を prompt に含める
- `spark_worker` は design trace と dependency-expanded handoff scope が揃った bounded implementation slice に使い、設計判断、scope 判断、review 判断は frontier owner / reviewer に残す
- chunk、slice、checkpoint、subpass の後は remaining planned work units と next gate を確認してから続行する
- repo-changing task では current checkout の run bundle `work_log.md` を継続更新する
- 新規作業は current checkout で kickoff します。`WORKTREE_SCOPE.md` と `worktree_scope_lint.py` は legacy cleanup / drift diagnosis 専用です
- stale な `WORKTREE_SCOPE.md`、別 branch、別 path の action log を見つけた場合は、current checkout の `work_log.md` に観測事実と扱いを残す
- `計画レビュー`、`詳細設計レビュー`、`文書通読レビュー` の分離や、implementation 着手条件は `.codex/agents/*.toml` を正本にする
- 包括的開発では `project_reviewer` を intake と closeout に追加し、repo-wide な integration risk を確認する
- 文書主体の成果物では `document_flow_reviewer` を通し、上から順に読んだときの意味の通り方を確認する
- README、workflow、guide、migration、specification など file responsibility が一般説明 prose の文書で reader-facing 構成を変える場合は `long-form-writing` を DSL-to-prose adapter として読み、docs-impact が高い場合だけ別 reviewer で `docs-completeness-review` も通す
- 論文、thesis chapter、scholarly note のような学術文章では `academic-writing` を読み、`notation_definition_reviewer`、`logic_gap_reviewer`、必要に応じて別 reviewer の `docs-completeness-review` を通す
- 投稿論文や thesis chapter の draft では `paper-writing` を読み、`citation_evidence_reviewer` も別 instance で通す
- high-risk code 変更、新規 behavior、または regression-prone な修正では `test-design` を読み、実装前に `test_designer` で nasty case と regression case を固定する
- contract-only wrapper や checker-owned validation だけの変更では、static contract validation と canonical command evidence を validation route に置く。pytest smoke、execution-only test、no-crash test、数値 smoke は behavior trigger がある場合に採用する
- validation tool の autofix は changed contract、changed lines、または task plan が名指しした checker-owned property に結び付く finding に適用し、広い validation で出た既存 style debt は residual evidence と repair route に分ける
- 研究・実験系の変更では active experiment profile の risk に応じて `report_reviewer` と research perspective reviewers を選ぶ
- JAX export / native runtime の task では、対象 implementation slice で `generic callable path`、`specialized coeff path`、`export-based generic path` のどれを触るか宣言する。generic path は `jax.export` artifact producer と consumer/runtime smoke を完了条件に含める
- cross-process export worker には serializable manifest と reconstruction recipe を渡す
- `LoadedProgram` のような runtime materialization は runtime vertex / lifetime scope として扱う
- まず導入済みライブラリ、既存 code path、既存 helper、既存 style を調べ、再利用と拡張を優先する
- 新規 helper や新規 module を足すときは、既存実装で足りる範囲と、導入済みライブラリの設定変更や薄い wrapper で足りる範囲を design packet に結び付ける
- worker は approved design または明白な局所 precedent に由来する variable、function、class、file、CLI flag、config key、public API identifier を使う
- implementation slice は contract-complete implementation として閉じる。request clause、acceptance contract、Implementation Source Packet、validation route を結び、implementation shortcut を見つけたら `design_issue_blocker` と evidence で design review へ戻す
- checkpoint review は diff だけでなく Abstract Design Frame、approved design packet、Design Side-Effect Map、source packet citation の一致を確認する
- role ごとの model / reasoning 設定は `.codex/agents/*.toml` に従う
- broad worker と review / quality-check gate は frontier role TOML、Abstract Design Frame と design trace から導かれた bounded slice の preferred candidate は `spark_worker`、execution-only experiment / log work は mini helper role TOML とする
- parent-managed write-scope rule は `worker.toml`、`spark_worker.toml`、planning / reviewer TOML、`team_manifest.yaml` を正本にする
- 正本は `agents/` と `documents/` から先に直す
- runtime entrypoint は薄く保つ
- skill は repo 正本を置き換えず、導線だけを担う

### 6. Validation

- Validation starts with lightweight evidence: static analysis, dependency
  checks, docs checks, route checks, and changed-file targeted tests. Full CI,
  long test suites, benchmarks, experiments, GPU / CPU numerical runs, solver
  sweeps, and randomized large cases use a task-linked approval note with
  request clause, expected signal, runtime / resource budget, stop condition,
  artifact path, and owner.
- After any validation test/check failure, prohibited actions are simplifying,
  reverting, deleting intended behavior/tests, weakening the oracle, or
  downscoping required validation just to pass. First record the five machine
  fields: `failing_contract`, `observation_level`, `cause_classification`,
  `intent_preservation`, and `evidence`. The canonical token-safe
  `cause_classification` and `intent_preservation` slug lists are owned by
  `documents/runtime-profiles-and-check-matrix.json` and projected into
  `documents/runtime-profiles-and-check-matrix.md`; this workflow section only
  states when Codex must apply that taxonomy. Repair with approved intent
  preserved through the owner route named by the taxonomy, route unrelated
  failures as residual evidence, and escalate approved-design / user-request
  conflicts before changing intent.
- Shared canon、Large delivery、高 risk 変更では差分限定ではなく全 repo 対象で `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` を通し、dependency graph、header 欠落、header format を確認する。Routine docs / Focused code は changed-file dependency checks と relevant downstream review を evidence にできる
- Large delivery、explicit comprehensive validation、高 risk 変更では user-facing completion 前に `make ci` または同等の full local confidence gate を通し、pytest、pyright、pydocstyle、ruff を全 repo 設定で確認する。Shared canon 変更では active profile が指定する `make agent-canon-pr-check` または等価な AgentCanon PR gate を使い、Routine docs / Focused code は active profile の targeted checks を evidence にできる
- Python / C++ 実装変更では `python3 tools/agent_tools/check_hardcoded_numbers.py --changed --exclude tests --exclude vendor --exclude reports` を通し、裸の非自明数値を名前付き定数、typed configuration、API input、または根拠付き `hardcoded-number-ok` へ解消する
- Python のログ出力 helper を変更した場合は `python3 tools/agent_tools/check_log_helper_names.py --changed --exclude vendor --exclude reports` を通し、ログ helper 名を `_log...` に揃える
- Hook、tool、skill、workflow、agent protocol、GitHub workflow、dependency manifest に触る前には `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` を走らせ、`TOOL_REJECTION_PREDICTED_GATE` を write-capable subagent handoff に渡す。parent 直編集に渡す場合は先に `PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes` と `PARENT_DIRECT_WRITE_EXCEPTION=<explicit_user_approval|runtime_blocker>` を記録する。予測 gate が出た場合は、gate-specific command と repair plan を実装前に固定する
- tool / checker / hook / reviewer / subagent feedback から実装へ進む場合は `$tool-finding-report` で finding packet を作り、raw artifact、structured artifact、impact、prompt feedback decision を handoff に渡す。`handoff_prompt_gap` または `shared_skill_or_workflow_gap` は次の write-capable subagent 起動前に prompt を修正し、`workflow_monitor.py --runtime-feedback ... action=prompt_repair` で記録する
- agent runtime / skill 変更では active profile に応じて `make agent-checks` または relevant subchecks を使う
- checkpoint では `make ci-quick` を使ってよい。final closeout は risk class に応じて `make ci`、`make agent-checks`、または targeted checks を選ぶ
- full confidence が必要な場合は `make ci`
- Python 変更では `pyright`、`pytest tests/`、`ruff check python tests --select D,E,F,I,UP --ignore E501` を確認する
- C / C++ 変更では project-native configure / build / test evidence を確認し、CMake project なら `cmake -S . -B build`、`cmake --build build`、`ctest --test-dir build` を既定候補にする
- 文書変更では markdown / link check を使う
- report を閉じる前には `documents/experiment-report-style.md` を確認する
- 研究系 task では `critical-review` と `report-review` の decision state を確認し、必要なら `research-perspective-review` を追加する

### 7. Closeout

#### Completion Readiness

- repo に残す差分がある task では、validation 後に commit を作る
- commit は `documents/BRANCH_SCOPE.md` の Git 上の runnable unit として作る。validation が参照した source、config、schema、fixture、文書、tool entrypoint を tracked tree に含める。code 変更では file-level code dependency と関数 / public entrypoint 単位の call-site evidence も残す。commit SHA、submodule SHA、validation command、対象 path、残った dirty / untracked path の分類を evidence に残す
- commit / PR の切り方は `documents/BRANCH_SCOPE.md` の範囲分割契約に従う。commit は実行単位、PR はレビュー単位として扱い、複数の問題、canonical owner、behavior or contract delta、validation route にまたがる差分は範囲表を作ってから merge 前に別 PR または別 commit へ分ける
- final report の前に branch push を行い、user が明示的に停止を指定した場合は停止理由を final report に残す
- user-facing final report は、`verification.txt` が `status=pass`、`closeout_gate.md` が `auditor_status=resolved` かつ `user_completion_report=unlocked`、`user_request_contract.md` が `all_clauses_resolved=yes` かつ `forbidden_drift_detected=no` の状態で出す
- `closeout_gate.md` の `all_planned_chunks_complete=yes` と `overall_delivery_complete=yes` が揃ったら、chunk completion を全体 completion evidence に統合する
- `closeout_gate.md` の `unfinished_tasks_absent=yes` で、予定作業、review 対応、validation、commit / push、shared canon sync、follow-up 判断の完了状態を示す
- `closeout_gate.md` の `dependency_headers_complete=yes` で、作成・編集した text file の依存 file header coverage を示す
- Shared canon、Large delivery、高 risk 変更では `closeout_gate.md` の `repo_wide_dependency_tools_complete=yes` とともに、checkpoint / final review で全 repo 対象の `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` と header 修正 evidence を残す。Routine docs / Focused code は targeted dependency evidence を残す
- Full local confidence gate が選択された変更では `closeout_gate.md` の `repo_wide_static_analysis_complete=yes` とともに、全 repo 対象の `make ci`、または `python3 -m pyright` と `python3 -m ruff check python tests --select D,E,F,I,UP --ignore E501` の static analysis evidence を残す。Routine docs / Focused code / profile-specific gate は `repo_wide_static_analysis_complete=profile_selected` と targeted static evidence を残し、`make_ci_status` を `targeted` または `not_applicable` にする
- `closeout_gate.md` の `spec_product_coverage_complete=yes` と `review_findings_integrated=yes` で、仕様 coverage と review finding disposition を示す
- `closeout_gate.md` の `review_findings_integrated=yes` は、review reject /
  requested-change への応答として、user request と design intent が保持された
  evidence を要求します。revert / discard が含まれる場合は、撤回、置換、owner
  外、unsafe replacement、または escalation の authority を示します
- `closeout_gate.md` の `mechanical_completion_loop_complete=yes` で、planned work、review findings、validation、dependency review、static analysis、reading evidence、commit / push、shared canon sync、follow-up 判断を構造化 loop evidence として残す
- `closeout_gate.md` の `subagents_closed=yes` で、run-local subagent の close と fresh lifecycle evidence を示す
- `closeout_gate.md` の `diff_check_agent_complete=yes` で、run-local diff-check artifact、read-only independent agent、latest diff ref、`approve` decision、findings disposition を示す
- `closeout_gate.md` の `canonical_tree_head_complete=yes` で、設計文書、implementation surface、snapshot tree、backup path の正本状態を示す
- `workflow_monitoring.md` の signals / behavior events / interventions / improvement decisions を埋め、skill / config / workflow / memory の改善判断を `applied`、`recorded`、`not_applicable` のいずれかにする
- hook、code checker、static analysis、CI、review tool の結果が parent protocol または subagent protocol を変えるべきかを確認し、`workflow_monitoring.md` に `hook_tool_feedback=reviewed`、`parent_protocol_update=<applied|recorded|not_required>`、`subagent_protocol_update=<applied|recorded|not_required>`、`protocol_feedback_reason=...` を残す
- evidence を確認済みの closeout では、`python3 tools/agent_tools/workflow_monitor.py --report-dir reports/agents/<run-id> --closeout-token-preset` で `evaluate_agent_run.py` が消費する standard behavior tokens を記録できます。この preset は記録 shortcut であり、`make ci`、dependency review、diff-check approval、review finding resolution は個別 evidence として残します。
- `tools/agent_tools/evaluate_agent_run.py --report-dir reports/agents/<run-id> --behavior-manifest evidence/agent-evals/agent_behavior_eval.toml --write` が pass し、`closeout_gate.md` の `agent_evaluation_complete=yes` と `agent_evaluation.md` の `feedback_actions_resolved: yes` が揃ったら、agent behavior evaluation と feedback resolution を complete にする
- `schedule.md` を TODO 正本として埋め、`work_log.md` に execution trail を残す
- `notes/guardrails/engineering_avoidances.md` の log-derived avoid に当たる変更は、修正または reviewer escalation の対象にする
- user request が generic path の usable smoke を求める場合、generic path の producer / consumer evidence を completion evidence にする
- JAX export / native runtime の generic path は、`jax.export` artifact producer と consumer/runtime evidence を completion evidence にする
- 実験・性能改善では、planned comparison run、acceptance criteria、raw result、interpretation evidence を分けて示す
- trainer replacement、scalability、superiority、広い theorem は baseline comparison と scope-limited evidence で主張する
- failure-onset dimension を記録し、implementation bug と frontier limit を分けて扱う
- 実験・性能改善では、correctness evidence と performance evidence を別項目で示す
- final report には branch、commit、push の成否を短く残す
- push が失敗した、または意図的に skip した場合は、その理由を final report に明記する
- push が自然な完了条件に含まれる場合は、push の許可を取りに戻らず実行する
- closeout 前に `memory/USER_PREFERENCES.md` を見直し、stable になった preference があれば `user-preference-sync` で `AGENTS.md` への昇格要否を判断する
- closeout 前に `memory/AGENT_PHILOSOPHY.md` を見直し、task retrospective、interaction observation、promotion candidate を `agent-learning` で残すか判断する
- closeout 前に `agent_evaluation.md` の feedback actions を見直し、stable な失敗防止は `agent-learning` で記録し、確定した guardrail 候補は positive operational condition として昇格可否を判断する
- review-only task や no-change task では、review result と no-change rationale を completion evidence にする

そのうえで、何を変えたか、何を確認したか、何を確認していないかを短く残して完了する

## Codex-Specific Rules

- `AGENTS.md` は Codex のruntime 入口として保つ
- `.agents/skills/` を正規 skill path とする
- repo-changing task では、stage ごとの subagent / specialist を明示する
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` は別 instance にする
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` も別 instance にする
- 論文 draft では `citation_evidence_reviewer` も別 instance にする
- 包括的開発では、parent が dependency order、wave plan、dependency-expanded disjoint write scope、integration order、review gate を handoff packet に載せます
- 複数 writer を要する場合は、衝突 target を先行 / 後続 wave に分けます。安全に分離できる writer は同一 wave、追加判断が要る writer は current checkout 内の後続 wave へ直列化します
- writer ごとの path / directory / object は `team_manifest.yaml` の write policy で管理します
- required review を resolved にしてから `worker` 相当の実装を始める
- tracked repo change がある task では、required review、validation、commit、`origin` への push を完了条件にする
- tracked repo change で push が自然な完了条件なら、push の許可を取りに戻らず実行する。user が明示的に停止を指定した場合や external block がある場合は、理由を evidence に残す
- planned work、review finding、validation、commit / push、shared canon sync、follow-up 判断の completion evidence を揃えて user-facing completion を返す
- `verification.txt`、`closeout_gate.md`、`user_request_contract.md` の close 条件を満たして user-facing completion を返す
- Codex 専用事情でも、再利用可能なルールは `agents/` に昇格する
- 会話文脈由来の運用は repo 正本へ昇格してから使う
