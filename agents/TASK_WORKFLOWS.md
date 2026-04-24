# Agent Task Workflows

この文書は、repo で使う workflow family の正本です。
task を細かく増やしすぎず、少数の family に寄せて運用します。

すべての family で、repo に持ち帰る実装パスは
[agents/workflows/implementation-waterfall-workflow.md](../../../agents/workflows/implementation-waterfall-workflow.md)
の段階ゲートに従います。
また、repo を編集する task では、stage ごとに適切な subagent / specialist を explicit に立てることを既定にします。
stage ごとの具体的な禁止事項は prose ではなく `.codex/agents/*.toml` に寄せます。

## 共通実装フロー

1. 要件整理
   - `manager`
   - `manager_reviewer`
1. 調査
   - 必要に応じて `researcher`
   - 必要に応じて `research_reviewer`
1. 実行計画立案
   - `scheduler`
1. 計画レビュー
   - `schedule_reviewer`
1. 詳細設計
   - `designer`
1. 詳細設計レビュー
   - `design_reviewer`
1. 文書通読レビュー
   - `document_flow_reviewer`
1. テストケース設計
   - `test_designer`
1. 実装
   - `implementer`
1. 実装 checkpoint review
   - `change_reviewer`
1. 最終受け入れ review
   - `final_reviewer`
1. 監査と gate close
   - `auditor`
   - `verifier`

ルール:
- 着手前に `workflow=<family>`、`skills=<...>`、`review=<...>` を宣言します
- repo-changing task では run bundle を先に作り、stage ごとの specialist / subagent を明示します
- repo-changing task では `team_manifest.yaml` の `run.subagent_prompt_packet` と role 別 `prompt_contract` を subagent handoff prompt に含めます
- `計画レビュー` と `詳細設計レビュー` の分離、`詳細設計レビュー` の強い gate 性、`文書通読レビュー` の着手条件は各 reviewer TOML を正本にします
- code change では `test_designer` を独立に立て、static path と nasty case を先に固定します
- 大規模 refactor では `Behavior Contract:`, `Allowed Structural Delta:`, `Forbidden Semantic Delta:`, `Files To Remove Or Move:`, `Path Mapping:` を `refactor_safety_case.md` に先に固定します
- `実行計画 -> 計画レビュー`、`詳細設計 -> 詳細設計レビュー -> 文書通読レビュー`、`実装 -> 実装 checkpoint review` は、それぞれ review decision が `approve` になるまで同じ段を反復します
- README、workflow、guide、migration 文書のような長文では `long-form-writing` を追加し、別 reviewer で docs completeness review も通します
- 学術文章では `academic-writing` を追加し、`notation_definition_reviewer`、`logic_gap_reviewer`、docs completeness review を別 reviewer で通します
- 論文や thesis chapter では `paper-writing` を追加し、`citation_evidence_reviewer` も別 reviewer で通します
- `詳細設計` の目標は、実装前提が十分に伝わる文書を起こすことです
- 詳細設計には `Implementation Source Packet` と `Design-To-Implementation Trace` を必ず含め、worker が読む artifact、repo docs、dependency/library survey、code path、test plan、request clause ID を固定します
- 実装では会話文脈や記憶より承認済み design packet を優先し、各 implementation slice で design artifact path、section、test plan item、request clause ID を引用します
- design packet から trace できない変更は実装せず、Gate 5-6 へ戻します
- 実装では既存コード、既存の命名、既存の文書スタイル、既存の module boundary、導入済みライブラリを徹底的に踏襲します
- 既存実装や導入済みライブラリで足りない理由、extend ではなく新規追加が必要な理由を詳細設計に書かずに実装へ進みません
- rate-limit pressure が強い場合は、design trace、naming、test plan、write scope が固定済みの狭い実装sliceだけ `spark_worker` へ移します
- `spark_worker` は設計判断、scope判断、review判断には使いません
- 要件整理では、今回 request、過去ログ由来の durable preference、repo/code precedent、domain/external constraint、unknown/open question を source bucket として分けます
- 要件整理では、ユーザーへ戻す前に notes、guardrails、documents、prior logs、local code / tests で解決できる unknown を解決し、根拠を `Resolved From Accumulated Context` に残します
- 要件レビューでは、active clause に `unknown_or_open_question` が残っていないことと、解決可能な unknown を放置していないことを `manager_reviewer` が確認します
- 詳細設計では、新規または rename する identifier、path、CLI flag、config key、public API の naming plan を固定します
- 実装では、詳細設計または明白な局所 precedent にない reusable / user-facing な名前を worker が発明しません
- 各 review の直後は、直前の execution role が feedback を反映してから次段へ進みます
- `revise` は同じ段の owner へ戻し、`escalate` は 1 つ上の設計段へ戻します
- chunk、slice、checkpoint、subpass は内部進捗であり、user-facing completion ではありません
- user-facing completion は、全 active clause、全 planned work unit、final review、validation、closeout gate、commit / push が揃ったときだけ返します
- branch 側で file 構成変更をした pass は、closeout 前に `agents/workflows/main-integration-workflow.md` の integration step まで設計します
- 構成変更を含む統合では、専用 integration worktree と `tools/ci/check_merge_structure.py` を省略しません
- tuning や探索の outer loop は waterfall に押し込まず、`Adaptive Improvement Loop` で backlog-driven に回します
- `/mnt/git` 配下の log 由来 guardrail は `notes/guardrails/engineering_avoidances.md` を正本にします
- specialized path の tuning だけで generic path の usable smoke を満たした扱いにしません
- spot run、debug run、smoke run、partial run は正式な comparison evidence や method 採否の根拠にしません
- correctness evidence と performance evidence を同じ evidence として扱いません
- code change、protocol change、XLA / runtime flag change を 1 iteration に混ぜません

