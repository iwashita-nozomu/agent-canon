# Closed AgentCanon Operational Issues

<!--
@dependency-start
contract issue
responsibility Documents closed AgentCanon operational issue storage.
upstream design ../README.md defines issue lifecycle and required fields
@dependency-end
-->

Move an issue file here only after its `status`, `resolved_by`, and
`close_condition` show the implemented and validated fix.
Closed issue files keep the same `AC-YYYYMMDD-short-slug.md` name they used in
`issues/open/`.

Closed issue files are immutable historical records. Codex and reviewers must
not treat them as active runtime, workflow, skill, or validation rules. When a
closed issue reveals a new current problem, open or update an active issue and
edit the owning source document instead of appending new scope here.
