# Agent coordination boundaries

<!--
@dependency-start
contract design
responsibility Defines the remaining role, packet, and tool-call owners after custom run-bundle retirement.
upstream design ../../agents/COMMUNICATION_PROTOCOL.md native collaboration
upstream design rust-agent-tool-migration.md retained tool migration
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/codex_agent_role_eval/routing.rs owns native task/role consistency
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/active_design_packet.rs owns persisted active-design packet normalization
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/issue_sync.rs owns IssueSync resident receipt commands
@dependency-end
-->

## Decision

Codex provides agent execution and collaboration. Git and the current conversation
carry the agreed scope, handoff, progress, and completion evidence. The custom
AgentTeam facade, run bootstrap, per-task contract/progress files, stage gates,
and task-close command are retired. Retained tools do not recreate this workflow.

## Remaining owners

- `agents/agents_config.json` and `agents/task_catalog.yaml` remain the role and
  task configuration sources. Native `codex_agent_role_eval` and runtime
  alignment read them directly; the Python `team_config.py` facade is retired.
- `active_design_packet.rs` validates the persisted design-packet schema.
  Mathematical correction routing remains in `task_catalog.yaml` and the
  computational-optimization skill. The unused Python run-bundle packet
  materializer is retired; this does not add a new run-bundle workflow.
- `issue_sync.rs` builds the existing bootstrap commands for resident receipt
  staging. Native collaboration and close-agent behavior remain with the
  existing host and Rust owners.
- Hook event publication and Eval accumulation retain their existing runtime
  and archive owners. Historical report readers may read existing artifacts;
  they do not require new task files or create active-run pointers.

Retained AgentCanon tool implementations move to their existing Rust owners.
Shell invokes the native CLI. Remove replaced implementations and exclusive
support code together with their obsolete callers.
