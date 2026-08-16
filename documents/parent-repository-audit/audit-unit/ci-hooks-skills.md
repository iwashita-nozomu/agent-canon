# CI Hooks And Skills Audit Unit
<!--
@dependency-start
contract design
responsibility Audits CI, hooks, public skills, catalog routing, adapters, and runtime execution surfaces.
upstream design ../README.md owns unit closure and semantic routing boundary
upstream design ../../design/parent-repository-audit.md owns capability and dependency edge design
upstream implementation ../../../agents/skills/agent-orchestration.md owns orchestrator and delegation contract
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py and ../../../tools/agent_tools/skill_dependency_map.py own projections
@dependency-end
-->

## Reader Map

CI、hook、canonical skill、catalog、adapter shim、capability、dependency map、runtime generated
graph の順に読みます。keyword trigger は候補説明に留め、capability、owner、dependency
map、resolver の結果を routing authority とします。

## Owner Responsibility

`agent-orchestration` が親を orchestrator とする workflow/delegation を所有し、public skill
の catalog、adapter、dependency graph、materializer はそれぞれ owner tooling が所有します。

## Invariant

CI/hook/skill/template は canonical owner から一意に辿れ、public audit capability が
semantic route と typed tool command を持つ。shim は薄い adapter で、catalog/source skill
の投影以外の policy を持たない。writer は repair→readback→close を実行し、finding report
だけで停止しない。

## Evidence Sources

- `agents/skills/catalog.yaml`
- `agents/skills/skill-dependencies.yaml`
- `.agents/skills/*/SKILL.md`
- `tools/agent_tools/skill_shim_materializer.py`
- `tools/agent_tools/skill_dependency_map.py`
- `.github/`、hooks、`check_agent_runtime_alignment.py`

## Repair Route

owner skill は `agent-orchestration` と対象 capability owner。catalog/dependency/source skill
を先に修正し、既存 `skill_shim_materializer.py` を一回実行して readback します。graph と
tool command は owner tooling で更新し、新しい checker や keyword-only shim を追加しません。

## Validation

catalog parse、capability route、skill-tool command readback、dependency-map check、shim
materializer second readback、CI/hook の static syntax を対象にします。runtime execution は
static invariant が確定できない hook/CI item だけです。

## Close Condition

canonical skill、catalog、dependency row、typed resolver/tool command、generated shim、graph
が同じ capability を指し、対象 readback が no-change/pass になる。契約変更時は関連 unit
だけが同じ PR で更新される。

## Related Change Surfaces

`surface:ci.hooks-skills`、`surface:skill.catalog`、`surface:skill.dependencies`、
`surface:skill.runtime-shim`、`surface:skill.graph`。これらの契約変更時だけ本 unit を更新します。

## Legacy Migration IDs

PRA-C040 PRA-C041 PRA-C042 PRA-C047 PRA-C048 PRA-C049 PRA-C055 PRA-C092 PRA-C093 PRA-C094 PRA-C095 PRA-C096 PRA-X026 PRA-X028 PRA-X029 PRA-X030 PRA-X031 PRA-X035 PRA-X049
