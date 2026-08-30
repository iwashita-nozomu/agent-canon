<!--
@dependency-start
contract template
responsibility Provides reusable reader-map and lifecycle fields for run artifacts.
upstream design ../README.md partial expansion and generated artifact boundary.
downstream implementation ../../../tools/agent/orchestration/agent_team.py expands this partial.
@dependency-end
-->

## Reader Map（読者 map）

この artifact は、指定された責務の判断と完了証跡を一つの読者経路で確認するための
run-local template です。本文を書く前に、次の欄を埋めて reader path と証拠の境界を
固定します。

- purpose:
- intended reader and decision:
- what this artifact contains:
- canonical source / generated projection / run-local artifact:
- owner and responsibility boundary:
- required readback and targeted validation:
- formatter command: `tools/bin/agent-canon docs format <paths...>`
- checker command: `tools/bin/agent-canon docs check <paths...>`
- post-format source readback:
- rendered/projection readback identity:
- lifecycle retention and cleanup owner:
