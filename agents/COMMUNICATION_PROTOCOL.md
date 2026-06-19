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

## 基本ルール

- 次の role が判断に使う情報は artifact に残します。
- reviewer は repo を直接修正せず、required change を artifact に残します。
- review を受けた role は `resolved`、`rejected`、`escalated` のいずれかで必ず応答します。
- scope や permission の変更は `manager` に戻します。

## 主要な通信面

1. `reports/agents/<run-id>/` の role artifact
1. `decision_log.md`
1. `team_manifest.yaml`

run 固有のやり取りは report bundle に残し、repo-wide の正本には持ち込みません。

## Handoff Packet

- `from`
- `to`
- `stage`
- `request_clause_ids`
- `summary`
- `requested_action`
- `pre_edit_repository_investigation`
- `fresh_subagent_context_capsule`
- `artifacts`
- `repo_changes`
- `pre_edit_rejection_prediction`
- `predicted_tool_rejection_gates`
- `rejection_preflight_command`
- `gate_specific_repair_plan`
- `design_issue_blocker`
- `open_questions`
- `status`

## Pre-Edit Repository Investigation Packet

Before selecting edit paths, direct parent edits, or write-capable subagent
handoff, the parent records a bounded pre-edit investigation packet. This is
the minimum evidence that repo investigation happened before implementation.

- `request_clause_ids`: user clauses covered by the edit
- `workflow_and_skills`: selected workflow, active skills, deferred dynamic
  wave triggers
- `implementation_surface_route`: `PRIMARY_SURFACE`, `PRIMARY_PATHS`,
  `FORBIDDEN_PATHS`, `REQUIRED_PRE_EDIT_CHECKS`, or a router-unavailable
  blocker
- `responsibility_search`: compact semantic-index / local-LLM / tool-catalog
  result paths, not broad raw `rg` dumps
- `reuse_survey`: existing tools, skills, workflows, helpers, libraries, and
  why reuse / extension / deletion / new implementation was selected
- `stale_surface_scan`: obsolete mirror, generated artifact, legacy wrapper,
  old convention, or source-canon drift checked before edits
- `dependency_scope`: `dependency_edit_scope.txt`, `dependency_graph.tsv`, or
  reason dependency expansion is not applicable
- `validation_route`: targeted checks and closeout gates derived from the
  packet
- `open_questions`: only items that cannot be resolved from repo evidence

Raw search hits, chat memory, and a list of nearest files are not sufficient.
If the packet is missing, implementation returns to investigation instead of
guessing an edit path.

## Fresh Subagent Context Capsule

Subagents are fresh per launch and do not inherit accumulated context. Each
handoff therefore includes a compact context capsule that is self-contained
enough to execute the role, but bounded enough to avoid broad repo reading.

- `objective`: one sentence with active non-goals
- `request_clause_ids`: clauses the subagent owns
- `state_snapshot`: branch, relevant commit or run-id, current stage, and
  parent integration owner
- `read_before_work`: exact files or sections to read, capped to role-owned
  surfaces
- `compact_artifacts`: router output, dashboard summary, checker finding
  packet, dependency scope, design trace, or report summary paths
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
catalog, agent protocol convention, or log-surface inventory, the implementer
receives the gate-specific command and a repair plan before editing. This
prevents spending implementation tokens
on changes that the hook/tool layer can already predict will be rejected.

## Review Packet

- `request_clause_ids`
- `finding`
- `severity`
- `required_change`
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
