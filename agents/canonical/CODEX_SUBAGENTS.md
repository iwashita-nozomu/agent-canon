<!--
@dependency-start
contract agent-runtime
responsibility Documents Codex Subagents for this repository.
upstream design ../task_catalog.yaml task routing catalog
upstream design ../agents_config.json permanent team role ownership and artifact policy
upstream design ../skills/agent-orchestration.md canonical validation trust boundary owner
upstream design ../skills/direct-luna-communication.md bounded direct Luna communication and runtime acknowledgement
upstream design ../../documents/codex/prompt-skill-evaluation-checklist.md empirical evaluation packet and report contract
upstream design ../../documents/design/request-intent-and-update-relation.md compact reuse, parallel handoff, and cleanup projection
downstream design CODEX_WORKFLOW.md workflow consumes subagent routing contract
downstream implementation ../../.codex/config.toml Codex runtime config consumes subagent routing
downstream implementation ../../.codex/agents/oop_readability_reviewer.toml OOP readability report reviewer role
@dependency-end
-->

# Codex Subagents

この文書は、Codex を primary runtime とする場合の subagent routing と inventory の正本です。
shared workflow は `agents/canonical/CODEX_WORKFLOW.md` に置き、この文書は inventory、mapping、activation に寄せます。
permanent team role ownership、required output、write policy は `agents/agents_config.json` を正本にします。
role profile/instruction authority は `agents/model_profiles.toml` と
`tools/agent/orchestration/model_profile_registry.py` が所有し、`.codex/agents/*.toml`
は closed generated readback view です。
project-level subagent registration と runtime budget は `.codex/config.toml` の `[agents]` と `[agents.<name>]` を正本にします。
prompt、routing、subagent-config drift の監査は `prompt_config_reviewer` を先に通し、
この file は inventory と activation の入口に保ちます。

## Compact request/update projection

`../../documents/design/request-intent-and-update-relation.md` の handoff flow は既存
agent context の再利用を優先し、owner/write-scope/DAG evidence が disjoint な場合だけ
必要な並列 handoff を作ります。descendant close、reservation release、terminal handback
はこの owner の既存 lifecycle evidence と `close_agent` receipt を使います。

Runtime collaboration capability and coordination receipts are owned by
`agents/COMMUNICATION_PROTOCOL.md#Runtime Collaboration Capability Handshake`.
This document only projects the route: read capability from the direct runtime
collaboration namespace, use `direct_peer` only after an `available` readback,
and use an honest `parent_relay` or `durable_artifact` path for
`unavailable`/`unverified` runtimes. Matcher names and `functions.exec` tool
inventories are not capability evidence. Child waves record the operation and
receipt reference in their handback; parent relay is never relabeled as peer
communication.

Compatibility evidence のある update operation は既存 agent context を reuse-ready state
へ更新し、active packet readback を完了 evidence にします。disjoint owner/write-scope/
dependency-order evidence のある update operation は必要な parallel handoff を
handoff-ready state へ進め、owner handoff と dependency-order readback を完了 evidence
にします。completed integration の readback は既存 cleanup receipt を dispatch-ready state
へ進め、`CleanupProof`、`G6`、terminal `close_agent` receipt を closeout evidence にします。

## この文書の読み方

- この文書は、Codex runtime の subagent inventory、activation、handoff、budget、role mapping を所有します。
- 前半は principles、budget、handoff context、wave plan、language / completeness / quality policy を扱い、後半は activation timing、command surface、role mapping、write safety、model settings、smoke test を扱います。
- parent agent は `## Wave Plan Contract` と `## Handoff Context Contract` を先に読み、writer / reviewer は `## Permanent Team To Codex Mapping` と `## Recommended Routing` を参照します。
- この文書の `parent Sol` は `.codex/config.toml` の parent projection を指し、
  child profile authority は `agents/model_profiles.toml` が所有します。
  `.codex/agents/*.toml` と `agents/agents_config.json` の profile fields は
  canonical materializer が生成する readback view です。
- chunked reading では、実行中の wave に関係する policy 節だけを開き、
  profile/instruction authority は `agents/model_profiles.toml`、生成済みの
  runtime readback は `.codex/agents/*.toml` で確認します。

## Principles

- role profile/instruction は `agents/model_profiles.toml` を優先し、
  `.codex/agents/*.toml` は generated readback として扱います
- logical role、selected Skills、execution profile、authority は別々に選びます。Luna profile は `$direct-luna-communication` の bounded packet で direct child として起動し、role-specific alias を physical team identity や capacity 根拠にしません
- permanent team ownership、artifact output、write policy は `agents/agents_config.json` を優先します
- subagent registration と runtime budget は `.codex/config.toml` を優先し、
  role model / reasoning は `agents/model_profiles.toml` を優先します
- prompt / config drift の reviewer output は hypothesis です。decision-owning
  reviewer または ship reviewer が current snapshot、reachable path、contract、
  witness/static proof を確認して adjudicate し、distinct unresolved risk の
  ときだけ specialist を追加します
- parent agent は orchestrator only です。repo-changing implementation /
  patch / doc-edit work では、親は handoff packet の選択、agent 起動、packet
  relay、依存順、status、最終外部 readback だけを担当し、調査、設計、実装、
  テスト、diff review、Issue/PR、評価、merge/conflict、validation/finding の
  判定を行いません
- routing と owner-critical な review を決めてから、必要な subagent wave
  だけを起動する
- Agent Wave の `計画 -> レビュー -> 編集` は候補 stage です。各 wave は
  選択した stage の plan artifact、review gate decision、edit handoff
  evidence だけを `team_manifest.yaml`、`schedule.md`、
  `workflow_monitoring.md` に残します。
- repo-changing task では、owner、責務、context、write authority、validation
  route が揃った launchable wave だけを立てる
- repo-changing implementation / patch / doc-edit work は、bounded request を
  含めて必ず write-capable implementer handoff first です。spawn authorization、
  tool gate、または他の launch blocker がある場合は typed blocked/retry/user-report
  packet を残し、親の直接編集へ切り替えません。
- 調査、レビュー、文書整備は分ける
- fan-out は active spawn budget と stage wave plan の範囲で管理する
- subagents may spawn bounded child subagents when their handoff packet includes `delegated_spawn_policy` with owner, input packet, expected output, dependency-expanded handoff scope, validation route, review gate, and remaining spawn budget
- 探索、レビュー、仕様確認の並列化を使い、write-heavy implementation は dependency order と disjoint write scope が揃った wave に限定する
- runtime の同時 spawn は `.codex/config.toml` の `max_threads` 以内に収め、role が多い task は wave に分ける
- subagent depth は `.codex/config.toml` の `agents.max_depth = 2` を正本にし、parent wave と child-subagent wave を active spawn budget 内で管理する
- 追加の subagent wave を立てるときは、parent または delegated stage owner が owner、input packet、expected output、write scope を明示する
- writer collision は current checkout 内の先行 / 後続 wave と validation rerun で解きます。branch/worktree 作成は `agents/canonical/CODEX_WORKFLOW.md` の Branch Reuse Default と PreToolUse `hook_safety.py` route に従います。
- subagent handoff の input packet は role ごとに owned scope を固定し、route seed と調査結果から展開した対象 path list、context artifacts、allowed / forbidden paths を渡します。
- reviewer には対象 path list、checker summary、structured dashboard / drilldown、該当 canon 節を先に渡します。
- fresh subagent は必要な launch ごとに `agents/COMMUNICATION_PROTOCOL.md`
  の `Fresh Subagent Context Capsule` を受け取ります。active agent を再利用
  できる場合は、同じ protocol-owned context を compatible な revised scope
  として更新します。`context_artifacts`、`allowed_paths`、`do_not_read`、
  `return_contract` などの capsule key は同文書を正本にし、schema の定義は
  同文書だけに置きます。
