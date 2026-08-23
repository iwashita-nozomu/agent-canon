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
downstream design workflows/implementation-waterfall-workflow.md consumes the active design packet contract
downstream implementation ../tools/agent_tools/agent_team.py normalizes and materializes active design packets
downstream implementation ../tools/agent_tools/waterfall_gate_check.py validates persisted active design packets
downstream implementation ../tools/agent_tools/tool_rejection_preflight.py predicts edit-time tool rejection gates
@dependency-end
-->


この文書は、agent-to-agent handoff と review の正本です。

## Reader Map

- This document owns the artifact-level communication contracts for handoff, pre-edit investigation, fresh subagent capsules, review packets, write scope, and escalation.
- The first sections define common rules and communication surfaces; the packet sections then specify exactly what must be handed between parent, subagents, reviewers, and implementers.
- Use `## Pre-Edit Repository Investigation Packet` before selecting edit paths, and `## Fresh Subagent Context Capsule` before launching or reusing any run-local subagent.
- For chunked reading, start from the packet type required by the current transition and read only the fields needed to make that transition auditable.
- After context compaction, follow `## Post-Compaction Objective Re-Declaration Contract` before any resumed action.

### Compact request/update projection

`../documents/design/request-intent-and-update-relation.md` is the compact flow connected to
this protocol's active context, write-scope, and handoff. Deltas attach to existing
capsules/packets, compatible context is reused, and only disjoint scope receives a separate
handoff. Transport schema and context ownership remain here.
Approved request effects travel through the existing goal/artifact/order/handoff delta fields;
write authority remains with the existing owner/write-scope packet.

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
- review の `rejected`、`revise`、`required_change` は、提案された実装や
  修正方法への判定であり、user request や design intent を rollback する権限では
  ありません。実行 role は、同じ意図を保つ修正、同じ意図を保つ再設計、または
  design / scope conflict の escalation に接続します。
- 実装 slice の削除、revert、discard は、該当 request clause が user / owner に
  よって撤回または置換された、canonical owner 外だった、または危険で代替修正や
  escalation が同じ意図を保持する場合だけ選べます。その場合も保持した clause、
  置換した clause、捨てた clause と理由を artifact に残します。
- scope や permission の変更は `manager` に戻します。

## Runtime Collaboration Capability Handshake

This section is the sole owner of the runtime collaboration capability and
coordination receipt contract. Generated manifests and hook events reference
this contract; they do not redefine its schema or infer platform capability.

The capability source is the direct runtime collaboration namespace exposed to
the current agent. `functions.exec` and its `ALL_TOOLS` inventory are never
capability evidence. A handshake has the following closed fields:

- `schema`: `agent-canon.communication-capability-handshake.v1`
- `status`: exactly `available`, `unavailable`, or `unverified`
- `effective_operations`: operations explicitly returned by the direct runtime
  readback, not merely names recognized by a matcher
- `evidence_ref`: a durable artifact or runtime readback reference; it is
  required for `available` and must not be fabricated when the runtime cannot
  expose it
- `source`: exactly `direct_runtime_collaboration_namespace`

The effective transport is derived from the handshake:

| status | allowed coordination mode | meaning |
| --- | --- | --- |
| `available` | `direct_peer` | the named operation was read back from the direct namespace |
| `unavailable` | `parent_relay` or `durable_artifact` | the parent or an artifact carries the message; no peer claim |
| `unverified` | `parent_relay` or `durable_artifact` | capability was not observed and remains unknown |

An operation matcher is observation only. Seeing `send_message`,
`followup_task`, `list_agents`, or `interrupt_agent` in an event does not change
`unavailable` or `unverified` into `available`.

### Coordination Receipt

Every coordination attempt emits one coordination receipt through the existing
`HookLogContext.append` base-event route. It is stored under the
`coordination_receipt` member of that transport event; it is not added to the
fixed `agent-canon.behavior-event.v1` snapshot field set. Its closed fields are:

- `schema`: `agent-canon.coordination-receipt.v1`
- `operation`: the observed operation
- `capability_status`: the handshake status used for the decision
- `effective_operations`: operations actually read back from the direct runtime
  namespace; the hook route uses an empty list when no readback is available
- `evidence_ref`: the handshake evidence or an explicit artifact reference
- `transport`: `direct_peer`, `parent_relay`, or `durable_artifact`
- `direct_peer`: a boolean consistency readback for the transport
- `status`: `succeeded`, `failed`, or `invalid_tool_result`, derived from the
  real tool response

`transport=direct_peer` is valid only with `capability_status=available` and
an evidence reference that names the operation. The hook dispatcher cannot
observe the parent handoff capability, so its receipt is always
`capability_status=unverified`, `effective_operations=[]`,
`transport=durable_artifact`, and `direct_peer=false`. A parent relay is always
recorded as `parent_relay`; it must never be rewritten as direct peer
communication. If the runtime cannot return the direct namespace, use
`durable_artifact` and preserve the honest `unverified` or `unavailable` status.

