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
shared workflow は [agents/canonical/CODEX_WORKFLOW.md](CODEX_WORKFLOW.md) に置き、この文書は inventory、mapping、activation に寄せます。
permanent team role ownership、required output、write policy は `agents/agents_config.json` を正本にします。
role profile/instruction authority は `agents/model_profiles.toml` と
`tools/agent/orchestration/model_profile_registry.py` が所有し、`.codex/agents/*.toml`
は closed generated readback view です。
project-level subagent registration と runtime limits は `.codex/config.toml` の `[agents]` と `[agents.<name>]` を正本にします。
prompt、routing、subagent-config drift の監査は `prompt_config_reviewer` を先に通し、
この file は inventory と activation の入口に保ちます。

## Compact request/update projection

[../../documents/design/request-intent-and-update-relation.md](../../documents/design/request-intent-and-update-relation.md) の handoff flow は既存
agent context の再利用を優先します。並行作業を選ぶ場合は実際の依存、write scope、
衝突を考慮し、起動結果と完了結果を区別して既存の handoff record に残します。

Runtime collaboration capability and coordination receipts are owned by
[agents/COMMUNICATION_PROTOCOL.md#Runtime Collaboration Capability Handshake](../COMMUNICATION_PROTOCOL.md#runtime-collaboration-capability-handshake).
This document only projects the route: read capability from the direct runtime
collaboration namespace, use `direct_peer` only after an `available` readback,
and use an honest `parent_relay` or `durable_artifact` path for
`unavailable`/`unverified` runtimes. Matcher names and `functions.exec` tool
inventories are not capability evidence. Child handoffs record actual operations
and results; parent relay is never relabeled as peer communication.

既存 context の再利用、別担当への handoff、integration の完了は、それぞれの実際の
owner、scope、result と必要な cleanup を根拠に判断します。

## この文書の読み方

- この文書は、Codex runtime の subagent inventory、handoff、role mapping、および launch mechanics を所有します。workflow family と role guidance は `agents/task_catalog.yaml` を読みます。
- 前半は coordination、handoff context、language / completeness / quality policy を扱い、後半は command surface、role mapping、write safety、model settings、smoke test を扱います。
- parent agent、writer、reviewer は現在の判断に関係する節と選択済み role の案内を参照します。
- この文書の `parent Sol` は `.codex/config.toml` の parent projection を指し、
  child profile authority は `agents/model_profiles.toml` が所有します。
  `.codex/agents/*.toml` と `agents/agents_config.json` の profile fields は
  canonical materializer が生成する readback view です。
- chunked reading では、現在の作業に関係する policy 節だけを開き、
  profile/instruction authority は `agents/model_profiles.toml`、生成済みの
  runtime readback は `.codex/agents/*.toml` で確認します。

## Principles

- role profile/instruction は `agents/model_profiles.toml` を優先し、
  `.codex/agents/*.toml` は generated readback として扱います
- logical role、selected Skills、execution profile、authority は別々に選びます。Luna profile は `$direct-luna-communication` の bounded packet で direct child として起動し、role-specific alias を physical team identity や capacity 根拠にしません
- permanent team ownership、artifact output、write policy は `agents/agents_config.json` を優先します
- subagent registration と actual runtime limits は `.codex/config.toml` を優先し、
  role model / reasoning は `agents/model_profiles.toml` を優先します
- prompt / config drift の reviewer output は hypothesis です。decision-owning
  reviewer または ship reviewer が current snapshot、reachable path、contract、
  witness/static proof を確認して adjudicate し、distinct unresolved risk の
  ときだけ specialist を追加します
- selected coordination/delegation route では parent agent は orchestrator /
  integrator です。親は handoff packet の選択、agent 起動、packet relay、
  status、選択済み integration と最終 readback を担当し、child に割り当てた
  implementation unit を代替実装しません。bounded single-owner route や
  user-guided debugging の executor は各 workflow owner が定めます
- selected route と必要な owner-critical review を解決します。関連する owner
  guidance は Markdown 相対リンクで示しますが、リンク先すべてを読む義務には
  しません。実際の native tool / child results を選択済み workflow の既存記録へ
  残し、起動結果と完了結果を区別します。
- selected delegation / coordination route だけが write-capable implementer
  handoff を作ります。起動できない場合は実際の原因を利用者または選択済み owner に
  伝え、child に割り当てた unit を親が代替実装しません。bounded single-owner
  execution はこの subagent route の対象外です。
- 調査、レビュー、文書整備は分ける
- 同時起動は configured native runtime limits と実際の依存・write conflict を根拠に選びます
- Nested child delegation is a workflow choice, not a required task stage. When selected, use the configured native collaboration route and record actual launch, completion, or failure.
- 探索、レビュー、仕様確認は必要に応じて並行し、write-heavy implementation では実際の依存と衝突を考慮する
- runtime の同時 spawn は `.codex/config.toml` の `max_threads` 以内に収める
- Runtime collaboration limits are owned by the configured runtime; do not derive a separate workflow capacity budget.
- child の起動だけで作業完了とせず、実際の完了結果を確認します。monitor status
  は補助的な readback であり、それだけで完了を判定しません。
- 同じ checkout root の write-capable agent は同時起動しません。先行writerの
  lifecycle終了とowner release/readback後だけ同じcheckoutを直列再利用します。
  並列writerはcheckout ownerが選択したdistinct checkout rootを使います。
- subagent handoff の input packet は role ごとに owned scope を固定し、route seed と調査結果から展開した対象 path list、context artifacts、allowed / forbidden paths を渡します。
- reviewer には対象 path list、checker summary、structured dashboard / drilldown、該当 canon 節を先に渡します。
- fresh subagent は必要な launch ごとに [agents/COMMUNICATION_PROTOCOL.md](../COMMUNICATION_PROTOCOL.md)
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
- `implementer.codex_agents` は canonical model/profile registry の generated view です。選択済み typed route の implementer role/profile と必要な owning review を使います。Luna は ambiguous design、causal repair、cross-owner integration、review を所有します。
- 分割境界は差し替え可能性で判断します。別実装、別証明、別 validation oracle、別 review decision に置き換えられる単位なら worker scope にできます。数理的に差し替えが起きない境界、記法だけの境界、固定 context、同じ oracle を共有する連続導出は、過剰な subagent 分割を避けて同じ input packet に残します。
- capacity や model の制約に遭遇したら、実際に得られた情報に基づき owner と次の作業を選び直します。
- 設計・scope 判断、曖昧な実装判断、multi-surface conflict resolution は
  registry-selected reasoning child または integration executor の findings と
  decision-owning reviewer の判定に分け、ship decision は ship reviewer が持つ
- plan mode や permissions のような mode は session 単位の設定として parent session 側で切り替える

## Collaboration Boundaries

- Select a logical role and model/profile from the task need and the existing
  role owners. A role candidate is metadata, not an automatic child launch.
- When delegation is selected, use the configured native collaboration route.
  Record actual launch, completion, and failure separately; neither a plan nor
  a monitor row proves completion.
- `.codex/config.toml` owns actual runtime limits such as `max_threads` and
  `max_depth`. Do not derive a second workflow capacity budget, impose a task
  fan-out quota, batch roles to fit a task ledger, or require capacity receipts.
- Split work by independent responsibility and real dependencies or write
  conflicts. Serialize writes that target the same checkout/path; disjoint
  work can proceed in parallel when the owner selects it.
- Nested child delegation is optional and depends on the selected role's
  responsibility and the native runtime. It is not a required task stage.
- Reuse an active role instance only when its owner, responsibility, context,
  and write authority remain compatible; otherwise choose a fresh assignment
  based on the actual task.
- Owner-produced Decision Sufficiency information can be carried when a
  design decision needs it. It is not a general startup, dispatch, or completion
  gate. The packet semantics remain owned by
  [agent-orchestration](../skills/agent-orchestration.md#decision-sufficiency-packet).
## Handoff Context Contract

Subagent の context は correctness gate です。parent は handoff prompt ごとに次を
structured handoff または、coordination/resumption が必要な場合の durable evidence
から導出します。

- `role_scope`: その role が判断する subdomain、責務、risk class。
- `reuse_survey`: `allowed_paths` や responsibility slice を決める前に
  共有する既存 asset context。known な current+historical asset paths、capability、
  disposition (`reuse`/`extend`/`restore`/`consolidate`/`replace`/`delete`/
  `reject`)、reason、test paths を含められます。この advisory/shared context
  の不在は dispatch または write を block しません。
- `allowed_paths`: 上記の known asset context と tests から導く対象 file /
  directory / glob の bounded list。context がある場合は独立した token 候補から
  path を選びません。context がない場合も既存 route は継続し、dispatch / write を
  block しません。repo root や `/workspace` は workspace identity として扱い、
  編集候補、検索 hit、checker finding、changed path を seed にし、responsibility
  search、reuse survey、stale-surface scan、dependency header graph の再帰展開結果
  である `dependency_edit_scope.txt` / `dependency_graph.tsv` を優先します。
- `required_artifacts`: checker output、structured dashboard、dependency-expanded scope、design / implementation packet、または review packet。context artifact を先に渡します。dependency-expanded scope が必要な場合は `bash tools/analysis/dependencies/run_repo_dependency_review.sh --report-dir <run-or-review-dir> --search-hits-file <hits>` または changed-path 相当の dependency review output を handoff に含めます。
- `canon_refs`: 必要な AgentCanon / project canon の節。
- `do_not_read`: unrelated modules、generated raw logs、historical reports、他 role の scope など、読まない surface。
- `expected_output`: findings schema、decision vocabulary、uncertainty / residual risk、test gaps。
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
- `tool_reuse_ledger`: selected write-capable implementer には、既存 tool を使うか拒否した理由を渡します。予測検査の扱いは [Optional Rejection Prediction](../COMMUNICATION_PROTOCOL.md#optional-rejection-prediction) に従います。

The worker prompt begins with the parent-selected `reuse_survey` assets and
test paths when known; for split or extraction work, the splitter inspects
current and git-history assets before acting on `allowed_paths` or forming a
narrower slice. Every child receives the same known asset context. This
advisory context is not a machine-enforced admission gate.

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
projected into [documents/runtime/runtime-profiles-and-check-matrix.md](../../documents/runtime/runtime-profiles-and-check-matrix.md). This section is
only the subagent handoff projection: handoffs must carry those five fields and
must cite the runtime profile taxonomy rather than defining a separate slug
list. Implementation bugs, test-oracle/spec mismatches, fixture or environment
issues, stale generated artifacts, unrelated failures, and approved-design /
user-request conflicts follow the owner routes named by the runtime profile
taxonomy.

For local merge conflicts, use the existing integration owner to review the
actual native Git conflicts against their source owners and read back the
integrated tree. Preserve unrelated or unknown user state; do not add a second
conflict/rework artifact contract to the handoff.

## Coordination

Selected coordination routes use their existing handoff and record owners.
Markdown links point to conditional owner guidance, not a mandatory graph or
read-set. Use actual native launch, completion, and failure results to assess the
work; existing Eval or owner review judges missing or unnecessary work, while a
route difference alone is not failure. Keep a compatible active agent when its
owner, scope, and authority still fit; separate independent work only when the
selected route requires distinct responsibility or write boundaries.

## ユーザー向け言語ポリシー

人間向けの更新、レビュー要約、handoff guidance、reader-facing docs は日本語で
書き、機械可読の key、command、path、role id、schema は既存の正本表記を保ちます。
選択された coordination route の言語 readback は既存 lifecycle owner を使います。

## 契約完全実装ポリシー

Implementation completeness follows [Codex Implementation](CODEX_IMPLEMENTATION.md)
and the selected route. This document does not copy its contract fields, gate names,
or completion evidence into a coordinator packet.

## Handoff 前スコープポリシー

Handoff scope follows the current cause, constraints, guarantee, and selected owner.
Use [Codex Intake](CODEX_INTAKE.md) for the bounded context decision and
[Communication Protocol](../COMMUNICATION_PROTOCOL.md) for the capsule. Do not
materialize a route-independent scope-discovery sequence here.

## Quality Check 既定ポリシー

Review activation follows the selected workflow's owning review gate. Candidate
roles and quality artifacts are not materialized by this inventory; use the selected
review owner when a distinct unresolved claim or risk requires it.

## Subagent Return

If a child has not returned a result, do not infer completion from a timeout or
monitor status. Use the runtime's available status and the actual workspace
result to decide whether to wait, continue disjoint work, or revise the handoff.
Do not retry a failed mutation unless its premises have changed; preserve any
active writer's scope until its actual completion or an explicit cancellation.

## Empirical Skill Evaluation Lifecycle

`skill_evaluator` is an optional specialist with activation
`explicit_empirical_skill_evaluation`. Use the catalog's `skill_evaluation`
family and selected role guidance when that route is chosen. Keep the evaluator
read-only and artifact-only; the evaluation reviewer owns scoring and
convergence. Any run bundle is separate from the evaluator prompt, which uses
the current Scenario Packet, packet-listed files, `do_not_read`, and fixed
output schema.
The evaluator's `mini_skill_evaluator_medium` profile (`gpt-6-luna/medium`) is
reserved for this explicit T14 lane; no permanent team role uses that profile.

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

Subagent role は必要な責務に応じて選びます。actual tool results や選択済み workflow
の記録が必要作業の欠落、不要な作業、または role scope 混線を示す場合、owning
skill/reviewer が判断し、parent は結果を既存 handoff route で relay します。

| Evidence Surface | Owning Skill | Subagent Responsibility Split |
| --- | --- | --- |
| log archive API、structured dashboard、routing miss、selection gap、actual execution records | `agent-log-analysis` | log-analysis owner が context artifact を生成し、`prompt_config_reviewer` は prompt / config drift、`docs_workflow_steward` は workflow / skill wording、`project_reviewer` は repo-wide operational risk を別 packet で見る。parent は launch/relay/status だけを担当する |
| repository layout、root shared view、responsibility scope、directory README、import boundary、project `.codex` / `.agents` view と personal `~/.codex` の境界 | `structure-refactor` | `explorer` は responsibility graph と stale surface、`execution_planner` は move / validation order、write-capable agent は disjoint path mapping、document-flow reviewer は reader route を見る |
| run bundle、spawn authorization、handoff capsule、same-role instance identity | `subagent-bootstrap` | parent は launch と handoff を所有し、selected role の input packet、scope、validation route を保ちます |

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

- subagent が読むべき checker result、hook log、dependency scope、review finding が handoff に入っていなかった場合、選択済み workflow の handoff guidance を更新します。
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

Start with roles needed for the current responsibility. Add another role only
when request evidence, an actual dependency, or a distinct review need calls for it.

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
- Use the catalog's intake guidance when it is relevant; a catalog listing alone
  does not require a role to be started.
- Handoffs include the objective and evidence map directly. When a run bundle is
  selected, pass the relevant `schedule.md` work and `work_log.md` results to
  the next role.
- Hand the next unchecked `schedule.md` work units to `execution_planner`
  instead of reconstructing durable progress from chat.

## Codex Command Surface

- official Codex CLI では `/model` で model / reasoning、`/plan` で plan mode、`/permissions` で approval preset を切り替えます
- これらは session-level setting で、per-agent TOML には書きません
- runtime が `/agent` を提供する場合は inventory 確認に使います
- `/agent` が使えない runtime では `.codex/agents/*.toml` を直接見ます
- run bundle は coordination、resumption、または selected workflow が durable
  lifecycle evidence を必要とするときだけ、既存 owner route で用意します
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
| `implementer` | `worker` by default; the selected typed route may supply `spark_worker` for a bounded slice, with actual tool-result evidence. Both roles may commit/push and return local head/check evidence; publisher/pr-processing owns Issue/PR writes and integration_executor owns merge/conflict resolution. |
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
  - README、workflow、guide、migration、specification など file responsibility が一般説明 prose の文書を、既存の根拠と reader-facing roadmap に基づいて直接執筆・改稿する。graph 分析は明示依頼または具体的な診断目的がある場合だけ選択する
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
  - Python diff の型、API境界、親 packet が選択した validation evidence を review する。validation scope は [python-review.md#Validation selection](../skills/python-review.md#validation-selection) と [agent-orchestration.md#Write-Capable Handoff Validation Trust Boundary](../skills/agent-orchestration.md#write-capable-handoff-validation-trust-boundary) を参照し、reviewer が追加の full suite を選択しない
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

## Role Selection by Need

次の表は役割を選ぶための候補です。固定された実行順序、task stage、wave、
全候補の起動を要求しません。具体的な owner、task request、Skill link、
実際の依存・write conflict に基づいて必要な role だけを選びます。

| 作業・確認事項 | role candidates |
| --- | --- |
| 要件 / intake | `requirements_organizer`; local precedent は `explorer` |
| external research / literature | `literature_researcher` |
| execution plan が有用な作業 | `execution_planner`, 必要な場合 `plan_reviewer` |
| detailed design と独立した design review | `detailed_designer`, `detailed_design_reviewer` |
| general prose / academic writing | `long_form_writer`; 選択した writing Skill に従う |
| document flow / citation / notation / logic | 対応する reviewer を具体的な reader risk に応じて選択 |
| implementation | `worker` を既定候補とし、選択された role/profile binding に従う |
| implementation後に未解決の test oracle がある | `test_designer` |
| changed-path / claim / science / report review | 該当する `agents_config.json` role owner |
| final release decision | `ship_reviewer` |

Configured role/model data defines the available candidates. It does not itself
launch work or require a particular sequence.
運用ルール:
- role ごとの詳細な実行制約は `.codex/agents/*.toml` を見ます
- この文書では route と inventory だけを決め、各 role の詳細条件は `.codex/agents/*.toml` に集約します
- parent は担当を実際の責務単位で選び、起動した role とその実結果を記録します。固定された実行順や全候補の起動は要求しません。
- subagent を起動するときは、選択された role の既存 prompt contract と [agents/COMMUNICATION_PROTOCOL.md](../COMMUNICATION_PROTOCOL.md) の context boundary を使います。関連 Markdown link は条件付き案内であり、全リンク先を読む義務にはしません
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
- math writer の handoff は `--math-intent-packet '<JSON>'` から作られ、必要な数理
  intent と write scope を実際の child に渡します。math writer の
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

- parent は選択済み writer handoff で各 writer の allowed path / directory を管理します
- write-capable handoff は `writer_target`（絶対 `checkout_root`、固定 `branch`、正規化済み `remote`、`allowed_paths`）を必須とし、branch は handoff 前に `repository-topic-clone.prepare` で用意します
- 同じ `checkout_root` で write target が衝突する作業は同時に起動せず、reader は同じ checkout を共有できます
- `repository-topic-clone.prepare` は選択済み mode の prepared checkout の ignored `.agent-canon/writer-target.json` に target と検証済み checkout identity を materialize します。PreToolUse はこの packet を正本として読み、環境変数は readback 一致確認に限って使い、modified path が `allowed_paths` の外なら拒否します。packet が無い checkout や packet 自身の変更は拒否し、read-only command はこの writer path gate の対象外です
- repository write は `worker`、`spark_worker`、`integration_executor` の各 write-capable route に限定します。IssueWorker の `publisher` は外部 GitHub publication 専用で target を持たず、reviewer と artifact-only role は read-only とします
- 同一 path、同一 directory ownership、同一 public API surface、shared Git index/HEAD、generated output、formatter output は順序制約つきの writer に割り当てます
- write-capable subagent instance を並行させる場合は、checkout roots と write targets の衝突を避けます
- same directory / same file / same canonical surface を同時に変更せず、衝突する作業は必要に応じて順に行います
- 独立した writer は checkout owner が用意した distinct checkout roots を使えます
- checkout の分離は通常の衝突回避を手動で行うためではなく、repository-topic lifecycle が親/同一 repository の `linked-worktree` または dependency repository の `independent-clone` として選択した独立 workstream に限ります
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
- review / quality-check role TOML は Luna/high を使い、hypotheses を decision-owning reviewer または ship reviewer へ返します。reviewer が current snapshot、reachable path、contract、witness/static proof を確認して accept / reject を adjudicate し、integration executor / publisher が edit / rollback / publication route を担当します。`ship_reviewer` は明示された final escalation の候補です
- Spark model は `spark_worker` の低遅延 implementation loop に集約し、repo inventory、tool drift survey、machine-report / experiment-log summarization、execution-only experiment / log work は Luna/high の通常 role に置きます。mini/medium は明示的な T14 skill validation の `skill_evaluator` に限ります。
- 明示 spawn 許可がある repo-changing task では、coding / implementation / patch / doc-edit work の実装に必要な根拠を揃えてから、次の判断を変える独立検証だけを Luna review child へ切ります。各 replaceable responsibility は一つの owning review で足り、文書 flow、requirements / plan、report traceability、research perspective は distinct unresolved claim / risk があるときだけ追加します。
- coding / implementation / patch / doc-edit work は、selected typed route の write-capable handoff と既存 readback を消費します。prompt-only bounded route は child を必要とせず、coordination route の parent/child ownership は上記の selected workflow owner に従います。
- cross-module 整合、API shape、命名 / 責務境界、依存再構成、安全性、性能、conflict resolution のいずれかが入った時点で `worker` または設計 review へ戻します
- Terra は canonical 登録された conditional read-only cross-cutting specialist candidate であり、always-on role ではありません。multi-owner dependency closure、compaction・long-run・incomplete handoff の context reconstruction、または複数案・finding の contradiction validation の evidence がある場合だけ active にし、evidence なしには選択しません。coordinator や general worker としては使わず、capability は `cross_owner_integration`、`context_reconstruction`、`adversarial_contradiction_validation` に限定します。
- ユーザーが提示した alternative architecture、または既存 finding に含まれる alternative は adversarial comparison の入力として Terra に渡せます。Terra 自身による未要求の新規案生成、architecture の採用、final decision は行いません。
- Terra の handback は owner closure と context capsule を含め、unresolved は Sol parent へ返します。
- `document_flow_reviewer` は README / workflow / guide / design doc / paper、新用語、公開 API、reader-facing docs があるときに起動します。code-only owner-bounded change では省略できます
- change-review decision が active のときは `diff_triage_reviewer` を既定 executable とします。`python_reviewer` / `cpp_reviewer` は changed-path evidence、parent packet evidence、または明示 review-pack activation で追加し、`reviewer` は broad diff / cross-surface / clause coverage に上げる場合だけ使います

## Research Perspective Review Pack

- default triage は `reproducibility_reviewer` に provenance、seed、command、environment、rerunability を見させ、`artifact_reviewer` に code、script、raw result、environment、artifact package の十分性を見させる
- benchmark protocol がある場合だけ `benchmark_reviewer` を追加します
- dataset / result path / metadata が中心の場合だけ `fair_data_reviewer` を追加します
- ML claim / uncertainty / limitation が中心の場合だけ `ml_science_reviewer` を追加します
- workflow / prototype discipline が論点の場合だけ `scientific_computing_reviewer` を追加します
- full pack は `research_perspective_review` を明示したとき、または triage が methodology / benchmark / FAIR-data / ML-science / scientific-computing risk を返したときだけ起動します
- decision-owning reviewer が findings を `fix now`、`follow-up`、`delete-ok`、`rejected` に adjudicate して handoff を返す。`rejected` finding は修復や rollback を起こしません

## Runtime Surfaces

- human routing and inventory canon: `agents/`
- permanent team ownership and write policy: `agents/agents_config.json`
- skill shim: `.codex/personal/skills/`
- Codex project config: `.codex/config.toml`
- generated Codex subagent readback views: `.codex/agents/*.toml`

設定運用メモ:
- role ownership や required output を変えるときは `agents/agents_config.json` を更新します
- project subagent registration と runtime limits を変えるときは
  `.codex/config.toml`、role model / reasoning を変えるときは
  `agents/model_profiles.toml` を更新して canonical materializer を実行します
- role-specific profile/instruction 条件は `agents/model_profiles.toml` の owner
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
  作り、各 perspective review artifact が実際に生成される
Role and profile selection is owned by the canonical model/profile registry and
the selected workflow. Sol is the parent; Luna owns ambiguous design, causal
repair, cross-owner integration, and review; Spark is an implementation option;
and `skill_evaluator` is selected for explicit empirical evaluation. Model and
profile policy stays out of `route.py`.

Use native tool results as the evidence of what ran and whether it succeeded;
preserve actual failures rather than inferring success from a plan or monitor.
Existing Eval or owner review can assess whether necessary work was missed or
unnecessary work was done. A different route alone is not a failure.

## Capacity And Lifecycle

Use the selected runtime's actual capacity information when it affects the
chosen work. For child work, retain actual launch, completion or failure, and
handoff evidence in the selected workflow's existing record; a monitor status
alone does not establish completion.
