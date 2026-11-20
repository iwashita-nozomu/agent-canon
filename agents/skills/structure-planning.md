# structure-planning
<!--
@dependency-start
contract skill
responsibility Establishes necessary content structure before prose and resolves unsettled document/artifact topology.
upstream design ../../documents/design/responsibility-rationale.md structure and visualization activation rationale
upstream design ../../documents/rule/README.md document rule canon
upstream design ../../documents/conventions/common/05_docs.md document responsibility and reading-activation boundary
upstream design ../../documents/design/README.md design canon reader route
upstream design code-visualization.md sole public visualization owner and typed projection contract
downstream implementation ../../.codex/personal/skills/structure-planning/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/dependency_headers.rs validates this adapter dependency header
@dependency-end
-->

## Purpose

新規文書や構成に影響する改稿で、読者が必要な情報と根拠を追える構成を決めます。

## Before prose

既存の見出しや構成メモを使います。不足する場合は本文の前に、節の役割、順序、
支える根拠を決めます。執筆中に足りない点が判明したら、該当する構成を更新します。

## Minimal structure decision

文書の分割や統合は、責務と読む契機で判断します。図が必要な関係は
[code-visualization](code-visualization.md) に委ねます。構成や根拠に関する未決事項は
影響する判断だけを扱い、範囲や主要方針の変更は
[Decision Order](agent-orchestration.md#decision-order) に従います。
