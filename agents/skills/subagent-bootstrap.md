# subagent-bootstrap
<!--
@dependency-start
contract skill
responsibility Documents subagent-bootstrap for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../COMMUNICATION_PROTOCOL.md defines pre-edit tool rejection handoff fields
upstream design ../internal-routines/subagent-startup.md owns the canonical private subagent startup route
upstream design ../internal-routines/design-implementation-correspondence.md clause fingerprint and implementation handoff correspondence route
upstream design ./direct-luna-communication.md direct Luna packet exchange and acknowledgement
@dependency-end
-->


## Reader Map

write-capable handoff の design context には、routine が発行した design
locator、design digest、clause IDs/fingerprints、forward/reverse validation
refs を参照として含めます。この skill は handoff lifecycle を owner とし、
対応 policy を再掲しません。

- Purpose: create run bundles and bounded subagent handoffs without losing role,
  write-scope, validation, and review evidence.
- Section path: Purpose, Use When, and Core References introduce the route;
  Standard Command contains the bootstrap commands and handoff rules;
  Subagent Return Investigation covers missing or stalled subagent returns.
- Use when: a task needs specialist delegation, reviewer/implementer separation,
  explicit wave records, or write-capable handoff packets.
- Boundary: this skill owns launch mechanics and evidence; workflow family
  selection stays with `agent-orchestration` and role behavior stays with
  `.codex/agents/*.toml`.
- Model names: `.codex/config.toml` owns the `gpt-5.6-sol/high` parent;
  `.codex/agents/*.toml` owns each child model and effort.

## Purpose

specialist delegation が必要な task で、run bundle、役割分担、write-scope を崩さずに起動します。
この skill は launch mechanics の正本であり、workflow family の選定や prompt /
config policy の第二の正本にはしません。

## Use When

- run artifact を残したい
- specialist を使う
- reviewer / implementer の責務を分けたい
- 計画レビュー agent、詳細設計レビュー agent、文書通読レビュー agent を分けたい
- `/goal` 確定前に read-only subagent、または明示許可待ちの handoff plan で goal draft、repo survey、first-slice plan を固めたい
- prompt、routing、subagent-config drift の修正前に dedicated prompt-audit subagent を挟みたい
- repo-changing implementation / patch / doc-edit work で、parent が
  orchestrator / integrator に徹し、write-capable subagent handoff を既定 route
  にする必要がある

## Core References

