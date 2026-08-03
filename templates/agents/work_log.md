# Work Log（作業ログ）
<!--
@dependency-start
contract template
responsibility Documents Work Log for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {{RUN_ID}}
- Task: {{TASK}}
- Owner: {{OWNER}}
- Created At (UTC): {{CREATED_AT}}

{{>reader_map}}

## Purpose（目的）

<!-- 意味のある execution step を chronological な run-local log として保持します。worktree action log が active でなくても必須です。 -->

- owner / responsibility unit:
- design-to-implementation trace:
- dependency / side-effect map:
- conflict intent and preserved state:
- failure-cause classification for unexpected actions:

## Entries（記録）

<!-- 意味のある step ごとに time、kind、request clause ID、ref、next action を 1 行追加します。 -->

## Wave Event Log（wave event log）

<!-- subagent wave event ごとに 1 行追加します。schedule.md と同じ Wave ID を使い、Wave Plan Contract の field、evidence ref、next action を記録します。 -->

| Time | Wave ID | Event Kind | Stage | Spawn Authority | Trigger | Budget Before | Budget After | Runtime Max Threads | Runtime Max Depth | Spawned Roles | Skipped Roles / Rationale | Allowed Paths | Do Not Read | Write Scope | Validation Route | Review Gate | Handoff Artifacts | Refs | Next Action |
| ---- | ------- | ---------- | ----- | --------------- | ------- | ------------- | ------------ | ------------------- | ----------------- | ------------- | ------------------------- | ------------- | ----------- | ----------- | ---------------- | ----------- | ----------------- | ---- | ----------- |
