# Agent Communication Protocol
<!--
@dependency-start
contract agent-runtime
responsibility Documents Agent Communication Protocol for this repository.
upstream design README.md agent canon overview
upstream design ../documents/design/request-intent-and-update-relation.md compact active-context and handoff projection
downstream design skills/agent-orchestration.md routes pre-edit investigation before path selection
downstream design skills/codex-task-workflow.md consumes pre-edit investigation and context capsules
downstream design skills/subagent-bootstrap.md consumes fresh subagent context capsules
downstream design TASK_WORKFLOWS.md routes active design packet ownership
downstream design skills/codex-task-workflow.md consumes the active design packet contract
downstream implementation ../tools/runtime/dispatch/agent-canon/src/waterfall_gate.rs validates persisted active design packets
downstream implementation ../tools/runtime/dispatch/agent-canon/src/tool_rejection_preflight.rs predicts edit-time tool rejection gates
@dependency-end
-->


この文書は、agent-to-agent handoff と review の正本です。

## Reader Map

- This document owns the artifact-level communication contracts for handoff, pre-edit investigation, fresh subagent capsules, review packets, write scope, and escalation.
- The first sections define common rules and communication surfaces; the packet sections then specify exactly what must be handed between parent, subagents, reviewers, and implementers.
- For write work, use `## Pre-Edit Repository Investigation` to establish the
  target, owner, scope, and authority; materialize route-specific artifacts
  only when selected. Use `## Fresh Subagent Context Capsule` before launching
  or reusing a run-local subagent.
- For chunked reading, start from the packet type required by the current transition and read only the fields needed to make that transition auditable.
- After context compaction, follow `## Post-Compaction Objective Re-Declaration Contract` before any resumed action.

### Compact request/update projection

[../documents/design/request-intent-and-update-relation.md](../documents/design/request-intent-and-update-relation.md) is the compact flow connected to
this protocol's active context, write-scope, and handoff. Deltas attach to existing
capsules/packets, compatible context is reused, and only disjoint scope receives a separate
handoff. Transport schema and context ownership remain here.
Approved request effects travel through the existing goal/artifact/order/handoff delta fields;
write authority remains with the selected owner and the scope in the current request/handoff.

An evidence-read operation reaches an answer-complete state and returns an evidence-backed
answer/read-scope receipt. An explicit write-clause operation reaches an owner-handoff state and
returns the existing owner/write-scope/acceptance readback. An approved update operation overlays
the compatible active context and reaches a goal/artifact/order/handoff sparse-delta state; its
completion evidence is the changed-clause and delta packet readback.

The closure packet is transported as path+section+clause/ref references; DIC owns
traversal and closure decisions, while this protocol owns capsule visibility and
handoff transport.

Implementation design packets also carry a `source_refs` reference to the
run-local `semantic_responsibility_contract.toml` instance. That instance is
the allocation readback for each semantic delta: one action, its obligations,
and exactly one primary verification owner per obligation. It is not a second
active-packet schema or a repository-wide populated registry.

After completed integration tree/remote readback, this protocol records the dispatch of the
existing owner cleanup executors and transports their receipts into the closeout packet. The
cleanup executors retain their existing owners and receipt formats.

## 基本ルール

- 次の role が判断に使う情報は artifact に残します。
- reviewer は repo を直接修正せず、required change を artifact に残します。
- review を受けた role は `resolved`、`rejected`、`escalated` のいずれかで必ず応答します。
- review の `rejected`、`required_change` は、提案された実装や
  修正方法への判定であり、user request や design intent を rollback する権限では
  ありません。実行 role は、同じ意図を保つ修正、同じ意図を保つ再設計、または
  design / scope conflict の escalation に接続します。
- 実装 slice の削除、revert、discard は、該当 request clause が user / owner に
  よって撤回または置換された、canonical owner 外だった、または危険で代替修正や
  escalation が同じ意図を保持する場合だけ選べます。その場合も保持した clause、
  置換した clause、捨てた clause と理由を artifact に残します。
