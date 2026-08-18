# Environment Change Proposal（環境変更提案）
<!--
@dependency-start
contract template
responsibility Documents Environment Change Proposal for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}
- Created At (UTC): {\{CREATED_AT}}

{{>reader_map}}

## Requirement Trace（要件 trace）

- Triggering Code Requirement（変更を要求する code 要件）:
- Blocked Or At-Risk Command（block または risk のある command）:
- Runtime Capability Needed（必要な runtime capability）:
- Why Existing Environment Is Insufficient（既存環境で足りない理由）:

## Motivation（動機）

<!-- なぜこの tool/environment change が必要で、なければどの workflow が block されるかを記録します。 -->

## Scope（対象）

- Surface: <!-- host / docker / CI / docs / scripts -->
- Affected Commands: <!-- make target、script、workflow -->
- Affected Code Paths Or Packages:
- Users Impacted: <!-- local only、CI only、または both -->

## Surface Decision（surface の判断）

- Preferred Source Of Truth: <!-- host / docker image / CI / shared script -->
- Why This Surface Owns The Change（この surface が変更を所有する理由）:
- Surfaces Explicitly Not Changed（明示的に変更しない surface）:

## Proposed Change（提案する変更）

- Tool Or Package:
- Purpose:
- Preferred Installation Surface:
- Alternatives Considered（検討した代替案）:

## Canon Impact（canon への影響）

- `docker/Dockerfile` update: <!-- yes/no + note -->
- `docker/requirements.txt` update: <!-- yes/no + note -->
- devcontainer / runtime pack update: <!-- yes/no + note -->
- CI / workflow update: <!-- yes/no + note -->
- Docs to update: <!-- README, QUICK_START, documents/... -->

## Validation Plan（validation 計画）

- Local checks（local check）:
- CI checks（CI check）:
- Runtime smoke command（runtime smoke command）:
- Rollback plan（rollback 計画）:

## Decision（判定）

<!-- approve / revise / reject を記録します。 -->