- theorem-driven、algorithm、implementation handoff では、protocol-owned capsule に `Target Binding Packet` が必須です。packet が complete になってから spawn し、unchecked output は verifier または owning reviewer が同じ public root に対して checker / validation を通した後だけ採用対象へ進みます。
- `計画レビュー`、`詳細設計レビュー`、`文書通読レビュー`、論文 draft の
  reviewer、学術文章の notation/logic reviewer は、owner-critical な
  validation または unresolved branch が選択した場合だけ起動する。必要な
  独立 review は同じ active agent に再利用せず、別の責務単位として切り出す
- 実装では既存コード、既存の命名、既存の文書スタイルの踏襲を優先する
- Codex の role ごとの model / reasoning 設定は `agents/model_profiles.toml` を正本にし、`.codex/agents/*.toml` は registry-generated view とする
- `implementer.codex_agents` は canonical model/profile registry の generated view です。implementation-executable fixed packet は Decision Sufficiency の `execute_spark` から `spark_worker` 一体を直接 materialize し、同じ packet の post-completion owning gate だけを続けます。Luna は ambiguous design、causal repair、graph-owned cross-owner integration、review を所有します。
- repo inventory、tool drift survey、static validation planning、diff-local review、機械 report の要約は、implementation の critical path を塞がない独立検証としてだけ read-only role に切る。coding / implementation / patch / doc-edit work が scope にある task では、write-capable handoff を既定 route として説明する。surface route seed、responsibility search、reuse survey、stale-surface scan、dependency expansion、validation plan、tool-rejection preflight から handoff packet が揃い次第、選択済み write-capable implementer の handoff を schedule し、parent は packet relay、依存順、status、最終 readback に集中する
- user が coding / implementation / patch / doc-edit work を求めた task では、read-only wave は setup evidence です。requirements、surface route seed、responsibility search、reuse survey、stale-surface scan、dependency expansion、validation plan、tool-rejection preflight から handoff scope を作ったら、bounded request でも write-capable implementer を起動または schedule します。親は packet relay、依存順、status、最終 readback だけを担当します。
- 分割境界は差し替え可能性で判断します。別実装、別証明、別 validation oracle、別 review decision に置き換えられる単位なら worker scope にできます。数理的に差し替えが起きない境界、記法だけの境界、固定 context、同じ oracle を共有する連続導出は、過剰な subagent 分割を避けて同じ input packet に残します。
- 固定 packet の candidate replacement は行いません。capacity/model failure は typed event として同じ immutable packet を queue し、exact target contradiction だけを一度の `StructuralDesignGap` として修復後、同じ Spark を再開します。
- 設計・scope 判断、曖昧な実装判断、multi-surface conflict resolution は
  registry-selected reasoning child または integration executor の findings と
  decision-owning reviewer の判定に分け、ship decision は ship reviewer が持つ
- plan mode や permissions のような mode は session 単位の設定として parent session 側で切り替える

## Activation Capacity Projection

- Handoff は owner-produced semantic decision-sufficiency record を消費します。
  owner、replaceable unit、implementation mechanism、validation route が明示され、
  design、path、failure semantics が固定された handoff は selected owner gate
  へ直接 route できます。追加の読み取り、packet、review、wave は次の決定を
  変える場合だけ追加します。DSV policy の意味論は
  `agents/skills/agent-orchestration.md#Decision Sufficiency Packet` だけが所有します。
- `.codex/config.toml` の `max_threads` は capacity topology の生成値を
  loader/readback した configured value です。現在は direct frontier `21` と
  nested reservation `6` から生成された `27` で、universal hard ceiling では
  ありません。
- `max_threads` は同時実行 capacity であり、総作業量を増やす許可では
  ありません。自律実行の目的関数は request completeness/correctness、minimum
  decision-relevant total work、minimum makespan の lexicographic order です。
- exact candidate digest ごとに candidate epoch を一つ持ち、initial owning review
  は一度だけ実行します。review は stable blocking finding IDs と advisory notes を
  分離し、repair 後は addressed blocker IDs と invalidated evidence だけを focused
  recheck します。
- follow-up action は decision tuple を変える typed evidence を生成するか、
  `|blocking findings| + |unresolved validation| + |unresolved request clauses|` を
  厳密に減らす場合だけ admissible です。同じ state/action fingerprint は
  `non_convergent_cycle` として停止し、新しい broad review や implementation pass を
  起動しません。
- zero blocker、zero unresolved request clause、selected validation pass または
  not_applicable は terminal ship/handoff です。その後の improvement は advisory
  または別 Issue とし、現 candidate epoch を再開しません。
- `.codex/config.toml` の `[agents].max_depth` は `2` を正本にし、one bounded child-subagent layer を許可します
- cap は同時実行数の上限として扱います
- `.codex/config.toml` の `[agents]` は budget と runtime timeout の設定であり、subagent spawn 許可は上位 runtime / developer instruction に従います
- active runtime が explicit user request を spawn 条件にする場合、parent は handoff plan と artifact packet を作って `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` を記録し、authorization が揃った時点で spawn します
- active な subagent 数は spawn budget で縛ります
- spawn budget は同時 active 数の上限です。Intake Responsibility Wave は active role set と catalog の `intake` stage から materialize し、`explorer` と `execution_planner` は evidence-gated dynamic wave として追加します。独立 workstream が複数ある場合は、workstream ごとの stage owner が vertical dynamic wave を起こします
- 独立 source workstream を選択する parent packet は、各 stream の substantial replaceable responsibility unit、`repository-topic-clone` typed route、disjoint write scope、dependency/merge order、validation route、reviewer ownership を固定します。generic prepare は exact clone/branch を再利用し、無い branch を最新 `origin/main` から作成します。dependency などの specialized skill は prepare 後の decorator であり、前提不一致は generic operation を止めません。ready な非衝突 stream は全て launch し、parent / delegated stage owner は全 descendants を monitor します。
- canonical lifecycle の owner evidence と computed identity が揃った repo-local
  `workspace/<topic-slug>/<repo-name>` prepare/reuse/use は operation-level の追加承認を
  要求しません。raw shared-checkout Git の protected mutation は従来の authority gate を
  維持します。closeout は lifecycle skill の cleanup dispatch、CAS/PR/publication/owner
  evidence の preflight、`CleanupProof` / receipt、typed hold の順で handback し、proof-free
  deletion を完了扱いにしません。
- 同じ responsibility unit の follow-up は compatible な worker context を再利用します。file-sized slice、細粒度の fresh agent、または同じ oracle を共有する断片化は parallel source workstream として起動しません。依存または衝突する stream は記録済み merge order の ordered wave にします。
- Wave は frontier-driven adaptive loop です。owning reviewer、verifier、または
  integration executor が checker / graph / review output から次 frontier queue を
  作り、必要な subagent を適応的に追加し、結果を処理して同じ validation を再実行
  します。parent は packet relay と status を管理します。frontier が
  `verified`、`refuted`、`unprovable_under_assumptions`、または checked external
  boundary に縮約された時点で closeout 条件を満たします。