- scope や permission の変更は `manager` に戻します。

### Consumer root instruction composition

Consumer root の [AGENTS.md](../AGENTS.md) は communication packet や agent 発言から生成しません。
AgentCanon の [ROOT_AGENTS.md](../ROOT_AGENTS.md) common base と、consumer が所有する
`documents/agent-canon/consumer-root-instructions.md` を、明示された composer の
入力として一度の deterministic composition に渡します。生成された通常 file は
consumer が commit して読みます。source checkout、runtime projection、symlink、vendor、
submodule、singular `AGENT.md` を通信経路に追加せず、nested directory の [AGENTS.md](../AGENTS.md) は
この root composition の対象外です。

## Native Collaboration

Use the collaboration tools exposed by the current runtime. Send the selected
operation first with the current target, scope and context. An actual result
establishes launch or completion; an inventory or role name does not. Repair an
observed failure at its owner and continue independent authorized work. Do not
create a capability manifest, run directory or identity receipt.

## 主要な通信面

Use native ToolCalls and messages for task coordination. Git owns the checkout
and diff. Project-owned experiment, proof, manuscript and figure artifacts keep
their existing paths and formats. Hook logs and Eval results keep their evidence
owners. Task manifests and progress files are not produced.

## Context Visibility Contract

Context is classified before it is handed to an agent. The goal is correct
shape, ownership, and traceability, not token minimization.

| Context Class | Contents | Rule |
| --- | --- | --- |
| `llm_visible_context` | Instructions, request clauses, selected source-packet fields, exact file sections, and evidence needed for the next decision. | May be large when required, but every item is tied to an owner, path, source packet, or request clause. |
| `local_tool_context` | Files, dashboards, raw tool output, generated packets, logs, and search results available by path or tool call. | Keep raw artifacts here unless a packet promotes a selected excerpt or structured summary. |
| `durable_memory` | Stable repo policy, source packets, issues, reports, and learned feedback stored in owner surfaces. | Do not rely on chat memory or compaction as the only record. |

### Source-Bound Runtime Evidence Certificate

When a run result needs durable runtime provenance, the materializer-owned
artifact-plus-receipt certificate is the visibility boundary. Consumers may
use the canonical `agent_canon.runtime_event.v1` prepared artifact for source
event identity, result-family authority, gate result, and target/base
identities only together with the latest validated
`agent_canon.runtime_event.publication_outcome_receipt.v1`. They must not
reconstruct those guarantees from hook summaries, copied chat text, or another
producer.

The prepared artifact joins one rollout record to one fixed result artifact and
one source snapshot. Its `publication_intent` states only
`prepared_state=prepared`. Post-target evidence is retained in an append-only
observation and then a distinct immutable receipt; `uncertain` blocks
consumers, and recovery may advance only by appending a linked `committed`
receipt. The graph owner persists the exact artifact and latest committed
receipt bytes in its single `BuildMaterial` transaction. Graph status, query,
context, and dependency-review consumers reuse that snapshot, perform one
bounded freshness probe per command, and report stale or unavailable state
rather than invoking the materializer again.

This certificate contract covers the generic materializer. Hook transport has
a separate approved boundary: PostToolUse publishes canonical per-event files
to the repository-owned spool, and an explicit archive checkpoint validates,
deduplicates, publishes, reads back, and only then finalizes them. Consumers do
not infer generic certificate guarantees from that hook projection. Skill,
subagent, task, eval, experiment, and PR-publication adapters remain with their
existing owners; this boundary does not add adapter-specific regeneration.

## Owner and invalidation packets

For distributed mechanism work, direct peer delivery and durable parent relay
carry the same owner-local packet. The packet names the external authority or
witness, owner, candidate/property, causal mechanism transition,
`not_guaranteed` boundary, failure semantics, execution plane, bounded tool
input, and exactly one primary observation. Its reuse key is the existing tuple
`(candidate_digest, property_ref, owner_ref, execution_plane,
tool_input_locator)`; this is a lookup tuple, not a generated ID or registry.

