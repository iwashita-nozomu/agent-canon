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
permanent team role ownership、required output、write policy は `agents/agents_config.json` を正本にします。
role ごとの具体的な禁止事項、handoff 条件、review separation は `.codex/agents/*.toml` を正本にします。
project-level subagent registration と runtime budget は `.codex/config.toml` の `[agents]` と `[agents.<name>]` を正本にします。
prompt、routing、subagent-config drift の監査は `prompt_config_reviewer` を先に通し、
この file を workflow prose や skill prose の重複格納先にしません。

## Principles

- role behavior は docs より `.codex/agents/*.toml` を優先します
- permanent team ownership、artifact output、write policy は `agents/agents_config.json` を優先します
- subagent registration と runtime budget は `.codex/config.toml` を優先し、role model / reasoning は `.codex/agents/*.toml` を優先します
- prompt / config drift を見つけたら、親がその場で policy prose を増やす前に `prompt_config_reviewer` の監査結果を要求します
- parent agent が最終編集責任を持つ
- routing と required review を決める前に subagent を乱立させない
- repo-changing task では、stage ごとに適切な subagent を explicit に立てる
- 調査、レビュー、文書整備は分ける
- 無制限 fan-out は避ける
- subagents may spawn bounded child subagents only when their handoff packet includes `delegated_spawn_policy` with owner, input packet, expected output, write scope, validation route, review gate, and remaining spawn budget
- 探索、レビュー、仕様確認の並列化は使うが、parallel write-heavy implementation は避ける
- runtime の同時 spawn は `.codex/config.toml` の `max_threads` 以内に収め、role が多い task は wave に分ける
- subagent depth は `.codex/config.toml` の `agents.max_depth = 2` を正本にし、parent wave と child-subagent wave を active spawn budget 内で管理する
- 追加の subagent wave を立てるときは、parent または delegated stage owner が owner、input packet、expected output、write scope を明示する
- 追加の `git worktree`、separate worktree、integration worktree は作成・使用しない。writer collision は current checkout 内の先行 / 後続 wave と validation rerun で解く
- subagent handoff の input packet は role ごとに bounded にし、`/workspace` や repo root 全体を読む scope として渡さない
- reviewer には raw repo / raw log / full tree ではなく、対象 path list、checker summary、compact dashboard / drilldown、該当 canon 節を先に渡す
- `計画レビュー` と `詳細設計レビュー` は別の subagent で行う
- `文書通読レビュー` は `詳細設計レビュー` と別の subagent で行う
- 論文 draft では `citation_evidence_reviewer` も別の subagent で行う
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` も別の subagent で行う
- `詳細設計レビュー` を、実装前でもっとも重要な gate とみなす
- 実装では既存コード、既存の命名、既存の文書スタイルの踏襲を優先する
- Codex の role ごとの model / reasoning 設定は `.codex/agents/*.toml` を正本にする
- Abstract Design Frame と approved packet で完全に切れる低リスク slice は Spark role TOML を first implementation candidate とする
- repo inventory、tool drift survey、static validation planning、diff-local review、機械 report の要約は、implementation の critical path を塞がない独立検証としてだけ read-only role に切る。coding / implementation / patch work が scope にある task では、既定の説明を write-capable handoff first にする。bounded `allowed_paths`、write scope、validation plan、tool-rejection preflight が揃い次第、write-capable `spark_worker` / `worker` handoff を schedule し、parent は handoff packet、統合順序、review gate、最終責任に集中する
- user が coding / implementation / patch work の subagent 委譲を明示した task では、read-only wave は setup evidence であり完了条件ではありません。requirements、bounded `allowed_paths`、write scope、validation plan、tool-rejection preflight が固定できたら、追加の read-only wave より先に `spark_worker` / `worker` を起動または schedule します。
- Spark role が runtime tool compatibility で起動失敗した場合は、同じ task を high-cost parent に戻す前に該当 role TOML の model / reasoning で fresh default subagent を再試行する
- 設計・scope 判断、曖昧な実装判断、multi-surface conflict resolution、ship decision は frontier role TOML に残す
- plan mode や permissions のような mode は session 単位の設定なので、subagent TOML には持たせず、parent session 側で切り替える

## Activation Budget

- runtime hard ceiling は [.codex/config.toml](../../.codex/config.toml) の `[agents].max_threads` を正本にし、現在は `24` です
- `.codex/config.toml` の `[agents].max_depth` は `2` を正本にし、one bounded child-subagent layer を許可します
- cap は同時実行数の上限として扱います
- `.codex/config.toml` の `[agents]` は budget と runtime timeout の設定であり、上位 runtime / developer instruction が要求する subagent spawn 許可を上書きしません
- active runtime が explicit user request なしの `spawn_agent` を禁止する場合、parent は handoff plan と artifact packet を作って `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` を記録し、許可が出るまで実際の spawn を行いません
- active な subagent 数は spawn budget で縛ります
- spawn budget は同時 active 数の上限です。first wave を budget まで埋める target ではありません。parent は Initial Intake Wave で requirements / exploration / execution planning を分け、以後の stage wave を workflow family の budget 内で追加します
- multi-agent family で予定 stage wave を起こさない場合は、rate limit、blocked role、irrelevant role、または parent-direct rationale を `schedule.md` / `workflow_monitoring.md` に残します
- 既定 budget は `Scoped Change Lite` で同時 4 体までです
- 既定 budget は `Scoped Change` で同時 8 体までです
- 既定 budget は `Large Delivery` / `Platform And Environment` で同時 10 体までです
- 既定 budget は `Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop` で同時 12 体までです
- budget 超過は例外扱いにし、parent が owner、理由、input packet、expected output、write scope、review gate を `schedule.md` と `work_log.md` に残します
- write-capable subagent は既定 1 体です。budget を増やしても、parent が dependency order、wave plan、disjoint write scope、integration order、review gate を明示しない並列 write は許可しません。衝突する target は禁止対象でも scope 縮小理由でもなく順序制約として先行 / 後続 wave に分け、同じ file / canonical surface / shared root contract に触れない複数 writer だけを同一 wave で並列化できます
- current checkout 内の wave plan で安全に分離できない場合は、separate worktree へ逃がさず、writer を後続 wave に直列化します
- parent はすべての role を同時に起こさず、requirements / planning / design / review / implementation を wave で切り替えます
- delegated stage owner が child subagents を起動する場合も、active spawn budget、max write budget、fresh lifecycle policy、current-checkout write-scope policy を継承します
- role 数が budget を超える review pack は batch に分け、前段の output を parent が束ねて次 batch へ渡します
- parent は stage をまたいで subagent をぶら下げたままにせず、gate を通過したら不要な instance を閉じます
- 新規 user request では前 task の subagent instance を使い回さず、新しい run bundle と fresh subagent を起こします
- 前 task の subagent に `send_input` して新規 task を継続させることは禁止します。必要な文脈は chat 要約ではなく run bundle と artifact path で渡します
- `team_manifest.yaml` の `run.subagent_lifecycle_policy` を subagent handoff prompt に含め、`fresh_subagents_required: true` と `reuse_for_new_task: forbidden` を実行時の機械契約にします
- closeout 前に run-local subagent を閉じ、`closeout_gate.md` の `subagents_closed=yes` と `Subagent Lifecycle Evidence` が揃うまで user-facing completion を返しません

## Handoff Context Budget

Subagent の context budget は correctness gate です。parent は handoff prompt ごとに次を固定します。

- `role_scope`: その role が判断する subdomain、stage、risk class。
- `allowed_paths`: 対象 file / directory / glob の bounded list。repo root や `/workspace` だけの指定は禁止。編集候補、検索 hit、checker finding、changed path を seed にし、dependency header graph を再帰展開した `dependency_edit_scope.txt` / `dependency_graph.tsv` を優先します。
- `required_artifacts`: checker output、compact dashboard、dependency-expanded scope、design / implementation packet、または review packet。raw logs や full reports を直接読ませず、まず compact artifact を渡します。dependency-expanded scope が必要な場合は `bash tools/agent_tools/run_repo_dependency_review.sh --report-dir <run-or-review-dir> --search-hits-file <hits>` または changed-path 相当の dependency review output を handoff に含めます。
- `canon_refs`: 必要な AgentCanon / project canon の節だけ。文書 tree 全体を辿らせません。
- `do_not_read`: unrelated modules、generated raw logs、historical reports、他 role の scope など、読まない surface。
- `expected_output`: findings schema、decision vocabulary、uncertainty / residual risk、test gaps。
- `implementation_surface_route`: implementation handoff では `PRIMARY_PATHS` を `allowed_paths` の seed、`FORBIDDEN_PATHS` を `do_not_read` の seed にします。router が unavailable なら、その blocker または deterministic fallback output を渡し、path を chat 印象で選びません。
- `tool_reuse_ledger` と `pre_edit_rejection_prediction`: write-capable `spark_worker` / `worker` には、既存 tool を使うか拒否した理由と `tool_rejection_preflight.py` の結果または pending blocker を渡します。

role 分割が妥当でも input packet が広すぎる場合は routing defect として扱います。例えば数値 algorithm review は `scientific_computing_reviewer` を subdomain 別に分けてもよいですが、各 agent には solver / optimizer / functional などの担当 path list と contract-check summary だけを渡します。Python API / typing review は `python_reviewer` に分け、数学 canon の full context は渡しません。

## Wave Plan Contract

Every subagent wave must be recorded with the same compact contract across
`team_manifest.yaml`, `schedule.md`, `workflow_monitoring.md`, and
`closeout_gate.md`: `wave_id`, `owner`, `spawn_authority`,
`spawn_budget.active_subagents`, `spawn_budget.max_write_subagents`,
`runtime_max_threads`, `runtime_max_depth`, `allowed_paths`, `do_not_read`,
`write_scope`, `validation_route`, `review_gate`, and `handoff_artifacts`.
Mid-task expansion uses the same contract; it is not an exception path.
`task_start.py` and `bootstrap_agent_run.py` emit
`RECOMMENDED_INITIAL_SUBAGENT_WAVE` and `RECOMMENDED_DYNAMIC_EXPANSION_WAVES`;
these values are executable Codex `agent_type` lists for the parent to pass to
the runtime spawn tool.

## Initial Intake Wave

Initial Intake Wave は repo-changing task の初期責務を要件、調査、実行計画に分ける初期 wave です。これは総同時起動数の cap ではありません。`requirements_organizer` は user-request clauses、acceptance criteria、source bucket を持ちます。`explorer` は evidence / reuse / stale-surface inventory と dependency-expanded bounded path list を持ちます。`execution_planner` は stage order、artifact routing、validation sequence、review route、Agent Wave Ledger を持ちます。parent はこの初期 wave の output を統合し、workflow family の active spawn budget と `max_depth = 2` の下で次の stage wave を起動します。stage owner に child-subagent 起動を委譲する場合は、`team_manifest.yaml` の `run.delegated_spawn_policy` と Wave Plan Contract を handoff prompt に含めます。

Tool-result route markers:
- raw checker/stat artifacts -> artifact_reviewer
- reader-facing narrative interpretation -> report_reviewer
- OOP mechanical reports -> oop_readability_reviewer
- repo-wide drift and integration risk -> project_reviewer

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
- This write-capable block is for goal-driven tasks. Ordinary repo-changing
  tasks with explicit implementation delegation do not require `goal.md`;
  they require a run bundle, bounded `allowed_paths`, write scope, validation
  plan, and tool-rejection preflight before `spark_worker` / `worker`.
- If rate limits force fewer agents, keep `requirements_organizer` and
  `explorer`; record why `execution_planner` or `plan_reviewer` was deferred.
- Handoffs must include `agents/workflows/codex-goals-workflow.md`,
  `agents/workflows/goal-plan-implementation-loop.md`, the candidate `goal.md`
  or goal artifact, and `team_manifest.yaml` lifecycle policy.
- Use `goal_loop.py plan` to hand the next unchecked work units to
  `execution_planner` instead of summarizing a large `goal.md` by chat.

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
| `designer` | `detailed_designer` |
| `design_reviewer` | `detailed_design_reviewer` |
| `document_flow_reviewer` | `document_flow_reviewer` |
| `test_designer` | `test_designer` |
| `implementer` | `spark_worker` first for narrow slices derived from the Abstract Design Frame and design trace; `worker` alternate route for broad or ambiguous implementation |
| `change_reviewer` | `python_reviewer`, `cpp_reviewer`, `diff_triage_reviewer`, then `reviewer` when escalation is needed |
| `final_reviewer` | `ship_reviewer` checks final diff traceability to the Abstract Design Frame and approved packet; then `reviewer` / `project_reviewer` when final gate escalation is needed |
| `verifier` | parent validation runner |
| `auditor` | parent closeout and workflow-monitoring gate |
| `researcher` | `literature_researcher` or `explorer` |
| `research_reviewer` | `reviewer` |
| `experimenter` | `experiment_runner` for runs; `worker` only for scoped runtime-output handling |
| `experiment_reviewer` | `reviewer` |
| `scheduler` | `execution_planner` |
| `schedule_reviewer` | `plan_reviewer` |
| `citation_evidence_reviewer` | `citation_evidence_reviewer` |
| `notation_definition_reviewer` | `notation_definition_reviewer` |
| `logic_gap_reviewer` | `logic_gap_reviewer` |
| `infra_steward` | parent + `docs_workflow_steward` or infrastructure-focused `worker` planning |
| `infra_reviewer` | `reviewer` |
| `reproducibility_reviewer` | `reproducibility_reviewer` |
| `scientific_computing_reviewer` | `scientific_computing_reviewer` |
| `benchmark_reviewer` | `benchmark_reviewer` |
| `artifact_reviewer` | `artifact_reviewer` |
| `fair_data_reviewer` | `fair_data_reviewer` |
| `ml_science_reviewer` | `ml_science_reviewer` |
| `project_reviewer` | `project_reviewer` |
| `docs_workflow_steward` | `docs_workflow_steward` |
| `prompt_config_reviewer` | `prompt_config_reviewer` |
| `python_reviewer` | `python_reviewer` |
| `cpp_reviewer` | `cpp_reviewer` |
| `report_reviewer` | `report_reviewer` |
| `critical_guardian` | `project_reviewer` |

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
  - README、workflow、guide、migration、specification など file responsibility が一般説明 prose の文書を、graph/DSL closure 後に roadmap-first で prose projection する
- `test_designer`
  - approved design と既存 code path を静的解析し、nasty case と regression case の test plan を起こす
- `diff_triage_reviewer`
  - 狭い diff の first-pass review を安価に行い、language-specific reviewer または broad `reviewer` へ上げるかを決める
- `ship_reviewer`
  - user request clause、Abstract Design Frame、approved packet、product diff、validation、dependency review、closeout artifact を照合する最終出荷 gate を担当する
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
  - Abstract Design Frame と approved design packet で完全に切れる低リスク実装、docs sync、test sync、mechanical cleanup を低遅延に処理する
- `docs_workflow_steward`
  - agent 文書、workflow、adapter file の整理を行う
- `prompt_config_reviewer`
  - `.codex/agents/*.toml`、`.codex/config.toml`、workflow prompt、routing skill の prompt/config drift を読み取り専用で監査する
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
| 一般説明 prose projection | `long_form_writer`。README、workflow、guide、migration、specification など file responsibility が一般説明 prose の文書では `long-form-writing` を DSL-to-prose adapter として使う |
| 学術文章起草 | `long_form_writer`。論文、thesis chapter、scholarly note では `academic-writing` を前提に draft する |
| 論文 draft 起草 | `long_form_writer`。投稿論文や thesis chapter では `paper-writing` を前提に draft する |
| 文書通読レビュー | 専用の `document_flow_reviewer` instance。詳細設計、README、workflow、reader-facing doc を上から順に読んで意味が通るかを見る |
| citation / evidence trace review | 専用の `citation_evidence_reviewer` instance。paper claim が citation、figure、table、appendix、result に辿れるかを見る |
| テストケース設計 | 専用の `test_designer` instance。approved design と既存 code path を静的解析し、最も意地の悪い edge case と regression case を test plan に落とす |
| 記号定義レビュー | 専用の `notation_definition_reviewer` instance。記号、略語、technical term、unit、index、assumption の定義順と一貫性を見る |
| 論理接続レビュー | 専用の `logic_gap_reviewer` instance。主張の飛躍、隠れた仮定、result と interpretation の境界を見る |
| report / claim-heavy narrative review | 専用の `report_reviewer` instance。evidence traceability、overclaim、reader-facing report quality を見る |
| OOP readability report documentation | 専用の `oop_readability_reviewer` instance。機械判定 report を事実として扱い、OOP 原則別に文書化する |
| 実装 | `IMPLEMENTATION_CODEX_AGENTS` を確認し、Abstract Design Frame から導かれ、design trace、naming、validation が固定済みの slice は `spark_worker`、broad / ambiguous slice は `worker` |
| 低リスク実装slice | Abstract Design Frame から導かれ、design trace、naming、validation が固定済みの slice だけを `spark_worker` first |
| 実装後レビュー | `reviewer`、`python_reviewer`、必要に応じて `cpp_reviewer` |
| 包括的開発の統合レビュー | `project_reviewer`、`docs_workflow_steward`、prompt/config surface がある場合は `prompt_config_reviewer`、`python_reviewer`、必要に応じて `cpp_reviewer` を intake / wrap-up の固定 stack として使う |

運用ルール:
- role ごとの詳細な実行制約は `.codex/agents/*.toml` を見ます
- この文書では route と inventory だけを決め、各 role の禁止事項を重複記述しません
- parent は stage を暗黙にまとめず、別 role を別 instance で起動します
- subagent を起動するときは、`team_manifest.yaml` の `run.subagent_prompt_packet`、該当 role の `prompt_contract`、`document_packet.read_before_work`、または `task_start.py` / `bootstrap_agent_run.py` の packet 出力をそのまま渡します
- workflow family ごとの prompt 正本は `agents/task_catalog.yaml` の `workflow_families[].subagent_prompt` です
- 一般説明 prose adapter を使う文書では `document_flow_reviewer` に加えて別 reviewer で `docs-completeness-review` を通します
- 学術文章では `document_flow_reviewer` に加えて `notation_definition_reviewer`、`logic_gap_reviewer`、別 reviewer の `docs-completeness-review` を通します
- 論文 draft では `citation_evidence_reviewer` も追加します
- research-driven change では `report_reviewer` と perspective reviewers を default にします

## Parallel Write Safety

- parent が `team_manifest.yaml` の write policy と handoff で writer ごとの allowed path / directory を管理します
- 同一 path、同一 directory ownership、同一 public API surface を複数 writer に割り当てません
- 同一 worktree の write-capable subagent は既定 1 人ですが、parent が dependency order、wave plan、disjoint write scope、integration order、review gate を固定した場合は複数 writer を同一 wave で使えます
- same directory / same file / same canonical surface を同時に触る writer は同一 wave に置きません
- 衝突する target は禁止でも scope 縮小理由でもなく順序制約として扱い、先行 wave の validation と tool rerun 後に後続 wave で統合します
- 複数 worktree は選択肢にしません。current checkout 内の wave plan で安全に分離できない writer は後続 wave へ直列化します
- review role は常に read-only とし、parent-managed write-scope discipline と single-writer-default の確認は `plan_reviewer` と `project_reviewer` の固定責務です

## Codex Model Settings

`.codex/agents/*.toml` は Codex runtime が読む materialized role 定義です。
role の `model` / `model_reasoning_effort` は各 agent TOML が正本です。
`.codex/config.toml` は project feature、runtime cap、MCP、skill、agent registry
だけを持ち、role model / reasoning を二重管理しません。

role の model / reasoning を変更するときは、該当 `.codex/agents/*.toml`
だけを更新し、`tools/agent_tools/check_agent_runtime_alignment.py` と
`tools/agent_tools/evaluate_codex_agent_roles.py` で検証します。Python checker、
workflow docs、task catalog に role list や model list を重複管理しません。

運用メモ:
- OpenAI / Codex の current product evidence は `$openai-docs` で確認します。
  この文書は個別 source URL や alternate route reference を保持しません。
- この repo では、設計判断・広域 synthesis・学術主張の精査・final judgment と broad / ambiguous implementation を frontier role TOML、bounded review / report traceability / checklist gate を mini review role TOML、狭い code survey / static test design / language review と Abstract Design Frame から導かれた設計済み低リスク実装 slice を Spark role TOML に寄せます。
- repo default の reasoning は `high` にし、`xhigh` は parent が明示的に必要と判断したときの manual escalation に留めます
- planning session の mode は official Codex CLI なら `/plan`、model / reasoning の切替は `/model`、approval preset は `/permissions` を使います
- 極端に狭く、待ち時間が支配的な implementation loop では、`worker` ではなく `spark_worker` を first candidate とします
- mini review role TOML は bounded review と report/checklist gate で使い、final judgment や scope を変える設計判断には使いません
- Spark role TOML は `spark_worker` や code-reading roles で使い、詳細設計、最終判断、重要 review には使いません
- `spark_worker` へ渡す条件は、Abstract Design Frame、Implementation Source Packet、Design-To-Implementation Trace、identifier naming、test plan、write scope がすべて固定済みであることです
- 明示 spawn 許可がある repo-changing task でも、repo inventory、tool drift survey、static validation failure triage、diff-local language review、機械 report 要約を常に先行 read-only wave へ切るわけではありません。coding / implementation / patch work が scope にある task では、implementation critical path を固定してから、並行可能な独立検証だけを Spark read-only role へ切ります。文書 flow、requirements / plan の bounded check、report traceability、research perspective checklist は、write-capable handoff を置き換えない範囲で mini review wave に切ります。
- user が coding / implementation / patch work の subagent 委譲を明示した task では、Spark read-only wave は write-capable handoff の準備です。実装可能な scope が固定された後は、`spark_worker` eligible なら `spark_worker`、それ以外は `worker` を起動または schedule し、read-only role だけで完了扱いにしません。
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

- human routing and inventory canon: `agents/`
- permanent team ownership and write policy: `agents/agents_config.json`
- skill shim: `.agents/skills/`
- Codex project config: `.codex/config.toml`
- Codex subagent definitions: `.codex/agents/*.toml`

設定運用メモ:
- role ownership や required output を変えるときは `agents/agents_config.json` を更新します
- project subagent registration と runtime budget を変えるときは `.codex/config.toml` を更新し、role model / reasoning を変えるときは `.codex/agents/*.toml` を更新します
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
- `.codex/agents/*.toml` が role ごとの model / reasoning 設定を持っている
- temporary run bundle を task ごとと full-team で作り、required output が実際に生成される
- `agents/agents_config.json` に perspective reviewers と artifact mapping がある
- `agents/task_catalog.yaml` に `research_perspective_triage` default pack と optional `research_perspective_review` pack がある
- `.codex/agents/*.toml` に対応 subagent 定義がある
- temporary run bundle を作って、各 perspective review artifact と `team_manifest.yaml` が実際に生成される