## Activation Quick Start

repo-changing task の最小 bundle:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "scoped repo change" \
  --task-id T1 \
  --owner "codex" \
  --workspace-root "$PWD"
```

研究・実験つき変更:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "research-backed change" \
  --task-id T4 \
  --owner "codex" \
  --workspace-root "$PWD"
```

環境変更:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "platform or environment change" \
  --task-id T8 \
  --owner "codex" \
  --workspace-root "$PWD"
```

学術文章:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "academic writing task" \
  --task-id T10 \
  --owner "codex" \
  --workspace-root "$PWD"
```

論文 draft:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "paper writing task" \
  --task-id T10 \
  --owner "codex" \
  --workspace-root "$PWD"
```

Codex parent が planning を行う session では、parent session 側の plan-mode command を先に有効化します。official Codex CLI では `/plan` です。

包括的開発:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

反復改善:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "adaptive improvement loop" \
  --task-id T13 \
  --owner "codex" \
  --workspace-root "$PWD"
```

補足:
- `--task-id` を使うと、`agents/task_catalog.yaml` にある task-default specialist と `default_for_tasks` review pack を自動で有効化します
- cost を気にしない run では `--task-id` を基本にし、狭い例外だけ `--enable` で足します

包括的開発の固定 Codex stack:
- `requirements_organizer`
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

single-writer ルール:
- 同一 worktree では `worker` だけが repo file を編集します
- 同一 worktree で複数の write-capable subagent を走らせません
- 同一ディレクトリの並列 write も許可しません
- 複数 writer が必要な場合は worktree を分け、各 worktree に writer を 1 人だけ置きます
- parent は worktree ごとの結果を順番に統合します

spawn budget ルール:
- depth は固定しませんが、active な subagent 数は family ごとの budget で縛ります
- 機械設定の正本は `agents/task_catalog.yaml` の `workflow_families[].spawn_budget` です
- workflow family ごとの subagent prompt 正本は `agents/task_catalog.yaml` の `workflow_families[].subagent_prompt` です
- `Scoped Change` は同時 5 体までを既定にします
- `Large Delivery` / `Platform And Environment` は同時 6 体までを既定にします
- `Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop` は同時 8 体までを既定にします
- budget 超過は例外扱いにし、`schedule.md` の stage plan と `work_log.md` に理由を書きます
- budget を増やしても write-capable subagent は同時 1 体までです

