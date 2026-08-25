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
upstream design ../internal-routines/design-implementation-correspondence.md universal design-to-implementation correspondence route
upstream design ../../documents/design/request-intent-and-update-relation.md compact question, write-clause, and update-overlay flow
upstream design ../../documents/tools/search-coordination.md unresolved owner/path search fallback
downstream implementation ../../tools/agent_tools/check_execution_time_aware_orchestration.py execution contract checker
downstream implementation ../../tools/agent_tools/skill_route_catalog.py derives canonical invocation order
downstream implementation ../../tools/agent_tools/skill_dependency_map.py validates and projects the dependency graph
downstream design ./direct-luna-communication.md owns bounded direct-Luna packet exchange and runtime acknowledgement
@dependency-end
-->

## Reader Map

設計を伴う repository-changing route では、owner selection の後に
`../internal-routines/design-implementation-correspondence.md` を stage route
として参照します。universal policy は同 routine にあり、この skill は route
selection の owner だけを持ちます。

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

### Compact request/update projection

`documents/design/request-intent-and-update-relation.md` is the compact design note for
this owner: read evidence closes advisory questions with an answer, explicit write clauses
enter the selected owner route, and in-progress input updates the existing packet with only
changed goal/artifact/order/handoff deltas. This skill owns the semantic decision; the note
adds no input classification or packet schema.
Added or changed request clauses pass the existing explicit-write-clause gate before owner
handoff; the approved effect uses the existing goal/artifact/order/handoff delta fields.

The request route records three positive transitions: read scope and evidence produce an
evidence-backed answer-complete state with answer/read-scope packet readback; an explicit write
clause with target, operation, owner, write set, and acceptance evidence produces an owner
handoff-ready state with existing write-packet readback; and an approved request update produces
the changed goal/artifact/order/handoff sparse delta state with changed-clause and delta-packet
readback. The write route materializes request clauses that carry the explicit write authority.

When the DIC activation gate is selected, this owner consumes DIC `DIC-010` and its
path+section+clause/ref closure packet. DIC owns traversal and forward/reverse closure;
this skill owns the request clause, explicit-write-clause gate, owner, and write-set
decision. Bounded owner/path/targeted-validation edits stay on the normal owner route
without DIC fingerprint or closure requirements.

## Purpose

task 開始時の mandatory routing skill です。
task を workflow family に分類し、skill set、handoff、review、runtime entrypoint を一貫した形にそろえます。

すべての skill tool command entry は単一の source-root contract を使います。論理コマンドは、実行前に AgentCanon source root を基準として解決します。各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、fallback-only skill を含む script entry の script path は絶対 path にします。

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
- `agents/skills/direct-luna-communication.md`

## Owner-First Read Trace

Repository source is not the first discovery surface. Before opening an
implementation file, test, hook, checker, or generated artifact, use this
fixed route:

1. Start at the active root `AGENTS.md` Reader Map and select the task Skill.
   Resolve its canonical path from `agents/skills/catalog.yaml`; do not guess
   from a nearby filename or a text-search hit.
   The root row only needs to identify the routing owner; it does not need one
   row per public Skill. Record the bridge as `Reader Map row -> routing owner
   -> selected Skill` when `task-routing` performs the final selection.
2. Read that canonical Skill completely. The Skill body is the first
   operational owner. If its body resolves the responsibility, operation, and
   validation route, record the owning section and do not follow a registry or
   rationale edge merely to fill the trace. Follow a task-relevant `upstream
   design` edge from its `@dependency-start` header only when the Skill body
   delegates a decision there or one of those three items remains unresolved.
   Never open a `downstream implementation` edge first.
3. Present the following short working update before implementation reading.
   It is a transient readback in the existing task update, not a new packet,
   schema, artifact, or closeout gate.

   ```text
   owner_trace_start=<active AGENTS.md Reader Map row>
   selected_skill=<agents/skills/catalog.yaml id -> canonical_doc>
   operational_owner=<selected Skill section or delegated upstream path + section>
   owner_route=<skill-body section or header edge description>
   docs_first_status=resolved|unresolved
   implementation_read=locked|ready
   ```

4. Set `implementation_read=ready` only when the Skill body and any owner it
   explicitly delegates to have been read and resolve the responsibility,
   intended operation, and validation route. Merely naming a delegated path
   leaves `docs_first_status=unresolved` and `implementation_read=locked` until
   that owner is read. A known source path is not sufficient by itself.
   `ready` is an admission state, not a claim that source was already opened;
   a read-only planner or evaluator can report `ready` while leaving the
   implementation unread.