## 主要な通信面

1. `reports/agents/<run-id>/` の role artifact
1. `decision_log.md`
1. `team_manifest.yaml`

run 固有のやり取りは report bundle に残し、repo-wide の正本には持ち込みません。

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

Before the generic runtime-event artifact exists, the sole context handoff is
the immutable `agent_canon.context_discovery_certificate.v1` produced by
`runtime_log_archive_git.py append-context-discovery`. The producer reads the
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
import_responsibility=<artifact path|not_applicable>
selected_owner_summary=<short summary tied to request clauses>
llm_visible_context=<selected excerpts or structured summary>
local_tool_context=<complete JSON/Markdown/raw artifact paths>
next_decision_changed=<routing|edit-location|validation|review|handoff|deferral>
```

Canonical tool commands:

```bash
python3 tools/agent_tools/repo_structure_contract.py --root <root> --format json > <run>/repo_structure_contract.json
python3 tools/agent_tools/responsibility_scope.py --root <root> --format json > <run>/responsibility_scope.json
python3 tools/agent_tools/file_surface_inventory.py --root <root> --submodule-aware --json-out <run>/file_surface_inventory.json --markdown-out <run>/file_surface_inventory.md
agent-canon structured-analysis document-inventory --root <root> > <run>/document_inventory.txt
python3 tools/agent_tools/import_responsibility.py --root <root> --format json > <run>/import_responsibility.json
```

Run `document-inventory` when document, README, generated report, stale-doc,
or reader-navigation surfaces are implicated. Run `import_responsibility.py`
when import boundaries or package layout are implicated. In parent repos where
the structure contract is not a root view, pass the qualified source-clone
path, for example
`--contract <agent-canon-source-clone>/documents/structure/repo-structure-contract.toml`.

## Handoff Packet

### Parent Orchestration-Only Contract

For every repository-changing task, including a bounded owner/path/validation
request, the parent is an orchestrator only. The parent may select and launch
agents, relay packets without changing their claims, manage dependency and
integration order, monitor status, and return final external readback. The
parent must not investigate, design, implement, run tests, review diffs, draft
or publish Issues/PRs, score evaluations, decide convergence, resolve merge
conflicts, or interpret validation/finding results.

A write-capable child is mandatory for every repository edit. Missing spawn
authorization, tool access, or another launch gate produces a typed
`status=blocked` / retry / user-report packet; it never authorizes a parent
write. Decision-owning reviewers or ship reviewers accept/reject findings and
choose the next action. A verifier runs prescribed validation, an auditor
creates the closeout artifact, an integration executor performs merge and
conflict resolution, a publisher or PR-processing child performs Issue/PR
writes, and an evaluation reviewer owns scoring and convergence.

Read-only conversational answers remain outside this repository-changing
route and do not create a write handoff.

Implementation handoffs project the canonical TargetStateContract and
ImplementationExecutionContract: complete owner/type/API/config/schema/path/
dependency/transition/deletion/validation structure, immutable packet identity,
Decision Sufficiency record, and empty unresolved decisions. An identical
owner/edit/validation action transitions directly to one complete materializer
pass and one post-completion owning gate. `ImplementationFeedback` covers
compile/static/deterministic failures; only an exact `StructuralDesignGap` is
repaired once and resumed by the same Spark. Tool calls are registry-issued
machine-readable `ToolCallToken` values.

Capacity and lifecycle fields use the canonical requested/configured/
platform-effective/workflow-demand/write-cap/nested-reserved/available terms;
effective is the minimum of available constraints after reservations. Closeout
must carry full descendant topology, durable handback, closure verification,
reservation release, and the canonical `close_agent` ToolCall. Open terminal
descendants, unknown descendants, missing handback, and reservation leaks fail.

- `from`
- `to`
- `stage`
- `request_clause_ids`
- `summary`
- `requested_action`
- `pre_edit_repository_investigation`
- `fresh_subagent_context_capsule`
- `pre_handoff_gate_status`
- `artifacts`
- `repo_changes`
- `pre_edit_rejection_prediction`
- `predicted_tool_rejection_gates`
- `rejection_preflight_command`
- `gate_specific_repair_plan`
- `design_issue_blocker`
- `open_questions`
- `status`

`pre_handoff_gate_status` records gate evidence before a write-capable
implementation handoff. Design-backed implementation handoffs require the
current `design_brief.md` path or revision and the selected owner/design gate.
`design_review.md` `Design Artifact Under Review`, approve evidence,
`waterfall-gate-check --gate design` evidence, and selected
`document_flow_review.md` status are required only when those gates are active.
Missing candidate review artifacts do not block an otherwise semantically
sufficient handoff; an active gate with missing, stale, or non-approve evidence
returns the task to its owning route.

## Active Design Packet Schema

This document owns the artifact-level schema named
`waterfall.design_packet.v1`. The record is closed and contains the five
runtime selection fields plus one clause registry and four typed graph entries:

- `schema`
- `design_artifact`
- `design_review_artifact`
- `document_flow_review_artifact`
- `document_flow_required`
- `clause_registry`
- `abstract_design_frame`
- `implementation_source_packet`
- `design_side_effect_map`
- `design_to_implementation_trace`

`schema` must equal `waterfall.design_packet.v1`. The three artifact fields are
non-empty relative paths that remain inside one run bundle and do not traverse
symlinks. `document_flow_required` is a boolean. Missing, unknown, mistyped, or
outside-bundle fields fail closed with the input boundary's typed field prefix.

Each graph entry is closed to `entry_id`, `responsibility_id`, `clause_refs`,
`owner_refs`, `source_refs`, `dependency_refs`, `output_refs`, and
`reviewer_refs`; entry dependencies are validated as a fixed acyclic order.
`agents/agents_config.json#artifacts.active_design_packet` owns the standard
record. `agent_team.py` owns the executable schema constants, normalization,
precedence, graph materialization, and source-byte identity used by task-start
and bootstrap. An explicit
`--active-design-packet` record overrides a workflow-family record, which
overrides the standard registry record. The selected record is persisted at
`team_manifest.yaml#run.active_design_packet`; after publication, that manifest
record is the only gate input. Producers, shared normalizers, materializers,
runtime checkers, and the waterfall gate must consume this same closed field
set and schema name.

