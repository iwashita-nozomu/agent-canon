<!--
@dependency-start
contract agent-runtime
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
role ごとの実行条件、handoff 条件、review separation は `.codex/agents/*.toml` を正本にします。
project-level subagent registration と runtime budget は `.codex/config.toml` の `[agents]` と `[agents.<name>]` を正本にします。
prompt、routing、subagent-config drift の監査は `prompt_config_reviewer` を先に通し、
この file は inventory と activation の入口に保ちます。

## この文書の読み方

- この文書は、Codex runtime の subagent inventory、activation、handoff、budget、role mapping を所有します。
- 前半は principles、budget、handoff context、wave plan、language / completeness / quality policy を扱い、後半は activation timing、command surface、role mapping、write safety、model settings、smoke test を扱います。
- parent agent は `## Wave Plan Contract` と `## Handoff Context Budget` を先に読み、writer / reviewer は `## Permanent Team To Codex Mapping` と `## Recommended Routing` を参照します。
- chunked reading では、実行中の wave に関係する policy 節だけを開き、role behavior の詳細は `.codex/agents/*.toml` へ戻します。

## Principles

- role behavior は docs より `.codex/agents/*.toml` を優先します
- permanent team ownership、artifact output、write policy は `agents/agents_config.json` を優先します
- subagent registration と runtime budget は `.codex/config.toml` を優先し、role model / reasoning は `.codex/agents/*.toml` を優先します
- prompt / config drift を見つけたら、親がその場で policy prose を増やす前に `prompt_config_reviewer` の監査結果を要求します
- parent agent は最終責任を持つ orchestrator / integrator です。repo-changing
  implementation / patch / doc-edit work では、親は handoff packet、agent
  起動、追加指示、統合、review / validation gate 判定に集中し、既定の
  implementer にはなりません
- routing と required review を決めてから subagent wave を起動する
- Agent Wave の標準順序は `計画 -> レビュー -> 編集` です。各 wave は
  plan artifact、review gate decision、edit handoff evidence を
  `team_manifest.yaml`、`schedule.md`、`workflow_monitoring.md` に残します。
- repo-changing task では、stage ごとに適切な subagent を explicit に立てる
- repo-changing implementation / patch / doc-edit work の既定 route は
  write-capable `spark_worker` / `worker` handoff first です。parent-direct は
  spawn authorization、tool gate、または explicit parent-direct approval がある
  場合の recorded exception としてだけ使い、`schedule.md` /
  `workflow_monitoring.md` / run bundle に理由を残します。
