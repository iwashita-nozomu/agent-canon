---
name: gpu-execution
description: "Use when planning, running, validating, or diagnosing GPU/CUDA/JAX/XLA/IREE backend execution, GPU validation blockers, nvidia-smi evidence, CUDA_VISIBLE_DEVICES handling, ExperimentRunner-based Python runs, or JAX/XLA preallocation-disabled execution."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:gpu-execution -->
<!-- canonical: agents/skills/gpu-execution.md sha256=11baaaa3c5011c6b9b9c23d75a4eb5891783d65a22ad05ef5fa87323d91474d9 -->
<!-- route: agents/skills/catalog.yaml#skill:gpu-execution.routing digest=33bafddb4378acdb9dcff135ab024c394854ce3398acf0990060e939be3f9502 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:gpu-execution digest=bd0ae3050ce484b65e9e4216a2da77b22f0387f8ba34965204c4f861d1fd3030 -->
<!-- commands: agents/skills/catalog.yaml#skill:gpu-execution.tool_commands digest=4b2997c146af1e9c3443993fc2336543520c485e9e5c6d14e9484f7c81c3da02 -->
<!-- host-config: path=../.agents/skills/gpu-execution/SKILL.md index=25 order=25 enabled=true digest=c7c302e2510e768540aa94229f89d92b4bb7b430b03fc5062750c4705d77a514 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=6aa1b1e14487b2f894118225e6564db6b7585cf5dbb14538d8cd49a1587ced76 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes gpu-execution for runtime discovery.
upstream design ../../../agents/skills/gpu-execution.md owner
@dependency-end
-->

# gpu-execution

## Canonical Skill

Canonical workflow and policy: [gpu-execution](../../../agents/skills/gpu-execution.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill gpu-execution --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
