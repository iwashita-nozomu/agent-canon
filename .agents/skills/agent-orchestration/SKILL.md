---
name: agent-orchestration
description: Mandatory routing skill for repository tasks. Use before selecting workflow family, skills, review roles, subagents, model/team policy, runtime entrypoints, or run bundles for Codex routing.
---
<!--
@dependency-start
contract skill
responsibility Routes the runtime skill entry to the canonical Agent Orchestration policy without copying that policy.
upstream design ../../../agents/skills/agent-orchestration.md owns orchestration and Decision Sufficiency policy.
upstream design ../../../agents/canonical/skills.md owns the public skill registry.
upstream design ../../../agents/skills/skill-dependencies.yaml owns typed skill prerequisites and invocation order.
upstream implementation ../../../tools/agent_tools/agent_team.py materializes machine ToolCall route packets.
upstream implementation ../../../tools/agent_tools/route.py derives the selected skill order from the dependency map.
@dependency-end
-->

# Agent Orchestration

## Reader Map

- Canonical policy: `agents/skills/agent-orchestration.md`.
- Execution-Time-Aware Work-Conservation Contract:
  `agents/skills/agent-orchestration.md#Execution-Time-Aware Work-Conservation Contract`.
- Parallel Fresh-Clone Workstreams:
  `agents/skills/agent-orchestration.md#Parallel-Fresh-Clone-Workstreams`.
- Executable scheduling fields: `dependency_dag`, `makespan_objective`,
  `responsibility_completeness`, `correctness`, `critical_path`, `ready_set`,
  `context_reuse`, `affected_evidence_invalidation`.
- Decision Sufficiency owner:
  `agents/skills/agent-orchestration.md#Decision Sufficiency Packet`.
- Runtime packet producer: `tools/agent_tools/agent_team.py`.
- Skill dependency source: `agents/skills/skill-dependencies.yaml`.
- Boundary: this file is a discovery shim and does not restate routing, DSV,
  ToolCall, subagent, or validation rules. The semantic sufficiency record is
  owner, replaceable unit, implementation mechanism, validation route, and any
  unresolved branch that can change them; durable packet transport is conditional.

## Tool Commands

<!-- skill-tool-commands:start -->
この skill の workflow を適用する前に、次の command packet を使用してください。

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill agent-orchestration --format text
```

論理コマンドは、実行前に AgentCanon source root を基準として解決します。各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、fallback-only skill を含む script entry の script path は絶対 path にします。

packet が出力した必須 command と、task に該当する conditional command を実行してください。
<!-- skill-tool-commands:end -->

1. Read `agents/skills/agent-orchestration.md` as the sole policy owner.
1. Consume the owner-produced semantic decision-sufficiency record referenced by
   the active route packet. A structured handoff or tool result is sufficient;
   use a durable packet reference only for coordination or resumption.
1. Execute the route packet's machine-readable ToolCall tokens and return their
   typed failure semantics without translating them into prose commands.