When a mechanism, effect/dependency closure, input, or source snapshot changes,
the owner sends an invalidation packet only across an existing dependency edge:
`from_owner`, `to_owner`, `candidate_digest`, `changed_mechanism_ref`,
`invalidated_property_ref`, `invalidated_receipt_ref`, `reason`,
`affected_edge`, and `owner_action=reevaluate_local_correspondence`. The packet
invalidates evidence, not requirements. The downstream owner decides whether its
own receipt is affected and records reuse/not-applicable when it is not; the
parent only transports, orders, and reports status.

An integration owner consumes receipt presence, compatibility, and dependency
closure and returns missing/incompatible references. It does not rerun the
owner command. `verified` is local causal correspondence, not approval, and a
reviewer, Issue, merge state, label, copied claim, or handoff cannot substitute
for the owner receipt. If direct peer transport is unavailable, the durable
relay preserves these semantics and reports the transport limitation honestly.

Before the generic runtime-event artifact exists, the sole context handoff is
the immutable `agent_canon.context_discovery_certificate.v1` produced by
`runtime-log-archive-git append-context-discovery`. The producer reads the
native `session_meta` and selected `event_msg` / `task_complete` records from
the finite Codex rollout source, binds repository and byte-range identities,
and publishes one no-replace certificate at
`reports/agents/<run-id>/context_discovery.<certificate-id>.json`.
`materialize-runtime-event` enumerates exactly one such certificate, validates
its repository, rollout, native-record, and hash joins, and uses the certified
task-completion bytes as its source event. It must not scan for an injected
`codex.context_discovery.v1` row, use a legacy top-level `task_complete`, or
re-derive context fields from another source.

## Post-Compaction Objective Re-Declaration Contract

After context compaction is detected, the first user-facing update from the parent agent before continuing must:

- declare the final user objective and completion condition;
- reconcile that objective against the latest user instruction and durable task/plan evidence (`request_clause_ids`, packets, design evidence, or ticketed decisions), and reject stale intermediate objectives;
- only then state or execute the next concrete action.

This applies before any tool call, file edit, or subagent instruction.
Compaction is not a substitute for durable task evidence or record.

## Structure Intake Packet

Use this packet before manual broad repository reading when a repo-changing
task needs structure, ownership, path selection, stale-surface, or document
responsibility evidence. It is the canonical structure-reading entrypoint for
ordinary task intake; `structure-refactor` owns deeper layout repair and
refactor decisions.

```text
structure_intake_root=<repo-root>
structure_intake_reason=<routing|edit-path|stale-surface|document-responsibility|handoff|review>
repo_structure_contract=<artifact path>
responsibility_scope=<artifact path>
file_surface_inventory=<artifact path>
document_inventory=<artifact path|not_applicable>
selected_owner_summary=<short summary tied to request clauses>
llm_visible_context=<selected excerpts or structured summary>
local_tool_context=<complete JSON/Markdown/raw artifact paths>
next_decision_changed=<routing|edit-location|validation|review|handoff|deferral>
```

Canonical tool commands:

```bash
agent-canon repo-structure-contract --root <root> --format json > <run>/repo_structure_contract.json
tools/bin/agent-canon responsibility-scope --root <root> --format json > <run>/responsibility_scope.json
agent-canon file-surface-inventory --root <root> --root-only --json-out <run>/file_surface_inventory.json --markdown-out <run>/file_surface_inventory.md
agent-canon structured-analysis document-inventory --root <root> > <run>/document_inventory.txt
```

Run `document-inventory` when document, README, generated report, stale-doc,
or reader-navigation surfaces are implicated. In parent repos where
the structure contract is not a root view, pass the qualified source-clone
path, for example
`--contract <agent-canon-source-clone>/documents/structure/repo-structure-contract.toml`.

## Handoff Packet

### Native Execution Authority