concurrent spawn budget:
- global runtime cap は `.codex/config.toml` の `max_threads = 12`
- `Scoped Change`: parent を除いて同時 4-5 agent を目安にします。通常は owner 1 + read-only reviewer / explorer 3-4 まで
- `Research-Driven Change`: parent を除いて同時 6-8 agent を目安にします。perspective reviewer は batch で回します
- `Platform And Environment` と `Large Delivery`: parent を除いて同時 5-6 agent を目安にします。planning / design / review を wave に分けます
- `Comprehensive Development` と `Adaptive Improvement Loop`: parent を除いて同時 6-8 agent を目安にします。review pack はまとめて起こさず、intake・implementation・wrap-up の波に分けます
- depth は固定しませんが、cap を超える fan-out は許可しません。必要な role が多いときは stage を細かく切って順次起動します

## Workflow Families

### 1. Scoped Change

対象:
- 局所バグ修正
- 小規模な docs/test 同期
- CI failure の切り分け

標準フロー:
1. 共通実装フローをそのまま 1 pass で通す
1. 小さい変更でも `scheduler`、`schedule_reviewer`、`designer`、`design_reviewer`、`document_flow_reviewer` を省略しない
1. code や test を触る task では `test_designer` を省略しない
1. 長文の docs task では `document_flow_reviewer` に加えて docs reviewer を省略しない
1. 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` を省略しない
1. 論文や thesis chapter では `citation_evidence_reviewer` も省略しない
1. active な subagent は同時 5 体までを既定にし、parent は stage 完了ごとに不要 instance を閉じる

### 2. Research-Driven Change

対象:
- 外部調査を伴う実装
- benchmark や比較実験を根拠にした改善

追加ロール:
- `researcher`
- `research_reviewer`
- `experimenter`
- `experiment_reviewer`
- 必要に応じて `reproducibility_reviewer`
- 必要に応じて `scientific_computing_reviewer`
- 必要に応じて `benchmark_reviewer`
- 必要に応じて `artifact_reviewer`
- 必要に応じて `fair_data_reviewer`
- 必要に応じて `ml_science_reviewer`

特徴:
- research と experiment を evidence として回す
- overclaim review を明示的に挟む
- cost を気にしない default では、`report_reviewer` と research perspective reviewers を常時有効化します
- `report_rewrite_required`、`extra_validation_required`、`rerun_required` が残る限り loop を閉じない
- ただし、1 回の repo 変更は 1 回の waterfall pass として閉じる
- 各 pass で計画レビュー、詳細設計レビュー、文書通読レビュー、checkpoint review、最終受け入れ review、audit review を省略しない
- agent が code change と run を継続反復する場合は `adaptive-improvement-loop` を追加する
- methodology、artifact、reporting policy を大きく変える場合は perspective reviewers を default にします
- active な subagent は同時 8 体までを既定にし、追加枠は read-only reviewer / researcher に使います
- repo-wide な research cleanup では task catalog の `T9` を基準に perspective reviewers をまとめて有効化する

### 3. Large Delivery

対象:
- 新機能追加
- 大規模 refactor
- 複数 chunk に分ける delivery

追加ロール:
- `scheduler`
- `schedule_reviewer`

特徴:
- milestone と chunk 境界を先に固定する
- milestone ごとに実行計画と詳細設計を分ける
- 各 chunk は checkpoint review までの subpass として閉じる
- chunk completion は umbrella request の completion ではない
- 各 chunk で checkpoint review を複数回に増やせる
- 逐次 review と最終 review を分ける
- 大規模 refactor では `$behavior-preserving-refactor` を追加します
- refactor pass では feature 追加を同じ pass に混ぜません
- refactor pass では `refactor_safety_case.md` を起こし、挙動保存契約、削除対象、path mapping、merge structure check を先に固定します
- refactor pass では `project_reviewer` と `docs_workflow_steward` を default specialist にし、cross-module drift と stale route を落とします

### 4. Platform And Environment

対象:
- Docker
- CI
- automation
- dependency / runtime upgrade

追加ロール:
- `infra_steward`
- `infra_reviewer`
- 必要に応じて `researcher`, `scheduler`, `experimenter`

特徴:
- `scheduler` と `schedule_reviewer` を省略せず、環境変更でも順序と handoff を固定する
- rollout と rollback を先に考える
- repo ルール、環境、automation を同時に更新する
- code requirement、blocked command、必要 runtime capability を `environment_change_proposal.md` に先に固定する
- 実装前に environment design を凍結し、acceptance gate で transition readiness を確認する
- `infra_steward` と `infra_reviewer` は、実行計画と詳細設計の両方に入力を出す
- `infra_reviewer` を詳細設計レビューと最終受け入れ review の両方へ参加させる
- Docker を変える task では source-of-truth surface、同期対象、rollout / rollback、validation matrix を必ず同じ pass に残す
- repo-wide な tool 導入案では理由、Docker 影響、validation、rollback を同時に残す

### 5. Comprehensive Development

対象:
- code、docs、tests、workflow、tools、Docker、CI をまたぐ repo-wide な整理
- agent canon、tooling、implementation convention を同時に触る rearchitecture
- 単一 chunk に閉じないが、1 つの umbrella plan で切りたい integrated delivery

追加ロール:
- `scheduler`
- `schedule_reviewer`
- `critical_guardian`
- `researcher`
- `research_reviewer`
- `infra_steward`
- `infra_reviewer`

固定 Codex stack:
- `project_reviewer`
- `docs_workflow_steward`
- `python_reviewer`
- `cpp_reviewer`

特徴:
- 背骨は共通実装フローと `agents/workflows/implementation-waterfall-workflow.md` の gate をそのまま使う
- task を docs / tools / runtime / implementation に分解しても、requirements、plan、design は 1 つの umbrella pass で閉じる
- `project_reviewer` を intake と closeout の両方で使い、repo-wide completeness と integration risk を確認する
- `docs_workflow_steward` は canon docs、workflow docs、entrypoint wrapper の整理に限定して使う
- `python_reviewer` と `cpp_reviewer` は言語差分に応じて implementation chunk review と final integration review に追加する
- `test_designer` は実装前に static path、failure mode、nasty edge case を洗い、worker が既存 test style で落とし込む
- 同一 worktree では `worker` だけが repo file を編集する
- 同一 worktree では parallel write を許可しない

### 6. Adaptive Improvement Loop

対象:
- benchmark を見ながらの性能改善
- tuning と比較実験を回しながらの段階的改造
- 調査、実験、protocol refinement、code change をまとめた改善 loop

追加ロール:
- `researcher`
- `research_reviewer`
- `experimenter`
- `experiment_reviewer`
- `report_reviewer`
- 必要に応じて `reproducibility_reviewer`
- 必要に応じて `scientific_computing_reviewer`
- 必要に応じて `benchmark_reviewer`
- 必要に応じて `artifact_reviewer`
- 必要に応じて `fair_data_reviewer`
- 必要に応じて `ml_science_reviewer`

特徴:
- outer loop は agile、iteration backlog を持ちます
- repo に持ち帰る各 extension は 1 回の waterfall pass として閉じます
- `Question`、`Comparison Target`、`Exit Criteria`、`Stop Budget`、`Improvement Backlog` を先に固定します
- 1 iteration は 1 extension、1 waterfall run-id、1 change pass、1 decision state に固定します
- 2 つ目の extension に入る前に、直前 extension の waterfall gate check、final review、`task-close`、commit / push を終えます。ただし、outer backlog 全体の completion と iteration completion を混同しません
- `experiment-lifecycle` を run-level loop に使い、改善 backlog は `adaptive-improvement-loop` で管理します
- tuning 中でも `test_designer`、`document_flow_reviewer`、`report_reviewer` を省略しません
- `approved` だけでなく `backlog_continue` と `direction_rethink_required` を正式な decision state として扱います
- 複数 writer が必要な場合は worktree を分け、各 worktree に writer を 1 人だけ置く
- `critical_guardian` は architecture、testing completeness、dependency conflict、implementation gap を cross-cutting に見る
- 最終 review では `final_reviewer` に加えて `project_reviewer` を使い、slice 単位ではなく全体の整合を確認する

## 選び方

1. task が局所修正なら `Scoped Change`
1. 外部調査や比較実験が必要なら `Research-Driven Change`
1. chunk 設計が必要なら `Large Delivery`
1. 環境や automation を触るなら `Platform And Environment`
1. code / docs / tools / runtime をまとめて rework するなら `Comprehensive Development`
1. tuning、実験、調査、比較改善を backlog で継続するなら `Adaptive Improvement Loop`

## 関連

- `agents/task_catalog.yaml`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/ARTIFACT_PLACEMENT.md`
- `agents/canonical/CLI_ENTRYPOINTS.md`
- `agents/workflows/experiment-workflow.md`
- `agents/workflows/research-workflow.md`
