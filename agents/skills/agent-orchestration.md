# agent-orchestration

<!--
@dependency-start
contract skill
responsibility Documents agent-orchestration for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ./dependency-analysis.md cause and fix-surface investigation route
upstream design ../COMMUNICATION_PROTOCOL.md pre-edit investigation and fresh subagent context packets
upstream design agent-orchestration.execution-contract.toml machine-readable execution contract
upstream design ./skill-dependencies.yaml typed public-skill prerequisites, successors, ordering, and parallel relations
upstream design ../internal-routines/design-implementation-correspondence.md universal design-to-implementation correspondence route
upstream design ../../documents/design/request-intent-and-update-relation.md compact question, write-clause, and update-overlay flow
upstream design ../../documents/tools/search-coordination.md unresolved owner/path search fallback
upstream implementation ../../tools/agent/skills/skill_document_reader.py bounded Skill read and EOF admission
downstream implementation ../../tools/validation/semantic/orchestration/check_execution_time_aware_orchestration.py execution contract checker
downstream implementation ../../tools/agent/skills/skill_route_catalog.py derives canonical invocation order
downstream implementation ../../tools/agent/skills/skill_dependency_map.py validates and projects the dependency graph
downstream design ./direct-luna-communication.md owns bounded direct-Luna packet exchange and runtime acknowledgement
@dependency-end
-->

## Reader Map

Design-implementation correspondence is read only after the selected route
activates that owner. A design file, design edit, or repository-changing task does
not activate it by itself. This skill selects the route; the selected workflow
owns its procedure.

- Purpose: mandatory repository-task routing that selects workflow family,
  active skills, roles, reviews, run bundle, and implementation route.
- Section path (lookup routes, not a startup reading list): Purpose, Use When,
  and Core References orient the reader;
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

[documents/design/request-intent-and-update-relation.md](../../documents/design/request-intent-and-update-relation.md) is the compact design note for
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

- [agents/TASK_WORKFLOWS.md](../TASK_WORKFLOWS.md)
- [documents/runtime/runtime-profiles-and-check-matrix.md](../../documents/runtime/runtime-profiles-and-check-matrix.md)
- [agents/COMMUNICATION_PROTOCOL.md](../COMMUNICATION_PROTOCOL.md)
- [agents/canonical/ARTIFACT_PLACEMENT.md](../canonical/ARTIFACT_PLACEMENT.md)
- [agents/canonical/CLI_ENTRYPOINTS.md](../canonical/CLI_ENTRYPOINTS.md)
- [agents/canonical/CODEX_SUBAGENTS.md](../canonical/CODEX_SUBAGENTS.md)
- `agents/skills/skill-dependencies.yaml`
- [agents/skills/direct-luna-communication.md](direct-luna-communication.md)

## Owner-First Read Trace

Repository source is not the first discovery surface. Before opening an
implementation file, test, hook, checker, or generated artifact, use this
fixed route:

1. Start at the active root [AGENTS.md](../../AGENTS.md) Reader Map and select the task Skill.
   Resolve its canonical path from `agents/skills/catalog.yaml`; do not guess
   from a nearby filename or a text-search hit.
   The root row only needs to identify the routing owner; it does not need one
   row per public Skill. Record the bridge as `Reader Map row -> routing owner
   -> selected Skill` when `task-routing` performs the final selection.
