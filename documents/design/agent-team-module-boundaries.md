# Agent coordination boundaries

<!--
@dependency-start
contract design
responsibility Defines the remaining role, packet, and tool-call owners after custom run-bundle retirement.
upstream design ../../agents/COMMUNICATION_PROTOCOL.md native collaboration
upstream design rust-agent-tool-migration.md retained tool migration
downstream implementation ../../tools/agent/orchestration/team_config.py role and task configuration
downstream implementation ../../tools/agent/orchestration/packets.py independently consumed design and mathematical inputs
downstream implementation ../../tools/agent/orchestration/tool_calls.py remaining tool-call adapters
@dependency-end
-->

## Decision

Codex provides agent execution and collaboration. Git and the current conversation
carry the agreed scope, handoff, progress, and completion evidence. The custom
AgentTeam facade, run bootstrap, per-task contract/progress files, stage gates,
and task-close command are retired. Retained tools do not recreate this workflow.

## Remaining owners

- `team_config.py` supplies role and task configuration consumed by routing and
  role evaluation. Role settings remain available independently of a run bundle.
- `packets.py` supplies independently consumed design and mathematical inputs.
  Experiment and proof artifacts retain their own owners and validation.
- `tool_calls.py` supplies adapters still consumed by issue publication. Native
  collaboration uses the host tools directly.
- Hook event publication and Eval accumulation retain their existing runtime
  and archive owners. Historical report readers may read existing bundles;
  they do not require new task files or create active-run pointers.

Retained AgentCanon tool implementations move to their existing Rust owners.
Shell invokes the native CLI. Remove replaced implementations and exclusive
support code together with their obsolete callers.