The `implementation_source_packet` and `design_to_implementation_trace` entries
must include the logical `artifact:semantic_responsibility_contract.toml`
source reference when the task has semantic deltas. The reference points into
the current run bundle; the contract checker validates the instance identity
and references without turning the active packet into a second responsibility
schema.

## Pre-Edit Repository Investigation Packet

Before selecting edit paths, direct parent edits, or write-capable subagent
handoff, the parent records a pre-edit investigation packet with explicit owner
and scope. This is the required evidence that repo investigation happened
before implementation.

- `request_clause_ids`: user clauses covered by the edit
- `workflow_and_skills`: selected workflow, active skills, deferred dynamic
  wave triggers
- `structure_intake`: `Structure Intake Packet` path, or reason it is not
  applicable
- `implementation_surface_route`: `PRIMARY_SURFACE`, `PRIMARY_PATHS`,
  `FORBIDDEN_PATHS`, `REQUIRED_PRE_EDIT_CHECKS`, or a router-unavailable
  blocker
- `responsibility_search`: structured semantic-index / deterministic search / tool-catalog
  result paths, not broad raw text-search dumps
- `reuse_survey`: existing tools, skills, workflows, helpers, libraries, and
  why reuse / extension / deletion / new implementation was selected
- `semantic_responsibility_contract`: run-local contract path, policy reference,
  delta actions, obligation owners, and hard-edge closure readback
- `stale_surface_scan`: obsolete mirror, generated artifact, legacy wrapper,
  old convention, or source-canon drift checked before edits
- `dependency_scope`: `dependency_edit_scope.txt`, `dependency_graph.tsv`, or
  reason dependency expansion is not applicable
- `validation_route`: targeted checks and closeout gates derived from the
  packet
- `llm_visible_context`: selected excerpts, structured summaries, or evidence
  that must be in the prompt for the next decision
- `local_tool_context`: artifact paths, command outputs, raw logs, dashboards,
  or search results intentionally kept out of the prompt
- `durable_memory_refs`: stable policy, issue, report, source packet, or memory
  references that survive chat compaction
- `open_questions`: only items that cannot be resolved from repo evidence

Raw search hits, chat memory, and a list of nearest files are not sufficient.
If the packet is missing, implementation returns to investigation instead of
guessing an edit path.

## Fresh Subagent Context Capsule

Subagents are fresh per launch and do not inherit accumulated context. Each
handoff therefore includes a structured context capsule that is self-contained
enough to execute the role and owned enough to avoid unrelated repo reading.

- `objective`: one sentence with active non-goals
- `request_clause_ids`: clauses the subagent owns
- `state_snapshot`: branch, relevant commit or run-id, current stage, and
  parent integration owner
- `read_before_work`: exact files or sections to read within role-owned
  surfaces
- `context_artifacts`: router output, dashboard summary, checker finding
  packet, dependency scope, design trace, or report summary paths
- `subagent_startup_route`: private internal startup route path from
  `team_manifest.yaml` `run.subagent_prompt_packet.subagent_startup_route`, or
  `not_applicable` when the run manifest does not provide one
