# agent-orchestration

<!--
@dependency-start
contract skill
responsibility Documents agent-orchestration for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../workflows/hypothesis-validation-workflow.md analysis-prioritized overlay routing
upstream design ../COMMUNICATION_PROTOCOL.md pre-edit investigation and fresh subagent context packets
upstream design agent-orchestration.execution-contract.toml machine-readable execution contract
upstream design ./skill-dependencies.yaml typed public-skill prerequisites, successors, ordering, and parallel relations
downstream implementation ../../tools/agent_tools/check_execution_time_aware_orchestration.py execution contract checker
downstream implementation ../../tools/agent_tools/skill_route_catalog.py derives canonical invocation order
downstream implementation ../../tools/agent_tools/skill_dependency_map.py validates and projects the dependency graph
@dependency-end
-->

## Reader Map

- Purpose: mandatory repository-task routing that selects workflow family,
  active skills, roles, reviews, run bundle, and implementation route.
- Section path: Purpose, Use When, and Core References orient the reader;
  Decision Order and the Execution-Time-Aware Work-Conservation Contract
  contain the operational rules; Outputs, Workflow Family Mapping, Public
  Skill Selection, Entrypoint Precedence, Review And Specialist Expectations,
  and Codex Implementation Routing define the routing result.
- Use when: starting any repository task or choosing workflow, skill, subagent,
  review, runtime entrypoint, or run-bundle policy.
- Boundary: this skill routes and records the packet; task-specific execution
  stays with the selected workflow and task-shape skills.
- Decision Sufficiency policy and `validate_decision_sufficiency_packet` live
  only in `Decision Sufficiency Packet`; downstream skills and tools preserve
  its verdict without defining a second validator.

## Purpose

task 開始時の mandatory routing skill です。
task を workflow family に分類し、skill set、handoff、review、runtime entrypoint を一貫した形にそろえます。

## Use When

- repository task を開始する
- どの workflow family を使うか決めたい
- skill、subagent、review、model / team policy、run bundle、runtime entrypoint を選ぶ
- prompt、routing、subagent-config の refactor task で、まずどの policy surface を直すか決めたい
- run bundle や review artifact の要否を決めたい
- Codex 内で共通ルールを保ちたい
- repo-wide / multi-surface の repo-changing task で、独立して差し替え可能な作業単位だけを multi-agent wave に切りたい
- user が coding / implementation / patch work の subagent 委譲を明示した
- repo-changing implementation / patch / doc-edit work で、parent を
  orchestrator / integrator として扱う必要がある

## Core References