- `agents/TASK_WORKFLOWS.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `agents/skills/direct-luna-communication.md`
- `agents/internal-routines/subagent-startup.md`
- `tools/agent_tools/bootstrap_agent_run.py`

## Standard Command

Use this command only when coordination, cross-agent transfer, or resumption
needs a durable run bundle. A repo-changing request by itself does not require
one; a complete structured handoff message or tool result can satisfy the
handoff contract.

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "repo-changing task" \
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

包括的開発:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

repo-changing task では、`--task-id` は catalog の候補を参照するだけです。
specialist と review pack は owner-critical decision、artifact operation、
または selected review gate が必要な場合だけ有効化します。
handoff / capsule fields の正本は `agents/COMMUNICATION_PROTOCOL.md` です。この skill は launch timing、role selection、wave ledger、authorization、closeout mechanics を所有し、capsule field list を第二の正本にしません。
subagent-only startup / internal skill routes are owned by `agents/internal-routines/subagent-startup.md`. Bootstrap cites that routine and carries `run.subagent_prompt_packet.subagent_startup_route` into handoff routing when present; it does not add `_...` labels to public skill routing or duplicate the capsule schema.
prompt / routing / subagent-config drift を直す task では、shared policy prose を
直接広く書き換える前に `prompt_config_reviewer` を prompt/config audit wave として起動し、
対象 surface は route seed として扱い、責務検索、再利用確認、stale surface scan、dependency expansion を通して handoff scope へ落とします。
goal-driven repo-changing task では、coordination/resumption が必要な場合にだけ
provisional run bundle を作ります。planned wave は launchable な owner,
context, write authority, validation route, and review gate が揃ったものだけ
materialize し、authority-blocked or conditional work を予定行として先に積みません。
catalog の `manager`、`explorer`、`execution_planner`、`plan_reviewer` は候補であり、
owner-critical evidence がある場合だけ起動します。
goal-driven task でも repository mirror file を readiness gate にしません。semantic handoff、または選択された run bundle が dependency-expanded scope、validation route、必要な owner-critical gate を閉じたら、launchable な write-capable implementer を起動または schedule します。read-only wave は setup evidence であり、実装を遅らせる固定 intake ではありません。
active runtime が explicit user request なしの `spawn_agent` を禁止する場合、read-only pre-goal wave も即座には起動せず、handoff packet、owner、expected output、`PRE_GOAL_SUBAGENT_AUTHORIZATION=required` を run bundle に残して許可待ちにします。
command output の generated model/profile view と `IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker` を確認します。implementation-executable handoff は semantic decision sufficiency が mechanism と validation route を閉じた場合だけ materialize し、post-completion gate は実際に選択された owner gate だけを続けます。
subagent の model / reasoning は該当 `.codex/agents/*.toml` を先に読みます。
read-only exploration に切る前に、その質問を所有する checker、router、semantic index、dashboard があるか確認し、ある場合は tool を先に呼びます。subagent は structured tool artifact が曖昧な場合の解釈や、tool-covered ではない judgement の独立 review に使い、同じ文書を読み直して決定論的 check を反復しません。
repo inventory、tool drift survey、機械 report 要約、experiment/log execution は、implementation の critical path を塞がない独立検証または実験実行として Luna/high の通常 role に切ります。mini/medium は明示 T14 `skill_evaluation` の fresh read-only artifact-only `skill_evaluator` に限り、permanent team role にはありません。static validation triage、diff-local Python / C++ review、bounded review、report traceability、checklist-style review gate は、該当 decision があるときに一つの accountable `gpt-5.6-luna/high` review role へ切ります。writer と owner gate/review は、semantic decision と selected validation route が要求する場合だけ分けます。parent-direct は explicit approval、spawn authorization blocker、または tool-gate blocker を記録した exception route です。
- fixed packet の worker substitution、smaller slice、speculative test、repeated preflight、rollback checkpoint、compatibility fallback は禁止します。compile/static failure は `ImplementationFeedback`、exact target contradiction は一度の `StructuralDesignGap` と同じ Spark の resume です。
選択済み candidate が起動できない場合は local/tool context に `selected_agent_type`、`write_capable_handoff_blocker`、`evidence`、`parent_packet_ref`、`status=blocked` を記録します。candidate を変える場合は explicit revised parent packet と wave を必須にします。`skill_evaluator`、実験実行 role、または review role の起動失敗は、同じ role packet と該当 `.codex/agents/*.toml` の `model` / `model_reasoning_effort` で原因を切り分けます。
command output の `WORKFLOW_SUBAGENT_PROMPT_PACKET` を確認し、すべての subagent handoff prompt は `agents/COMMUNICATION_PROTOCOL.md` の `Context Visibility Contract` と `Fresh Subagent Context Capsule` を満たすように、`team_manifest.yaml` の `run.subagent_prompt_packet` と該当 role の `prompt_contract` から selected fields だけを入れます。full packet、raw stdout、raw logs、broad chat summary は prompt に貼りません。
固定の `STANDARD_AGENT_WAVE_SEQUENCE=selected_stages_only` を completion 条件にしません。
各 wave は owner-critical な plan、review、edit のうち実際に必要な stage だけを
記録し、未選択 stage の artifact を作りません。
command output の `DEFAULT_QUALITY_CHECKS=candidate_only`、
candidate role / agent-type lines を確認し、
review と edit の handoff では `team_manifest.yaml` の
`run.default_quality_check_policy` を含めます。
handoff prompt には repo root や `/workspace` 全体ではなく、dependency-expanded `allowed_paths`、該当 canon 節、`do_not_read` surface、expected output schema を含め、context artifact は `agents/COMMUNICATION_PROTOCOL.md` が定義する capsule で参照します。implementation handoff では implementation-surface router の `PRIMARY_PATHS` を `allowed_paths` の seed、`FORBIDDEN_PATHS` を `do_not_read` の seed にし、router が unavailable なら deterministic router recovery output を local provisional source-packet evidence として保持するか `router_unavailable_blocker` を記録します。この evidence は新しい candidate や public route を自動選択せず、responsibility search と dependency scope で handoff path を確定するための local/tool context に限定します。`allowed_paths` は手書き対象だけで閉じず、編集候補、検索 hit、checker finding、changed path を seed に dependency header graph で再帰展開した `dependency_edit_scope.txt` / `dependency_graph.tsv` を優先します。full tree search、raw accumulated logs、unrelated module scan が必要になった場合は、parent へ escalation して input packet を拡張してから進めます。
theorem-driven、algorithm、implementation handoff では、protocol-owned `Target Binding Packet` を Fresh Subagent Context Capsule に必ず入れます。packet が不完全な場合は subagent を起動せず、parent が capsule または source packet を補完します。subagent から返った unchecked theorem sketch、型が合っていない式、public root への到達が示されていない local counterexample、または code suggestion は、親が同じ public root に対する checker / validation route を通すまで採用しません。
write-capable subagent へ渡す前に `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` を走らせるか明示引用し、`TOOL_REJECTION_PREDICTED_GATE`、`rejection_preflight_command`、gate-specific repair plan を handoff に含めます。Hook / Tool / SKILL / workflow / protocol surface では、予測 gate が `agentcanon_new_tool_source_route`、`codex_hook_runtime_alignment`、`tool_catalog`、`agent_protocol_convention`、`log_surface_inventory_guard` を出す場合があるため、対応 command を実装前の必須 evidence として渡します。既存 AgentCanon tool source はこの新規 source route gate では止めません。
設計解釈、衝突解決、広い architecture 判断、scope 判断を含む implementation は `worker` に戻します。
write-capable coding / docs-edit subagent を authorization または tool gate で起動できない場合は、`WRITE_SUBAGENT_AUTHORIZATION=required` または gate-specific blocker を run bundle に残し、その slice について read-only 分析を増やし続けません。parent-direct へ切り替える場合は、blocked subagent route、exception rationale、owner boundary、targeted validation を同じ run bundle に残します。
独立 workstream が複数ある場合は、workstream ごとに stage owner を置き、`run.delegated_spawn_policy` の下で vertical dynamic wave を起こします。同じ parent wave へ全 role を flat に詰め込むのは避け、入力 packet、write scope、validation route、review gate が交差しない sibling wave だけを同時に走らせます。
log-analysis 由来の wave は `agent-log-analysis` の `Finding Route Packet` を
input にします。`finding_class` が `wave_execution`、`skill_selection`、
`workflow_attribution`、`eval_gap`、`archive_hygiene`、`prompt_or_config_drift`、
または `structure_boundary` のときは、その route target を stage owner とし、
parent は launch mechanics、budget、fresh lifecycle、wave ledger の整合だけを持ちます。
同じ role を複数起動する場合は、`instance_partition` を
`repo_key`、`hook_family`、`skill_name`、`workflow_name`、`issue_id`、
または path scope で分けます。instance id は
`<role_type>:<repo_key>:<finding_class>:<partition>:<seq>` を推奨形にします。
parent または delegated stage owner が実際に spawn / skip / replacement を行ったら、`python3 tools/agent_tools/workflow_monitor.py --subagent-wave ...` で `schedule.md` と `workflow_monitoring.md` を同じ `wave_id` で更新します。delegated child wave は `remaining_spawn_budget` を必ず含めます。
Wave は「最初に決めた agent 数を一度だけ走らせる」運用ではありません。
parent は各 wave の出力を frontier queue に戻し、次に必要な bounded handoff を
作ります。compatible な active agent には revised scope を渡し、fresh subagent は
独立 review、disjoint write authority、incompatible owner/context、または failed
context integrity の場合だけ追加します。同じ checker / validation は次の決定を
変える場合だけ再実行します。次 frontier が repository / code / tool action で進む
限り、`unverified_with_next_witness` や `connection_unconnected` を user-facing
停止点にしてはいけません。
validation failure を次 writer に返す場合は、handoff に `failing_contract`、
`observation_level`、`cause_classification`、`intent_preservation`、`evidence`
を含め、pass 目的の単純化、revert、intended behavior / test 削除、
oracle weakening、validation downscope を禁止事項として明示します。
調査、環境変更、学術文章、包括的開発の強い review coverage は task catalog
側の候補として管理します。owner-critical な decision、unresolved branch、または
selected validation route が必要とした場合だけ有効化します。
`test_designer` は default の実装前 gate ではありません。implementer が
owning mechanism を確立または修復した後、static analysis、既存 checker、
targeted validation が所有しない具体的な oracle / specification / regression /
failure-mode risk が parent packet に記録された場合だけ、条件付きで起動します。
risk がない場合は activation decision を記録して test-plan artifact と
test-design tool run を省略し、ordinary code change、bug fix、parser change、
validation failure だけでは起動しません。
contract-only wrapper では checker-owned validation と static contract evidence を handoff に入れます。
T12 の `scheduler`、`schedule_reviewer`、`project_reviewer`、
`docs_workflow_steward`、`prompt_config_reviewer` は候補 specialists です。
owner-critical な責務、unresolved branch、または selected validation route が
有効化した role だけを active にします。change-review decision が active のときは
`diff_triage_reviewer` が既定で、`python_reviewer` / `cpp_reviewer` は changed-path
evidence、parent packet evidence、または明示 review-pack activation がある場合だけ
materialize します。
Codex で planning を含む parent session では、plan-mode command を先に使います。official Codex CLI では `/plan` です。
runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を見ます。
計画、詳細設計、文書通読、学術文章の review は candidate です。選択された review
claims が同じ owner、responsibility、context、write authority、validation route を
共有する場合は active instance を再利用し、独立 review や distinct unresolved
claim/risk のために分ける場合だけ fresh instance を使います。
包括的開発では、parent が `team_manifest.yaml` の write policy で writer ごとの path / directory を管理します。scope が重なる場合は current checkout 内の後続 wave に serialize し、別 `git worktree` へ分けません。
各 user input は `same_active_task_delta`、`scope_or_contract_change`、または
`new_task` として分類しますが、新しい turn や名前を変えた packet だけでは
fresh agent の理由になりません。owner、responsibility、context、write authority、
validation route が互換なら active agent を再利用し、revision scope も同じ責任単位へ
配送します。独立 review、disjoint write authority、incompatible owner/context、または
failed context integrity の場合だけ fresh agent / wave を起こします。coordination または
resumption が必要な場合は checkpoint と updated packet path を durable に残し、それ以外
は structured handoff message/tool result を使います。
subagent handoff prompt には lifecycle decision と fresh-agent 条件を含めますが、
`fresh_subagents_required: true` や `reuse_for_new_task: forbidden` を一律の機械契約には
しません。

Review roles and packs remain candidates until an owner-critical decision or a
distinct unresolved claim/risk activates them. Keep one owning review gate per
replaceable responsibility. Reviewer output is hypothesis input only: the
parent/integration owner accepts it only with current-snapshot, reachable-path,
contract, and witness/static-proof evidence. Rejected hypotheses carry
`reason_code` and `evidence_ref` for stale, unreachable, private/incidental,
duplicate, already-covered, evidence-free, out-of-scope, or unproven-design
conflicts; they do not start a wave or authorize rollback.

## Subagent Return Investigation

すべての非終端 subagent について、`wait_agent` timeout は polling boundary
であり lifecycle deadline ではありません。各 blocking poll は
`timeout_ms <= 60000` とし、全体の completion wait は required user-facing
progress update と既存の new-state / revised-packet gate を各 poll 間で
満たす bounded poll の反復として継続できます。timeout、empty update、
応答遅延だけを理由に interrupt または cancellation を行ってはいけません。
操作前に active runtime の status、message、interrupt、close capability を
確認します。この runtime では非割込みの status 確認に `list_agents`、同一
task の packet 配送に `send_message` を使い、`interrupt_agent` は user の
明示取消後に限ります。利用不能な `send_input(interrupt=...)` または
`close_agent` operation を作り出してはいけません。

bounded poll の timeout、empty status、または wave decision point での
final response 未着は `subagent_no_return_investigation` として扱います。parent は
agent id、wave id、wait command と timeout、last known status、last
workflow-monitor event、runtime / tool error、log / dashboard pointer、cause
hypothesis を `workflow_monitoring.md` と closeout evidence に残し、現在の status
と回収済み evidence を記録して parent decision point へ control を戻します。

同種の wait または status probe を再度実行するには `new state evidence`
または `explicit revised packet` を必須にします。scope、allowed paths、
owner、review gate が変わる場合は explicit revised packet を記録した
fresh follow-up wave へ切り替えます。timeout、empty status、final response
未着は `termination_action=preserve_running_instance` と
`resolution_decision=await_new_state|continue_disjoint_parent_work` に写像します。
prior agent が非終端なら `write_scope=reserved` と
`overlapping_writer=blocked` を保持します。

active runtime に close operation がある場合だけ、runtime status
`completed|errored|shutdown` または user の明示取消後にその operation を
使います。active runtime に close operation がない場合は terminal status が
観測されるまで instance を保持し、closeout_gate.md の Subagent Lifecycle
Evidence に `runtime_no_close_operation:terminal_status_observed` を記録します。
非終端の no-return instance は
`subagents_closed=no`、`lifecycle_gate=pending` とします。

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read `agents/skills/subagent-bootstrap.md`.
1. Read `agents/canonical/CODEX_SUBAGENTS.md`.
1. Read `agents/skills/direct-luna-communication.md` when the selected execution
   profile is Luna, and require its effective model / effort readback before
   admitting work.
1. Read `agents/internal-routines/subagent-startup.md` before preparing
   subagent-only startup or internal skill route handoffs. The canonical private
   startup route is `agents/internal-routines/subagent-startup.md`; historical
   startup labels are not public skills or accepted route aliases.
1. Treat `agents/COMMUNICATION_PROTOCOL.md` as the single owner of handoff and
   capsule fields. This skill owns launch timing, role selection, wave ledger,
   authorization, and closeout mechanics; it does not create a second capsule
   schema.
1. For repo-changing tasks, create or inspect a run bundle only when
   coordination, resumption, or the selected workflow needs durable lifecycle
   evidence. A semantically complete structured handoff can satisfy the packet
   contract.
1. For goal-driven repo-changing tasks, materialize a provisional intake wave
   only when its owner-critical evidence can change the next decision. The
   catalog `manager`, `requirements_organizer`, `explorer`, `execution_planner`,
   and `plan_reviewer` roles remain candidates until activated.
1. For goal-driven and ordinary repo-changing coding, implementation, patch, or doc-edit work, use the same readiness boundary. After the structured handoff or, when selected, the run bundle and pre-handoff investigation packet derive dependency-expanded handoff scope, validation plan, and tool-rejection preflight evidence, launch or schedule the selected write-capable implementer; do not wait for a repository mirror of session goal state. Read-only waves are setup evidence, not a substitute for the implementation handoff. The parent remains orchestrator / integrator and does not become the default implementer.
1. If the active runtime requires explicit user authorization before `spawn_agent`, do not silently spawn even read-only pre-goal agents. Record the fan-out plan, handoff packets, and `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` in the run bundle, then wait for or request authorization.
1. Use `--task-id` when the selected route needs catalog evidence; task-default
   specialists and review packs are candidates, not automatic work.
1. Keep one owning review gate for one replaceable responsibility. Reuse an active
   compatible review instance; create a separate instance only for independent
   review, disjoint authority, incompatible owner/context, or a distinct unresolved
   claim/risk that the owning gate cannot judge.
1. Check the command output for `IMPLEMENTATION_CODEX_AGENTS` when an
   implementation wave is selected.
1. Treat `STANDARD_AGENT_WAVE_SEQUENCE=selected_stages_only` as a candidate
   projection, not a mandatory plan-review-edit sequence.
   Record only selected plan, review, or edit evidence; no fixed sequence creates
   an unselected stage.
1. Check the command output for `DEFAULT_QUALITY_CHECKS=candidate_only`,
   `DEFAULT_QUALITY_CHECK_ROLES`, and `DEFAULT_QUALITY_CHECK_AGENT_TYPES`.
   Review and edit handoffs include `team_manifest.yaml`
   `run.default_quality_check_policy`.
1. Require `IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker`; `worker` is the default. Select `spark_worker` only when the parent packet supplies `--select-agent-type implementer=spark_worker:<evidence>`, and require the selection in `SUBAGENT_AGENT_TYPE_SELECTIONS` and `team_manifest.yaml`.
1. Resolve logical role, selected Skills, execution profile, and authority as separate fields. When the selected profile is Luna, use `$direct-luna-communication` with a direct `gpt-5.6-luna` override and do not require or select a role-specific physical alias. Read `.codex/agents/<role>.toml` only when a capability-specific or compatibility route explicitly selects that executable view.
1. Before assigning read-only exploration, run the canonical checker, router, semantic index, or dashboard when one owns the question. Use subagents to interpret ambiguous structured tool artifacts or independently review non-tool-covered judgment, not to repeat deterministic tool checks by reading the same documents.
1. For repo inventory, tool drift survey, machine-report summarization, and experiment/log execution, use the ordinary `gpt-5.6-luna/high` roles when they are independent verification or bounded execution that does not delay the implementation critical path. Reserve `gpt-5.4-mini/medium` for the fresh, read-only, artifact-only `skill_evaluator` in explicit T14 `skill_evaluation`; it is absent from permanent team roles.
1. For static validation triage, diff-local Python / C++ review, bounded review, report traceability, and checklist-style review gates, select one accountable `gpt-5.6-luna/high` review role for the active decision; use `gpt-5.6-luna/xhigh` only for `ship_reviewer` findings.
1. For coding / implementation / patch / doc-edit requests, describe the default route as write-capable handoff first. Once route seed, responsibility search, reuse survey, stale-surface scan, dependency expansion, validation plan, and tool-rejection preflight produce a handoff packet, schedule or launch the selected write-capable implementer; parent owns the handoff packet, integration order, review gate, and final responsibility.
1. Treat a bounded implementation slice as `spark_worker` eligible only when it is derived from the Abstract Design Frame and is one file or one abstraction unit, public interface unchanged, no dependency change, no specification interpretation, and locally testable. Eligibility does not replace the explicit typed parent-packet selection.
1. Keep every handoff packet owned after discovery: include dependency-expanded `allowed_paths`, relevant canon sections, explicit `do_not_read` surfaces, and expected output schema, with context artifacts referenced through the protocol-owned capsule. Use `/workspace` or the repo root only as workspace identity, then derive handoff scope from route seed, responsibility search, reuse survey, stale-surface scan, and dependency expansion. For implementation handoff, seed `allowed_paths` from implementation-surface router `PRIMARY_PATHS` and `do_not_read` from `FORBIDDEN_PATHS`; if the router is unavailable, retain deterministic router recovery output only as local provisional source-packet evidence or record `router_unavailable_blocker` before handoff. This evidence does not select a new candidate or public route; confirm the handoff paths through responsibility search and dependency scope.
1. For a fresh launch, build the `Fresh Subagent Context Capsule` through
   `agents/COMMUNICATION_PROTOCOL.md` and its `Context Visibility Contract`.
   Reuse an active agent when owner, responsibility, context, write authority,
   and validation route remain compatible, including revised scope. New turns or
   renamed packets alone do not require fresh launch. Keep full packets, raw
   stdout, raw logs, broad chat summaries, and full dashboards in local/tool
   context by path instead of pasting them into the prompt.
1. When `team_manifest.yaml` provides
   `run.subagent_prompt_packet.subagent_startup_route`, carry that structural
   route field into the handoff packet and downstream review result. Do not
   convert it into prompt keyword routing, public `ACTIVE_SKILLS`, or a
   duplicated capsule schema.
1. For theorem-driven, algorithm, or implementation handoffs, include the
   protocol-owned `Target Binding Packet` in the capsule before spawning. If the
   packet is incomplete, repair the capsule or source packet first. A subagent's
   unchecked theorem sketch, type-incompatible formula, local counterexample, or
   code suggestion is not an implementation instruction until the parent has run
   the stated checker / validation route and confirmed it targets the same public
   root.
1. Build `allowed_paths` from dependency headers when possible: expand edited paths, search hits, checker findings, or changed files through `run_repo_dependency_review.sh` and pass `dependency_edit_scope.txt` / `dependency_graph.tsv` instead of only a hand-written file list.
1. If the selected candidate cannot launch, record local/tool evidence with `selected_agent_type`, `write_capable_handoff_blocker`, `evidence`, `parent_packet_ref`, and `status=blocked`; changing candidates requires an explicit revised parent packet and wave.
1. Send broad implementation, design interpretation, conflict resolution, or architecture-sensitive work to `worker`.
1. For T12, treat `scheduler`, `schedule_reviewer`, `project_reviewer`,
   `docs_workflow_steward`, and `prompt_config_reviewer` as candidates. Activate
   only owner-critical roles or roles selected by the validation route. When the
   change-review decision activates, use `diff_triage_reviewer` as its default
   executable; materialize `python_reviewer` / `cpp_reviewer` only from
   changed-path evidence, parent packet evidence, or explicit review-pack
   activation.
1. If a write-capable coding / docs-edit subagent cannot be launched because authorization or tool gates are missing, record `WRITE_SUBAGENT_AUTHORIZATION=required` or the gate-specific blocker in the run bundle and stop expanding read-only analysis for that slice. Parent-direct is allowed only as a recorded exception with blocked route, exception rationale, owner boundary, and targeted validation.
1. Default to one writer in the current checkout. If multiple writers are necessary, use them only when `team_manifest.yaml` fixes dependency order, wave plan, disjoint write scope, integration order, and review gate; colliding writers are serialized into later waves in the current checkout instead of split into separate worktrees.
1. For multiple independent workstreams, schedule a stage owner per workstream and let that owner create a vertical dynamic wave under `run.delegated_spawn_policy` instead of flattening every role into one parent wave. Only sibling waves with disjoint input packets, write scopes, validation routes, and review gates may run together.
1. For log-analysis-driven launches, require the `Finding Route Packet` from `agents/skills/agent-log-analysis.md`. Use `finding_class` to choose the destination owner and `instance_partition` to shard same-role instances by `repo_key`, `hook_family`, `skill_name`, `workflow_name`, `issue_id`, or path scope.
1. For same-role log-analysis instances, use an id shaped like `<role_type>:<repo_key>:<finding_class>:<partition>:<seq>` and give each instance its own structured evidence cell, allowed paths, expected output, validation route, and review gate.
1. After the parent or delegated stage owner actually spawns, skips, or replaces a wave, record it with `python3 tools/agent_tools/workflow_monitor.py --subagent-wave ...`; delegated child waves must include `remaining_spawn_budget`.
1. Treat a wave as an adaptive loop, not a fixed one-shot fan-out. The parent integrates each wave result, reruns the same checker / validation route, turns remaining frontier rows into the next bounded handoff queue, and spawns fresh follow-up agents when repository / code / tool action can advance the frontier. Do not return `unverified_with_next_witness`, `connection_unconnected`, or bridge gaps as user-facing stopping points while the next frontier can still be worked.
1. When returning a validation failure to the next writer, include
   `failing_contract`, `observation_level`, `cause_classification`,
   `intent_preservation`, and `evidence` in the handoff, and forbid pass-only
   simplification, revert, intended behavior/test deletion, oracle weakening,
   or validation downscope.
1. Classify each user input as `same_active_task_delta`, `scope_or_contract_change`,
   or `new_task`, but do not start fresh solely because the turn or packet name
   changed. Reuse an active agent when owner, responsibility, context, write
   authority, and validation route remain compatible. Start a fresh agent/wave
   only for independent review, disjoint write authority, incompatible
   owner/context, or failed context integrity. Durable checkpoint and updated
   packet paths are required only for coordination or resumption.
1. When context changes mid-task, update the capsule artifact path and send that path; do not append unbounded chat summaries to old handoff prompts.
1. Include the selected lifecycle decision and fresh-agent conditions from
   `team_manifest.yaml` in handoff prompts; do not require
   `fresh_subagents_required: true` or `reuse_for_new_task: forbidden` as
   universal values.
1. For every nonterminal subagent, treat a `wait_agent` timeout as a polling boundary rather than a lifecycle deadline. Each blocking poll must use `timeout_ms <= 60000`; an overall completion wait may span repeated bounded polls, with required user-facing progress updates and the existing new-state or revised-packet gate between polls. A timeout, empty update, or slow response alone never authorizes interruption or cancellation. Resolve the active runtime's status, message, interrupt, and close capabilities before acting: in this runtime, use `list_agents` for noninterrupting status inspection, `send_message` for same-task packet delivery, and `interrupt_agent` only after explicit user cancellation. Do not invent unavailable `send_input(interrupt=...)` or `close_agent` operations.
1. If a bounded poll times out, returns empty status, or a run-local subagent has no final response at a wave decision point, record `subagent_no_return_investigation` with agent id, wave id, wait command and timeout, last known status, last workflow-monitor event, runtime or tool error, log / dashboard pointers, and cause hypothesis. Record the current status and recovered evidence, then return control to the parent decision point. Another wait or status probe requires `new state evidence` or `explicit revised packet`; scope, owner, allowed-path, or review-gate changes require a fresh follow-up wave from that packet. Map timeout, empty status, and absent final response to `termination_action=preserve_running_instance`, `resolution_decision=await_new_state|continue_disjoint_parent_work`, `write_scope=reserved`, and `overlapping_writer=blocked`.
1. Before assigning write-capable work, run or cite `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and include `TOOL_REJECTION_PREDICTED_GATE` lines, `rejection_preflight_command`, and the gate-specific repair plan in the handoff. Treat hook runtime, skill mirror sync, tool catalog, agent protocol convention, and log-surface inventory gates as implementation blockers until the repair command is run or explicitly scheduled in the same handoff.
1. Use an active runtime close operation only when that capability exists and the runtime reports `completed|errored|shutdown`, or after explicit user cancellation. When the active runtime provides no close operation, preserve the instance until a terminal status is observed and record `runtime_no_close_operation:terminal_status_observed` as `Subagent Lifecycle Evidence` in `closeout_gate.md`. A nonterminal no-return instance records `subagents_closed=no` and `lifecycle_gate=pending`.

- Purpose: runtime skill for preparing specialist delegation, run-bundle
  bootstrap, stage subagents, and Codex implementation routing.
- Use When: a task needs a fresh subagent, explicit handoff packet, wave ledger
  update, or write-capable implementation routing. Compatible active agents may
  be reused for revised scope.
- Tool Commands: run this skill's command packet, then read the canonical
  `agents/skills/subagent-bootstrap.md` route before spawning or recording waves.
- Boundary: do not spawn or reuse agents without bounded scope, validation
  route, review gate, and lifecycle evidence.