- `pre_handoff_gate_status`: design review and gate-check status required
  before write-capable implementation handoff
- `allowed_paths` / `do_not_read`: role-specific path boundaries
- `expected_output_schema`: artifact name, findings format, or patch summary
- `validation_route`: commands or review gate the parent will use
- `return_contract`: what changed, what evidence supports it, unresolved
  blockers, and whether more context is needed
- `design_issue_policy`: if the role finds an API shape, responsibility
  boundary, path layout, naming, algorithm, theorem target, test oracle,
  dependency direction, runtime contract, or config-surface gap, it records
  `design_issue_blocker` with evidence and returns to the design/review gate
  instead of absorbing the issue with local fallback, wrapper, helper, branch,
  compatibility route, test relaxation, or docs overwrite

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
entire repo docs into the prompt. If a subagent needs more context, it asks for
an expanded packet path; parent updates the capsule and records the change in
the Agent Wave Ledger.

Before the parent edits directly or a write-capable subagent starts repository
edits, the parent runs or cites:

```bash
python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>
```

The handoff work log includes the resulting
`TOOL_REJECTION_PREDICTED_GATE` lines or an explicit
`TOOL_REJECTION_PREFLIGHT=pass` observation. If a predicted gate names OOP
readability, helper inventory, dependency headers, GitHub workflow checks, hook
runtime alignment, skill mirror sync, AgentCanon tool source routing, tool
catalog, agent protocol convention, responsibility scope, or log-surface
inventory, the implementer receives the gate-specific command and a repair plan
before editing. The `responsibility_scope` gate records the owning
`responsibility-scope.toml` scope, owner, class, and protecting tools for each
planned path, so the implementation surface stays inside the declared owner
contract.

## CompletionCoverage v1 Schema Contract

`COMMUNICATION_PROTOCOL.md` owns the human-readable schema and evidence
semantics for the deterministic completion read model. The canonical chain is
the existing append-only logical run ledger, the generated
`agent-canon.completion-coverage.v1` artifact, and its deterministic reader.
No database, persistence service, second ledger, or closeout aggregation is
introduced.

The ledger accepts exactly these semantic kinds:
`request_clause`, `responsibility_unit`, `decision`, `change`,
`review_finding`, `validation`, `failure`, `publication_state`, and `deferral`.
Every event is bound to `run_id`, `context_id`, an event identity or sequence,
an `intent_id`, an owner, `state_owner`, `api_owner`, `dependency_owner`, an
outcome, and source/artifact evidence references. Responsibility boundaries,
decisions, failures, deferrals, and publication transitions cannot be grouped.

The generated v1 artifact carries `source_binding`, deterministic projection
metadata, semantic events, `coverage_map`, typed owner-boundary evidence, gate
evidence, failure responses, and applicable W1 resource certificates. A
coverage map has one direct or mechanically valid group mapping per active
clause. Success requires `uncovered`, `multiply_mapped`, `orphan`, `redundant`,
and `empty` to all be empty. Group mappings retain explicit member IDs and are
allowed only for mechanically identical owner/unit/outcome facts.

Typed OOP evidence consists only of owner overlap, state ownership, API
boundary, and dependency-boundary facts. Line count, length, scalar score,
`min_score`, and `final_score` are not schema fields or completion gates.
Test-first, test-count/coverage, mutation, private-helper, and checker-retest
rules are not evidence gates; each residual trust boundary has one canonical
evidence owner.

The single Markdown/math/Mermaid format/check route is
`tools/bin/agent-canon docs check <changed-markdown-paths>`. The single
PostToolUse/Stop hook contract is the existing dispatcher, with schema
`agent-canon.posttooluse-stop.v1`; readers consume its evidence and do not add
a second dispatcher or child-check path.

Validation failures record `failing_contract`, `observation_level`,
`cause_classification`, `intent_preservation`, `evidence`, the two taxonomy
references (`documents/runtime/runtime-profiles-and-check-matrix.json` and its
generated Markdown reader), same-intent repair or escalation, its owner and
result, and result artifact references. The taxonomy text is not copied into
this schema.

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

## Write Scope Packet

- `role`
- `workspace`
- `allowed_paths`
- `forbidden_paths`
- `owned_files`
- `integration_owner`
- `merge_strategy`

write-capable role を複数使う場合は、handoff の前に write scope packet を残します。
同じ file を 2 つの writer に同時に割り当てません。
同じディレクトリを複数 writer が触る場合は、`owned_files` を file 単位で disjoint にします。
file 境界を切れない場合は、同一 workspace の並列 write をやめ、別 worktree へ分けるか parent が直列化します。

## Escalation

次では `manager` へ戻します。

- reviewer と execution role で合意できない
- scope 外の変更が必要
- permission 拡張が必要
- research や experiment だけでは根拠が不足する
- infra change に rollback がない
