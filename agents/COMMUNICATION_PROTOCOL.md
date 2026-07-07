# Agent Communication Protocol
<!--
@dependency-start
contract agent-runtime
responsibility Documents Agent Communication Protocol for this repository.
upstream design README.md agent canon overview
downstream design skills/agent-orchestration.md routes pre-edit investigation before path selection
downstream design skills/codex-task-workflow.md consumes pre-edit investigation and context capsules
downstream design skills/subagent-bootstrap.md consumes fresh subagent context capsules
downstream implementation ../tools/agent_tools/tool_rejection_preflight.py predicts edit-time tool rejection gates
@dependency-end
-->


この文書は、agent-to-agent handoff と review の正本です。

## Reader Map

- This document owns the artifact-level communication contracts for handoff, pre-edit investigation, fresh subagent capsules, review packets, write scope, and escalation.
- The first sections define common rules and communication surfaces; the packet sections then specify exactly what must be handed between parent, subagents, reviewers, and implementers.
- Use `## Pre-Edit Repository Investigation Packet` before selecting edit paths, and `## Fresh Subagent Context Capsule` before launching or reusing any run-local subagent.
- For chunked reading, start from the packet type required by the current transition and read only the fields needed to make that transition auditable.

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
the structure contract is not a root view, pass
`--contract vendor/agent-canon/documents/repo-structure-contract.toml`.

## Handoff Packet

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
current `design_brief.md` path or revision, matching `design_review.md`
`Design Artifact Under Review`, `design_review.md decision=approve`,
`waterfall-gate-check --gate design` pass evidence, and selected
`document_flow_review.md` status when that workflow gate is active. Missing,
stale, or non-approve design review status returns the task to Gate 5-6 before
handoff.

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
- `responsibility_search`: structured semantic-index / local-LLM / tool-catalog
  result paths, not broad raw text-search dumps
- `reuse_survey`: existing tools, skills, workflows, helpers, libraries, and
  why reuse / extension / deletion / new implementation was selected
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

## Parent-Direct Context Note

For an approved parent-direct exception whose owner boundary, replaceable unit,
validation route, and public impact boundary are already evidenced, the full
Pre-Edit Repository Investigation Packet can be replaced by a short
Parent-Direct Context Note. Routine docs, Focused code, typo/link/format-only,
or other bounded work still needs the exception rationale when the work is
repo-changing implementation / patch / doc-edit. File count alone is not enough
to choose this note.

The note records:

- `owner`
- `target_path`
- `request_clause`
- `parent_direct_exception_rationale`
- `reuse_basis`
- `design_oop_boundary`
- `pre_handoff_gate_status`
- `validation_route`
- `llm_visible_context`
- `local_tool_context`
- `durable_memory_refs`

The note is still a context-construction artifact. Raw search hits, nearest
editable files, and chat context alone are not enough.

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

The handoff or parent-direct work log includes the resulting
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

## Review Packet

- `request_clause_ids`
- `finding`
- `severity`
- `required_change`
- `intent_preservation`: validation-failure response values are the canonical
  slugs from `documents/runtime-profiles-and-check-matrix.json`; reviewer
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