5. If the Skill body and its task-relevant delegated edge do not resolve one
   operational owner, report the unresolved item and use the bounded purpose search in
   `documents/tools/search-coordination.md`. Search results nominate an owner;
   they do not unlock implementation until the selected Skill/upstream-owner
   trace is resolved.

When the Skill body resolves the owner, do not build a semantic index, sweep
the repository, or traverse every dependency-header edge. This keeps the route
short enough for low-reasoning agents while preserving the Skill body as the
operational owner and the existing dependency header as the only delegated
edge owner.

## Decision Order

Canonical model/profile selection and ToolCall materialization belong to the
registry/materializer owners, not `route.py`. Sol remains parent. When a
selected logical role uses a Luna profile, compose that role, its selected
Skills, authority, and bounded task packet through `direct-luna-communication`;
do not turn the logical role name into the physical team or capacity identity.
Terra, Spark, and `gpt-5.4-mini` remain capability-specific routes. Decision sufficiency is semantic: execution may start
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
1. repo-changing execution では、owner、責務単位、実装機構、validation route が未確定のときだけ deterministic search を使う。明示された owner/README/user path が一つの編集先を選ぶ場合は provider 全体を走査せず、その owner evidence を source packet に記録する。`python3 tools/agent_tools/search.py --query-file <request.txt> --providers text,semantic,vector,tool,header-deps,code-deps --format json` が利用できない場合は診断を残し、実際に owner/path の曖昧さが残るときだけ `router_unavailable_blocker` とする
1. 広い prose 読み込み、raw log 探索、subagent 起動の前に、その判定を正本として持つ canonical tool があるか確認する。tool-covered surface では tool を先に呼び、pass / finding の structured output を信頼する。ただし tool が返した path は作業 packet であり、`requested_scope` を縮める許可ではありません。owner、依存、downstream、意図的に外す surface を確認し、packet が user request を覆うことを証明してから編集に入ります
1. Structure Intake Packet と構造 checker は、directory/path ownership、root view、stale surface、document responsibility などの構造変更、または owner/path の曖昧さが実際に次の編集判断を変える場合だけ作る。通常の bounded edit、直接 owner path、README/user path の変更ではこれを必須化しない。必要な場合は `repo_structure_contract.py`、`responsibility_scope.py`、`file_surface_inventory.py --submodule-aware`、`import_responsibility.py` のうち判断に必要なものだけを使い、選択した構造要約を context に残す
1. LLM-visible context に material を追加する前に Context Input Discipline を通す。各 material は routing、編集場所、validation、review、保留判断のどれを変えるのかを持つ必要があります。既読の owner surface、tool output、artifact は path、line、artifact reference で再利用し、runtime view と canonical owner、同じ log の再出力、同じ checker 結果の全文貼り直しは重複 input として扱います。exact wording が対象でない長い raw output は durable artifact と構造要約へ移し、request coverage と design evidence を落とさずに LLM-visible context を作ります
1. 調査、レビュー、追加確認は、継続前に次に進む作業を記録します。次の作業は、経路決定、編集場所の決定、検証、Issue 記録、担当者付きの保留、対象外記録のいずれかです。次の作業が同じ場合は、現在の記録の補助根拠に圧縮して、実装、検証、Issue 処理へ戻ります。
1. 実行前の時間・資源・停止条件 artifact は、選択された execution profile または
   workflow が要求する場合だけ作成する。通常の targeted test、smoke、checker は
   そのコマンドと結果を直接記録し、未選択の pre-test artifact を完了条件にしない。
