# subagent-bootstrap
<!--
@dependency-start
contract skill
responsibility Documents subagent-bootstrap for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../COMMUNICATION_PROTOCOL.md defines pre-edit tool rejection handoff fields
upstream design ../internal-routines/subagent-startup.md owns the canonical private subagent startup route
@dependency-end
-->


## Reader Map

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
goal-driven task では、write-capable implementation subagent は `goal.md` が parseable で、Codex goal view が mirrored / queued され、Plan-mode evidence mapping が揃うまで起動しません。
通常の repo-changing task で coding / implementation / patch / doc-edit work が scope に入る場合は、この goal-driven `goal.md` block を適用しません。semantic handoff が dependency-expanded scope、validation route、必要な owner-critical gate を閉じたら、launchable な write-capable implementer を起動または schedule します。read-only wave は setup evidence であり、実装を遅らせる固定 intake ではありません。
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
