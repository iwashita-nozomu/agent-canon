<!--
@dependency-start
contract template
responsibility Documents Schedule for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
upstream design ../../agents/skills/agent-orchestration.md execution-time-aware work-conservation owner
@dependency-end
-->

# Schedule（schedule）


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

{{>reader_map}}

## Stage Plan（stage 計画）

| Stage | Owner Agent | Review Agent | Inputs | Exit Criteria | Status |
| ----- | ----------- | ------------ | ------ | ------------- | ------ |

## Execution-Time-Aware Plan（実行時間を考慮した計画）

<!-- 下記の canonical owner を射影し、scheduling policy を再記述したり duration cutoff を追加したりしません。AgentCanon execution graph が active な run では ready_set / dispatch_batch / wait_reason は actual ToolCall transition の readback であり、parent が手動で波や完了を決定しません。 -->

- Owner contract: `agents/skills/agent-orchestration.md#Execution-Time-Aware Work-Conservation Contract`
- Executable scheduling fields: `dependency_dag`, `responsibility_completeness`, `correctness`, `decision_relevant_total_work`, `makespan_objective`, `critical_path`, `ready_set`, `context_reuse`, `affected_evidence_invalidation`, `candidate_epoch`, `blocking_finding_ids`, `focused_recheck`, `terminal_state`.
- Dependency DAG / closure:
- Responsibility completeness:
- Correctness:
- Decision-relevant total work:
- Makespan objective:
- Critical path:
- Ready set:
- Useful ready set:
- Dispatch batch:
- Wait reason (only when the useful ready set is empty):
- Context reuse:
- Affected evidence invalidation:
- Candidate epoch:
- Blocking finding IDs:
- Focused recheck:
- Terminal state:

### Distributed owner correspondence

Scheduling fields are local work-convergence state; they do not create a
guarantee or approval authority. Each mechanism owner records one causal
owner-local receipt with its authority/witness, mechanism transition,
`not_guaranteed` boundary, execution plane, bounded tool input, and exactly one
primary observation. Reuse the tuple
`(candidate_digest, property_ref, owner_ref, execution_plane,
tool_input_locator)` and invalidate only the owner receipt plus existing
dependency-edge descendants affected by a mechanism/input/source change.
The parent transports and orders packets. Integration consumes receipt
presence/compatibility/DAG closure and does not rerun owner commands.

- Owner receipt references:
- Invalidation packets along existing edges:
- Integration missing/incompatible receipts:
- Unaffected receipts reused:

| DAG Node | Depends On | Conflict Scope | Status | Evidence |
| -------- | ---------- | -------------- | ------ | -------- |

## Clause Coverage（clause coverage）

| Clause ID | Covered By Stage | Review Gate | Status |
| --------- | ---------------- | ----------- | ------ |

## Planned Work Units（planned work unit）

<!-- この table が canonical task TODO surface です。closeout まで具体的な work unit と status をここに保持します。 -->

| Unit ID | Clause IDs | Owner | Completion Evidence | Next Gate | Status |
| ------- | ---------- | ----- | ------------------- | --------- | ------ |

## Task Completion Boundary（task 完了境界）

<!-- user-facing completion 前に成立すべき条件を定義します。active clause 解決、selected work unit 完了、selected owning review gate の判定、review convergence、validation、closeout gate unlock、commit/push を含みます。candidate review pack と rejected hypothesis は work を作らず、chunk/slice/checkpoint/subpass は内部進捗だけです。 -->

## Explicit Subagents（明示的 subagent）

<!-- 各 stage に使う具体的な Codex subagent または permanent team role を記録します。 -->

## Agent Wave Ledger（agent wave ledger）

<!-- Agent Wave Ledger は team_manifest.yaml の execution_graph.result_readback と workflow_monitor.py の Actual Wave Events を表示する欄です。readiness / completion は run manifest の実 ToolCall result で判断し、この表から wave を追加・完了扱いしません。mid-task user additions は既存の workflow_monitor.py route で記録し、その変更後の graph transition を同じ run に渡します。`Delegated Policy Ref` は指定された team_manifest path を指します。 -->

| Wave ID | Parent Or Delegate | Spawn Authority | Trigger | Budget Before | Budget After | Runtime Max Threads | Runtime Max Depth | Spawned Roles | Role Instances | Skipped Roles / Rationale | Allowed Paths | Do Not Read | Write Scope | Validation Route | Review Gate | Handoff Artifacts | Delegated Policy Ref | Status |
| ------- | ------------------ | --------------- | ------- | ------------- | ------------ | ------------------- | ----------------- | ------------- | -------------- | ------------------------- | ------------- | ----------- | ----------- | ---------------- | ----------- | ----------------- | -------------------- | ------ |

## Reuse And Continuity Constraints（reuse と継続の制約）

<!-- 従うべき既存 code、naming、API、test、docs style を記録します。 -->

## Risks（リスク）

<!-- sequencing risk、merge risk、verification risk を記録します。 -->