1. 編集 path または handoff の前に、調査量を未確定の owner/path、構造変更、または実際の設計分岐に合わせる。明示された bounded request でも、親は owner packet を選択・relay するだけで、調査・設計・編集・検証を自ら行わず、write-capable child handoff を要求する。設計/API/OOP の判断が未解決なら設計 route に戻す。raw search hits、nearest editable file、または chat context だけで owner が決まらない場合のみ追加調査する
1. workflow family は、owner boundary、差し替え可能な単位、validation route、public behavior / schema impact の evidence がそろうまで暫定 route として扱う。現在の route と、どの evidence で固定または変更するかを記録します。task id が分かる場合も、task catalog は catalog seed であり、後続の境界 evidence を無視する根拠にはしません
1. 実装 route を ready 扱いする前に Design Integrity Gate を通す。request clauses を owning responsibility model に対応付け、`Abstract Design Frame` または routing / handoff note を引用し、予定単位が差し替え可能であることを確認します。API shape、責務境界、path layout、命名、アルゴリズム、test oracle、依存方向、runtime contract、config surface の判断が design packet で閉じていない場合は、`design_issue_blocker=<issue>` を記録して詳細設計 / design review へ戻し、implementation shortcut として吸収しません
1. repo-changing task では、外形的な作業量や file 数ではなく design / OOP boundary と ownership clarity で実装経路を選ぶ。`requested_scope` と `work_scope` を分け、`work_scope` は段階化、routing、委譲してよく、要求された file、workflow、check、doc、PR state を `covered_surfaces`、`deferred_surfaces`、`omitted_surfaces` のいずれかに分類します。implementation / patch / doc-edit work は bounded でも必ず write-capable child を launch または schedule し、owner、責務、context、write authority、validation route が互換な active agent は revised scope でも再利用します。The parent is an orchestrator only: it owns handoff, launch, packet relay, dependency order, status, and final readback. review、validation、integration、publication、evaluation の判定は対応する child owner が行います。独立 review、disjoint write authority、incompatible owner/context、または failed context integrity だけが fresh agent の根拠です。repo-wide、multi-surface、長文文書群、shared runtime surface というだけでは無制限に multi-agent を起動しない。write-capable handoff が runtime authorization や tool gate で詰まる場合は typed blocker を記録し、親が代替実行しない
1. multi-agent にする場合でも、分割境界は `差し替え可能な単位` に限る。別実装、別証明、別文書責務、別 validation oracle、別 review decision に置き換え得る境界だけを slice / wave / worker scope にする。数理的に差し替えが発生しない境界、単なる記法・読解補助・固定 context・同じ oracle を共有する連続導出は分割せず、同じ packet と同じ owner scope に残す
1. subagent scheduling は `CODEX_SUBAGENTS.md` が所有する typed capacity handshake と lifecycle ledger を消費し、ready dependency-DAG frontier の stage owner ごとに `vertical dynamic wave` を組みます。requested / configured / platform-effective / workflow-demand / write-cap / nested-reserved / available を分離し、既知制約の最小値を startup で read back してから reservation 成功時だけ spawn します。capacity が足りない ready work は失敗させず queue し、durable handback、全 descendant close readback、reservation release を終えた slot から再開します。固定 active/write 数、disposable capacity probe、または generated role view は scheduling authority になりません
1. repo-changing execution では `team_manifest.yaml` に `run.spawn_budget.active_subagents`、`run.spawn_budget.max_write_subagents`、`run.spawn_budget.runtime_max_threads`、`run.write_scope_policy.max_write_subagents` が分離して出ることを starter / closeout evidence に含める
1. prompt-derived skill routing が必要なら `python3 tools/agent_tools/route.py --prompt "<user request>" --format json` を使い、`ACTIVE_SKILLS` を current stage の宣言、`DEFERRED_SKILLS` を後続 wave trigger として扱う。`bootstrap_agent_run.py` を使う場合は、`SUGGESTED_SKILLS`、`ACTIVE_SKILLS`、`DEFERRED_SKILLS` と `run.repo_tool_routing_policy` を同じ source packet として保持し、`REPO_DYNAMIC_SKILL_ROUTING_CANDIDATES` から later wave の skill を追加したらその skill の command packet を再生成する
1. `agents/skills/README.md` から current stage に必要な public skill だけを足す。依存 source clone / module lifecycle が scope の場合は `$dependency-module-change` を一般 route として先に選び、AgentCanon update はその具体例として後続に置く。routing update に全 skill family を列挙せず、後続 stage で必要になった skill を wave ごとに追加する
1. repo-changing execution の編集では、既存 tool の実行や owner-bounded patching の前提として runtime `SKILL.md` 読了を要求しません。対象 property を正本として持つ既存 tool または command packet を先に使い、結果の解釈や修正に必要な owner surface だけを開きます。
1. owner boundary、差し替え可能な単位、validation route が閉じた bounded edit も、write-capable child の通常 routeとして実行する。parent は既存 tool と targeted validation を child packet に指定するだけで、実行結果を自ら解釈しない。public API/behavior/schema の追加、縮小、削除、rename、restriction、deprecation、意味変更だけは `scoped_change` または broader route に進め、必要な dependency/consumer/migration/docs closure を形成する
1. prompt / routing / subagent-config drift が task の中心なら、親が policy prose を直接広く直す前に `prompt_config_reviewer` で prompt/config audit を切る
1. starter command と review / specialist stack を family と mode に合わせて決める
1. repo-changing execution では `python3 tools/agent_tools/check_convention_compliance.py` を closeout gate に入れ、機械化済み規約を prompt 内で再実装しない
1. implementation が scope に入るときだけ Codex routing を出す
1. tool が既に check した property を `explorer` や read-only reviewer に再読解させない。subagent へ渡すのは structured tool artifact と owned finding scope で、tool output が必要な抽象を欠く場合は tool contract の不足として扱う

