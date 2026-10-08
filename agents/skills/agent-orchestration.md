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

Use the active root [AGENTS.md](../../AGENTS.md) and the selected Skill to find
the current owner. Read the applicable constraints and decision guidance before
changing a repository surface. Follow a linked owner only when it resolves a
decision the active route delegates or a material fact remains open; do not
traverse every reference or inspect inactive branches just to complete a trace.
This guidance does not relax higher-priority requirements to read a selected
runtime Skill in full.
When ownership is still unclear, use the bounded purpose search in
[documents/tools/search-coordination.md](../../documents/tools/search-coordination.md)
and verify the nominated owner against its actual responsibility.

`skill-document-reader` can help locate or read a long section. Its index,
chunks, and EOF metadata describe returned text; they do not establish that an
instruction was understood or applied. Use it when it helps, not as an admission
gate or a substitute for reading the relevant instructions. Reuse context that
still applies and revisit only premises changed by new evidence.

For branched Skills, state the condition that activates each branch near the
branch guidance. Keep shared authority and safety constraints visible wherever
they apply. Split content only when separate sections make the actual decision
easier to find; a branch map or file split is not required for every Skill.

## Decision Order

Classify whether the current request is advisory or authorizes repository
execution, then resolve only facts that could change the owner, mechanism,
required behavior, scope, or validation. Compare those facts with current source,
callers, state, constraints, and source authority; keep observations, inferences,
and unresolved premises distinct. For work crossing directories or surfaces,
establish the shared repository orientation and follow only the callers and
consumers that can affect the replaceable unit. Use an existing tool when it owns
the question; search when the owner or mechanism remains uncertain.

Resolve workflow, skills, roles, and runtime profile from `agents/task_catalog.yaml`
and their registry owners. A bounded task stays with its execution owner; a child,
review, specialist, artifact, or durable run bundle is selected only when its
owner or the current coordination need calls for it. When actions depend on one
another, respect those dependencies; independent, non-conflicting work can run
in parallel when the selected route and runtime support it. Carry settled context
forward and reopen a decision only when new evidence can change it.

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

The bounded route leaves execution with one owner using the existing task
evidence; it does not materialize a run bundle, schedule, completion-coverage
ledger, child packet, broad review, or inactive gate records. That owner carries
out the requested work and its applicable closeout obligations: inspect the
exact diff, use selected validation, integrate the current base when publication
requires it, and read back any authorized Issue, branch, commit, or PR update.
Read-only, local-only, and no-change requests do not manufacture commit or push
evidence. Unavailable selected validation remains `need verification`; failed
validation remains failed. Route selection plans work but never proves it
finished. The existing coordinated `task_close.py` predicate remains limited to
`coordination`.

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

For a selected coordination route, let the current dependency, collision,
authority, and evidence state determine the next operation. Refresh only edges
that could change the next owner, order, or merge decision. Dispatch every ready
node that is non-conflicting and admissible under actual capacity; serialize
collisions and do not invent timed stages. Batch remote reads, queue snapshots,
and tool operations only when they share an authority, input, or readback
boundary, preserving each node's identity and evidence. Reuse the warm worker
and reviewer contexts for repeated repair when the owner and route remain
compatible. Invalidate only evidence affected by the repaired node and its
dependent closure. Compute owner, schema, dependency, validation, and publication
closure when the selected workflow needs those edges. Review the exact candidate
closure once; accepted findings create only affected repair nodes. Wait only
when the useful ready set is empty; record the concrete predecessor, collision,
capacity, or external-state blocker, and resume when it changes.

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

Return the route and evidence needed for the next decision: whether the request
is advisory or executable, the selected workflow/owner, any active role or
review, the required validation, and unresolved facts that could change them.
Use the existing task update, tool result, or handoff; do not create an artifact
or repeat a settled selection merely to fill this list.

For repository changes, let actual dependencies and unresolved decisions choose
the work order. Activate requirements, design, document flow, implementation,
review, or specialist work only when the affected surface needs it. A bounded
task can carry decision evidence directly; materialize the selected workflow's
run bundle and handoff only for coordination or resumption. When creating a PR,
include the selected routing declaration and, when the route tool provides them,
its `ACTIVE_SKILLS` / `DEFERRED_SKILLS` in the PR body, run bundle, or linked
comment.

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

Choose validation from the changed contract and the guarantee the result must
establish. Targeted evidence is sufficient when it covers that guarantee; use
broader suites, dependency review, or remote CI when integration or remaining
risk makes them relevant. Reuse evidence that still applies and do not create
empty reviewer or template artifacts.

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

Use `bootstrap_agent_run.py` when the selected route needs its catalog-driven
starter guidance or durable coordination/resumption record. It can provide
routing-only starter guidance without turning every advisory request into a
run bundle. A repository-changing mode or task ID alone does not require one;
bounded work can use its existing task evidence.

## Review And Specialist Expectations

Choose review and specialist owners from the selected catalog route and the
claims that need judgment; a workflow family alone does not require a fixed
review stack. On the mathematical-intent route, `mathematical_correctness_reviewer`
checks equations, assumptions, correspondence, oracle, and changed-path scope.
That review does not approve architecture, JIT, backend, runtime, routing,
environment, or proof-tool changes; hand those claims to their owner.

For research-backed claims, carry the source packet from `literature-survey`
into design, implementation, benchmark, and report decisions that use it.
Reader-facing prose may need `document_flow_reviewer` or docs completeness
review when the document path is part of the requested result. Academic work
may need notation and logic review; paper drafts also need citation-evidence
review. Select each for the actual deliverable and unresolved claim.

## Codex Implementation Routing

When implementation is in scope, consume the selected catalog route and
implementation role. Use a child only when the typed route requires one. Give
the selected writer the source, caller, scope, allowed paths, validation, and
rejection evidence needed for its responsibility; investigate only facts that
can change those decisions. When the write handoff is ready, do not hold it for
unrelated read-only work. Let dependencies and collisions determine ordering,
and run independent work in parallel when authority and validation boundaries
permit it. The parent owns handoff, packet relay, dependency order, status, and
final external readback.

For a selected Luna profile, use `$direct-luna-communication` to build the
bounded packet and read back effective model/effort before admitting work. An
unavailable, hidden, or mismatched runtime remains a blocker; do not fall back
to another model or role alias. Use the selected profile and role configuration
from their registry owners rather than a local role matrix. A prompt/config
change may need `prompt_config_reviewer` when that review is selected; do not
rewrite a shared policy surface from chat context alone. If a runtime or tool
gate blocks a selected child, preserve its blocker evidence and authority
boundary.

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
