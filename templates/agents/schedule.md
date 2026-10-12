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

## Clause Coverage（clause coverage）

| Clause ID | Covered By Stage | Review Gate | Status |
| --------- | ---------------- | ----------- | ------ |

## Planned Work Units（planned work unit）

<!-- この table が canonical task TODO surface です。closeout まで具体的な work unit と status をここに保持します。 -->

| Unit ID | Clause IDs | Owner | Completion Evidence | Next Gate | Status |
| ------- | ---------- | ----- | ------------------- | --------- | ------ |

## Task Completion Boundary（task 完了境界）

<!-- user-facing completion 前に成立すべき条件を定義します。active clause 解決、selected work unit 完了、selected owning review gate の判定、validation、closeout、commit/push を含みます。candidate review pack と rejected hypothesis は work を作らず、chunk/slice/checkpoint/subpass は内部進捗だけです。 -->

## Explicit Subagents（明示的 subagent）

<!-- 各 stage に使う具体的な Codex subagent または permanent team role を記録します。 -->

## Reuse And Continuity Constraints（reuse と継続の制約）

<!-- 従うべき既存 code、naming、API、test、docs style を記録します。 -->

## Risks（リスク）

<!-- sequencing risk、merge risk、verification risk を記録します。 -->