The user agreement and selected native route define authority. The parent may
perform authorized bounded edits and may delegate independent work. Send each
child its actual checkout and allowed scope; preserve reviewer read-only roles.
No agent identity, spawn receipt or writer packet is an editing permission gate.
Preserve filesystem containment, unknown state and actual Git identity.

## Active Design Packet Schema

Keep selected design documents and review evidence at their project owner paths.
A handoff carries the needed clauses, assumptions, interfaces, side effects and
verification references. Mathematical intent, experimental inputs and proof
artifacts retain their domain contracts. No team manifest, task packet file or
custom gate is required to make those references authoritative.

## Pre-Edit Repository Investigation

Before a write, establish the target repository and revision, requested behavior
and governing contract, canonical owner, assigned write paths and authority,
checkout identity, and selected validation route. Start from the target; inspect
exact callers or history only when they resolve an open contract or a selected
cross-surface change. Existing task and handoff context is sufficient for an
ordinary bounded write; a separate investigation packet is not a dispatch
prerequisite.

Materialize structured investigation evidence or explicit request-clause mapping
only when the selected coordination or design route needs it. Such route-owned
artifacts, including `request_clause_ids` when applicable, travel through the
existing handoff; they do not gate other routes.

Asset reuse context is carried through the existing `reuse_survey` handoff field
when the splitter has investigated candidate assets. The survey may record
exact candidate paths, capabilities, dispositions, reasons, and test paths for
current or historical assets. A known selected asset and its tests become
starting context for every child; missing advisory reuse context does not block
dispatch or writing.

Broad search output or remembered context does not replace the target, governing
contract, assigned scope, or authority.

## Checkout Identity Readback

Every agent and work unit that can inspect or change repository state carries
one observational `checkout_identity` block at bounded lifecycle transitions.
The block is produced by
`tools/bin/agent-canon checkout-identity --format lines` and contains
exactly these fields:

- `cwd`: absolute directory in which the operation is acting
- `git_root`: absolute Git toplevel, or `unknown`
- `branch`: the current branch name, or `detached` for a detached `HEAD`
- `head`: the resolved `HEAD` commit, or `unknown`
- `remote`: normalized remote `owner/repository`, or `unknown`

Read it once at agent/work-unit start, after a cwd or checkout change, before
conflict resolution, before commit/push/PR, before cleanup or destructive Git,
and in subagent handoff/final handback. Reuse the same block while checkout
state is unchanged; ordinary commands do not trigger another read. The block
describes where an operation runs and does not grant authority or replace any
branch, worktree, merge, cleanup, or publication policy.

## Fresh Subagent Context Capsule

Subagents are fresh per launch and do not inherit accumulated context. Each
handoff carries the selected task, objective and owned request clauses, current
and retained requirements, relevant retirement reasons and unresolved points,
current stage and checkout identity, exact owner files or sections to read, role
boundary, expected result, and return contract. The latest explicit user
instruction governs conflicts while compatible earlier requirements remain
active. Keep evidence local unless needed for the next decision; link to this
section instead of restating capsule fields.

For write-capable work, carry the selected checkout identity and assigned
repository/path scope in the active conversation or handoff. Carry the selected route's validation command or review gate when applicable;
include route evidence only when the task needs it. Include a
`pre_handoff_gate_status` only for a gate selected by the current route. Active
gate evidence follows the rules in Handoff Packet; advisory data and unrelated
route artifacts are not generic dispatch gates.

The fresh capsule carries the same known selected asset context to every child.
For a split, extraction, or missing suspected predecessor, the splitter must
investigate current and git-history assets before decomposition or prototyping;
the resulting survey and tests are shared context. A reviewer may request
missing reuse evidence, but absent advisory context does not hard-fail dispatch
or writing.

When a role discovers an unresolved API, responsibility, path, naming, oracle,
dependency, runtime, or configuration boundary, return it with evidence to the
owning design/review route instead of absorbing it with a local fallback.