- 調査、レビュー、文書整備は分ける
- fan-out は active spawn budget と stage wave plan の範囲で管理する
- subagents may spawn bounded child subagents when their handoff packet includes `delegated_spawn_policy` with owner, input packet, expected output, dependency-expanded handoff scope, validation route, review gate, and remaining spawn budget
- 探索、レビュー、仕様確認の並列化を使い、write-heavy implementation は dependency order と disjoint write scope が揃った wave に限定する
- runtime の同時 spawn は `.codex/config.toml` の `max_threads` 以内に収め、role が多い task は wave に分ける
- subagent depth は `.codex/config.toml` の `agents.max_depth = 2` を正本にし、parent wave と child-subagent wave を active spawn budget 内で管理する
- 追加の subagent wave を立てるときは、parent または delegated stage owner が owner、input packet、expected output、write scope を明示する
- writer collision は current checkout 内の先行 / 後続 wave と validation rerun で解きます。branch/worktree 作成は `agents/canonical/CODEX_WORKFLOW.md` の Branch Reuse Default と PreToolUse `branch_worktree_guard.py` に従います。
- subagent handoff の input packet は role ごとに owned scope を固定し、route seed と調査結果から展開した対象 path list、context artifacts、allowed / forbidden paths を渡します。
- reviewer には対象 path list、checker summary、structured dashboard / drilldown、該当 canon 節を先に渡します。
- fresh subagent は launch ごとに `agents/COMMUNICATION_PROTOCOL.md` の `Fresh Subagent Context Capsule` を受け取ります。`context_artifacts`、`allowed_paths`、`do_not_read`、`return_contract` などの protocol-owned capsule key は同文書を正本にし、schema の定義は同文書だけに置きます。
- theorem-driven、algorithm、implementation handoff では、protocol-owned capsule に `Target Binding Packet` が必須です。packet が complete になってから spawn し、unchecked output は親が同じ public root に対して checker / validation を通した後だけ採用対象へ進みます。
- `計画レビュー` と `詳細設計レビュー` は別の subagent で行う
- `文書通読レビュー` は `詳細設計レビュー` と別の subagent で行う
- 論文 draft では `citation_evidence_reviewer` も別の subagent で行う
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` も別の subagent で行う
- `詳細設計レビュー` を、実装前でもっとも重要な gate とみなす
- 実装では既存コード、既存の命名、既存の文書スタイルの踏襲を優先する
- Codex の role ごとの model / reasoning 設定は `.codex/agents/*.toml` を正本にする
- Abstract Design Frame と approved packet で完全に切れる低リスク slice は `spark_worker` を preferred implementation candidate とする
- repo inventory、tool drift survey、static validation planning、diff-local review、機械 report の要約は、implementation の critical path を塞がない独立検証としてだけ read-only role に切る。coding / implementation / patch / doc-edit work が scope にある task では、write-capable handoff を既定 route として説明する。surface route seed、responsibility search、reuse survey、stale-surface scan、dependency expansion、validation plan、tool-rejection preflight から handoff packet が揃い次第、write-capable `spark_worker` / `worker` handoff を schedule し、parent は handoff packet、統合順序、review gate、最終責任に集中する
- user が coding / implementation / patch / doc-edit work を求めた task では、read-only wave は setup evidence です。requirements、surface route seed、responsibility search、reuse survey、stale-surface scan、dependency expansion、validation plan、tool-rejection preflight から handoff scope を作ったら、`spark_worker` / `worker` を起動または schedule します。parent-direct completion は既定 route ではなく、blocked subagent route または explicit approval を記録した例外です。
- 分割境界は差し替え可能性で判断します。別実装、別証明、別 validation oracle、別 review decision に置き換えられる単位なら worker scope にできます。数理的に差し替えが起きない境界、記法だけの境界、固定 context、同じ oracle を共有する連続導出は、過剰な subagent 分割を避けて同じ input packet に残します。
- `spark_worker` が runtime capacity または compatibility で起動できない場合は、同じ packet を `worker` に渡して実装 route を継続する
- 設計・scope 判断、曖昧な実装判断、multi-surface conflict resolution、ship decision は frontier role TOML に残す
- plan mode や permissions のような mode は session 単位の設定として parent session 側で切り替える

## Activation Budget

- runtime hard ceiling は [.codex/config.toml](../../.codex/config.toml) の `[agents].max_threads` を正本にし、現在は `24` です
- `.codex/config.toml` の `[agents].max_depth` は `2` を正本にし、one bounded child-subagent layer を許可します
- cap は同時実行数の上限として扱います
- `.codex/config.toml` の `[agents]` は budget と runtime timeout の設定であり、subagent spawn 許可は上位 runtime / developer instruction に従います
- active runtime が explicit user request を spawn 条件にする場合、parent は handoff plan と artifact packet を作って `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` を記録し、authorization が揃った時点で spawn します
- active な subagent 数は spawn budget で縛ります
- spawn budget は同時 active 数の上限です。parent は Intake Responsibility Wave で requirements / exploration / execution planning を分け、以後の stage wave を workflow family の budget 内で追加します。独立 workstream が複数ある場合は、workstream ごとの stage owner が vertical dynamic wave を起こします
- Wave は frontier-driven adaptive loop です。parent は checker / graph / review
  output から次 frontier queue を作り、必要な subagent を適応的に追加し、結果を
  integrate して同じ validation を再実行します。frontier が
  `verified`、`refuted`、`unprovable_under_assumptions`、または checked external
  boundary に縮約された時点で closeout 条件を満たします。
- multi-agent family で予定 stage wave を絞る場合は、rate limit、blocked role、irrelevant role、または parent-direct exception rationale を `schedule.md` / `workflow_monitoring.md` に残します
- `role` は subagent type / behavior contract であり、実行単位は `role_type+instance_id` です。同じ role を複数起動する場合は、各 instance に distinct `input_packet`、`allowed_paths` / `do_not_read`、`expected_output`、`validation_route`、`review_gate` を与えます。read-only role は review focus や input packet が分離される場合に同一 wave で複数起動できます。write-capable role は disjoint write scope と parent integration order がある場合だけ同一 wave で複数起動できます。
- role topology と same-role instance policy は `agents/task_catalog.yaml` の `workflow_families[].role_topology` を source にし、`team_manifest.yaml` の `run.spawn_wave_recommendation.role_topology` に mirror します。`.codex/config.toml` の `max_threads` は runtime cap として扱います。
- 既定 budget は `Owner-Bounded Change` で同時 4 体までです
- 既定 budget は `Scoped Change` で同時 8 体までです
- 既定 budget は `Large Delivery` / `Platform And Environment` で同時 10 体までです
- 既定 budget は `Research-Driven Change` / `Comprehensive Development` / `Adaptive Improvement Loop` で同時 12 体までです
- budget 超過は例外扱いにし、parent が owner、理由、input packet、expected output、write scope、review gate を `schedule.md` と `work_log.md` に残します
- write-capable subagent instance は既定 1 体から始めます。複数 writer は dependency order、wave plan、disjoint write scope、integration order、review gate を明示してから同一 wave に置きます。衝突する target は順序制約として先行 / 後続 wave に分け、同じ file / canonical surface / shared root contract から分離できる複数 writer instance を同一 wave で並列化できます。同じ `spark_worker` や `worker` role を複数起動する場合も、instance ごとの `role_type+instance_id` と disjoint write scope を必須にします。
- current checkout 内の wave plan で安全に分離できる writer は同一 wave、分離に追加判断が要る writer は後続 wave に直列化します
- parent は requirements / planning / design / review / implementation を wave で切り替えます
- delegated stage owner が child subagents を起動する場合も、active spawn budget、max write budget、fresh lifecycle policy、current-checkout write-scope policy を継承します
- role 数が budget を超える review pack は batch に分け、前段の output を parent が束ねて次 batch へ渡します
- running 中の write-capable subagent の write scope が parent の次作業または後続 writer と重なる場合、parent は close より同期を優先します。同期では `wait_agent`、workspace 上の成果物確認、または interrupt による現状報告で、完了済み変更、未完了点、判断理由を回収します。同期できた場合は、その成果を統合し、parent または後続 subagent の作業境界を更新してから作業を続けます。同期不能、長時間停止、または scope 変更で役割が終了した場合だけ、理由と回収済み evidence を `schedule.md`、`workflow_monitoring.md`、または `work_log.md` に残して close します。
- parent は stage gate を通過したら完了した instance を閉じます
- 新規 user request では新しい run bundle と fresh subagent を起こします
- 前 task の文脈は run bundle と artifact path で渡し、新規 task は fresh subagent で開始します
- 作業中の user 追加指示は、parent が `same_active_task_delta`、`scope_or_contract_change`、`new_task` に分類してから処理します。`same_active_task_delta` は `python3 tools/agent_tools/workflow_monitor.py --mid-task-user-input ...` で現在の run bundle、`schedule.md` Agent Wave Ledger、`workflow_monitoring.md` に checkpoint と updated packet path を追記し、unchanged role scope がある場合に run-local active subagent へ `send_input` できます。scope、allowed paths、review gate、または owner が変わる場合は fresh follow-up wave を起こします。`new_task` は fresh run-local subagent と新しい run bundle に切り替えます。
- `team_manifest.yaml` の `run.subagent_lifecycle_policy` を subagent handoff prompt に含め、`fresh_subagents_required: true` と `reuse_for_new_task: forbidden` を実行時の機械契約にします
- closeout 前に run-local subagent を閉じ、`closeout_gate.md` の `subagents_closed=yes` と `Subagent Lifecycle Evidence` を user-facing completion の readiness evidence にします

## Handoff Context Contract

Subagent の context は correctness gate です。parent は handoff prompt ごとに次を run bundle evidence から導出します。

- `role_scope`: その role が判断する subdomain、stage、risk class。
- `allowed_paths`: 対象 file / directory / glob の bounded list。repo root や `/workspace` は workspace identity として扱い、編集候補、検索 hit、checker finding、changed path を seed にし、responsibility search、reuse survey、stale-surface scan、dependency header graph の再帰展開結果である `dependency_edit_scope.txt` / `dependency_graph.tsv` を優先します。
- `required_artifacts`: checker output、structured dashboard、dependency-expanded scope、design / implementation packet、または review packet。context artifact を先に渡します。dependency-expanded scope が必要な場合は `bash tools/agent_tools/run_repo_dependency_review.sh --report-dir <run-or-review-dir> --search-hits-file <hits>` または changed-path 相当の dependency review output を handoff に含めます。
- `canon_refs`: 必要な AgentCanon / project canon の節。
- `do_not_read`: unrelated modules、generated raw logs、historical reports、他 role の scope など、読まない surface。
- `expected_output`: findings schema、decision vocabulary、uncertainty / residual risk、test gaps。
- `implementation_surface_route`: implementation handoff では `PRIMARY_PATHS` を `allowed_paths` の seed、`FORBIDDEN_PATHS` を `do_not_read` の seed にします。router が unavailable なら、その blocker または deterministic fallback output を渡し、path selection を packet output に基づけます。
- `tool_route`: `run.repo_tool_routing_policy` への参照。
- `tool_commands`: 選択済み skill ごとの `show_skill_packet`、`required_commands`、
  `task_matching_conditional_commands`、`validation_commands`。
- `tool_evidence`: `dynamic_skill_routing` の候補、`tool_catalog_matches`、実行済み
  tool packet の結果。
- `tool_reuse_ledger` と `pre_edit_rejection_prediction`: write-capable `spark_worker` / `worker` には、既存 tool を使うか拒否した理由と `tool_rejection_preflight.py` の結果または pending blocker を渡します。

role 分割が妥当でも、coverage map なしに広い `requested_scope` を狭い input packet へ潰す場合は routing defect として扱います。例えば数値 algorithm review は `scientific_computing_reviewer` を subdomain 別に分けてもよいですが、parent は全体の `requested_scope` を持ち続け、各 agent には solver / optimizer / functional などの担当 path list、contract-check summary、`covered_surfaces`、`deferred_surfaces`、`omitted_surfaces` を渡します。Python API / typing review は `python_reviewer` に分け、数学 canon は担当 work packet に必要な節と、外した canon 節の理由を添えます。

## Validation Failure Response Handoff Contract

Handoff packets that include validation, review repair, or closeout authority
must carry the validation-failure-response contract. After any validation
test/check failure, prohibited actions are simplifying, reverting, deleting
intended behavior/tests, weakening the oracle, or downscoping required
validation just to pass. The packet records `failing_contract`, `observation_level`,
`cause_classification`, `intent_preservation`, and `evidence` before
implementation intent changes.

The canonical token-safe `cause_classification` and `intent_preservation` slug
lists are owned by `documents/runtime-profiles-and-check-matrix.json` and
projected into `documents/runtime-profiles-and-check-matrix.md`. This section is
only the subagent handoff projection: handoffs must carry those five fields and
must cite the runtime profile taxonomy rather than defining a separate slug
list. Implementation bugs, test-oracle/spec mismatches, fixture or environment
issues, stale generated artifacts, unrelated failures, and approved-design /
user-request conflicts follow the owner routes named by the runtime profile
taxonomy.

## Wave Plan Contract

Every subagent wave must be recorded with the same structured contract across
`team_manifest.yaml`, `schedule.md`, `workflow_monitoring.md`, and
`closeout_gate.md`: `wave_id`, `owner`, `spawn_authority`,
`spawned_roles`, `role_instances`,
`spawn_budget.active_subagents`, `spawn_budget.max_write_subagents`,
`runtime_max_threads`, `runtime_max_depth`, `allowed_paths`, `do_not_read`,
`write_scope`, `validation_route`, `review_gate`, and `handoff_artifacts`.
`spawned_roles` is the legacy aggregate for dashboards. `role_instances`
is the deterministic same-role identity ledger; each entry uses
`role_type:instance_id:input_packet`, and repeated `role_type` entries must
have distinct `instance_id` and bounded packet/scope evidence.
The standard wave sequence is `plan`, `review`, `edit`. `team_manifest.yaml`
records this as `run.standard_wave_sequence`; each dynamic wave points back to
that sequence with `standard_sequence_ref`. The plan artifact records owner,
input packet, route seed, validation route, and next gate. The review gate
checks the route seed against responsibility search, reuse survey, stale-surface
scan, and dependency expansion. The edit handoff starts from that
dependency-expanded packet and bounded write scope.
Mid-task expansion uses the same contract as the standard path.
When work can be split into independent workstreams, record the dependency
edge and stage owner for each vertical dynamic wave instead of flattening all
roles into one parent-owned wave. Sibling workstreams may run in the same
runtime budget only when their input packets, write scopes, validation routes,
and review gates are disjoint, and when each workstream has a replaceable output
unit. An independent wave boundary changes the implementation, proof, oracle, or
review decision; other material stays in the same packet to prevent
over-splitting. Colliding workstreams become ordered waves.
`task_start.py` and `bootstrap_agent_run.py` emit
`RECOMMENDED_INITIAL_SUBAGENT_WAVE` and `RECOMMENDED_DYNAMIC_EXPANSION_WAVES`;
these values are executable Codex `agent_type` lists for the parent to pass to
the runtime spawn tool. After a parent or delegated stage owner actually
spawns, skips, or replaces a wave, record the actual result with
`python3 tools/agent_tools/workflow_monitor.py --subagent-wave ...`; this
updates `schedule.md` and `workflow_monitoring.md` by `wave_id` and replaces the
bootstrap authority blocker for `WAVE-1`. Delegated child waves must include
`remaining_spawn_budget` so nested launch remains bounded by
`run.delegated_spawn_policy`.

## ユーザー向け言語ポリシー

repo-changing run は `team_manifest.yaml` に
`run.user_facing_language_policy` を持ちます。人間が読む作業更新、最終報告、
レビュー要約、handoff guidance、reader-facing docs は日本語で書きます。
機械可読の key、command、path、role id、schema は正本表記を保ちます。

`task_start.py` と `bootstrap_agent_run.py` は
`USER_FACING_LANGUAGE=ja`、`USER_FACING_LANGUAGE_SOURCE`、
`USER_FACING_LANGUAGE_SCOPE`、`USER_FACING_MACHINE_FIELDS` を起動時 evidence
として出します。handoff packet は `run.user_facing_language_policy` を参照し、
subagent と reviewer へ同じ言語方針を渡します。

## 契約完全実装ポリシー

repo-changing run は `team_manifest.yaml` に
`run.contract_complete_implementation_policy` を持ちます。実装 behavior は
request clauses、acceptance contract、`Implementation Source Packet`、
`Design-To-Implementation Trace`、dependency-expanded scope、validation route、
review gate から導きます。

見た目の広さ、`Owner-Bounded Change`、MVP、thin slice は暫定的な routing、
wave、validation profile の signal に留めます。owner boundary や impact surface が
違うと分かった時点で route を更新します。contract gap、責務境界、API shape、
依存方向、runtime contract の不足が見えた場合は `design_issue_blocker` として
Gate 5-6 に戻します。

`task_start.py` と `bootstrap_agent_run.py` は
`IMPLEMENTATION_COMPLETENESS_POLICY=contract_complete`、
`IMPLEMENTATION_COMPLETENESS_SCOPE_BASIS`、
`IMPLEMENTATION_COMPLETENESS_REQUIRED_INPUTS`、
`IMPLEMENTATION_COMPLETENESS_ROUTE_SIGNALS`、
`IMPLEMENTATION_COMPLETENESS_ESCALATION` を起動時 evidence として出します。
handoff packet は `run.contract_complete_implementation_policy` を参照し、parent、
worker、reviewer が同じ completion basis を共有します。

## Handoff 前スコープポリシー

repo-changing run は `team_manifest.yaml` に
`run.pre_handoff_scope_policy` を持ちます。この policy は scope discovery を
`surface_route_seed`、`responsibility_search`、`reuse_survey`、
`stale_surface_scan`、`dependency_expansion`、`handoff_scope` の順に並べた
packet flow として扱います。

implementation surface router、検索結果、checker finding、変更済み path は
seed です。responsibility search、reuse survey、stale-surface scan、
dependency expansion の handoff evidence が揃った後で、`allowed_paths`、
`do_not_read`、`write_scope`、`validation_route`、`review_gate` へ写します。
`task_start.py` と `bootstrap_agent_run.py` は
`PRE_HANDOFF_SCOPE_POLICY=discovery_before_handoff_scope` と
`PRE_HANDOFF_SCOPE_STATUS=seed_then_expand_before_handoff` を起動時 evidence
として出します。

## Quality Check 既定ポリシー

repo-changing Agent Wave run は `team_manifest.yaml` に
`run.default_quality_check_policy` を持ちます。この policy は
`run.standard_wave_sequence` を参照し、active な quality-check role と対応する
Codex `agent_type` を `agents/agents_config.json` から展開します。provenance は
task-default specialists、changed-path language reviewers、manual enables、
default review packs から記録します。

既定の quality-check role は、選択済み workflow family と task で active な場合の
`test_designer`、`change_reviewer`、`docs_workflow_steward`、
`python_reviewer`、`cpp_reviewer` です。`change_reviewer` は
`agents/agents_config.json` にある diff-local reviewer set へ展開され、
該当 role が active な場合は `diff_triage_reviewer` も含みます。review と edit
handoff packet は `run.default_quality_check_policy` を含め、parent wave と
delegated child wave が同じ quality-check route を参照します。

`task_start.py` と `bootstrap_agent_run.py` は
`DEFAULT_QUALITY_CHECKS=enabled`、`DEFAULT_QUALITY_CHECK_ROLES`、
`DEFAULT_QUALITY_CHECK_AGENT_TYPES`、provenance lines を出します。これらの
stdout line は、implementation handoff 前に既定の quality-check route を選択した
起動時 evidence です。

## Subagent Return Investigation

`wait_agent` timeout, empty wait status, or an absent final response at a wave
decision point is a subagent lifecycle signal. The parent records
`subagent_no_return_investigation` before choosing the next action for that
run-local agent.

The investigation record includes `agent_id`, `wave_id`, wait command and
timeout, last known status, last workflow-monitor event, runtime / tool error,
log or dashboard pointers, cause hypothesis, and the selected resolution
decision. Valid resolution decisions are `continue_wait`,
`status_probe_same_task`, `close_and_replace_fresh_wave`, and
`escalate_runtime_issue`.

`status_probe_same_task` is limited to bounded status evidence for the same
active task. Scope, owner, allowed-path, or review-gate changes move through the
fresh follow-up wave path already defined by the wave contract and lifecycle
policy.

## Intake Responsibility Wave

Intake Responsibility Wave は、repo-changing task の責務分割を要件、調査、実行計画に分ける intake wave です。独立 workstream が複数ある場合、Intake Responsibility Wave は各 workstream の責務分担 wave として扱い、以後は stage owner が必要な child wave を vertical dynamic wave として追加します。`requirements_organizer` は user-request clauses、acceptance criteria、source bucket を持ちます。`explorer` は evidence / reuse / stale-surface inventory と dependency-expanded bounded path list を持ちます。`execution_planner` は stage order、artifact routing、validation sequence、review route、Agent Wave Ledger を持ちます。parent はこの intake wave の output を統合し、workflow family の active spawn budget と `max_depth = 2` の下で次の stage wave を起動します。stage owner に child-subagent 起動を委譲する場合は、`team_manifest.yaml` の `run.delegated_spawn_policy` と Wave Plan Contract を handoff prompt に含めます。

## Skill-Level Responsibility Boundaries

Subagent role は先に evidence surface で分けます。dashboard や run
bundle が `missing_actual_waves`、大量の skipped intake roles、または同一
role の scope 混線を示す場合、parent は skill boundary を先に決め、その
boundary に沿って subagent packet を作ります。

| Evidence Surface | Owning Skill | Subagent Responsibility Split |
| --- | --- | --- |
| log archive API、structured dashboard、routing miss、selection gap、wave execution reconciliation | `agent-log-analysis` | parent が context artifact を生成し、`prompt_config_reviewer` は prompt / config drift、`docs_workflow_steward` は workflow / skill wording、`project_reviewer` は repo-wide operational risk を別 packet で見る |
| repository layout、root shared view、responsibility scope、directory README、import boundary、project `.codex` / `.agents` view と personal `~/.codex` の境界 | `structure-refactor` | `explorer` は responsibility graph と stale surface、`execution_planner` は move / validation order、write-capable agent は disjoint path mapping、document-flow reviewer は reader route を見る |
| run bundle、spawn authorization、wave ledger、handoff capsule、fresh lifecycle、same-role instance identity | `subagent-bootstrap` | parent は launch mechanics を所有し、stage owner は `role_type+instance_id`、input packet、remaining budget、validation route、review gate を持つ child wave だけを起こす |

Skill を連鎖させる場合は、前 skill が作った context artifact、handoff
packet、または structure contract を次 skill の input にします。境界は
`allowed_paths`、`do_not_read`、`expected_output`、`validation_route`、
`review_gate` を含む artifact path で渡します。

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

subagent protocol feedback の必須 token セットは次です。

```text
hook_tool_feedback=reviewed
parent_protocol_update=<applied|recorded|not_required>
subagent_protocol_update=<applied|recorded|not_required>
protocol_feedback_reason=<short-reason>
```

## Pre-Goal Activation

Goal-driven repo-changing tasks prepare subagent fan-out before the final
`/goal` command when the goal intent is clear. The parent may draft the candidate
goal, and read-only roles check the draft before implementation. If the active
runtime requires explicit spawn authorization, persist the handoff packets and
spawn the roles after authorization.

Candidate pre-goal roles:

- `requirements_organizer`: derive a conservative Objective, non-goals,
  constraints, and Exit Criteria from the user request and durable repo notes.
- `explorer`: inspect repo docs, prior notes, dependency surfaces, existing
  tools, and reuse candidates that affect the goal.
- `execution_planner`: group open `GW*` rows into the next cohesive slice after
  `goal_loop.py plan` exists.
- `plan_reviewer`: verify that the candidate goal is checkable and that the
  selected slice has evidence gates and rollback boundaries.

Start with the roles needed for the current stage, keep unused roles as dynamic
wave triggers, and add them when goal evidence, dependency state, or review
separation requires them.

Activation Conditions:

- These pre-goal agents are read-only for draft checking. If the user explicitly
  requested a repo edit and the goal has already been mirrored into `goal.md`,
  the write-capable route can proceed.
- Write-capable `worker` / `spark_worker` instances start after `goal.md` is
  parseable, the Codex goal view is mirrored or queued, and the Plan-mode output
  contains evidence mapping.
- This goal readiness rule applies to goal-driven tasks. Ordinary repo-changing
  tasks with explicit implementation delegation use a run bundle, bounded
  `allowed_paths`, write scope, validation plan, and tool-rejection preflight
  before `spark_worker` / `worker`.
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
| `implementer` | `spark_worker` preferred for bounded slices derived from the Abstract Design Frame and design trace; `worker` alternate route for broad or ambiguous implementation |
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
| Legacy label `critical_guardian` | Historical lookup label; active routing and inventory use `project_reviewer` |

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
  - reuse-prioritized の detailed design 文書、Design Side-Effect Map、identifier naming plan を起こす
- `detailed_design_reviewer`
  - 実装前の最重要 gate として設計文書、Design Side-Effect Map、identifier naming plan を独立に確認する
- `document_flow_reviewer`
  - 文書を上から順に読み、用語導入、section 順序、reader-facing side effect、reader path が自然かを確認する
- `citation_evidence_reviewer`
  - 論文主張が citation、figure、table、derivation、appendix、result に辿れるかを確認する
- `notation_definition_reviewer`
  - 記号、略語、technical term、unit、index、assumption の definition-before-use と一貫性を確認する
- `logic_gap_reviewer`
  - claim-to-evidence のつながり、hidden assumption、result と interpretation の飛躍を確認する
- `long_form_writer`
  - README、workflow、guide、migration、specification など file responsibility が一般説明 prose の文書を、graph/DSL closure 後に roadmap-led で prose projection する
- `test_designer`
  - approved design と既存 code path を静的解析し、nasty case と regression case の test plan を起こす
- `diff_triage_reviewer`
  - 狭い diff の triage review を境界証拠付きで行い、language-specific reviewer または broad `reviewer` へ上げるかを決める
- `ship_reviewer`
  - user request clause、Abstract Design Frame、Design Side-Effect Map、approved packet、product diff、validation、dependency review、closeout artifact を照合する最終出荷 gate を担当する
- `explorer`
  - 読み取り専用で codebase / docs / workflow の調査を行う
- `reviewer`
  - 読み取り専用で diff と risk を findings-led で洗う
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
| 詳細設計 | `detailed_designer`。既存 code path 調査が要るなら `explorer` を補助に使う。主要設計判断の downstream surface は Design Side-Effect Map に落とす |
| 詳細設計レビュー | 専用の `detailed_design_reviewer` instance。Design Side-Effect Map が実装者へ渡せる粒度か確認する |
| 一般説明 prose projection | `long_form_writer`。README、workflow、guide、migration、specification など file responsibility が一般説明 prose の文書では `long-form-writing` を DSL-to-prose adapter として使う |
| 学術文章起草 | `long_form_writer`。論文、thesis chapter、scholarly note では `academic-writing` を前提に draft する |
| 論文 draft 起草 | `long_form_writer`。投稿論文や thesis chapter では `paper-writing` を前提に draft する |
| 文書通読レビュー | 専用の `document_flow_reviewer` instance。詳細設計、README、workflow、reader-facing doc を上から順に読んで意味が通るかを見て、reader-facing side effect が reader path に現れているか確認する |
| citation / evidence trace review | 専用の `citation_evidence_reviewer` instance。paper claim が citation、figure、table、appendix、result に辿れるかを見る |
| テストケース設計 | 専用の `test_designer` instance。approved design と既存 code path を静的解析し、最も意地の悪い edge case と regression case を test plan に落とす |
| 記号定義レビュー | 専用の `notation_definition_reviewer` instance。記号、略語、technical term、unit、index、assumption の定義順と一貫性を見る |
| 論理接続レビュー | 専用の `logic_gap_reviewer` instance。主張の飛躍、隠れた仮定、result と interpretation の境界を見る |
| report / claim-heavy narrative review | 専用の `report_reviewer` instance。evidence traceability、overclaim、reader-facing report quality を見る |
| OOP readability report documentation | 専用の `oop_readability_reviewer` instance。機械判定 report の status / count / path / line を保持し、tool fact と reviewer judgment を分けて OOP 原則別に文書化する |
| 実装 | `IMPLEMENTATION_CODEX_AGENTS` を確認し、Abstract Design Frame から導かれ、design trace、naming、validation、dependency-expanded handoff scope が揃った slice は `spark_worker`、broad / ambiguous slice は `worker` |
| 低リスク実装slice | Abstract Design Frame から導かれ、design trace、naming、validation、dependency-expanded handoff scope が揃った slice だけを `spark_worker` preferred |
| 実装後レビュー | `reviewer`、`python_reviewer`、必要に応じて `cpp_reviewer`。Design Side-Effect Map から外れた side effect は設計差分として扱う |
| 包括的開発の統合レビュー | `project_reviewer`、`docs_workflow_steward`、prompt/config surface がある場合は `prompt_config_reviewer`、`python_reviewer`、必要に応じて `cpp_reviewer` を intake / wrap-up の固定 stack として使う |

運用ルール:
- role ごとの詳細な実行制約は `.codex/agents/*.toml` を見ます
- この文書では route と inventory だけを決め、各 role の詳細条件は `.codex/agents/*.toml` に集約します
- parent は stage を暗黙にまとめず、別 role を別 instance で起動します
- subagent を起動するときは、`team_manifest.yaml` の `run.subagent_prompt_packet`、該当 role の `prompt_contract`、`document_packet.read_before_work`、または `task_start.py` / `bootstrap_agent_run.py` の packet 出力を local/tool context として参照します。prompt へは `agents/COMMUNICATION_PROTOCOL.md` が定義する `Fresh Subagent Context Capsule` を渡し、packet stdout や full artifact は貼りません
- context が増えたら capsule artifact を更新して再配送します
- workflow family ごとの prompt 正本は `agents/task_catalog.yaml` の `workflow_families[].subagent_prompt` です
- 一般説明 prose adapter を使う文書では `document_flow_reviewer` に加えて別 reviewer で `docs-completeness-review` を通します
- 学術文章では `document_flow_reviewer` に加えて `notation_definition_reviewer`、`logic_gap_reviewer`、別 reviewer の `docs-completeness-review` を通します
- 論文 draft では `citation_evidence_reviewer` も追加します
- research-driven change では `report_reviewer` と perspective reviewers を default にします

## Parallel Write Safety

- parent が `team_manifest.yaml` の write policy と handoff で writer ごとの allowed path / directory を管理します
- 同一 path、同一 directory ownership、同一 public API surface は順序制約つきの writer に割り当てます
- 同一 worktree の write-capable subagent instance は既定 1 人から始めますが、parent が dependency order、wave plan、dependency-expanded disjoint write scope、integration order、review gate を handoff packet に載せた場合は同じ role type を含む複数 writer instance を同一 wave で使えます
- same directory / same file / same canonical surface を同時に触る writer は先行 / 後続 wave に分けます
- 衝突する target は順序制約として扱い、先行 wave の validation と tool rerun 後に後続 wave で統合します
- writer は current checkout 内の wave plan で分離し、追加判断が要る writer は後続 wave へ直列化します
- review role は常に read-only とし、parent-managed write-scope discipline と writer-instance separation の確認は `plan_reviewer` と `project_reviewer` の固定責務です

## Codex Model Settings

`.codex/agents/*.toml` は Codex runtime が読む materialized role 定義です。
role の `model` / `model_reasoning_effort` は各 agent TOML が正本です。
`.codex/config.toml` は project feature、runtime cap、MCP、skill、agent registry
を持ち、role model / reasoning は agent TOML に集約します。

role の model / reasoning を変更するときは、該当 `.codex/agents/*.toml`
を更新し、`tools/agent_tools/check_agent_runtime_alignment.py` と
`tools/agent_tools/evaluate_codex_agent_roles.py` で検証します。Python checker、
workflow docs、task catalog は agent TOML を参照します。

運用メモ:
- OpenAI / Codex の current product evidence は `$openai-docs` で確認します。
  この文書は product-evidence route を示します。
- この repo では、repo inventory、tool drift survey、machine-report summarization、execution-only experiment / log work を mini helper role TOML に残します。設計判断・広域 synthesis・学術主張の精査・final judgment、broad / ambiguous implementation、static validation triage、diff-local language review、bounded review、report traceability、checklist / quality-check gate は frontier role TOML に寄せ、Abstract Design Frame から導かれた設計済み低リスク実装 slice は `spark_worker` に寄せます。
- repo default の reasoning は non-review role では `high` にし、review / quality-check role TOML は `xhigh` を既定にします
- planning session の mode は official Codex CLI なら `/plan`、model / reasoning の切替は `/model`、approval preset は `/permissions` を使います
- 極端に狭く、待ち時間が支配的な implementation loop では、`worker` ではなく `spark_worker` を preferred candidate とします
- review / quality-check role TOML は frontier model と `xhigh` reasoning を使い、final judgment や scope を変える設計判断も frontier review route に残します
- Spark model は `spark_worker` の低遅延 implementation loop に集約し、repo inventory、tool drift survey、machine-report / experiment-log summarization、execution-only helper work は mini helper role TOML に置きます
- `spark_worker` へ渡す条件は、Abstract Design Frame、Implementation Source Packet、Design-To-Implementation Trace、identifier naming、test plan、dependency-expanded handoff scope が揃っていることです
- 明示 spawn 許可がある repo-changing task では、coding / implementation / patch / doc-edit work の implementation critical path を pre-handoff investigation packet で作ってから、並行可能な独立検証を read-only role へ切ります。文書 flow、requirements / plan の bounded check、report traceability、research perspective checklist は、write-capable handoff を支える frontier review wave に切ります。
- coding / implementation / patch / doc-edit work を求める repo-changing task では、read-only / review wave は write-capable handoff の準備です。実装可能な handoff scope が dependency expansion から出た後は、`spark_worker` eligible なら `spark_worker`、それ以外は `worker` を起動または schedule し、completion route は write-capable handoff、integration、review、validation で構成します。parent-direct は explicit exception rationale と validation evidence がある場合だけ completion route にできます。
- `spark_worker` eligible な実装は、Abstract Design Frame から導かれた差し替え可能な単位で、stable public interface、stable dependencies、fixed specification、既存 test / docs の局所更新で閉じるものです。eligibility は design trace と dependency-expanded handoff scope で判断します。
- cross-module 整合、API shape、命名 / 責務境界、依存再構成、安全性、性能、conflict resolution のいずれかが入った時点で `worker` または設計 review へ戻します
- `document_flow_reviewer` は README / workflow / guide / design doc / paper、新用語、公開 API、reader-facing docs があるときに起動します。code-only owner-bounded change では省略できます
- `reviewer` は broad diff / cross-surface / clause coverage に上げる role とし、Python-only / C++-only / bounded diff では `python_reviewer`、`cpp_reviewer`、`diff_triage_reviewer` を entry reviewer にします

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
- stage 固有の実行条件を増やすときは、この文書より先に `.codex/agents/*.toml` を更新します
- wrapper や root entrypoint は `.codex/agents/*.toml` の参照入口に保ちます

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