### Local Capability Priority

Subagent communication capability and coordination receipts follow the sole
contract in `agents/COMMUNICATION_PROTOCOL.md#Runtime Collaboration Capability
Handshake`; this route does not duplicate that schema. Read the direct runtime
collaboration namespace before selecting `direct_peer`. Matcher/tool inventory
names are not capability evidence, so `unavailable`/`unverified` routes remain
`parent_relay` or `durable_artifact`.

Local Capability Priority (LCP) の全文規則はこの節だけが所有します。LCP が
競合する候補 operation、`issue_defer`、または `split` を含む作業として選択された
場合だけ、既存の scope / handoff record に operation mapping を記録します。
単純な bounded/advisory single-operation task にこの mapping を新しい universal
gate や closeout gate として要求しません。新しい classifier、schema、state machine、
run artifact、closeout consumer は追加しません。

canonical record は、run bundle がある場合はその `work_log`/scope record、run bundle
がなく structured handoff がある場合はその structured handoff、両方がない場合だけ
closeout recordの順で一つだけ選びます。親 packet、Issue、closeout はこの recordを
locatorで参照し、mappingを複製しません。既存の `requested_scope`、`work_scope`、
`covered_surfaces`、`deferred_surfaces`、`omitted_surfaces` と Decision Sufficiency
record は、選択した canonical recordの既存 fields として再利用します。

mapping が選択された場合だけ、作業範囲の既存 record に実行順で次の項目を一行ずつ
記録します。これは既存 record の prose/table field であり、新しい public schema では
ありません。

```text
request_clause: <exact quote> [locator: <request contract section/line>]
operation_id: <owner-qualified unique id>
priority: <execution list ordinal; lower runs first>
depends_on: <zero or more operation_id values>
split_parent_id: <parent operation_id or none>
split_child_id: <child operation_id or none>
operation: <one replaceable operation and owner>
evidence: <observed local/Pro capability or explicit absence, with locator>
classification: mandatory|local_only|pro_capable_nonblocking
disposition: local_execute|issue_defer|split
state: <resulting state after the selected disposition>
completion_evidence: <artifact, command result, local Issue, or readback>
```

mapping 内の `operation_id` は owner-qualified で一意、`depends_on` は同じ mapping
内に存在し、priority order は topological order で cycle を持たず、同順位の候補は
record 上の行順を維持します。split は親行と子行を ID で結び、子の行順と依存を明示
します。request clause は原文と locator を必須とし、Pro 可否は prompt keyword や
モデルの一般的な自己評価から導出しません。

unknown は disposition 前に mapping 行にも disposition にも入れません。先に Decision Sufficiency の
未解決 branch / `evidence_missing` として記録し、local evidence が解決するか、既存の
明示された omitted/deferred authority が成立するまで handled/close と扱いません。
したがって disposition は、根拠のある `mandatory`、`local_only`、または明示された
`pro_capable_nonblocking` に対してだけ選びます。

`mandatory` と `local_only` は、required owner skill が selected/activated になった
後で `local_execute` に投入します。user must-do、現在の blocker、root-cause
investigation、acceptance validation、Docker/devcontainer/CI、環境依存のログ取得、
filesystem side effect、Git mutation/conflict、remote mutation/readback、PR/Issue
integration、および後続 owner/validationを決める依存 operationもこの local routeを
先に通します。local_execute operationの owner skillが `DEFERRED_SKILLS` 候補なら、
先にその skill を activateし、deferred のまま実行しません。