- `agents/TASK_WORKFLOWS.md`
- `documents/runtime/runtime-profiles-and-check-matrix.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/ARTIFACT_PLACEMENT.md`
- `agents/canonical/CLI_ENTRYPOINTS.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `agents/skills/skill-dependencies.yaml`

## Decision Order

Canonical model/profile selection and ToolCall materialization belong to the
registry/materializer owners, not `route.py`. Sol remains parent; Luna owns
ambiguous design, causal repair, graph-owned cross-owner integration, and
review; Spark is the fixed implementation owner; `gpt-5.4-mini` is
skill-evaluator-only. Decision sufficiency is semantic: execution may start
when owner, replaceable unit, implementation mechanism, validation route, and
the unresolved branch that could change one of those decisions are explicit.
No artifact shape, digest, count, or fixed stage sequence is a substitute for
that decision.

1. 他の task-shape skill を選ぶ前に、この skill で request が `repo-changing execution` か `routing-only/advisory` かを先に分ける
1. owner、edit mechanism、validation action を選ぶ前に semantic decision
   sufficiency を確認する。owner、replaceable unit, implementation mechanism,
   validation route, and any unresolved branch that can change them are the
   minimum decision fields. A structured handoff message or tool result is
   sufficient; create a durable packet only when coordination or resumption
   needs one.
1. repo-changing execution で実装 owner が明示 path と source packet でまだ固定されていない場合は、編集 path を選ぶ前に `python3 tools/agent_tools/search.py --query-file <request.txt> --providers text,semantic,vector,tool,header-deps,code-deps --format json` を走らせる。bounded candidate path を source packet seed にし、owner、responsibility、dependency evidence から `allowed_paths`、`do_not_read`、required checks を導く。deterministic search が失敗した場合は path selection を `router_unavailable_blocker` へ遷移させ、owner、responsibility、dependency evidence が一つの canonical route を示した時点で継続する
1. 広い prose 読み込み、raw log 探索、subagent 起動の前に、その判定を正本として持つ canonical tool があるか確認する。tool-covered surface では tool を先に呼び、pass / finding の structured output を信頼する。ただし tool が返した path は作業 packet であり、`requested_scope` を縮める許可ではありません。owner、依存、downstream、意図的に外す surface を確認し、packet が user request を覆うことを証明してから編集に入ります
1. repo-changing execution で構造、ownership、path selection、stale surface、document responsibility が scope に入る場合は、手作業の広い読み込みより前に `agents/COMMUNICATION_PROTOCOL.md` の `Structure Intake Packet` を作るか引用する。正本の構造読み込み tool は `repo_structure_contract.py`、`responsibility_scope.py`、`file_surface_inventory.py --submodule-aware`、`agent-canon structured-analysis document-inventory`、import boundary が関係する場合の `import_responsibility.py` です。artifact path と選択した構造要約を `llm_visible_context` に入れ、complete JSON、Markdown inventory、raw log、full document list は `local_tool_context` に残します
1. LLM-visible context に material を追加する前に Context Input Discipline を通す。各 material は routing、編集場所、validation、review、保留判断のどれを変えるのかを持つ必要があります。既読の owner surface、tool output、artifact は path、line、artifact reference で再利用し、runtime view と canonical owner、同じ log の再出力、同じ checker 結果の全文貼り直しは重複 input として扱います。exact wording が対象でない長い raw output は durable artifact と構造要約へ移し、request coverage と design evidence を落とさずに LLM-visible context を作ります
1. 調査、レビュー、追加確認は、継続前に次に進む作業を記録します。次の作業は、経路決定、編集場所の決定、検証、Issue 記録、担当者付きの保留、対象外記録のいずれかです。次の作業が同じ場合は、現在の記録の補助根拠に圧縮して、実装、検証、Issue 処理へ戻ります。
1. 重いコマンドや動作確認を予定する前に、タスクに結び付いた実行前の確認記録を
   作るか引用します。確認記録には、依頼の対応箇所、コマンドの種類、先に使った
   静的解析・読み取り evidence、実行が必要な未解決 signal、見込み時間、使う資源、
   停止条件、成果物の場所、担当者を入れます。重いコマンドには、動作確認、
   smoke run、CI 全体、長いテスト一式、ベンチマーク、実験、GPU / CPU 数値実行、
   ソルバーの一括確認、大きな乱択ケースが含まれます。
1. 編集 path または write-capable subagent handoff の前に、調査量を task risk に合わせる。広い surface、未確定 path、multi-agent handoff では `agents/COMMUNICATION_PROTOCOL.md` の `Pre-Edit Repository Investigation Packet` を作るか引用する。明示 path で owner boundary、差し替え可能な単位、validation route、public impact boundary が evidence で閉じている修正、Routine docs、Focused code、typo / link / format-only では、同文書の `Parent-Direct Context Note` を routing / handoff artifact として残せますが、これは親の edit authorization ではありません。note には owner、対象 path、request clause、exception rationale if any、reuse 根拠、design / OOP boundary、validation route、`llm_visible_context`、`local_tool_context`、`durable_memory_refs` を入れる。raw search hits、nearest editable file、または chat context だけで調査完了扱いにしない
1. workflow family は、owner boundary、差し替え可能な単位、validation route、public behavior / schema impact の evidence がそろうまで暫定 route として扱う。現在の route と、どの evidence で固定または変更するかを記録します。task id が分かる場合も、task catalog は catalog seed であり、後続の境界 evidence を無視する根拠にはしません
1. 実装 route を ready 扱いする前に Design Integrity Gate を通す。request clauses を owning responsibility model に対応付け、`Abstract Design Frame` または routing / handoff note を引用し、予定単位が差し替え可能であることを確認します。API shape、責務境界、path layout、命名、アルゴリズム、test oracle、依存方向、runtime contract、config surface の判断が design packet で閉じていない場合は、`design_issue_blocker=<issue>` を記録して詳細設計 / design review へ戻し、implementation shortcut として吸収しません
1. repo-changing task では、外形的な作業量や file 数ではなく design / OOP boundary と ownership clarity で実装経路を選ぶ。`requested_scope` と `work_scope` を分け、`work_scope` は段階化、routing、委譲してよく、要求された file、workflow、check、doc、PR state を `covered_surfaces`、`deferred_surfaces`、`omitted_surfaces` のいずれかに分類します。implementation / patch / doc-edit work の handoff は、別 writer が必要な場合だけ launch または schedule し、owner、責務、context、write authority、validation route が互換な active agent は revised scope でも再利用します。parent は選択された handoff、起動、追加指示、統合、review / validation gate 判定を所有する orchestrator / integrator です。独立 review、disjoint write authority、incompatible owner/context、または failed context integrity だけが fresh agent の根拠です。parent-direct は、責務境界、対象 owner、reuse 方針、validation route が明確で、現在の work packet が requested scope を覆うか明示 deferred surface を記録し、かつ `PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes` と `PARENT_DIRECT_WRITE_EXCEPTION=<explicit_user_approval|runtime_blocker>` を recorded exception として残した場合だけ使う。repo-wide、multi-surface、長文文書群、shared runtime surface というだけでは無制限に multi-agent を起動しない。write-capable handoff が runtime authorization や tool gate で詰まる場合は、parent-direct に黙って縮退せず、run bundle または structured local/tool context に `selected_agent_type`、`write_capable_handoff_blocker`、`evidence`、`parent_packet_ref`、`status=blocked` を記録する
1. multi-agent にする場合でも、分割境界は `差し替え可能な単位` に限る。別実装、別証明、別文書責務、別 validation oracle、別 review decision に置き換え得る境界だけを slice / wave / worker scope にする。数理的に差し替えが発生しない境界、単なる記法・読解補助・固定 context・同じ oracle を共有する連続導出は分割せず、同じ packet と同じ owner scope に残す
1. subagent scheduling は `CODEX_SUBAGENTS.md` が所有する typed capacity handshake と lifecycle ledger を消費し、ready dependency-DAG frontier の stage owner ごとに `vertical dynamic wave` を組みます。requested / configured / platform-effective / workflow-demand / write-cap / nested-reserved / available を分離し、既知制約の最小値を startup で read back してから reservation 成功時だけ spawn します。capacity が足りない ready work は失敗させず queue し、durable handback、全 descendant close readback、reservation release を終えた slot から再開します。固定 active/write 数、disposable capacity probe、または generated role view は scheduling authority になりません
1. repo-changing execution では `team_manifest.yaml` に `run.spawn_budget.active_subagents`、`run.spawn_budget.max_write_subagents`、`run.spawn_budget.runtime_max_threads`、`run.write_scope_policy.max_write_subagents` が分離して出ることを starter / closeout evidence に含める
1. prompt-derived skill routing が必要なら `python3 tools/agent_tools/route.py --prompt "<user request>" --format json` を使い、`ACTIVE_SKILLS` を current stage の宣言、`DEFERRED_SKILLS` を後続 wave trigger として扱う。`task_start.py` / `bootstrap_agent_run.py` を使う場合は、`SUGGESTED_SKILLS`、`ACTIVE_SKILLS`、`DEFERRED_SKILLS` と `run.repo_tool_routing_policy` を同じ source packet として保持し、`REPO_DYNAMIC_SKILL_ROUTING_CANDIDATES` から later wave の skill を追加したらその skill の command packet を再生成する
1. `agents/skills/README.md` から current stage に必要な public skill だけを足す。依存 source clone / module lifecycle が scope の場合は `$dependency-module-change` を一般 route として先に選び、AgentCanon update はその具体例として後続に置く。routing update に全 skill family を列挙せず、後続 stage で必要になった skill を wave ごとに追加する
1. repo-changing execution の編集では、既存 tool の実行や owner-bounded patching の前提として runtime `SKILL.md` 読了を要求しません。対象 property を正本として持つ既存 tool または command packet を先に使い、結果の解釈や修正に必要な owner surface だけを開きます。
1. owner boundary、差し替え可能な単位、validation route、public impact boundary が evidence で閉じている修正、Routine docs、Focused code、typo / link / format-only、明示的な bounded route 依頼では `$owner-bounded-routing` を追加し、owner boundary、existing-tool route、targeted validation をそこで固定する。file 数や外形的な作業量だけで route を固定しません。実装 behavior は契約完全実装ポリシーから導く
1. prompt / routing / subagent-config drift が task の中心なら、親が policy prose を直接広く直す前に `prompt_config_reviewer` で prompt/config audit を切る
1. starter command と review / specialist stack を family と mode に合わせて決める
1. repo-changing execution では `python3 tools/agent_tools/check_convention_compliance.py` を closeout gate に入れ、機械化済み規約を prompt 内で再実装しない
1. implementation が scope に入るときだけ Codex routing を出す
1. tool が既に check した property を `explorer` や read-only reviewer に再読解させない。subagent へ渡すのは structured tool artifact と owned finding scope で、tool output が必要な抽象を欠く場合は tool contract の不足として扱う

## Validation Boundary Contract

検査を選ぶ前に、対象propertyの論理的な役割を次の三つから分類します。

- `necessary_presence`: 要求されたディレクトリ、ファイル、リンク、正本参照、または入力条件が存在すること。欠落はfailureですが、存在だけでは実装や構造全体の正しさを証明しません。
- `forbidden_presence`: 削除済みラッパー、旧経路、禁止されたroot copy、またはownerが明示した不許可surfaceが存在しないこと。存在はfailureですが、無いことだけでは他の要件を証明しません。
- `sufficient_behavior`: 実装の意味、公開契約、状態遷移、数理特性、またはreader-facing成果が成立すること。これはownerが明示した場合だけ、必要な観測・静的解析・証明・テストで閉じます。

readiness、構造確認、移行漏れ確認は原則として `necessary_presence` と
`forbidden_presence` に留めます。例示tree、manifestの列挙、コピーの存在、
format成功を、完成形の十分条件や全責務の証明へ自動昇格させません。
`sufficient_behavior` が未要求の作業に、動作テスト、完全一致比較、実行成功、
網羅的レビューを追加してはいけません。逆にownerが十分条件を要求した場合は、
必要条件だけで完了扱いにせず、要求されたbehavior evidenceへ進みます。

各validation itemは `boundary_class`、failure predicate、owner surface、次に
変わる判断をrouting packetまたはtool artifactで示します。判断が変わらない
確認は重複確認として削除し、warningだけの確認はcompletion gateに昇格させません。

mode の意味:

- `repo-changing execution`
  - repo を今から触る
  - run bundle や kickoff command は coordination、resumption、または選択された
    workflow が要求する場合だけ必要
  - `$codex-task-workflow` は execution stage で足す
  - `$subagent-bootstrap` は repo-changing implementation / patch / doc-edit work、Shared canon / Large delivery / high-risk / multi-step / explicit subagent work の handoff / wave が ready になった stage で足す
  - task-shape skill は `$agent-orchestration` の後に足す
- `routing-only/advisory`
  - workflow family、skill、review、starter guidance だけを先に決める
  - full kickoff や repo-changing-only skill を勝手に足さない
  - 普通の相談、壁打ち、説明だけの turn を含む
  - repo state 確認、shell / GitHub check を走らせず、会話だけで応答する
  - user が repo inspection、file edit、validation、PR / issue 処理、CI 確認、または実装作業を求めた時点で `repo-changing execution` へ切り替え、切り替えをユーザー向け update で明示してから preflight へ進む

## Execution-Time-Aware Work-Conservation Contract

This is the canonical owner for execution-time-aware scheduling across
repository workflows. Consumers may project its state fields, but they must
not create a second scheduling policy or reduce the requested responsibility.
The machine-readable contract is
`agents/skills/agent-orchestration.execution-contract.toml`; its production
checker is `tools/agent_tools/check_execution_time_aware_orchestration.py`.
The selected-skill command catalog owns the required checker invocation; this
owner and its runtime shim do not duplicate that command.

Model the complete requested work as a dependency DAG. Each node is a full
replaceable responsibility unit, not a file-sized chunk, timed slice, or review
fragment. Edges represent owner, schema, dependency, validation, conflict, and
publication prerequisites. The DAG includes the complete owner and consumer
closure before dispatch begins; prompt-keyword routing is not a scheduling
signal.

The optimization objective is to minimize makespan subject to responsibility
completeness and correctness. Efficiency is therefore a scheduling objective,
never permission to omit, split, weaken, or prematurely close a required node.
Runtime observations may inform ordering, but no fixed duration, elapsed-time
limit, or timeout cutoff may cut the requested scope. An operational timeout
may mark a node blocked and trigger recovery; it may not turn incomplete work
into completion.

At every dispatch decision:

1. Refresh the dependency DAG and compute the complete remaining closure.
2. Compute the critical path through the remaining DAG. Use it to prioritize
   ready work, not to discard other ready work or to manufacture durations.
3. Compute the ready set: nodes whose predecessors and required closure
   evidence are satisfied. Dispatch every ready node that is non-conflicting
   and admissible under actual capacity; do not serialize while another useful
   ready node can run.
4. Batch remote reads, queue snapshots, and tool operations that share an
   authority, input, or readback boundary. Preserve each node's identity and
   exact evidence even when operations are batched.
5. Reuse the warm worker and reviewer contexts for repeated repair when the
   responsibility unit and route are unchanged. Invalidate only evidence
   affected by the repaired node and its dependent closure; retain unaffected
   evidence.
6. Compute owner, schema, dependency, validation, and publication closure
   before opening the owning review. Review the exact candidate closure once;
   accepted findings create only the affected repair nodes.
7. Wait only when the useful ready set is empty. Record the predecessor,
   conflict, capacity, or external-state blocker that makes it empty, then
   resume when that state changes. Waiting is not an elapsed-time scope gate.

The schedule must continue until every required node is complete and correct,
including its review, validation, and publication evidence. This contract is
state- and dependency-driven; prompt keywords, arbitrary serial waits, and
hard-coded durations cannot replace the DAG, ready-set, critical-path, or
closure decisions.

### Canonical Skill Invocation Order

`agents/skills/catalog.yaml` enumerates public skill identities and owns prompt
triggers. The typed dictionary `agents/skills/skill-dependencies.yaml` owns
required prerequisites, successors, explicit order constraints, responsibility
groups, and parallel-independent relations. `route.py` expands selected skills
with required prerequisites and derives their topological invocation order from
that dictionary. Prompt keywords select candidates only; they do not encode a
second call order or related-skill list.

### Parallel Fresh-Clone Workstreams

Vendor-first is the default for one nonparallel source stream. It is not a
prohibition on explicitly requested parallel independent work. A parent may
select `workspace/<topic-slug>/<module-basename>` fresh clones from latest
`origin/main` when the remaining DAG contains substantial replaceable
responsibility units with disjoint write scopes, explicit dependency and merge
order, independent validation routes, and distinct reviewer ownership. The
typed lifecycle route is
`dependency_module_change.py prepare --placement workspace`; its exact topic,
module, branch, owner evidence, computed clone path, and source identity are
part of the handoff evidence. Fresh mode always creates the requested branch
from fetched `origin/main` and refuses an existing local or remote branch;
continuation uses the separately typed
`dependency_module_change.py prepare --placement workspace-continuation` route.

For an eligible parallel set, the parent must launch every ready non-conflicting
stream under actual capacity, preserve each stream's full responsibility unit,
monitor all descendants and wave state, and reuse a compatible worker context
for follow-up work. Splitting a responsibility into fine-grained fresh agents,
file-sized clones, or timed fragments is not an independent workstream and is
not admissible. Colliding or dependent streams remain ordered by the recorded
dependency/merge order.

Every stream branch must fetch and merge the latest `origin/main` before its
candidate review or PR. The parent preserves the explicit merge order when
integrating candidates; a base-read or CAS check without the merge is
insufficient.

## Decision Sufficiency Packet

この節は semantic Decision Sufficiency policy の唯一の正本であり、
`validate_decision_sufficiency_packet` の唯一の意味論 owner です。consumer は必要な
場合に decision record を parse、serialize、import、forward できますが、artifact の
存在、JSON schema、digest、hypothesis count、read count、task-size 分類、または固定
threshold を execution の前提にできません。

Decision sufficiency is complete when the record or handoff names:

- the owning responsibility and replaceable unit;
- the implementation mechanism and validation route; and
- each unresolved branch that could change the owner, unit, mechanism, or route.

The record may remain in the handoff message or tool result. A durable/file
packet is conditional on coordination, cross-agent transfer, or resumption.
When no unresolved branch can change the next owner/edit/validation decision,
begin the selected work without manufacturing a packet or review stage.

When lifecycle coordination needs a durable serialization, the existing
`DecisionSufficiencyPacket` envelope may carry the semantic record below. This
serialization is optional and is not a task-entry or implementation-form
requirement.

```json
{
  "schema": "agent-canon.decision-sufficiency.v1",
  "decision_id": "dsv:<sha256>",
  "request_clause_ids": ["request-clause-id"],
    "owner": "canonical owner responsibility",
    "replaceable_unit": "replaceable responsibility unit",
    "implementation_mechanism": "existing mechanism or approved edit mechanism",
    "validation_route": "targeted validation command or checker",
    "unresolved_branch": {
      "branch_id": "b-1",
      "condition": "condition that could change owner, unit, mechanism, or route",
      "changes_next_decision": true
    },
  "irrelevant_unknowns": [
    {
      "schema": "agent-canon.irrelevant-unknown.v1",
      "unknown_id": "unknown:<64-lowercase-hex>",
      "field": "field name",
      "description": "why this cannot change the next action",
      "evidence_refs": ["evidence:<64-lowercase-hex>"],
      "affects_owner_edit_validation": false,
      "blocking": false,
      "serialized_in_decision_packet": true,
      "validator_owner": "absolute path to agents/skills/agent-orchestration.md#validate_decision_sufficiency_packet"
    }
  ],
  "rejection": null,
  "threshold_policy": "none"
}
```

`H`、`possible_branches`、`route_verdict`、`value_of_information`、evidence
digest、または threshold は generic routing fields ではありません。必要な場合に
限り、固定 Spark implementation route (`tools/agent_tools/implementation_route.py`)
の transport detail として scoped されます。Decision sufficiency is determined by
the semantic owner, replaceable unit, implementation mechanism, validation route, and
unresolved branches that can change them; no hypothesis-space or read-count form is
required.
A durable serializer may include states and evidence references when coordination
needs them. Additional reads, searches, reviews, and checks are justified only
when they can change the next owner, unit, mechanism, validation route, or
unresolved branch; otherwise return to the selected work.

When all known evidence selects the same owner, unit, mechanism, and validation
route, do not manufacture a zero-value investigation, packet, or review stage.
Use a design or review stage only when an unresolved branch can change one of
those decisions. Unknowns that cannot change the next decision are non-blocking
and may remain in local context.

Lifecycle consumers validate only the identity and transport fields they need;
they do not become a second semantic sufficiency owner or require a file-backed
artifact for an otherwise complete handoff.

If a semantic field is missing, report the unresolved owner/edit/validation
branch directly. Do not convert missing artifact fields, counts, or digests into
a new mandatory gate.

## Outputs

- current provisional workflow route, plus the evidence that will freeze or revise it
- semantic decision-sufficiency record: owner, replaceable unit, implementation
  mechanism, validation route, and unresolved branches that can change them;
  durable packet reference only when coordination or resumption needs it
- request mode (`repo-changing execution` or `routing-only/advisory`)
- 必要な role / specialist
- 契約に必要な review と handoff 構成
- `Pre-Edit Repository Investigation Packet` の path、または routing / handoff
  artifact としての Parent-Direct Context Note path
- repo-editing task なら、owner-critical route を先に選ぶ。requirements、plan、
  design、document-flow、implementation、review の段階は、各 surface の未解決
  decision と validation need が実際に要求する場合だけ起動する
- 着手時の作業 update 用の `workflow=<family>`, `skills=<active-now>`, `review=<...>` 宣言。`skills=<...>` では `$agent-orchestration` を先頭に置き、後続 skill は dynamic wave trigger として run bundle 側へ残す
- PR を作る task では、同じ routing 宣言と `python3 tools/agent_tools/route.py --prompt "<user request>" --format json` の `ACTIVE_SKILLS` / `DEFERRED_SKILLS` を PR body、run bundle、または linked comment に残す
- coordination/resumption が必要な場合だけ run bundle command と specialist
  activation を materialize する
- `IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker` と typed parent-packet selection による implementer routing
- `team_manifest.yaml` の `run.spawn_budget` による active/write/runtime/depth budget の階層
- nested subagent が必要な場合は、`run.delegated_spawn_policy` に owner、child role、入力 packet、expected output、dependency-expanded handoff scope、validation route、review gate を載せます
- parallel write が要るなら file 単位の write-scope 方針

## Review Activation And Adjudication

Review roles and review packs are candidates, not a default stage sequence.
Select one owning review gate for the claims in one replaceable responsibility.
Activate a specialist only when a distinct unresolved claim or risk cannot be
judged by that gate. A reviewer returns hypotheses; the parent / integration
owner adjudicates them and owns edit, revert, rollback, and publication state.

Accept a hypothesis only when it cites the current source snapshot, a reachable
input/control path, the violated request/design/behavior contract, and a witness
or static proof that changes the owner, edit, or validation decision. Reject
unreachable, stale-snapshot, private/incidental, duplicate, already-covered,
evidence-free, out-of-scope, or unproven approved-design-conflict hypotheses
with `reason_code` and `evidence_ref`. A rejected hypothesis opens no repair or
review wave and cannot cause rollback. Only an accepted finding that changes
requested behavior, owner/design boundary, correctness, validation, or
publication state enters same-owner rework.

Adjudicate failures against the selected final validation topology. A failure
observable only through a duplicate, superseded, or non-owner gate removed from
that route is unreachable for the active task: reject it with
`reason_code=superseded_gate_unreachable` and an `evidence_ref`; it opens no
repair/review wave, and production/source is not changed to satisfy that gate.
A still-valid issue owned by another trust boundary is recorded with
`reason_code=outside_active_trust_boundary` and handed to that owner separately;
do not import it into the active task.

Validation is static/targeted first. Full suites, full dependency review, and
remote CI are selected once for the final candidate only when the touched
contract requires them. Do not materialize empty reviewer or template artifacts.

## Workflow Family Mapping

| Task Shape                                                                                              | Primary Family              | Notes                   |
| ------------------------------------------------------------------------------------------------------- | --------------------------- | ----------------------- |
| owner-bounded local bug fix or CI/flaky-test fix with evidenced validation route                        | `Owner-Bounded Change`      | `T1`, `T2`              |
| local change that needs design, public behavior, workflow, or cross-module validation                   | `Scoped Change`             | `T3`                    |
| research-backed implementation, benchmark/experiment optimization, academic paper/thesis/scholarly note | `Research-Driven Change`    | `T4`, `T5`, `T9`, `T10` |
| large refactor or large multi-surface delivery                                                          | `Large Delivery`            | `T6`, `T7`              |
| environment, CI, Docker, dependency rollout                                                             | `Platform And Environment`  | `T8`                    |
| repo-wide workflow/tooling/canon rearchitecture                                                         | `Comprehensive Development` | `T11`, `T12`            |
| backlog-driven tuning and empirical improvement loop                                                    | `Adaptive Improvement Loop` | `T13`                   |

task id が分かる場合は、task catalog 側の family を正本にします。

## Public Skill Selection

- user が明示した `$skill-name` は preserve します
- `$agent-orchestration` は routing skill として常に先頭に置きます
- `repo-changing execution` が始まる stage では `$codex-task-workflow` を足します
- `$subagent-bootstrap` は repo-changing implementation / patch / doc-edit work の current stage で active にし、Shared canon / Large delivery / high-risk / multi-step / explicit subagent work で bootstrap evidence が必要な stage でも足します
- 非自明または substantive な文書作成・追記・改稿で section order、reader path、claim support、source map、canonical route、または document responsibility が変わる場合は、共通の構造先行 gate として `prose-reasoning-graph` と `structure-planning` を足します。typo / link / format-only では `md-style-check` を使い、`structure_contract=skipped` と理由を残します
- file / document responsibility の判定結果から DSL->文章 adapter を選びます。README、workflow、guide、migration、specification などの一般説明 prose では `long-form-writing` を足します。これは長さではなく責務による選択です
- 投稿論文や thesis chapter の draft では `paper-writing` を優先します
- paper draft ではない scholarly note や broader academic text では `academic-writing` を使います
- scope が paper draft と broader academic prose をまたぐなら、`paper-writing` を優先し、必要なときだけ `academic-writing` を追加します
- PR body、PR evidence comment、status update、decision brief、presentation narrative、PPT storyboard、または tool、JSON / JSONL、hook、eval、checker、experiment、review、audit の結果から reader-facing report を作る場合は `report-writing` を使います。report output は user が HTML、browser view、dashboard、web page、external browser publication を明示しない限り Markdown を既定にします。PPT / deck が scope に入る場合は visual asset plan と slide-production workflow も明示します。raw machine result を保存、コピー、蓄積する場合は `result-artifact-writeout` も併用します
- HTML output、HTML report、browser-readable page、dashboard、local preview server、external browser publication が明示された場合は `html-output` を使います
- HTML の experiment / Eval report が明示された場合は `html-experiment-report` と `html-output` を併用します
- report、experiment plan / report、Eval output、decision brief、presentation / PPT deck、HTML view、document、paper、refactor の構造が非自明な場合、または primary figure / table / ponchi-e / slide / section / slice、source map、source-to-slide map、invalid interpretation boundary を先に決める必要がある場合は `structure-planning` を足します
- tool、checker、hook、static analysis を走らせて問題を探す、full finding packet と mechanical priority order を作る、implementation / refactor planning に渡す場合は `tool-finding-report` を使います。before / after impact 比較は明示された場合だけ追加します。raw result を保存する場合は `result-artifact-writeout`、reader-facing narrative を作る場合は `report-writing` も併用します。reader-facing narrative が非自明な finding packet、priority policy、metric / count contract、source map を持つ場合は `structure-planning` も併用します
- README、workflow、guide、migration、specification docs は一般説明 prose adapter を正にしつつ、evidence-backed status、evaluation、audit、review、decision、recommendation section を含む場合は `report-writing` を overlay として足します
- research-backed implementation、benchmark、external research、prior art、公式
  docs、文献由来の method claim を使って code、protocol、report claim、design を
  変える場合は、`skills=...` / run bundle の skill call sequence で
  `literature-survey` を `research-workflow` より前に呼び、その source packet、
  limitation、contrary evidence、adoption/exclusion decision を固定してから
  `research-workflow` に進みます
- large refactor では `refactor-loop`、environment task では `environment-maintenance`、repo-wide rearchitecture では `comprehensive-development`、outer loop tuning では `adaptive-improvement-loop` を使います
- directory layout、directory README responsibility、root view、path mapping、responsibility-scope map、source-tree ownership の refactor では `structure-refactor` と `refactor-loop` を併用します
- task 開始前に expected AgentCanon repo structure、root view、`vendor/agent-canon/`、`.gitmodules`、または canonical path の欠落 / 移動 / stale state が疑われる場合は、通常 task の前に `structure-refactor` の pre-task structure repair route を使います。AgentCanon-owned root view / submodule drift なら `agent-canon-update` も併用します
- optimizer、solver、preconditioner、gradient、Jacobian、Hessian、KKT、収束、tolerance、数値 benchmark、数値 test 診断が scope にある場合は `computational-optimization` を使います
- GPU / CUDA / JAX / XLA / IREE 実行、`CUDA_VISIBLE_DEVICES`、`nvidia-smi`、ExperimentRunner Python 実行、JAX preallocation 無効化、GPU validation blocker が scope にある場合は `gpu-execution` を使います
- 原因考察、仮説、修正箇所選定、複数候補比較、change-impact packet 作成、repair-planning / subagent handoff context が task の中心にある場合は `dependency-analysis` を足します。原因仮説を扱う場合は `agents/workflows/hypothesis-validation-workflow.md` を overlay として明示します
- Markdown file edit、docs lint / link / heading repair、Mermaid / math drift、formatter adjacent check、`agent-canon docs`、docs-check failure、Markdown style drift が scope にある場合は `md-style-check` を足します。substantive な文書変更は `prose-reasoning-graph` と `structure-planning` も併用します
- skill / tool / workflow / hook / eval の蓄積ログ分析、routing miss、selection gap、弱い skill の調査が scope にある場合は `agent-log-analysis` を足します
- AgentCanon source update、`vendor/agent-canon` submodule latest / pin update、root runtime view repair、parent AgentCanon update TODO、または `make agent-canon-ensure-latest` / `tools/update_agent_canon.sh` routing が scope にある場合は `agent-canon-update` を足します。parent repo の `canon-pin` branch lane が必要な場合だけ `agent-update-branch` も併用します
- user / reviewer feedback が agent 行動、routing miss、再発防止、task retrospective、agent-side memory update を要求する場合は `agent-learning` を足します
- 関係のない family skill は足しません
- tool 化済みの規約検証は task-shape skill として増やさず、`check_convention_compliance.py` の gate に委譲します

## Entrypoint Precedence

- repo-editing task や kickoff command が必要な task では `bootstrap_agent_run.py` を優先します
- `task_start.py` は routing-only starter guidance に向きます
- `task id がある` ことだけでは `task_start.py` を優先する理由にはなりません。repo-changing execution なら task id 付きでも bootstrap を使います

## Review And Specialist Expectations

- family に応じた reviewer / specialist stack まで出します
- `Research-Driven Change` では research / report / reproducibility / benchmark / artifact 系 reviewer を落としません
- `Research-Driven Change` のどの分岐でも、文献・一次資料に基づく実装 claim は
  `literature-survey` の source packet から design、implementation、benchmark、
  report へ trace します。`literature-survey` を `research-workflow` の後段や
  report-only cleanup に回して source claim を実装後に補う skill call sequence
  にはしません。
- 一般説明 prose adapter を使う docs では、docs-impact がある場合に `document_flow_reviewer` と docs completeness review を使います
- academic/paper work では notation / logic review を落とさず、paper draft では `citation_evidence_reviewer` も追加します

## Codex Implementation Routing

- implementation が scope に入るときだけ routing を出します
- `bootstrap_agent_run.py` か `task_start.py` の output で `IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker` を確認してから route します
- prompt/config drift を含む task では、routing 決定後の詳細 diff を `prompt_config_reviewer` に監査させ、親が chat 文脈だけで共有 policy surface を広く書き換えません
- coding / implementation / patch / doc-edit work を求める repo-changing task は、read-only survey / review role だけで完了扱いにしません。surface route seed、responsibility search、reuse survey、stale-surface scan、dependency expansion、validation plan、tool-rejection preflight から handoff scope を作ったら、追加の read-only wave より先に selected write-capable implementer を起動または schedule します。parent は実装者ではなく orchestrator / integrator として、handoff packet、起動、追加指示、統合、review / validation gate を所有します。
- Runtime authorization や tool gate で write-capable subagent を起動できない場合は、local/tool context に `WRITE_SUBAGENT_AUTHORIZATION=required` または `write_capable_handoff_blocker=<gate>`、`selected_agent_type`、`evidence`、`parent_packet_ref`、`status=blocked` を記録します。parent-direct 実装へ進める route は、`PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes` と `PARENT_DIRECT_WRITE_EXCEPTION=<explicit_user_approval|runtime_blocker>` 付き revised workflow route です。
- Routine docs / Focused code でも implementation / patch / doc-edit work は、別 writer が必要な場合だけ write-capable handoff を選びます。parent-direct は risk class、check matrix、owner boundary、targeted validation、exception rationale が実装前に記録された場合だけ使います。`worker` が既定で、`spark_worker` は Abstract Design Frame、design trace、identifier naming、test-plan artifact / evidence（active workflow または touched surface が post-implementation test design を選択し、その activation により `test_plan.md` が必須になった場合のみ）、dependency-expanded handoff scope が揃った低リスク slice に対し、parent packet が `--select-agent-type implementer=spark_worker:<evidence>` を明示し、stdout / manifest が選択を記録した場合だけ使います。選択済み candidate が blocked の場合は local/tool context に `selected_agent_type`、`write_capable_handoff_blocker`、`evidence`、`parent_packet_ref`、`status=blocked` を記録し、candidate を変える場合は parent packet と wave の改訂を必須にします。
- 設計解釈、衝突解決、広い architecture 判断、scope 判断を含む slice は `worker` を使います。
- `spark_worker` は詳細設計、review、final judgment には使いません。