2. Read the selected discovered `SKILL.md`'s common constraints and short
   branch conditions first. The Skill body is the first operational owner.
   Select the branch needed for the current action before opening its details;
   apply this inside one file, at nested branches, and across linked Skills.
   Resolve an unknown condition with only the evidence needed to decide it,
   not by reading every alternative. Read every currently applicable branch and
   its shared safety constraints; leave later stages, validation, and recovery
   details unread until their own condition becomes true.
   Use `bootstrap.sh ... tool run --root <registered-project> skill-document-reader -- ...`
   with `index`, then `chunk --heading <selected-heading>`. A named section ends
   before the next heading, including a child heading; selecting a parent does
   not select its descendants. Continue the selected section from `next_offset`
   until `section_eof=true`. Reuse unchanged reads instead of restarting them.
   If responsibility, operation, and validation are resolved,
   do not follow a registry or rationale edge merely to fill the trace. Follow a
   task-relevant `upstream design` edge only when the active branch delegates a
   decision or one of those items remains unresolved. Never open a
   `downstream implementation` edge first. Apply the same section selection to
   canonical `agents/skills/<skill>.md`; a link alone does not activate its body.
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

4. Set `implementation_read=ready` only after the common constraints and all
   sections needed for the current action have actually been consumed through
   `section_eof=true`. Neither discovered nor canonical Skills require
   `file_eof=true`; unread inactive branches do not lock the current action.
   A required section prefix, an unresolved condition needed for this action,
   or a named path alone leaves `docs_first_status=unresolved` and
   `implementation_read=locked`.
   `ready` is an admission state, not a claim that source was already opened.
   The optional `admit --owner PATH#HEADING ...` checks only supplied sections'
   readability/EOF metadata, not the model's reading or selection sufficiency.
   Merely naming a delegated path does not unlock implementation. Do not create
   a per-read receipt, identifier, approval gate, or duplicate canonical Skill body.
   The existing-tool-before-read exception remains available for the tool action
   itself, not for interpreting or repairing its result without the needed reads.
5. If the Skill body and its task-relevant delegated edge do not resolve one
   operational owner, report the unresolved item and use the bounded purpose search in
   [documents/tools/search-coordination.md](../../documents/tools/search-coordination.md). Search results nominate an owner;
   they do not unlock implementation until the selected Skill/upstream-owner
   trace is resolved.

When the Skill body resolves the owner, do not build a semantic index, sweep
the repository, or traverse every dependency-header edge. This keeps the route
short enough for low-reasoning agents while preserving the Skill body as the
operational owner and the existing dependency header as the only delegated
edge owner.

When authoring or revising a branched Skill, keep common constraints and a short
`condition -> [section](#heading)` route before the details. Put branch bodies
under separate headings or linked files, not in the common read block. Do not
hide shared safety requirements inside an optional branch or put branch
selection conditions only inside the branch body. This is not a whole-file split
or a new read ledger requirement.

## Decision Order

1. Classify the request as `routing-only/advisory` or `repo-changing execution`.
2. Identify premises that could change the owner, mechanism, required guarantee,
   scope, or validation; verify them against current source, callers, inputs/state,
   constraints, and source authority. Distinguish observed facts, inferences, and
   unresolved decision-relevant premises; investigate only missing facts that can
   change the decision. For repo-wide or multi-surface execution, first establish
   the shared repository orientation required by `ROOT_AGENTS.md`, then follow
   relevant cross-directory callers and consumers to resolve the replaceable unit.
   Use an existing canonical tool when it owns the question; search only when owner
   or mechanism remains ambiguous. A handoff or tool result is enough unless
   coordination/resumption needs durable state.
3. Resolve family, stage, and role candidates from `agents/task_catalog.yaml`.
   A bounded owner/path/validation route runs through its execution owner; a
   child exists only when the selected typed route requires it.
4. Materialize model/profile and ToolCall values through their registry owners.
   For Luna, use `direct-luna-communication`; preserve the logical role and do
   not turn aliases into new capacity or approval rules.
5. When work is split, carry the shared repository orientation through the existing
   handoff, then add only the owner-specific context and validation each operation
   needs. Update it with new cross-owner findings. Bounded source context narrows
   reading, not responsibility. Do not repeat completed searches, full scans,
   inactive stages, or generic review packs when they cannot change the next
   owner/edit/validation decision.
6. Select review, specialist, and artifact routes only when the changed contract
   or an unresolved risk needs them; return to the selected workflow after the
   decision is closed.