- multi-agent family で予定 stage wave を絞る場合は、rate limit、blocked role、irrelevant role、または選択した coordination rationale を `schedule.md` / `workflow_monitoring.md` に残します
- `role` は permanent responsibility id であり、実行単位は `role_id+instance_id+agent_type` です。同じ role を複数起動する場合は、各 instance に distinct `input_packet`、`allowed_paths` / `do_not_read`、`expected_output`、`validation_route`、`review_gate` を与えます。read-only role は review focus や input packet が分離される場合に同一 wave で複数起動できます。write-capable role は disjoint write scope と integration executor の順序証拠がある場合だけ同一 wave で複数起動できます。
- role topology と same-role instance policy は `agents/task_catalog.yaml` の `workflow_families[].role_topology` を source にし、`team_manifest.yaml` の `run.spawn_wave_recommendation.role_topology` に mirror します。`.codex/config.toml` の `max_threads` は topology-derived requested/configured readback であり、platform-effective / current-available capacity は handshake の別入力です。
- workflow demand、write-cap、nested reservation、available capacity は
  [capacity handshake](#capacity-and-lifecycle) の generated projection です。
  固定 active/write 数、task-size/count/time budget、または disposable probe は
  認可根拠になりません。saturation は同じ immutable packet を queue します。
- `Skill Evaluation` は evaluator-only の同時 active 1 体、write-capable
  1 体上限です。評価 role 自体は read-only です
- budget 超過は例外扱いにし、parent が owner、理由、input packet、expected output、write scope、review gate を `schedule.md` と `work_log.md` に残します
- write-capable subagent instance は既定 1 体から始めます。複数 writer は dependency order、wave plan、disjoint write scope、integration order、review gate を明示してから同一 wave に置きます。衝突する target は順序制約として先行 / 後続 wave に分け、同じ file / canonical surface / shared root contract から分離できる複数 writer instance を同一 wave で並列化できます。同じ `spark_worker` や `worker` role を複数起動する場合も、instance ごとの `role_id+instance_id+agent_type` と disjoint write scope を必須にします。
- current checkout 内の wave plan で安全に分離できる writer は同一 wave、分離に追加判断が要る writer は後続 wave に直列化します
- parent は owner-critical な requirements / planning / design / review / implementation stage だけを選択して切り替えます。固定 plan-review-edit sequence はありません
- delegated stage owner が child subagents を起動する場合も、active spawn budget、max write budget、fresh lifecycle policy、current-checkout write-scope policy を継承します
- activated review role 数が budget を超える場合だけ batch に分け、前段の output を parent が束ねて次 batch へ渡します。candidate pack は materialize しません
- running 中の write-capable subagent の write scope が parent の次作業または後続 writer と重なる場合、parent は同期を優先します。同期では `wait_agent`、workspace 上の成果物確認、または `interrupt=false` の status request で、完了済み変更、未完了点、判断理由を回収します。timeout、empty status、final response 未着は `resolution_decision=await_new_state|continue_disjoint_parent_work` と `termination_action=preserve_running_instance` に写像します。parent は status と回収済み evidence を記録して control を戻します。同種の wait を続けるには new state evidence または explicit revised packet を必須にします。scope 変更後も非終端 subagent の write scope は保持し、`overlapping_writer=blocked` とします。`close_agent` の authority は runtime status `completed|errored|shutdown` または user の明示取消です。
- parent は stage gate を通過したら完了した instance を閉じます
- 各 user input は `same_active_task_delta`、`scope_or_contract_change`、または
  `new_task` として分類しますが、新しい turn、名前を変えた packet、または scope の
  改訂だけでは fresh agent の理由になりません。owner、responsibility、context、write
  authority、validation route が互換なら active agent を再利用し、同じ責任単位へ
  revised scope を配送します。独立 review、disjoint write authority、incompatible
  owner/context、または failed context integrity の場合だけ fresh agent / wave を
  起こします。coordination または resumption が必要な場合だけ checkpoint と updated
  packet path を durable に残し、それ以外は structured handoff message/tool result を
  使います。
- `run.subagent_lifecycle_policy` はこの判断と fresh-agent 条件を handoff prompt へ渡し
  ますが、`fresh_subagents_required: true` や `reuse_for_new_task: forbidden` を一律の
  機械契約にはしません
- 各 source/reviewer/PR/pin agent は durable handback の直後に全 descendants
  を閉じ、reservation release receipt を ledger に残します。
  `completed-but-open`、unknown descendant、reservation leak は G6 failure です。
  closeout は `DurableHandback -> descendants_closed -> reservations_released ->
  CleanupProof -> G6 -> terminal CloseAgentToolCall` の machine sequence を受理し、
  terminal CloseAgentToolCall を唯一の close operation とします。
  非終端の no-return instance は `termination_action=preserve_running_instance`
  として terminal token materialization を block します。

## Handoff Context Contract

Subagent の context は correctness gate です。parent は handoff prompt ごとに次を
structured handoff または、coordination/resumption が必要な場合の durable evidence
から導出します。

- `role_scope`: その role が判断する subdomain、stage、risk class。
- `allowed_paths`: 対象 file / directory / glob の bounded list。repo root や `/workspace` は workspace identity として扱い、編集候補、検索 hit、checker finding、changed path を seed にし、responsibility search、reuse survey、stale-surface scan、dependency header graph の再帰展開結果である `dependency_edit_scope.txt` / `dependency_graph.tsv` を優先します。
- `required_artifacts`: checker output、structured dashboard、dependency-expanded scope、design / implementation packet、または review packet。context artifact を先に渡します。dependency-expanded scope が必要な場合は `bash tools/analysis/dependencies/run_repo_dependency_review.sh --report-dir <run-or-review-dir> --search-hits-file <hits>` または changed-path 相当の dependency review output を handoff に含めます。
- `canon_refs`: 必要な AgentCanon / project canon の節。
- `do_not_read`: unrelated modules、generated raw logs、historical reports、他 role の scope など、読まない surface。
- `expected_output`: findings schema、decision vocabulary、uncertainty / residual risk、test gaps。
- `conflict_or_rework_packet`: merge conflict resolution または validation
  finding の repair を行う handoff は、repository-qualified base/head/merge-base、
  affected path、base/ours/theirs の immutable blob reference と hunk inventory、
  staged/unmerged state、unaffected user/unknown content、selected cause、expected
  mechanism、exact owning edit delta、disposition (`keep`/`replace`/`manual`)、
  rationale、focused preservation readback を含めます。preserved changed/context
  lines は captured source hunk から導出し、caller-supplied content は許可しません。
  path list や clean merge だけでは十分な handoff としません。
- `implementation_surface_route`: implementation handoff では `PRIMARY_PATHS` を `allowed_paths` の seed、`FORBIDDEN_PATHS` を `do_not_read` の seed にします。router が unavailable なら、その blocker または deterministic router recovery output を local provisional route evidence として渡し、path selection を packet output に基づけます。
- `decision_sufficiency_packet_ref`: coordination/resumption が必要な場合だけ使う
  durable decision-sufficiency record の参照。意味上は owner、replaceable unit、
  implementation mechanism、validation route、そこに影響する unresolved branch を
  handoff に含めます。`H`、digest、count、固定 envelope は実行の必須条件ではありません。
- `tool_route`: `run.repo_tool_routing_policy` への参照。
- `tool_call_tokens`: 選択済み skill 専属 tool の canonical `tool_id`、argument
  schema、typed arguments、intent、typed failure semantics を持つ machine token。
  machine token のまま実行し、typed failure semantics を保持します。
- `tool_evidence`: `dynamic_skill_routing` の候補、`tool_catalog_matches`、実行済み
  tool packet の結果。
- `tool_reuse_ledger` と `pre_edit_rejection_prediction`: selected write-capable implementer には、既存 tool を使うか拒否した理由と `tool_rejection_preflight.py` の結果または pending blocker を渡します。

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
lists are owned by `documents/runtime/runtime-profiles-and-check-matrix.json` and
projected into `documents/runtime/runtime-profiles-and-check-matrix.md`. This section is
only the subagent handoff projection: handoffs must carry those five fields and
must cite the runtime profile taxonomy rather than defining a separate slug
list. Implementation bugs, test-oracle/spec mismatches, fixture or environment
issues, stale generated artifacts, unrelated failures, and approved-design /
user-request conflicts follow the owner routes named by the runtime profile
taxonomy.

For conflict/rework handoffs, the integration executor or repair worker must
preserve the packet's unaffected paths and hunks. Whole-file checkout, reset,
reclone, overwrite, or regeneration is not a resolution shortcut: it requires
the captured stage/hunk inventory and an explicit reconstruction map. A failed
preservation readback returns work to the owning path/hunk; it does not permit
deleting the candidate or reopening broad review.

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
`role_id:instance_id:agent_type`, with manifest rows also carrying the input
packet reference. Repeated `role_id` entries must have distinct `instance_id`
and bounded packet/scope evidence.
Task-catalog role families, task default specialists, review packs, changed-path
roles, and `codex_agents` entries are candidate evidence. Materialization
activates only owner-critical roles or roles selected by an unresolved branch or
validation route, and selects at most one executable
`agent_type` for one active `role_id`; the first `codex_agents` entry is the
default. A later entry is selected only when the parent packet records the
typed role-to-agent evidence through `--select-agent-type`, stdout records
`SUBAGENT_AGENT_TYPE_SELECTIONS`, and `team_manifest.yaml` records
`agent_type_selections`. A blocked candidate records local/tool evidence with
`selected_agent_type`, `write_capable_handoff_blocker`, `evidence`,
`parent_packet_ref`, and `status=blocked`; changing candidates requires a
revised parent packet and wave.
For T12 (`agent workflow tooling, AgentCanon submodule flow, or canon
rearchitecture`), `scheduler`, `schedule_reviewer`, `project_reviewer`,
`docs_workflow_steward`, and `prompt_config_reviewer` are candidate specialists;
activate only the owner-critical roles selected by the route. `researcher`, `research_reviewer`, `infra_steward`,
`infra_reviewer` and `python_reviewer` require explicit parent-packet evidence,
changed-path evidence, or an explicitly selected review pack. `test_designer`
requires an implementation handoff that records an established or repaired
owning mechanism. Launch it proactively after that handoff; its first output is
an activation decision and boundary classification. Only an unresolved oracle,
specification, regression, or failure-mode risk outside existing validation
produces test cases, and the resulting set must be logically minimal while
covering the selected contract.
`plan`, `review`, and `edit` are conditional stage candidates. When selected,
`team_manifest.yaml` may record `run.standard_wave_sequence` and a dynamic wave
may point to it with `standard_sequence_ref`; neither field makes an unselected
stage mandatory. A selected plan artifact records owner, input packet, route
seed, validation route, and next gate. A selected review gate checks only the
evidence that can change the route. A selected edit handoff starts from the
dependency-expanded packet and bounded write scope. Mid-task expansion uses the
same conditional contract, and a compatible active agent may receive revised
scope without a fresh wave.
When work can be split into independent workstreams, record the dependency
edge and stage owner for each vertical dynamic wave instead of flattening all
roles into one parent-owned wave. Sibling workstreams may run in the same
runtime budget only when their input packets, write scopes, validation routes,
and review gates are disjoint, and when each workstream has a replaceable output
unit. An independent wave boundary changes the implementation, proof, oracle, or
review decision; other material stays in the same packet to prevent
over-splitting. Colliding workstreams become ordered waves.
`bootstrap_agent_run.py` emit
`RECOMMENDED_INITIAL_SUBAGENT_WAVE` and `RECOMMENDED_DYNAMIC_EXPANSION_WAVES`;
`RECOMMENDED_INITIAL_SUBAGENT_WAVE` is derived from active roles in the catalog
`stage_waves` `intake` stage, not from a fixed list of registered agent types.
`RECOMMENDED_DYNAMIC_EXPANSION_WAVES` is display-only. The authoritative
bootstrap stdout field for executable dynamic expansion is
`RECOMMENDED_DYNAMIC_EXPANSION_ROLE_INSTANCES`, and
`team_manifest.yaml` `role_instances` is the authoritative manifest ledger.
After a parent or delegated stage owner actually spawns, skips, or replaces a
wave, record the actual result with
`python3 tools/runtime/lifecycle/workflow_monitor.py --subagent-wave ...`; this
updates `schedule.md` and `workflow_monitoring.md` by `wave_id` and replaces the
bootstrap authority blocker for `WAVE-1`. Delegated child waves must include
`remaining_spawn_budget` so nested launch remains bounded by
`run.delegated_spawn_policy`.

## ユーザー向け言語ポリシー

repo-changing run は `team_manifest.yaml` に
`run.user_facing_language_policy` を持ちます。人間が読む作業更新、最終報告、
レビュー要約、handoff guidance、reader-facing docs は日本語で書きます。
機械可読の key、command、path、role id、schema は正本表記を保ちます。

`bootstrap_agent_run.py` は
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

`bootstrap_agent_run.py` は
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
`bootstrap_agent_run.py` は
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
`change_reviewer`、`docs_workflow_steward`、
`python_reviewer`、`cpp_reviewer` です。`change_reviewer` が active な場合の
既定 executable は `diff_triage_reviewer` です。`python_reviewer`、
`cpp_reviewer`、`reviewer` は言語 evidence、parent packet、または review-pack
activation がある場合だけ選ばれます。review と edit handoff packet は
`run.default_quality_check_policy` を含め、parent wave と delegated child wave が
同じ quality-check route を参照します。

`bootstrap_agent_run.py` は
`DEFAULT_QUALITY_CHECKS=candidate_only`、candidate role / agent-type lines、
selected-stage provenance lines を出します。これらの stdout line は候補の
ルーティング情報であり、owner-critical decision または distinct unresolved
claim/risk が選択されるまで quality-check stage や artifact を materialize しません。

## Subagent Return Investigation

`wait_agent` timeout, empty wait status, or an absent final response at a wave
decision point is a subagent lifecycle signal. The parent records
`subagent_no_return_investigation`, returns control to the parent decision
point, and gates another wait on new state evidence or an explicit revised
packet. These signals map to `termination_action=preserve_running_instance` and
`resolution_decision=await_new_state|continue_disjoint_parent_work`.

The investigation record includes `agent_id`, `wave_id`, wait command and
timeout, last known status, last workflow-monitor event, runtime / tool error,
log or dashboard pointers, cause hypothesis, and the owner action taken after
control returns. Another wait or probe is valid only after new state evidence
arrives or the parent records an explicit revised packet. Scope, owner,
allowed-path, or review-gate changes move through the fresh follow-up wave path
already defined by the wave contract and lifecycle policy, but the prior
nonterminal agent keeps its write scope with `overlapping_writer=blocked`.
`close_agent` authority is runtime status `completed|errored|shutdown` or an
explicit user cancellation. Timeout and absent-response inference preserve the
nonterminal status.

## Intake Responsibility Wave

Intake Responsibility Wave は、責務分割または coordination が必要な
repo-changing task でだけ catalog の `stage_waves` から materialize する
候補 wave です。`WAVE-1` は owner-critical な active role set と catalog の
`intake` stage が選択された場合だけ来ます。標準 catalog の `manager`、
`requirements_organizer`、`explorer`、`execution_planner` は候補であり、
evidence / reuse / stale-surface inventory、dependency-expanded bounded path
list、stage order、artifact routing、validation sequence、review route、または
Agent Wave Ledger が次の判断を変える場合だけ起動します。独立 workstream が
複数ある場合も、必要な child wave だけを vertical dynamic wave として追加します。
stage owner または integration executor が wave の output を統合し、workflow family の
active spawn budget と `max_depth = 2` の下で次の決定へ進みます。parent は packet relay
と依存順を管理します。stage owner に child-subagent 起動を委譲する場合は、
`team_manifest.yaml` の `run.delegated_spawn_policy` と Wave Plan Contract を handoff
prompt に含めます。

## Empirical Skill Evaluation Lifecycle

`skill_evaluator` is an optional specialist with activation
`explicit_empirical_skill_evaluation`. T14 uses the catalog-owned
`skill_evaluation` family: its default active role set is only
`skill_evaluator`, and the catalog `skill_evaluation` stage materializes that
fresh evaluator as T14's initial executable instance. Worker, `spark_worker`,
and reviewer waves remain outside the default T14 topology; a parent packet
must separately enable any follow-up role. The evaluation reviewer owns scoring
and convergence and keeps the evaluator read-only and artifact-only. The
standard run bundle contains orchestration, review, verification, monitoring,
evaluation, and closeout artifacts. They are not part
of the evaluator prompt; its prompt contract references only the current
Scenario Packet, packet-listed files, `do_not_read`, and the fixed output schema.
The evaluator's `gpt-5.4-mini/medium` setting is reserved for this explicit T14
lane; no permanent team role uses that model assignment.

1. Parent Iteration 0 freezes one answer-free Scenario Packet for each frozen
   scenario: `full` and `changed`. The packet carries
   the full Prompt Under Test text and path, Canonical Target Files, Prompt
   Dependency Files, the frozen scenario, requirements/checklist, method, and
   fixed report grammar. Expected commands, expected artifacts, answers, prior
   evaluator reasoning, and prior results stay in parent-local evidence.
2. Each iteration launches a fresh `skill_evaluator` instance for exactly one
   scenario. Every scenario, iteration, and malformed-report rerun receives a
   new instance. Fresh provenance includes a unique instance ID,
   iteration ID, and Scenario Packet digest.
3. A malformed report is unscored and rerun with a new fresh evaluator on the
   same frozen packet. It is neither a pass nor a convergence iteration.
4. After every return, the evaluation reviewer scores the observed `Output` and
   requirement observations against the frozen checklist. The evaluator emits report
   validity through `evaluation_status` and initializes feedback / learning
   fields as unresolved. It emits no reviewer score or convergence status; the
   evaluation reviewer artifact owns `parent_score_percent`, `parent_critical_pass`,
   and the final feedback / learning resolution.
6. An iteration converges only when all three scenarios have valid reports,
   parent-passing requirements, `ambiguity=none`, and the exact renderer-route
   requirements. Completion requires two consecutive converged iterations,
   matching per-scenario retry counts, zero retries, and a hold-out gap below
   15 percentage points in both iterations.

The evaluation reviewer records packet digest, evaluator provenance, raw report,
parsed requirements, `parent_score_percent`, `parent_critical_pass`, retry count,
ambiguity, and convergence decision.
The evaluator receives exactly the packet-listed files. Team context and prior
reports stay in parent-local evidence.

## Skill-Level Responsibility Boundaries

Subagent role は先に evidence surface で分けます。dashboard や run
bundle が `missing_actual_waves`、大量の skipped intake roles、または同一
role の scope 混線を示す場合、owning skill/reviewer が skill boundary を決め、
parent はその boundary に沿った subagent packet を relay します。

| Evidence Surface | Owning Skill | Subagent Responsibility Split |
| --- | --- | --- |
| log archive API、structured dashboard、routing miss、selection gap、wave execution reconciliation | `agent-log-analysis` | log-analysis owner が context artifact を生成し、`prompt_config_reviewer` は prompt / config drift、`docs_workflow_steward` は workflow / skill wording、`project_reviewer` は repo-wide operational risk を別 packet で見る。parent は launch/relay/status だけを担当する |
| repository layout、root shared view、responsibility scope、directory README、import boundary、project `.codex` / `.agents` view と personal `~/.codex` の境界 | `structure-refactor` | `explorer` は responsibility graph と stale surface、`execution_planner` は move / validation order、write-capable agent は disjoint path mapping、document-flow reviewer は reader route を見る |
| run bundle、spawn authorization、wave ledger、handoff capsule、fresh lifecycle、same-role instance identity | `subagent-bootstrap` | parent は launch mechanics を所有し、stage owner は `role_id+instance_id+agent_type`、input packet、remaining budget、validation route、review gate を持つ child wave だけを起こす |

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

- `requirements_organizer`: derive a target-state-complete Objective, non-goals,
  constraints, and Exit Criteria from the user request and durable repo notes.
- `explorer`: inspect repo docs, prior notes, dependency surfaces, existing
  tools, and reuse candidates that affect the goal.
- `execution_planner`: group the open work in the selected handoff or run-bundle
  `schedule.md` into the next cohesive slice.
- `plan_reviewer`: verify that the complete responsibility unit is checkable;
  checkpoints remain nonblocking observations outside rollback and micro-slice
  gates.

Start with the roles needed for the current stage, keep unused roles as dynamic
wave triggers, and add them when goal evidence, dependency state, or review
separation requires them.

Activation Conditions:

- These pre-goal agents are read-only for draft checking. A write-capable route
  proceeds after the user-authorized repository change has a structured handoff
  with objective, owner boundary, implementation mechanism, and evidence map.
- Write-capable `worker` / `spark_worker` instances do not wait for a repository
  mirror of session goal state.
- Goal-driven and ordinary repo-changing tasks use a structured handoff with
  bounded `allowed_paths`, write scope, validation plan, and tool-rejection
  preflight before the selected write-capable implementer. Use a run bundle when
  coordination or resumption requires durable lifecycle evidence.
- Materialize the initial goal intake from the active role set and catalog
  `intake` stage only when that wave is owner-critical. If selected, add or defer
  `explorer`, `execution_planner`, and `plan_reviewer` as evidence-gated dynamic
  roles; catalog listing alone does not create a wave.
- Handoffs include the objective and evidence map directly. When a run bundle is
  selected, pass `schedule.md`, `work_log.md`, and `team_manifest.yaml`
  lifecycle policy to the next role.
- Hand the next unchecked `schedule.md` work units to `execution_planner`
  instead of reconstructing durable progress from chat.

## Codex Command Surface

- official Codex CLI では `/model` で model / reasoning、`/plan` で plan mode、`/permissions` で approval preset を切り替えます
- これらは session-level setting で、per-agent TOML には書きません
- runtime が `/agent` を提供する場合は inventory 確認に使います
- `/agent` が使えない runtime では `.codex/agents/*.toml` を直接見ます
- run bundle は `python3 tools/runtime/lifecycle/bootstrap_agent_run.py ...` で、
  coordination、resumption、または selected workflow が durable lifecycle
  evidence を必要とするときだけ先に作ります
- `--task-id` の task-default specialist と default review pack は候補として
  読み込み、owner-critical operation、unresolved branch、または selected
  validation route が有効化したものだけを materialize します

## Permanent Team To Codex Mapping

この表は logical responsibility と capability route の対応です。Luna-backed
rows は role 名の custom-agent alias を物理 team member として起動せず、選択済み
role / Skills / authority を `$direct-luna-communication` packet に載せます。
`terra`、`spark_worker`、`skill_evaluator` は能力差があるため独立 route のままです。

| Permanent Team Role | Codex Subagent / Parent Role |
| ------------------- | ---------------------------- |
| `manager` | parent + `requirements_organizer` |
| `terra` | conditional read-only cross-cutting specialist; `terra` profile only |
| `manager_reviewer` | `manager_reviewer` |
| `designer` | `detailed_designer` |
| `design_reviewer` | `detailed_design_reviewer` |
| `document_flow_reviewer` | `document_flow_reviewer` |
| `test_designer` | `test_designer` |
| `implementer` | `worker` by default; `spark_worker` only for a bounded slice selected by `--select-agent-type implementer=spark_worker:<evidence>` and recorded in stdout / manifest. Both roles may commit/push and return local head/check evidence; publisher/pr-processing owns Issue/PR writes and integration_executor owns merge/conflict resolution. |
| `integration_executor` | existing `worker` executable with explicit integration scope; owns merge/conflict resolution and branch/tree readback |
| `publisher` | existing `worker` executable with explicit publication scope; owns authorized Issue/PR writes and remote readback |
| `change_reviewer` | `diff_triage_reviewer` by default; `python_reviewer`, `cpp_reviewer`, then `reviewer` only with language or broad-review eligibility evidence |
| `final_reviewer` | `ship_reviewer` checks final diff traceability to the Abstract Design Frame and approved packet; then `reviewer` / `project_reviewer` when final gate escalation is needed |
| `verifier` | prescribed validation runner |
| `auditor` | closeout artifact and workflow-monitoring gate |
| `researcher` | `literature_researcher` or `explorer` |
| `research_reviewer` | `reviewer` |
| `experimenter` | `experiment_runner` for runs; `worker` only for scoped runtime-output handling |
| `experiment_reviewer` | `reviewer` |
| `mathematical_correctness_reviewer` | existing Luna/high `reviewer` executable with a dedicated math-intent packet and scope contract |
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
| `skill_evaluator` | fresh `skill_evaluator` for one explicit frozen Scenario Packet; artifact-only observed report |
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
- `mathematical_correctness_reviewer`
  - 既存の Luna/high `reviewer` executable を使う専用 logical role として、math-intent packet の `math_object` / `problem`、`variables` / `domains` / `units`、`objective` / `residual`、`constraints`、`equations` / `definitions`、`assumptions` / `approximations`、`derivation`、`iteration_map` / `update_map`、`invariants` / `limits` / `stopping_scalar` / `failure_semantics`、`equation_to_code_map`、`math_oracle` / `counterexample`、および mapped changed-path scope を確認する。数学対応の finding だけを返し、architecture、framework、JIT、compiler、backend、runtime、container、routing、environment、common infrastructure、proof-tool / IR infrastructure の編集を承認しない
- `logic_gap_reviewer`
  - claim-to-evidence のつながり、hidden assumption、result と interpretation の飛躍を確認する
- `long_form_writer`
  - README、workflow、guide、migration、specification など file responsibility が一般説明 prose の文書を、graph/DSL closure 後に roadmap-led で prose projection する
- `test_designer`
  - owning mechanism の確立または修復後に積極的に起動し、まず activation decision と boundary classification を返す。既存のstatic analysis、checker、targeted validationの外側にある未解決oracleだけを、重複・no-crash・内部形状固定なしの論理的に最小なtest planへ落とす
- `diff_triage_reviewer`
  - 狭い diff の triage review を境界証拠付きで行い、language-specific reviewer または broad `reviewer` へ上げるかを決める
- `ship_reviewer`
  - user request clause、Abstract Design Frame、Design Side-Effect Map、approved packet、product diff、validation、dependency review、closeout artifact を照合する最終出荷 gate を担当する
- `explorer`
  - 読み取り専用で codebase / docs / workflow の調査を行う
- `reviewer`
  - 読み取り専用で diff と risk を findings-led で洗う
- `python_reviewer`
  - Python diff の型、API境界、親 packet が選択した validation evidence を review する。validation scope は `../skills/python-review.md#Validation route` と `../skills/agent-orchestration.md#Write-Capable Handoff Validation Trust Boundary` を参照し、reviewer が追加の full suite を選択しない
- `cpp_reviewer`
  - C / C++ diff を build、header、ownership、native test 前提で洗う
- `oop_readability_reviewer`
  - `tools/oop/*/readability.py` の機械 report を読み、判定値を変えずに reader-facing な文書化、false positive 候補、優先度整理を行う
- `worker`
  - bounded な実装変更を切り出し、approved design と local precedent の naming に従う。commit/push を含む実装・統合境界の実行は可能だが、PR create/merge/close、admin override、base integration 判断、最終統合評価は parent が保持する。
- `terra`
  - multi-owner dependency closure、context reconstruction、adversarial contradiction validation を担当する conditional read-only specialist candidate。owner closure と context capsule を確認し、accepted / rejected / escalated の handback を Sol parent に返す。always-on、実装、coordinator、general worker、PR 操作、manifest の恒久正本化は担当しない。
- `spark_worker`
  - Abstract Design Frame と approved design packet で完全に切れる低リスク実装、docs sync、test sync、mechanical cleanup を低遅延に処理する。実装・commit/push は可だが、PR create/merge/close、admin override、base integration 判断、最終統合評価は parent が保持する。
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
- `skill_evaluator`
  - explicit empirical skill evaluation で、parent-provided の一つの answer-free Scenario Packet だけを読み、固定 Output grammar の observed report を artifact-only で返す。実装、checker、nested agent、scenario reuse は行わない
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
| テストケース設計 | 実装後に owning mechanism と具体的な未解決 risk が記録された場合だけ、専用の `test_designer` instance を条件付きで起動する。まず activation decision を返し、checker-owned property は static validation へ戻し、具体的な behavior regression oracle だけを test plan に落とす |
| 記号定義レビュー | 専用の `notation_definition_reviewer` instance。記号、略語、technical term、unit、index、assumption の定義順と一貫性を見る |
| 論理接続レビュー | 専用の `logic_gap_reviewer` instance。主張の飛躍、隠れた仮定、result と interpretation の境界を見る |
| 数理修正の intent / scope review | `computational-optimization` の math-intent packet を先に作り、専用の `mathematical_correctness_reviewer` instance が equations、変数 / 単位、仮定、導出、更新則、停止 / failure、equation-to-code map、math oracle、changed-path scope を確認する。generic designer、benchmark、scientific-computing reviewer より前に行い、非数理 surface は sibling handoff に分ける |
| report / claim-heavy narrative review | 専用の `report_reviewer` instance。evidence traceability、overclaim、reader-facing report quality を見る |
| OOP readability report documentation | 専用の `oop_readability_reviewer` instance。機械判定 report の status / count / path / line を保持し、tool fact と reviewer judgment を分けて OOP 原則別に文書化する |
| 実装 | `IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker` を確認し、既定は `worker`。`spark_worker` は `--select-agent-type implementer=spark_worker:<evidence>` の parent packet selection が stdout / manifest に記録された bounded slice だけに使う |
| 低リスク実装slice | Abstract Design Frame、design trace、naming、validation、dependency-expanded handoff scope は `spark_worker` selection の必要 evidence ですが、それだけで既定 candidate を切り替えない |
| 実装後レビュー | change-review decision が active のとき、`change_reviewer` は `diff_triage_reviewer` を既定 executable とする。`python_reviewer` / `cpp_reviewer` は changed-path evidence、parent packet evidence、または明示 review-pack activation がある場合だけ materialize する。Design Side-Effect Map から外れた side effect は設計差分として扱う |
| 包括的開発の統合レビュー | T12 の `scheduler`、`schedule_reviewer`、`project_reviewer`、`docs_workflow_steward`、`prompt_config_reviewer` は候補 specialists です。owner-critical な責務、unresolved branch、または selected validation route が有効化した role だけを active にします。`python_reviewer` / `cpp_reviewer` も changed-path evidence、parent packet evidence、または明示 review-pack activation がある場合だけ active にします |

運用ルール:
- role ごとの詳細な実行制約は `.codex/agents/*.toml` を見ます
- この文書では route と inventory だけを決め、各 role の詳細条件は `.codex/agents/*.toml` に集約します
- parent は stage を暗黙にまとめず、別 role を別 instance で起動します
- subagent を起動するときは、`team_manifest.yaml` の `run.subagent_prompt_packet`、該当 role の `prompt_contract`、`document_packet.read_before_work`、または `bootstrap_agent_run.py` の packet 出力を local/tool context として参照します。prompt へは `agents/COMMUNICATION_PROTOCOL.md` が定義する `Fresh Subagent Context Capsule` を渡し、packet stdout や full artifact は貼りません
- context が増えたら capsule artifact を更新して再配送します
- math-intent route の write-capable handoff には、protocol の Target Binding Packet に加えて
  `mathematical_intent_packet` を必ず添えます。packet は `math_object` / `problem`, `variables` /
  `domains` / `units`, `objective` / `residual`, `constraints`, `equations` / `definitions`,
  `assumptions` / `approximations`, `derivation`, `iteration_map` / `update_map`, `invariants` /
  `limits` / `stopping_scalar` / `failure_semantics`, `equation_to_code_map`, `math_oracle` /
  `counterexample`, `mathematical_definition_paths`, `mathematical_oracle_paths`,
  `mathematical_documentation_paths`, mapped `allowed_paths`, default
  `forbidden_surfaces`、`separate_handoff_targets` を含みます。必須欄、map、oracle が欠けた
  handoff は `math_packet_missing` として停止し、worker は推測で scope を補いません
- 通常 bootstrap は `--math-intent-packet '<JSON>'` を受け取り、run manifest と canonical
  `spawn_agent` ToolCall の両方へ同じ正規化済み packet を渡します。math writer の
  `writer_target.allowed_paths` は packet の `allowed_write_paths` の部分集合でなければならず、
  architecture / JIT / backend / runtime / routing / environment / proof / IR infrastructure
  は `separate_handoff_targets` に残し、math packet の厳密な `allowed_write_paths` にない
  path は spawn 前に拒否します。packet が明示的に数理実装として mapped した `src/runtime`
  のような path は許可します。非数理 route では packet を要求せず、math reviewer も起動しません
- workflow family ごとの prompt 正本は `agents/task_catalog.yaml` の `workflow_families[].subagent_prompt` です
- 一般説明 prose adapter を使う文書では `document_flow_reviewer` に加えて別 reviewer で `docs-completeness-review` を通します
- 学術文章では `document_flow_reviewer` に加えて `notation_definition_reviewer`、`logic_gap_reviewer`、別 reviewer の `docs-completeness-review` を通します
- 論文 draft では `citation_evidence_reviewer` も追加します
- research-driven change では `report_reviewer` と perspective reviewers を default にします

## Checkout Identity at Git Boundaries

各 agent / work unit は、Git 状態に関係する作業単位の開始時に、既存の
`checkout_identity` readback を一度 handoff context に含めます。cwd または
checkout が変わった後、conflict 解消前、commit / push / PR 前、cleanup または
destructive Git 前、subagent handoff と final handback でも同じ block を更新します。
通常のコマンドごとには繰り返しません。

readback は `python3 tools/runtime/authority/checkout_identity.py --format lines` で取得し、
絶対 `cwd`、Git root、branch（detached を含む）、HEAD、normalized remote
`owner/repository` を運びます。これは観測情報だけであり、branch / worktree authority、
approval、merge、cleanup、Issue、publication の権限を追加しません。Git root または
remote を解決できない場合は `unknown` をそのまま伝え、対象操作が identity を必要と
するときだけ既存の owner route で停止します。

## Parallel Write Safety

- parent が `team_manifest.yaml` の write policy と handoff で writer ごとの allowed path / directory を管理します
- write-capable handoff は `writer_target`（絶対 `checkout_root`、固定 `branch`、正規化済み `remote`、`allowed_paths`）を必須とし、branch は handoff 前に `repository-topic-clone.prepare` で用意します
- 同一 wave の writer target が同じ `checkout_root` を持つ場合、agent team は spawn callback 前に typed collision として拒否します。reader は `writer_target` を持たず同じ checkout を共有できます
- `repository-topic-clone.prepare` は dedicated clone の ignored `.agent-canon/writer-target.json` に target と検証済み checkout identity を materialize します。PreToolUse はこの packet を正本として読み、環境変数は readback 一致確認に限って使い、modified path が `allowed_paths` の外なら拒否します。packet が無い checkout や packet 自身の変更は拒否し、read-only command はこの writer path gate の対象外です
- repository write は `worker`、`spark_worker`、`integration_executor` の各 write-capable route に限定します。IssueWorker の `publisher` は外部 GitHub publication 専用で target を持たず、reviewer と artifact-only role は read-only とします
- 同一 path、同一 directory ownership、同一 public API surface、shared Git index/HEAD、generated output、formatter output は順序制約つきの writer に割り当てます
- 同一 worktree の write-capable subagent instance は、writer target が distinct である場合だけ同じ role type を含む複数 writer instance を同一 wave で使えます
- same directory / same file / same canonical surface を同時に触る writer は先行 / 後続 wave に分けます
- 衝突する target は順序制約として扱い、先行 wave の validation と tool rerun 後に後続 wave で統合します
- writer は current checkout 内の wave plan で分離し、追加判断が要る writer は後続 wave へ直列化します
- isolated worktree は通常の衝突回避には使わず、明示 workflow が要求する genuinely independent alternative implementation experiment に限定します
- review role は常に read-only とし、parent-managed write-scope discipline と writer-instance separation の確認は `plan_reviewer` と `project_reviewer` の固定責務です

writer target は短命な handoff 値であり、claim file、PID、expiry、daemon、または別の writer registry を作りません。worker と integration_executor の生成 prompt は target の checkout で開始し、`git switch`、`git checkout`、branch rename、`git worktree` を実行しないことを明示します。外部 GitHub publication 専用の publisher は target 不要です。

## Codex Model Settings

`agents/model_profiles.toml` が canonical typed profile authority です。
`agents/execution_topology.json` は logical role と physical execution profile の
分離、および direct-Luna default を所有します。
`tools/agent/orchestration/model_profile_registry.py` は closed generated views として
`.codex/agents/*.toml` と `agents/agents_config.json` を materialize します。
generated views は projection digest / readback surfaces であり、手動で編集しては
なりません。model / reasoning の変更は registry / team / runtime source から始め、
generated views を再生成して projection digest と readback を検証します。Codex
runtime は再生成後に restart し、readback で反映を確認します。

運用メモ:
- OpenAI / Codex の current product evidence は `$openai-docs` で確認します。
  この文書は product-evidence route を示します。
- `agents/model_profiles.toml` の closed registry が parent / reasoning / implementation / ship / Spark / evaluator profiles と explicit role bindings を所有します。`.codex/agents/*.toml` と `agents/agents_config.json` は generated projection と runtime readback を提供します。`spark_worker` は typed fixed-packet route が選んだ機械的実装だけに使います。
- 親の既定は Sol/high とし、Sol/xhigh は high-risk / final escalation evidence があるときに起動します
- planning session の mode は official Codex CLI なら `/plan`、model / reasoning の切替は `/model`、approval preset は `/permissions` を使います
- 極端に狭く、待ち時間が支配的な implementation loop は `spark_worker` selection の evidence になり得ますが、`worker` 既定を切り替えるには explicit parent-packet selection が必要です
- review / quality-check role TOML は Luna/high を使い、hypotheses を decision-owning reviewer または ship reviewer へ返します。reviewer が current snapshot、reachable path、contract、witness/static proof を確認して accept / reject を adjudicate し、integration executor / publisher が edit / rollback / publication route を担当します。`ship_reviewer` は明示された final escalation の候補です
- Spark model は `spark_worker` の低遅延 implementation loop に集約し、repo inventory、tool drift survey、machine-report / experiment-log summarization、execution-only experiment / log work は Luna/high の通常 role に置きます。mini/medium は明示的な T14 skill validation の `skill_evaluator` に限ります。
- `spark_worker` へ渡す条件は、Abstract Design Frame、Implementation Source Packet、Design-To-Implementation Trace、identifier naming、test-plan artifact / evidence（active workflow または touched surface が post-implementation test design を選択し、その activation により `test_plan.md` が生成されたか必須になった場合のみ）、dependency-expanded handoff scope に加え、typed parent-packet selection が stdout / manifest に記録されていることです
- 明示 spawn 許可がある repo-changing task では、coding / implementation / patch / doc-edit work の implementation critical path を pre-handoff investigation packet で作ってから、次の判断を変える独立検証だけを Luna review child へ切ります。各 replaceable responsibility は一つの owning review gate で足り、文書 flow、requirements / plan、report traceability、research perspective は distinct unresolved claim / risk が owning gate で判定できないときだけ specialist wave として起動します。
- coding / implementation / patch / doc-edit work を求める repo-changing task では、read-only / review wave は write-capable handoff の準備です。実装可能な handoff scope が dependency expansion から出た後は、bounded request でも `worker` を既定として起動または schedule し、`spark_worker` は explicit parent-packet selection が記録された場合だけ使います。completion route は handoff、integration、review、validation で構成し、親は直接編集・テスト・判定を行いません。
- `spark_worker` を選択できる実装は、Abstract Design Frame から導かれた差し替え可能な単位で、stable public interface、stable dependencies、fixed specification、既存 test / docs の局所更新で閉じるものです。この eligibility evidence に加えて typed parent-packet selection が必要です。
- cross-module 整合、API shape、命名 / 責務境界、依存再構成、安全性、性能、conflict resolution のいずれかが入った時点で `worker` または設計 review へ戻します
- Terra は canonical 登録された conditional read-only cross-cutting specialist candidate であり、always-on role ではありません。multi-owner dependency closure、compaction・long-run・incomplete handoff の context reconstruction、または複数案・finding の contradiction validation の evidence がある場合だけ active にし、evidence なしには選択しません。coordinator や general worker としては使わず、capability は `cross_owner_integration`、`context_reconstruction`、`adversarial_contradiction_validation` に限定します。
- ユーザーが提示した alternative architecture、または既存 finding に含まれる alternative は adversarial comparison の入力として Terra に渡せます。Terra 自身による未要求の新規案生成、architecture の採用、final decision は行いません。
- Terra の handback は owner closure、context capsule、`accepted`・`rejected`・`escalated` のいずれかを含め、unresolved は Sol parent へ返します。descendant close と reservation release は既存 lifecycle receipt を消費し、`team_manifest.yaml` は run 生成 artifact のまま恒久正本にしません。
- `document_flow_reviewer` は README / workflow / guide / design doc / paper、新用語、公開 API、reader-facing docs があるときに起動します。code-only owner-bounded change では省略できます
- change-review decision が active のときは `diff_triage_reviewer` を既定 executable とします。`python_reviewer` / `cpp_reviewer` は changed-path evidence、parent packet evidence、または明示 review-pack activation で追加し、`reviewer` は broad diff / cross-surface / clause coverage に上げる場合だけ使います

## Research Perspective Review Pack

- default triage は `reproducibility_reviewer` に provenance、seed、command、environment、rerunability を見させ、`artifact_reviewer` に code、script、raw result、environment、artifact package の十分性を見させる
- benchmark protocol がある場合だけ `benchmark_reviewer` を追加します
- dataset / result path / metadata が中心の場合だけ `fair_data_reviewer` を追加します
- ML claim / uncertainty / limitation が中心の場合だけ `ml_science_reviewer` を追加します
- workflow / prototype discipline が論点の場合だけ `scientific_computing_reviewer` を追加します
- full pack は `research_perspective_review` を明示したとき、または triage が methodology / benchmark / FAIR-data / ML-science / scientific-computing risk を返したときだけ起動します
- decision-owning reviewer が findings を `fix now`、`follow-up`、`delete-ok`、`rejected` に adjudicate して handoff を返す。`rejected` は `reason_code` と `evidence_ref` を持ち、修復 / review wave / rollback を起こさない

## Runtime Surfaces

- human routing and inventory canon: `agents/`
- permanent team ownership and write policy: `agents/agents_config.json`
- skill shim: `.codex/personal/skills/`
- Codex project config: `.codex/config.toml`
- generated Codex subagent readback views: `.codex/agents/*.toml`

設定運用メモ:
- role ownership や required output を変えるときは `agents/agents_config.json` を更新します
- project subagent registration と runtime budget を変えるときは
  `.codex/config.toml`、role model / reasoning を変えるときは
  `agents/model_profiles.toml` を更新して canonical materializer を実行します
- stage 固有の profile/instruction 条件は `agents/model_profiles.toml` の owner
  route で変更し、canonical materializer による generated view regeneration を
  必須とします
- wrapper や root entrypoint は `.codex/agents/*.toml` の参照入口に保ちます
- generation 後は alignment readback を確認し、load 済み session の projection
  freshness は registry materialization と fresh-session restart/readback で回復します

## Smoke Test

runtime inventory や review pack を変えたら、まず次を実行します。

    python3 tools/validation/semantic/runtime/check_agent_runtime_alignment.py
    python3 eval/checkers/smoke_test_research_perspective_pack.py

この smoke test は次を確認します。

- `agents/task_catalog.yaml` の各 task が有効な specialist / review pack へ展開できる
- `agents/agents_config.json` の required output が実テンプレートに結び付いている
- `.codex/config.toml` が `.codex/agents/*.toml` を全 role 登録している
- `.codex/agents/*.toml` が role ごとの model / reasoning 設定を持っている
- selected workflow が bundle を必要とする場合だけ temporary run bundle を
  作り、required output が実際に生成される
- `agents/agents_config.json` に perspective reviewers と artifact mapping がある
- `agents/task_catalog.yaml` に `research_perspective_triage` default pack と optional `research_perspective_review` pack がある
- `.codex/agents/*.toml` に対応 subagent 定義がある
- perspective review が選択され bundle が必要な場合だけ temporary run bundle を
  作り、各 perspective review artifact と `team_manifest.yaml` が実際に生成される
Fixed packet projection is owned by the canonical model/profile registry,
implementation-route, capacity-handshake, and team/closeout consumers. Sol is
the parent; Luna owns ambiguous design, causal repair, graph-owned cross-owner
integration, and review; Spark is the fixed implementation owner; and
`gpt-5.4-mini` is skill-evaluator-only. Model/profile policy stays out of
`route.py`.

Tool calls are canonical `ToolCallToken` values from the registry: natural
language carries intent and typed failure semantics only. The implementation
projection is Target-State-First and Decision Sufficiency is machine-readable;
an identical owner/edit/validation action rejects unvalued read/search/check/
review and transitions immediately to one direct Spark materialization followed
by one owning gate. Compile/static failures are implementation feedback. Only
an exact target contradiction creates one `StructuralDesignGap`, repaired once
before the same Spark resumes.

## Capacity And Lifecycle

Capacity terms are requested, configured, platform-effective, workflow-demand,
write-cap, nested-reserved, and available. Effective capacity is the minimum
of known available constraints after reservations. Session reload mismatch is
typed `restart_required`/queue evidence; model-capacity events are distinct
from thread saturation. Lifecycle closeout is
`spawned -> active -> durable result/error -> handed back -> all descendants
closure verified -> close requested -> closed -> reservation released`; any
open terminal, unknown descendant, missing handback, or leaked reservation
fails closeout. The parent-visible ledger carries full topology and the
canonical `close_agent` ToolCall in CloseoutPacket.
