<!--
@dependency-start
contract template
responsibility Provides reusable review evidence, oracle, failure, and conflict fields.
upstream design ../README.md partial expansion and generated artifact boundary.
upstream design ../../../agents/skills/change-review.md conditional security-audit evidence and coverage.
downstream implementation ../../../tools/agent/orchestration/agent_team.py expands this partial.
@dependency-end
-->

## Review Contract（レビュー契約）

レビューは現在の source snapshot、到達可能な input/control path、契約、witness または
static proof がそろい、owner・実装・validation・publication の判断が変わる finding だけを
受け付けます。

- owner / responsibility と OOP または type boundary:
- design-to-implementation trace:
- dependency と side-effect map:
- tests より前の algorithm contract:
- necessary-and-sufficient oracle/test boundary:
- failure-cause classification:
- conflict intent と保持した user/design intent:
- independent reviewer と証跡 readback:
- rejected finding の reason code と evidence reference:

明示的なセキュリティ監査では、`change-review` の Explicit security audit 手順に従い、
既存の証跡に防御経路・候補の判定・調査範囲を残します。