`issue_defer` は、ユーザーの明示した policy または既存の承認済み capability evidence
により Pro-capable と確認された、非必須・非ブロッキング operation に限ります。
docs review、analysis、explanation、read-only research など、ローカルで実行可能でも
この条件を満たす operation は、ローカルで試してからIssueへ移す二段階にせず、分類時点
から直接 `issue_defer` にします。local-only capability、must-do、blocker/root-cause
investigation、acceptance validation、remote mutation/integration、およびそれらに
必要なreadbackはこの例外に含めず、`local_execute` します。Issue handoffは
repository-qualified GitHub URL/numberを使い、offline時だけprivate
`agent-canon-log/feedback/issue-packets/pending/`にbody locator/digestを記録します。
remote Issueのcreate/view/edit/close/reopenはhost adapterから実行し、container内で
GitHub credentialやnetworkを扱いません。

依存がある operationは `priority` と `depends_on` が許す順に進めます。split は
local_executeすべき子と issue_defer できる子が同じ依頼に含まれる場合だけ使い、親子ID、
依存順、owner、validation、completion evidenceを同じ canonical recordへ記録します。
各 operation は `operation -> resulting state -> completion evidence` の順で完了を示し、
退避した operation は完了ではなく durable Issue への引き渡し状態です。

token削減は調査範囲を縮めません。既存 issue capsule、context packet、handoff record の
locator を再利用して raw log の全文再掲を避けます。`DEFERRED_SKILLS` は task-routing が
所有する後続 skill candidateであり、operationの `issue_defer` とは独立です。skill が
deferred でも local_execute operationは先に skillをactivateして実行し、skillが active
でも上記の明示された Pro-capable nonblocking operationだけが issue_deferできます。両者を
結ぶ alias、schema field、route outputは追加しません。

## Validation Boundary Contract

検査を選ぶ前に、対象propertyの論理的な役割を次の三つから分類します。

- `necessary_presence`: 要求されたディレクトリ、ファイル、リンク、正本参照、または入力条件が存在すること。欠落はfailureですが、存在だけでは実装や構造全体の正しさを証明しません。
- `forbidden_presence`: 削除済みラッパー、旧経路、禁止されたroot copy、またはownerが明示した不許可surfaceが存在しないこと。存在はfailureですが、無いことだけでは他の要件を証明しません。
- `sufficient_behavior`: 実装の意味、公開契約、状態遷移、数理特性、またはreader-facing成果が成立すること。これはownerが明示した場合だけ、必要な観測・静的解析・証明・テストで閉じます。

### Write-Capable Handoff Validation Trust Boundary

write-capable handoff の `validation_route` は、親が選んだ閉じた信頼境界です。
worker はその route に明示された validation command を実行し、変更 mechanism に
必要な read-only/static confirmation だけを追加できます。repository の既定 test
command、tool の利用可能性、または worker 自身の不安から、未選択の test、full
suite、full scan、global rescan を追加してはいけません。full suite / full scan /
global rescan は owner packet または変更後の responsibility graph が明示的に選んだ
場合だけ route に含めます。

すでに実行中の長時間 check は観測対象として扱い、強制停止も同一 check の再実行も
しません。handoff にない check を worker が起動した場合は、完了条件へ昇格させず
`unexpected action` として親へ返します。repository contract の欠落が原因なら、親は
この owner の修正 finding として扱い、worker 側に新しい checker、test、時間閾値を
追加させません。

この境界は `test-design` の起動条件や oracle 契約を変更しません。既存 mechanism が
確立または修復された後、既存 checker と targeted validation で閉じない具体的な
test-owned risk が残る場合だけ `test_designer` を起動し、起動後もその risk を必要
十分に覆う oracle と production mechanism の修復を優先します。

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
Validation command scope is governed by the preceding write-capable handoff
trust boundary; work-conservation scheduling does not authorize a worker to
expand a selected validation route.

Use a dependency/overlap graph only when the selected work has real ordering,
schema, validation, publication, or collision edges. A node is a full
replaceable responsibility unit, not a file-sized chunk or timed slice. Direct
owner edits and one-writer tasks need no manufactured DAG or schedule artifact;
prompt-keyword routing is never a scheduling signal.

The optimization objective is lexicographic, in this order: request
completeness and correctness, minimum decision-relevant total work, then
minimum makespan. Makespan therefore never makes extra parallel review,
implementation, or validation work free. A ready action is admissible only
when it can change the decision tuple `(owner, implementation mechanism,
validation route, terminal state)`, strictly decrease the unresolved measure
defined below, or open a typed new candidate epoch from new evidence.
Efficiency is never permission to omit, split, weaken, or prematurely close a
required node. Runtime observations may inform ordering, but no fixed duration,
elapsed-time limit, or timeout cutoff may cut the requested scope. An
operational timeout may mark a node blocked and trigger recovery; it may not
turn incomplete work into completion.