For theorem-driven, algorithm, or implementation handoffs, the capsule also
includes a `Target Binding Packet`. This prevents a subagent from proving,
refuting, naming, or implementing a nearby but different claim.

- `target_statement_or_behavior`: exact theorem, property, behavior, or patch
  slice owned by this role
- `public_root_or_entrypoint`: public function, generated root, or API surface
  that the target is about, including its input and return schema
- `projection_or_call_path`: return field, theorem projection, or code path
  through which the target is reached
- `identifier_naming_plan`: exact file, function, class, theorem, artifact,
  CLI flag, and config-key names this role may create or rename; include the
  responsibility vocabulary, local naming family, and forbidden generic names
- `accepted_top_level_assumptions`: assumptions allowed because they are over
  the target `Problem`, config, runtime environment, backend profile, or
  approved source packet
- `forbidden_assumptions`: proof-only state, proof-only config, arbitrary
  helper variables, surrogate theorem types, or local counterexamples not
  shown reachable from the public root
- `current_evidence`: generated code / IR / theorem graph / checker result /
  dependency-scope artifacts the subagent must consume
- `completion_condition`: verified, refuted, unprovable-under-assumptions, or
  patch plus validation; partial suggestions are not completion
- `unchecked_output_policy`: unchecked theorem sketches, type-incompatible
  formulas, or implementation suggestions must be labeled as unchecked and
  must not be adopted by the parent before local checker / validation evidence
  passes

Do not paste full run transcripts, full dashboards, raw accumulated logs, or
entire repo docs into the prompt. If a child needs more context, refer to the
smallest relevant source or result and carry any scope change in the existing
handoff.

### Optional Rejection Prediction

Select required checks from the changed contract and its owning validation route.
When those are known, proceed directly; path-based rejection prediction is an
optional diagnostic, not an edit, handoff, or completion gate:

```bash
tools/bin/agent-canon tool-rejection-preflight --root . <planned-edit-paths>
```

Use it only to resolve uncertainty about relevant checks. Predictions are
candidates, not observed failures or authority to add checks and repairs.
An unavailable or unused predictor does not block otherwise authorized work;
do not require a pending blocker, pass, or skip record for it. Required
validation, authorization, and safety checks retain their own failure semantics.

Use diagnostic results in the current conversation only when they change a
decision. No diagnostic work log or status fields are required. The diagnostic
`responsibility_scope` gate records the `responsibility-scope.toml` scope,
owner, class, and protecting tools for each planned path; it does not replace
the owner's contract or prove that those checks ran.

## Review Decision Boundary

The selected reviewer reports its decision and findings through native handoff.
Resolve accepted findings against the current contract and diff. Lifecycle status
and a successful tool call do not establish a review decision.

## Review Packet

- `request_clause_ids`
- `finding`
- `severity`
- `required_change`
- `intent_preservation`: validation-failure response values are the canonical
  slugs from `documents/runtime/runtime-profiles-and-check-matrix.json`; reviewer
  withdrawal, supersession, owner-boundary, or unsafe-replacement rationale
  belongs in `revert_or_discard_authority` instead of extending this field
- `revert_or_discard_authority`: rollback、revert、または slice discard を求める
  場合だけ、撤回 / 置換 / owner 外 / unsafe replacement / escalation の根拠を書く
- `evidence`
- `status`

## Git Write Scope

The active task handoff identifies the selected repository, branch, and owned
paths. Before mutation, read the checkout's branch and current Git state, keep
changes within the assigned responsibility, and preserve unknown changes.
Serialize changes that share a file, directory owner, Git index, or public
surface. Do not create a separate write-scope packet or agent identity record.
file 境界を切れない場合は、同一 workspace の並列 write をやめ、別 worktree へ分けるか parent が直列化します。

## Escalation

次では `manager` へ戻します。

- reviewer と execution role で合意できない
- scope 外の変更が必要
- permission 拡張が必要
- research や experiment だけでは根拠が不足する
- infra change に rollback がない