### Local Capability Priority

Subagent communication capability and coordination receipts follow the sole
contract in [agents/COMMUNICATION_PROTOCOL.md#Runtime Collaboration Capability Handshake](../COMMUNICATION_PROTOCOL.md#runtime-collaboration-capability-handshake); this route does not duplicate that schema. Read the direct runtime
collaboration namespace before selecting `direct_peer`. Matcher/tool inventory
names are not capability evidence, so `unavailable`/`unverified` routes remain
`parent_relay` or `durable_artifact`.

Local Capability Priority (LCP) is used only when a request has competing local,
deferred, or split operations. Reuse the existing task/handoff record and follow
its owner and dependency order. Ordinary bounded/advisory work needs no mapping,
ledger, classifier, schema, approval, or extra closeout gate. Required work,
blockers, root-cause investigation, validation, mutations, and readback stay on
their existing owner routes; an external defer is chosen only with explicit
existing capability authority.

## Validation Boundary Contract

### Write-Capable Handoff Validation Trust Boundary

The handoff’s selected commands are the trust boundary. Run those commands and
only mechanism-required static/read-only confirmation; do not add repository-default
tests, full scans, or global rescans. Observe an already-running check rather than
restarting it. Return an unexpected or missing route to its owner instead of adding
a checker, field, threshold, or test here.

### Checkout Identity Readback

Git identity and writer targets are read through the existing checkout and repository-topic
owners when a Git operation or write handoff is selected. This skill does not repeat
their commands, permission checks, or target fields.

mode の意味:

- `repo-changing execution`
  - repo を今から触る
  - run bundle や kickoff command は coordination、resumption、または選択された
    workflow が要求する場合だけ必要
  - `$codex-task-workflow` は execution stage で足す
  - `$subagent-bootstrap` は catalog の typed route が child handoff を要求し、handoff / wave が ready になった stage で足す
  - task-shape skill は `$agent-orchestration` の後に足す
- `routing-only/advisory`
  - workflow family、skill、review、starter guidance だけを先に決める
  - full kickoff や repo-changing-only skill を勝手に足さない
  - 普通の相談、壁打ち、説明だけの turn を含む
  - repo state 確認、shell / GitHub check を走らせず、会話だけで応答する
  - repository inspection and other read-only evidence gathering stay on the advisory/read route. File edits, validation execution that mutates task state, PR/Issue mutation, or implementation select the corresponding write/execution route before that operation

## Execution-Time-Aware Work-Conservation Contract

This is the canonical owner for execution-time-aware scheduling across
repository workflows. Consumers may project its state fields, but they must
not create a second scheduling policy or reduce the requested responsibility.
The machine-readable contract is
`agents/skills/agent-orchestration.execution-contract.toml`; its production
checker is `tools/validation/semantic/orchestration/check_execution_time_aware_orchestration.py`.
The selected-skill command catalog owns the maintenance checker invocation.
Select it when this contract, its checker, or a declared consumer changes, not
merely because a repository task uses this skill. This owner and its runtime
shim do not duplicate that command.
Validation command scope is governed by the preceding write-capable handoff
trust boundary; work-conservation scheduling does not authorize a worker to
expand a selected validation route.

`agents/task_catalog.yaml#execution_route_policy` is the single execution-route
selector. Reuse established owner/topology facts through `route.py --area closeout
--execution-context <JSON>`; no separate packet file is required. Resolve unknown
scope, public-contract boundaries, or validation oracles before choosing either
execution route. One root, owner, and writer with no dependency, collision,
publication, or resumption coordination selects `bounded_fast_path`; otherwise
use existing `coordination`. Risk labels, prompt keywords, and file/line counts
are not route predicates.

The bounded route has exactly `route -> execute -> verify_close`. Its execution
owner uses the existing task evidence directly; it does not materialize a run
bundle, schedule, completion coverage, child packet, broad review, full suite,
or inactive `not_applicable` / `not_selected` gate records.
During `verify_close`, inspect the exact diff, run only selected validation,
integrate latest main and resolve conflicts, then publish and read back the
Issue branch/commit/PR and record scope, results, limitations, and status in the
Issue and user report. Existing read-only/local-only/no-change exceptions still
apply; the route does not manufacture commit/push evidence. Unavailable selected
validation is `need verification`, not a pass or permission for unrelated tests.
Failed validation remains failed. The router plans these operations; selecting
an execution route never proves their completion. The existing coordinated
`task_close.py` predicate is unchanged and is emitted only for `coordination`.

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

## Owner Correspondence and Workstreams

Use the existing owner receipt, repository-topic lifecycle, and validation route when
coordination is selected. The parent transports owner results and dependency order;
it does not synthesize child claims, rerun an owner command, or create a second
receipt/ledger. Independent workstreams may run in parallel only with disjoint owner
scopes and validation oracles; collisions remain ordered by the existing checkout and
integration owners.

### Canonical Skill Invocation Order

`agents/skills/catalog.yaml` owns public skill identity and prompt triggers.
`agents/skills/skill-dependencies.yaml` and the selected route provide prerequisites
and order. Use `route.py` to materialize the selected command sequence; prose does
not create a second order or related-skill list.

### Repository Topic Clone Workstreams

Use `repository-topic-clone` for prepared source workstreams and its existing
prepare, merge, and cleanup operations. Keep exact checkout identity, branch, remote,
dirty state, and merge readback with that owner; raw Git or manual clone is not an
alternative route. A bounded one-writer task needs no workstream packet.

## Decision Sufficiency Packet

Before execution, settle the owning responsibility, replaceable unit, mechanism,
validation route, and any unresolved branch that could change them. Keep this
record in the existing handoff or tool result; materialize a durable packet only
for coordination or resumption. If the next decision is already fixed, continue
without manufacturing another packet, schema, digest, count, or review stage.
Consumers may transport the selected record but do not redefine its meaning.

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
- PR を作る task では、同じ routing 宣言と `python3 tools/agent/orchestration/route.py --prompt "<user request>" --mode routing-only --format json` の `ACTIVE_SKILLS` / `DEFERRED_SKILLS` を PR body、run bundle、または linked comment に残す
- coordination/resumption が必要な場合だけ、選択された workflow owner の既存 run-bundle
  と handoff を materialize する

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

Task-to-family mapping, activation mode, stage selection, and required roles are
owned by `agents/task_catalog.yaml` (`tasks[].family`,
`workflow_activation_policy`, `workflow_families[].roles`, and
`role_topology_defaults.stage_waves`). This skill resolves that typed record and
does not maintain a parallel task-shape table. [agents/TASK_WORKFLOWS.md](../TASK_WORKFLOWS.md) is the
reader map for the same owner.

### Mathematical intent route

数理・数値挙動の修正だけは task catalog の `mathematical_correction` route を先に
解決します。既存の math-intent owner が packet、owner、reviewer、ordering を提供する
ので、この skill は field list や別の eligibility test を複製しません。非数理の Docker、
JIT、runtime、routing、environment、CI、architecture work は通常 route に残し、同じ
依頼の非数理 clause は sibling owner に分けます。

## Public Skill Selection

1. Preserve an explicit `$skill-name` request and put `$agent-orchestration` first.
2. Add `$codex-task-workflow` for repository-changing execution; add
   `$subagent-bootstrap` only when the selected typed route needs a child,
   coordination, or resumption.
3. Select a task-shape owner from the actual output: `refactor-loop` for structural
   migration, `comprehensive-development` for repo-wide canon/tooling work,
   `environment-maintenance` for environment contracts, and `adaptive-improvement-loop`
   for an explicitly requested outer tuning loop.
4. Add document, research, report, HTML, slide, or academic skills only when that
   deliverable is requested. Use the selected owner’s existing command route for
   formatting, evidence, and artifact writeout.
5. Add `dependency-analysis`, `computational-optimization`, `gpu-execution`, or
   `structure-refactor` only when the current owner/mechanism decision actually
   depends on that domain. Keep non-domain work on its existing route.
6. Use `integration`, `pr-processing`, `worktree-health`, `md-style-check`,
   `agent-log-analysis`, or `agent-canon-update` only for the corresponding
   operation; unrelated family skills do not activate them.

## Entrypoint Precedence

- repo-editing task や kickoff command が必要な task では `bootstrap_agent_run.py` を優先します
- `bootstrap_agent_run.py` は routing-only starter guidance に向きます
- `task id がある` ことだけでは `bootstrap_agent_run.py` を優先する理由にはなりません。repo-changing execution なら task id 付きでも bootstrap を使います

## Review And Specialist Expectations

- family に応じた reviewer / specialist stack まで出します
- math-intent route では `mathematical_correctness_reviewer` が equations、variables、units、
  assumptions、derivation、update / stopping map、equation-to-code correspondence、math
  oracle、changed-path scope を検証します。この reviewer の finding は数学 correspondence
  と scope の判定だけを行い、architecture / JIT / backend / runtime / routing / environment /
  proof-tool の編集を承認しません。必要なら別 owner の sibling handoff を返します
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
- selected execution profile が Luna の場合は、logical role、selected Skills、reasoning effort、authority、bounded paths、expected output、validation route を `direct_luna_handoff_packet_v1` に合成します。Effective model と effort は選択済み profile と `$direct-luna-communication` owner から解決し、`fork_turns="none"` で direct child を起動します。effective model / effort の一致前に work を admit せず、unavailable / hidden / mismatch を legacy role alias や別 model へ fallback しません。
- `bootstrap_agent_run.py` の output で `IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker` を確認してから route します
- prompt/config drift を含む task では、routing 決定後の詳細 diff を `prompt_config_reviewer` に監査させ、親が chat 文脈だけで共有 policy surface を広く書き換えません
- coding / implementation / patch / doc-edit work を求める repo-changing task は、typed route が child handoff を要求する場合に限り、read-only survey / review role だけで完了扱いにしません。surface route seed、responsibility search、reuse survey、stale-surface scan、dependency expansion、validation plan、tool-rejection preflight から handoff scope を作ったら、追加の read-only wave より先に selected write-capable implementer を起動または schedule します。parent は実装者ではなく orchestrator として、handoff packet、起動、packet relay、依存順、status、最終 readback を所有します。
- Runtime authorization や tool gate で write-capable subagent を起動できない場合は、local/tool context に blocker evidence を記録します。
- Routine docs / Focused code でも implementation / patch / doc-edit work は、catalog の typed route が要求する場合だけ write-capable handoff を選び、実装 role/profile は [Codex Subagents](../canonical/CODEX_SUBAGENTS.md) の選択結果を消費します。ここで default、Spark eligibility、blocked-candidate fields、candidate re-selection を再定義しません。
- 設計解釈、衝突解決、広い architecture 判断、scope 判断を含む slice は `worker` を使います。
- `spark_worker` は詳細設計、review、final judgment には使いません。

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Use [Owner-First Read Trace](agent-orchestration.md#owner-first-read-trace) to read only common constraints and currently selected branches of this policy owner.
1. When the selected execution profile is Luna, read
   [agents/skills/direct-luna-communication.md](direct-luna-communication.md) and use its bounded packet,
   effective-runtime readback, and typed blocker contract.
1. Consume the owner-produced semantic decision-sufficiency record referenced by
   the active route packet. A structured handoff or tool result is sufficient;
   use a durable packet reference only for coordination or resumption.
1. Execute the route packet's machine-readable ToolCall tokens and return their
   typed failure semantics without translating them into prose commands.
