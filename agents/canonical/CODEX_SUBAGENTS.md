<!--
@dependency-start
responsibility Documents Codex Subagents for this repository.
upstream design ../task_catalog.yaml task routing catalog
downstream design CODEX_WORKFLOW.md workflow consumes subagent routing contract
downstream implementation ../../.codex/config.toml Codex runtime config consumes subagent routing
downstream implementation ../../.codex/agents/oop_readability_reviewer.toml OOP readability report reviewer role
@dependency-end
-->

# Codex Subagents

この文書は、Codex を primary runtime とする場合の subagent routing と inventory の正本です。
shared workflow は `agents/canonical/CODEX_WORKFLOW.md` に置き、この文書は inventory、mapping、activation に寄せます。
role ごとの具体的な禁止事項、handoff 条件、review separation は `.codex/agents/*.toml` を正本にします。
project-level subagent registration と runtime budget は `.codex/config.toml` の `[agents]` と `[agents.<name>]` を正本にします。

## Principles

- role behavior は docs より `.codex/agents/*.toml` を優先します
- parent agent が最終編集責任を持つ
- routing と required review を決める前に subagent を乱立させない
- repo-changing task では、stage ごとに適切な subagent を explicit に立てる
- 調査、レビュー、文書整備は分ける
- 再帰的 fan-out は避ける
- 探索、レビュー、仕様確認の並列化は使うが、parallel write-heavy implementation は避ける
- runtime の同時 spawn は `.codex/config.toml` の `max_threads` 以内に収め、role が多い task は wave に分ける
- subagent の depth や fan-out は固定値で規定せず、task の複雑さ、review の独立性、write scope 分離で決める
- 追加の subagent 層を立てるときは、parent が owner、input packet、expected output、write scope を明示する
- `計画レビュー` と `詳細設計レビュー` は別の subagent で行う
- `文書通読レビュー` は `詳細設計レビュー` と別の subagent で行う
- 論文 draft では `citation_evidence_reviewer` も別の subagent で行う
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` も別の subagent で行う
- `詳細設計レビュー` を、実装前でもっとも重要な gate とみなす
- 実装では既存コード、既存の命名、既存の文書スタイルの踏襲を優先する
- Codex の default は、frontier-required 判断系を `gpt-5.5` `high`、conditional review を `gpt-5.4-mini` `medium`、cheap-first survey / test / language review / narrow execution を `gpt-5.3-codex-spark` `low` に分ける
- `gpt-5.3-codex-spark` は `spark_worker`、`experiment_runner`、cheap-first reviewer で使い、approved packet で完全に切れる低リスク slice の first candidate とする
- repo inventory、tool drift survey、static validation planning、diff-local review、機械 report の要約は Spark read-only wave を先に使い、parent / `gpt-5.5` は統合判断、設計判断、最終責任に集中する
- Spark role が runtime tool compatibility で起動失敗した場合は、同じ task を high-cost parent に戻す前に `model="gpt-5.3-codex-spark"`、`reasoning_effort="low"` の fresh default subagent で再試行する
- 設計・scope 判断、曖昧な実装判断、multi-surface conflict resolution、ship decision は `gpt-5.5` 側に残す
- plan mode や permissions のような mode は session 単位の設定なので、subagent TOML には持たせず、parent session 側で切り替える

## Activation Budget

- runtime hard ceiling は [.codex/config.toml](../../../../.codex/config.toml) の `[agents].max_threads` を正本にし、現在は `24` です
- cap は depth 制限ではなく同時実行数の上限として扱います
- `.codex/config.toml` の `[agents]` は budget と runtime timeout の設定であり、上位 runtime / developer instruction が要求する subagent spawn 許可を上書きしません
- active runtime が explicit user request なしの `spawn_agent` を禁止する場合、parent は handoff plan と artifact packet を作って `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` を記録し、許可が出るまで実際の spawn を行いません
- depth は固定しませんが、active な subagent 数は spawn budget で縛ります
- 既定 budget は `Scoped Change Lite` で同時 4 体までです
- 既定 budget は `Scoped Change` で同時 8 体までです
- 既定 budget は `Large Delivery` / `Platform And Environment` で同時 10 体までです
- 既定 budget は `Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop` で同時 12 体までです
- budget 超過は例外扱いにし、parent が owner、理由、input packet、expected output、write scope、review gate を `schedule.md` と `work_log.md` に残します
- write-capable subagent は既定 1 体です。budget を増やしても、parent が dependency order、wave plan、disjoint write scope、integration order、review gate を明示しない並列 write は許可しません。衝突する target は禁止対象でも scope 縮小理由でもなく順序制約として先行 / 後続 wave に分け、同じ file / canonical surface / shared root contract に触れない複数 writer だけを同一 wave で並列化できます
- 同一 worktree の wave plan で安全に分離できない場合だけ separate worktree を使います
- parent はすべての role を同時に起こさず、requirements / planning / design / review / implementation を wave で切り替えます
- role 数が budget を超える review pack は batch に分け、前段の output を parent が束ねて次 batch へ渡します
- parent は stage をまたいで subagent をぶら下げたままにせず、gate を通過したら不要な instance を閉じます
- 新規 user request では前 task の subagent instance を使い回さず、新しい run bundle と fresh subagent を起こします
- 前 task の subagent に `send_input` して新規 task を継続させることは禁止します。必要な文脈は chat 要約ではなく run bundle と artifact path で渡します
- `team_manifest.yaml` の `run.subagent_lifecycle_policy` を subagent handoff prompt に含め、`fresh_subagents_required: true` と `reuse_for_new_task: forbidden` を実行時の機械契約にします
- closeout 前に run-local subagent を閉じ、`closeout_gate.md` の `subagents_closed=yes` と `Subagent Lifecycle Evidence` が揃うまで user-facing completion を返しません

## Hook And Tool Feedback To Subagent Protocol

hook、code checker、static analysis、CI、review tool の結果が subagent の責務や handoff に関係する場合、parent は次回の chat で注意するだけで閉じません。
結果を見て、subagent protocol の更新要否を `workflow_monitoring.md` の behavior event に記録します。

- subagent が読むべき checker result、hook log、dependency scope、review finding が handoff に入っていなかった場合、`team_manifest.yaml` の packet、workflow family prompt、または該当 handoff 手順を更新します。
- 特定 role が同じ失敗を見逃した場合、`.codex/agents/<role>.toml`、この文書、または role に対応する skill / workflow を更新します。
- tool / hook の誤検知や task-local noise で protocol 変更が不要な場合でも、`subagent_protocol_update=not_required` と `protocol_feedback_reason=<short-reason>` を記録します。
- reviewer role は、最新 diff だけでなく、hook / tool feedback が parent protocol と subagent protocol の判断まで閉じているかを確認します。

subagent protocol feedback の最小 token は次です。

```text
hook_tool_feedback=reviewed
parent_protocol_update=<applied|recorded|not_required>
subagent_protocol_update=<applied|recorded|not_required>
protocol_feedback_reason=<short-reason>
```

## Pre-Goal Activation

Goal-driven repo-changing tasks do not wait for the final `/goal` command before
preparing subagent fan-out. The parent may draft the initial goal, but the draft
must be checked by read-only roles before implementation. If the active runtime
requires explicit spawn authorization, "checked by read-only roles" means
spawn the roles only after authorization; otherwise persist their handoff
packets and block implementation until the authorization question is resolved.

Default pre-goal wave:

- `requirements_organizer`: derive a conservative Objective, non-goals,
  constraints, and Exit Criteria from the user request and durable repo notes.
- `explorer`: inspect repo docs, prior notes, dependency surfaces, existing
  tools, and reuse candidates that affect the goal.
- `execution_planner`: group open `GW*` rows into the first cohesive slice after
  `goal_loop.py plan` exists.
- `plan_reviewer`: verify that the candidate goal is checkable and that the
  first slice has evidence gates and rollback boundaries.

Constraints:

- These pre-goal agents are read-only unless the user explicitly requested a
  repo edit and the goal has already been mirrored into `goal.md`.
- Write-capable `worker` / `spark_worker` instances are blocked until
  `goal.md` is parseable, the Codex goal view is mirrored or queued, and the
  Plan-mode output contains evidence mapping.
- If rate limits force fewer agents, keep `requirements_organizer` and
  `explorer`; record why `execution_planner` or `plan_reviewer` was deferred.
- Handoffs must include `agents/workflows/codex-goals-workflow.md`,
  `agents/workflows/goal-plan-implementation-loop.md`, the candidate `goal.md`
  or goal artifact, and `team_manifest.yaml` lifecycle policy.
- When repo MCP exposes `goal.plan`, use it with `goal.loop_status` to hand the
  next unchecked work units to `execution_planner` instead of summarizing a
  large `goal.md` by chat.

## Codex Command Surface

- official Codex CLI では `/model` で model / reasoning、`/plan` で plan mode、`/permissions` で approval preset を切り替えます
- これらは session-level setting で、per-agent TOML には書きません
- runtime が `/agent` を提供する場合は inventory 確認に使います
- `/agent` が使えない runtime では `.codex/agents/*.toml` を直接見ます
- run bundle は `python3 tools/agent_tools/bootstrap_agent_run.py ...` で先に作ります
- `--task-id` を使うと、task catalog の task-default specialist と default review pack を bundle へ自動展開します

## Permanent Team To Codex Mapping

| Permanent Team Role | Codex Subagent / Parent Role |
| ------------------- | ---------------------------- |
| `manager` | parent + `requirements_organizer` |
| `manager_reviewer` | `manager_reviewer` |
| `scheduler` | `execution_planner` |
| `schedule_reviewer` | `plan_reviewer` |
| `designer` | `detailed_designer` |
| `design_reviewer` | `detailed_design_reviewer` |
| `document_flow_reviewer` | `document_flow_reviewer` |
| `citation_evidence_reviewer` | `citation_evidence_reviewer` |
| `test_designer` | `test_designer` |
| `notation_definition_reviewer` | `notation_definition_reviewer` |
| `logic_gap_reviewer` | `logic_gap_reviewer` |
| `implementer` | `spark_worker` first for design-traced narrow slices; `worker` fallback for broad or ambiguous implementation |
| `change_reviewer` | `python_reviewer`, `cpp_reviewer`, `diff_triage_reviewer`, then `reviewer` when escalation is needed |
| `final_reviewer` | `ship_reviewer`, then `reviewer` / `project_reviewer` when final gate escalation is needed |
| `critical_guardian` | `project_reviewer` |
| `researcher` | `literature_researcher` or `explorer` |
| `infra_steward` | parent + `docs_workflow_steward` or infrastructure-focused `worker` planning |

## Built-In Or Project-Scoped Roles
- `requirements_organizer`
  - 変更要求、source bucket、scope、acceptance criteria、reuse target を整理する
- `manager_reviewer`
  - 要件 contract、source bucket、accumulated context resolution、unknown handling を独立に確認する
- `execution_planner`
  - stage 順序、担当 subagent、validation 順序、rollback point を固定する
- `plan_reviewer`
  - 実行計画の順序、review 分離、rollback readiness を確認する
- `detailed_designer`
  - reuse-first の detailed design 文書と identifier naming plan を起こす
- `detailed_design_reviewer`
  - 実装前の最重要 gate として設計文書と identifier naming plan を独立に確認する
- `document_flow_reviewer`
  - 文書を上から順に読み、用語導入、section 順序、reader path が自然かを確認する
- `citation_evidence_reviewer`
  - 論文主張が citation、figure、table、derivation、appendix、result に辿れるかを確認する
- `notation_definition_reviewer`
  - 記号、略語、technical term、unit、index、assumption の definition-before-use と一貫性を確認する
- `logic_gap_reviewer`
  - claim-to-evidence のつながり、hidden assumption、result と interpretation の飛躍を確認する
- `long_form_writer`
  - README、workflow、guide、migration 文書のような長文を roadmap-first に起草する
- `test_designer`
  - approved design と既存 code path を静的解析し、nasty case と regression case の test plan を起こす
- `diff_triage_reviewer`
  - 狭い diff の first-pass review を安価に行い、language-specific reviewer または broad `reviewer` へ上げるかを決める
- `ship_reviewer`
  - user request clause、product diff、validation、dependency review、closeout artifact を照合する最終出荷 gate を担当する
- `explorer`
  - 読み取り専用で codebase / docs / workflow の調査を行う
- `reviewer`
  - 読み取り専用で diff と risk を findings-first で洗う
- `python_reviewer`
  - Python diff を型、pytest、ruff 前提で洗う
- `cpp_reviewer`
  - C / C++ diff を build、header、ownership、native test 前提で洗う
- `oop_readability_reviewer`
  - `tools/oop/*/readability.py` の機械 report を読み、判定値を変えずに reader-facing な文書化、false positive 候補、優先度整理を行う
- `worker`
  - bounded な実装変更を切り出し、approved design と local precedent の naming に従う
- `spark_worker`
  - approved design packet で完全に切れる低リスク実装、docs sync、test sync、mechanical cleanup を低遅延に処理する
- `docs_workflow_steward`
  - agent 文書、workflow、adapter file の整理を行う
- `project_reviewer`
  - repo-wide な inventory と workflow health を確認する
- `literature_researcher`
  - 論文、survey、比較論文、仕様資料の調査と先行研究整理を行う
- `report_reviewer`
  - experiment report の根拠と reader-facing quality を確認する
- `reproducibility_reviewer`
  - provenance、seed、command、environment、rerunability を確認する
- `scientific_computing_reviewer`
  - incremental change、testing、automation、prototype discipline を確認する
- `benchmark_reviewer`
  - fairness、case mix、confounder、benchmark anti-pattern を確認する
- `artifact_reviewer`
  - code、script、raw result、environment、artifact package の十分性を確認する
- `fair_data_reviewer`
  - metadata、命名、result path、再利用性を確認する
- `ml_science_reviewer`
  - assumptions、limitations、uncertainty、reader-facing reporting を確認する

棲み分け:
- `document_flow_reviewer` は design / README / workflow などの top-down readability を見る
- `report_reviewer` は experiment report の evidence traceability と overclaim を見る

## Recommended Routing

| Stage | Default Subagent Pattern |
| ----- | ------------------------ |
| 要件整理 | `requirements_organizer`。local precedent 調査が要るなら `explorer` を補助に使う |
| 要件レビュー | 専用の `manager_reviewer` instance。notes、docs、prior logs、local precedent で解決できる unknown が残っていないかを見る |
| 調査 | 外部文献は `literature_researcher`、local precedent は `explorer` |
| 実行計画立案 | `execution_planner` |
| 計画レビュー | 専用の `plan_reviewer` instance |
| 詳細設計 | `detailed_designer`。既存 code path 調査が要るなら `explorer` を補助に使う |
| 詳細設計レビュー | 専用の `detailed_design_reviewer` instance |
| 長文起草 | `long_form_writer`。README、workflow、guide、migration 文書では `long-form-writing` を前提に draft する |
| 学術文章起草 | `long_form_writer`。論文、thesis chapter、scholarly note では `academic-writing` を前提に draft する |
| 論文 draft 起草 | `long_form_writer`。投稿論文や thesis chapter では `paper-writing` を前提に draft する |
| 文書通読レビュー | 専用の `document_flow_reviewer` instance。詳細設計、README、workflow、reader-facing doc を上から順に読んで意味が通るかを見る |
| citation / evidence trace review | 専用の `citation_evidence_reviewer` instance。paper claim が citation、figure、table、appendix、result に辿れるかを見る |
| テストケース設計 | 専用の `test_designer` instance。approved design と既存 code path を静的解析し、最も意地の悪い edge case と regression case を test plan に落とす |
| 記号定義レビュー | 専用の `notation_definition_reviewer` instance。記号、略語、technical term、unit、index、assumption の定義順と一貫性を見る |
| 論理接続レビュー | 専用の `logic_gap_reviewer` instance。主張の飛躍、隠れた仮定、result と interpretation の境界を見る |
| report / claim-heavy narrative review | 専用の `report_reviewer` instance。evidence traceability、overclaim、reader-facing report quality を見る |
| OOP readability report documentation | 専用の `oop_readability_reviewer` instance。機械判定 report を事実として扱い、OOP 原則別に文書化する |
| 実装 | `IMPLEMENTATION_CODEX_AGENTS` を確認し、design trace、naming、validation が固定済みの slice は `spark_worker`、broad / ambiguous slice は `worker` |
| 低リスク実装slice | design trace、naming、validation が固定済みの slice だけを `spark_worker` first |
| 実装後レビュー | `reviewer`、`python_reviewer`、必要に応じて `cpp_reviewer` |
| 包括的開発の統合レビュー | `project_reviewer`、`docs_workflow_steward`、`python_reviewer`、必要に応じて `cpp_reviewer` を intake / wrap-up の固定 stack として使う |

運用ルール:
- role ごとの詳細な実行制約は `.codex/agents/*.toml` を見ます
- この文書では route と inventory だけを決め、各 role の禁止事項を重複記述しません
- parent は stage を暗黙にまとめず、別 role を別 instance で起動します
- subagent を起動するときは、`team_manifest.yaml` の `run.subagent_prompt_packet`、該当 role の `prompt_contract`、`document_packet.read_before_work`、または `task_start.py` / `bootstrap_agent_run.py` の packet 出力をそのまま渡します
- workflow family ごとの prompt 正本は `agents/task_catalog.yaml` の `workflow_families[].subagent_prompt` です
- 長文文書では `document_flow_reviewer` に加えて別 reviewer で `docs-completeness-review` を通します
- 学術文章では `document_flow_reviewer` に加えて `notation_definition_reviewer`、`logic_gap_reviewer`、別 reviewer の `docs-completeness-review` を通します
- 論文 draft では `citation_evidence_reviewer` も追加します
- research-driven change では `report_reviewer` と perspective reviewers を default にします

## Parallel Write Safety

- parent が `team_manifest.yaml` の write policy と handoff で writer ごとの allowed path / directory を管理します
- 同一 path、同一 directory ownership、同一 public API surface を複数 writer に割り当てません
- 同一 worktree の write-capable subagent は既定 1 人ですが、parent が dependency order、wave plan、disjoint write scope、integration order、review gate を固定した場合は複数 writer を同一 wave で使えます
- same directory / same file / same canonical surface を同時に触る writer は同一 wave に置きません
- 衝突する target は禁止でも scope 縮小理由でもなく順序制約として扱い、先行 wave の validation と tool rerun 後に後続 wave で統合します
- 複数 worktree は、同一 worktree の wave plan で安全に分離できない場合の選択肢です
- review role は常に read-only とし、parent-managed write-scope discipline と single-writer-default の確認は `plan_reviewer` と `project_reviewer` の固定責務です

## Codex Model Policy

| Role Bucket | Roles | Model | Reasoning |
| ----------- | ----- | ----- | --------- |
| Frontier-Required Planning / Design / Synthesis | `requirements_organizer`, `execution_planner`, `detailed_designer`, `long_form_writer`, `literature_researcher` | `gpt-5.5` | `high` |
| Frontier-Required Review / Ship Decision | `manager_reviewer`, `plan_reviewer`, `detailed_design_reviewer`, `citation_evidence_reviewer`, `notation_definition_reviewer`, `logic_gap_reviewer`, `reviewer`, `project_reviewer`, `ship_reviewer` | `gpt-5.5` | `high` |
| Broad Or Ambiguous Implementation | `worker` | `gpt-5.5` | `high` |
| Conditional Frontier / Specialist Review | `document_flow_reviewer`, `docs_workflow_steward`, `report_reviewer`, `reproducibility_reviewer`, `scientific_computing_reviewer`, `benchmark_reviewer`, `artifact_reviewer`, `fair_data_reviewer`, `ml_science_reviewer`, `oop_readability_reviewer` | `gpt-5.4-mini` | `medium` |
| Cheap-First Survey / Test / Diff Review | `explorer`, `test_designer`, `python_reviewer`, `cpp_reviewer`, `diff_triage_reviewer` | `gpt-5.3-codex-spark` | `low` |
| Execution-Only / Low-Latency Narrow Implementation | `spark_worker`, `experiment_runner` | `gpt-5.3-codex-spark` | `low` |

運用メモ:
- OpenAI の GPT-5.5 release notes では、GPT-5.5 は Codex で利用可能で、agentic coding、computer use、knowledge work、early scientific research での改善が強いとされています。
- この repo では、frontier 判断を `gpt-5.5`、条件付き specialist review を `gpt-5.4-mini` `medium`、cheap-first survey / static test design / language review / diff triage / execution-only task を `gpt-5.3-codex-spark` `low` に寄せます。
- repo default の reasoning は `high` にし、`xhigh` は parent が明示的に必要と判断したときの manual escalation に留めます
- planning session の mode は official Codex CLI なら `/plan`、model / reasoning の切替は `/model`、approval preset は `/permissions` を使います
- 極端に狭く、待ち時間が支配的な implementation loop では、`worker` ではなく `spark_worker` を first candidate とします
- `gpt-5.3-codex-spark` は `spark_worker`、`experiment_runner`、cheap-first reviewer で使い、詳細設計、最終判断、重要 review には使いません
- `spark_worker` へ渡す条件は、Implementation Source Packet、Design-To-Implementation Trace、identifier naming、test plan、write scope がすべて固定済みであることです
- 明示 spawn 許可がある repo-changing task では、repo inventory、tool drift survey、static validation failure triage、diff-local language review、機械 report 要約を parent が抱え込まず、先に Spark read-only wave へ切ります
- `spark_worker` eligible な実装は、1 file または単一抽象ユニット、public interface 変更なし、依存追加なし、仕様解釈なし、既存 test / docs の局所更新で閉じるものに限ります
- cross-module 整合、API shape、命名 / 責務境界、依存再構成、安全性、性能、conflict resolution のいずれかが入った時点で `worker` または設計 review へ戻します
- `document_flow_reviewer` は README / workflow / guide / design doc / paper、新用語、公開 API、reader-facing docs があるときに起動します。純粋な code-only lite fix では省略できます
- `reviewer` は broad diff / cross-surface / clause coverage に上げる role とし、Python-only / C++-only / narrow diff では `python_reviewer`、`cpp_reviewer`、`diff_triage_reviewer` を first reviewer にします

## Research Perspective Review Pack

- default triage は `reproducibility_reviewer` に provenance、seed、command、environment、rerunability を見させ、`artifact_reviewer` に code、script、raw result、environment、artifact package の十分性を見させる
- benchmark protocol がある場合だけ `benchmark_reviewer` を追加します
- dataset / result path / metadata が中心の場合だけ `fair_data_reviewer` を追加します
- ML claim / uncertainty / limitation が中心の場合だけ `ml_science_reviewer` を追加します
- workflow / prototype discipline が論点の場合だけ `scientific_computing_reviewer` を追加します
- full pack は `research_perspective_review` を明示したとき、または triage が methodology / benchmark / FAIR-data / ML-science / scientific-computing risk を返したときだけ起動します
- parent が findings を `fix now`、`follow-up`、`delete-ok` に再分類して反映する

## Runtime Surfaces

- human canon: `agents/`
- skill shim: `.agents/skills/`
- Codex project config: `.codex/config.toml`
- Codex subagent definitions: `.codex/agents/*.toml`

設定運用メモ:
- stage 固有の禁止事項を増やしたいときは、この文書より先に `.codex/agents/*.toml` を更新します
- wrapper や root entrypoint に同じ規則を重ね書きしません

## Smoke Test

runtime inventory や review pack を変えたら、まず次を実行します。

    python3 tools/agent_tools/check_agent_runtime_alignment.py
    python3 tools/agent_tools/smoke_test_research_perspective_pack.py

この smoke test は次を確認します。

- `agents/task_catalog.yaml` の各 task が有効な specialist / review pack へ展開できる
- `agents/agents_config.json` の required output が実テンプレートに結び付いている
- `.codex/config.toml` が `.codex/agents/*.toml` を全 role 登録している
- `.codex/agents/*.toml` の model split が frontier-required / conditional-frontier / cheap-first / execution-only bucket に揃っている
- temporary run bundle を task ごとと full-team で作り、required output が実際に生成される
- `agents/agents_config.json` に perspective reviewers と artifact mapping がある
- `agents/task_catalog.yaml` に `research_perspective_triage` default pack と optional `research_perspective_review` pack がある
- `.codex/agents/*.toml` に対応 subagent 定義がある
- temporary run bundle を作って、各 perspective review artifact と `team_manifest.yaml` が実際に生成される