When coordination is selected, dispatch decisions:

1. Refresh only the dependency and collision edges that can change the next
   owner, order, or merge decision.
2. Dispatch every ready node that is non-conflicting and admissible under actual
   capacity; serialize colliding units and do not invent timed stages.
3. Batch remote reads, queue snapshots, and tool operations that share an
   authority, input, or readback boundary. Preserve each node's identity and
   exact evidence even when operations are batched.
4. Reuse the warm worker and reviewer contexts for repeated repair when the
   responsibility unit and route are unchanged. Invalidate only evidence
   affected by the repaired node and its dependent closure; retain unaffected
   evidence.
5. Compute owner, schema, dependency, validation, and publication closure only
   when the selected workflow requires those edges. Review the exact candidate
   closure once; accepted findings create only affected repair nodes.
6. Wait only when the useful ready set is empty. Record the predecessor,
   conflict, capacity, or external-state blocker that makes it empty, then
   resume when that state changes. Waiting is not an elapsed-time scope gate.

For autonomous review and repair, one exact candidate digest defines one
candidate epoch. The initial owning review runs at most once in that epoch and
returns stable blocking finding IDs separately from advisory notes. Advisory,
style preference, duplicate, already-covered, and evidence-free findings do not
reopen implementation. A repair targets assigned blocking finding IDs, and the
following focused recheck may inspect only those IDs plus evidence invalidated
by the repair. It may not restart broad review or add a new blocker unless a
new contract, reachable-behavior witness, or structural contradiction opens a
new candidate epoch.

For a state `S`, define the unresolved measure as
`mu(S) = |blocking_finding_ids| + |unresolved_validation_ids| +
|unresolved_request_clause_ids|`. After the one initial review, every admitted
action must either change the decision tuple using typed evidence or strictly
decrease `mu`. Repeating the same state fingerprint and action fingerprint is
a `non_convergent_cycle`; stop that action and hand back the typed cycle rather
than starting another review or implementation pass. Zero blocking findings,
zero unresolved request clauses, and selected validation `pass` or
`not_applicable` form the terminal ship/handoff condition. Improvement ideas
after that point are advisory or separate-Issue work.

The selected schedule continues until its required units, validation, and
publication evidence are complete. This contract is state- and
dependency-driven; prompt keywords, arbitrary serial waits, and hard-coded
durations cannot replace a real ordering or collision decision.

## Distributed owner correspondence

The scheduling state above is a local work-convergence utility. Its finding IDs,
review status, and terminal projection do not create a guarantee or publication
authority. A mechanism owner must instead emit one owner-local receipt containing
the external authority/witness, causal mechanism transition, `not_guaranteed`
boundary, failure semantics, execution plane, tool input, and exactly one primary
observation. The receipt is reusable by the tuple
`(candidate_digest, property_ref, owner_ref, execution_plane, tool_input_locator)`;
it has no global ID, registry, approval, counter, or time threshold.

Independent owner streams may run in parallel when their write scopes and
validation oracles are disjoint. The parent transports typed packets, orders
existing dependency edges, reports status, and performs remote readback. It does
not combine child claims into a guarantee. When a mechanism or its effect/input
closure changes, the owner sends an invalidation packet only along existing
dependency edges. Each downstream owner decides whether its own receipt is
affected; unaffected receipts are reused without rerunning their commands.

The publication/integration owner consumes receipt presence, candidate/property/
owner compatibility, and dependency closure. It reports a bounded
`missing_or_incompatible` list and never reruns Docker, link, eval, project-test,
or owner commands. `verified` means owner-local causal correspondence, not
approval. Reviewer, Issue, merge, label, and copied-agent claims remain
intermediate references; unsupported claims are `advisory` or `unproven`.

### Canonical Skill Invocation Order

`agents/skills/catalog.yaml` enumerates public skill identities and owns prompt
triggers. The typed dictionary `agents/skills/skill-dependencies.yaml` owns
required prerequisites, successors, explicit order constraints, responsibility
groups, and parallel-independent relations. `route.py` expands selected skills
with required prerequisites and derives their topological invocation order from
that dictionary. Prompt keywords select candidates only; they do not encode a
second call order or related-skill list.

### Repository Topic Clone Workstreams

親、依存、standalone の source workstream はすべて
`repository-topic-clone` の単一 lifecycle を使います。要求された clone/edit/update
operation を先に保ち、`workspace/<topic-slug>/<repo-name>` の exact identity が既存
clone と一致すれば named branch を再利用し、branch が無ければ最新
`origin/main` から作成します。repository kind は prepare 後の policy decorator
であり、specialized skill の前提が合わない場合はその decorator だけを外して generic
operation を続けます。

canonical `repository_topic_clone.py` / `dependency_module_change.py` の
`prepare` と `merge-main` は、task owner の非空 owner evidence、computed path、
remote、branch、module identity が一致する repo-local workspace に対して、operation-level
の追加承認なしで dispatch します。この carve-out は `<project-root>/workspace/<topic>/`
の canonical lifecycle tool に限定されます。hook が保護する shared-checkout の raw Git
mutation（checkout/switch、branch/worktree、reset/restore/clean/stash、protected update
wrapper）は同じ command でも既存の明示 authority gate を通します。canonical tool の
内部で必要な Git 操作を理由に、caller が raw Git authority を付けたり、manual clone、
別 path、`rm -rf` を選んだりしてはいけません。

`dependency_module_change.py status` は adapter-only の read command です。generic
lifecycle、owner-evidence、または operation-level approval carve-out には含めません。

task closeout では `repository-topic-clone` または `dependency-module-change` skill に
`cleanup` dispatch を必ず割り当てます。canonical cleanup は request から computed clone を
解決し、selected Git toplevel、owner evidence/marker、URL、branch、clean non-detached state、
および fetch した `origin/<branch>` の local HEAD/tree 一致を preflight します。candidate CAS、
PR lifecycle、publication readback は任意の追加 evidence であり、指定時だけ coherent set と
merged publication readback を検証します。preflight が成功して `CleanupProof` / cleanup
receipt を返したときだけ `--apply` の削除を受理し、未達・衝突・unknown dirty state・proof
mismatch は clone/topic root を保持した typed hold として closeout packet に記録します。
通常 cleanup に workspace packet artifact は不要で、proof-free deletion は完了状態になりません。

workstream の scope は repository 構造、依存 edge、差し替え可能な責務単位、validation
route から形成します。`.gitignore`、単一 file、行数、diff 件数は clone lifecycle や
owner-bounded route の選択根拠になりません。複数 workstream は disjoint write scope、
dependency/merge order、reviewer ownership が成立する場合だけ並列化します。

For an eligible parallel set, the parent must launch every ready non-conflicting
stream under actual capacity, preserve each stream's full responsibility unit,
monitor all descendants and wave state, and reuse a compatible worker context
for follow-up work. Splitting a responsibility into fine-grained fresh agents,
file-sized clones, or timed fragments is not an independent workstream and is
not admissible. Colliding or dependent streams remain ordered by the recorded
dependency/merge order.

Every stream branch must fetch and normally merge the latest `origin/main`
before its candidate review or PR. Dirty state and merge conflicts are preserved
as typed evidence for intentional resolution. The integration executor performs
the merge/conflict resolution according to the explicit dependency order; the
parent relays that order and readback. A base-read or CAS check without the merge
is insufficient.

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
      "validator_owner": "agents/skills/agent-orchestration.md#Decision Sufficiency Packet"
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
- `Pre-Edit Repository Investigation Packet` の path と write-capable handoff
  packet path
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
judged by that gate. A reviewer returns hypotheses; the decision-owning reviewer
adjudicates them, the integration executor owns edit/revert/rollback integration,
and the publisher owns publication state.

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
- HTML の experiment / Eval artifact が明示された場合は `html-output` を直接使います。新しい実行・再実行が必要な場合だけ `experiment-lifecycle`、reader-facing claim が必要な場合だけ `report-writing` を追加します
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
- task 開始前に standalone AgentCanon source、`bootstrap.sh`、外部 runtime root、または canonical path の欠落 / 移動 / stale state が疑われる場合は、通常 task の前に `structure-refactor` の pre-task structure repair route を使います。AgentCanon source/runtime drift なら `agent-canon-update` も併用します
- optimizer、solver、preconditioner、gradient、Jacobian、Hessian、KKT、収束、tolerance、数値 benchmark、数値 test 診断が scope にある場合は `computational-optimization` を使います
- GPU / CUDA / JAX / XLA / IREE 実行、`CUDA_VISIBLE_DEVICES`、`nvidia-smi`、ExperimentRunner Python 実行、JAX preallocation 無効化、GPU validation blocker が scope にある場合は `gpu-execution` を使います
- 原因考察、仮説、修正箇所選定、複数候補比較、change-impact packet 作成、repair-planning / subagent handoff context が task の中心にある場合は `dependency-analysis` を足します。原因仮説を扱う場合は `agents/workflows/hypothesis-validation-workflow.md` を overlay として明示します
- Markdown file edit、docs lint / link / heading repair、Mermaid / math drift、formatter adjacent check、`agent-canon docs`、docs-check failure、Markdown style drift が scope にある場合は `md-style-check` を足します。substantive な文書変更は `prose-reasoning-graph` と `structure-planning` も併用します
- skill / tool / workflow / hook / eval の蓄積ログ分析、routing miss、selection gap、弱い skill の調査が scope にある場合は `agent-log-analysis` を足します
- AgentCanon source、bootstrap/runtime、skill、eval/archive、または AgentCanon source PR が scope にある場合は `agent-canon-update` を足します。親repoはAgentCanon sourceをvendor/submoduleとして更新しません
- user / reviewer feedback が agent 行動、routing miss、再発防止、task retrospective、private knowledge update を要求する場合は `agent-learning` を足します
- 関係のない family skill は足しません
- tool 化済みの規約検証は task-shape skill として増やさず、`check_convention_compliance.py` の gate に委譲します

## Entrypoint Precedence

- repo-editing task や kickoff command が必要な task では `bootstrap_agent_run.py` を優先します
- `bootstrap_agent_run.py` は routing-only starter guidance に向きます
- `task id がある` ことだけでは `bootstrap_agent_run.py` を優先する理由にはなりません。repo-changing execution なら task id 付きでも bootstrap を使います

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
- selected execution profile が Luna の場合は、logical role、selected Skills、reasoning effort、authority、bounded paths、expected output、validation route を `direct_luna_handoff_packet_v1` に合成し、`$direct-luna-communication` で `model="gpt-5.6-luna"`、`fork_turns="none"` の direct child を起動します。effective model / effort の一致前に work を admit せず、unavailable / hidden / mismatch を legacy role alias や別 model へ fallback しません。
- `bootstrap_agent_run.py` の output で `IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker` を確認してから route します
- prompt/config drift を含む task では、routing 決定後の詳細 diff を `prompt_config_reviewer` に監査させ、親が chat 文脈だけで共有 policy surface を広く書き換えません
- coding / implementation / patch / doc-edit work を求める repo-changing task は、read-only survey / review role だけで完了扱いにしません。surface route seed、responsibility search、reuse survey、stale-surface scan、dependency expansion、validation plan、tool-rejection preflight から handoff scope を作ったら、追加の read-only wave より先に selected write-capable implementer を起動または schedule します。parent は実装者ではなく orchestrator として、handoff packet、起動、packet relay、依存順、status、最終 readback を所有します。
- Runtime authorization や tool gate で write-capable subagent を起動できない場合は、local/tool context に blocker evidence を記録します。
- Routine docs / Focused code でも implementation / patch / doc-edit work は、bounded request を含めて write-capable handoff を選びます。`worker` が既定で、`spark_worker` は Abstract Design Frame、design trace、identifier naming、test-plan artifact / evidence（active workflow または touched surface が post-implementation test design を選択し、その activation により `test_plan.md` が必須になった場合のみ）、dependency-expanded handoff scope が揃った低リスク slice に対し、parent packet が `--select-agent-type implementer=spark_worker:<evidence>` を明示し、stdout / manifest が選択を記録した場合だけ使います。選択済み candidate が blocked の場合は typed blocker を記録し、親は実行しません。
- 設計解釈、衝突解決、広い architecture 判断、scope 判断を含む slice は `worker` を使います。
- `spark_worker` は詳細設計、review、final judgment には使いません。

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read `agents/skills/agent-orchestration.md` as the sole policy owner.
1. When the selected execution profile is Luna, read
   `agents/skills/direct-luna-communication.md` and use its bounded packet,
   effective-runtime readback, and typed blocker contract.
1. Consume the owner-produced semantic decision-sufficiency record referenced by
   the active route packet. A structured handoff or tool result is sufficient;
   use a durable packet reference only for coordination or resumption.
1. Execute the route packet's machine-readable ToolCall tokens and return their
   typed failure semantics without translating them into prose commands.
