# skill-cleanup
<!--
@dependency-start
contract skill
responsibility Routes canonical skill and generated runtime cleanup as one source-to-readback unit.
upstream design ./README.md shared public skill canon
upstream design ../../documents/design/responsibility-cleanup.md responsibility-unit cleanup contract
upstream design ../../documents/design/skill-runtime-shim-materialization.md generated shim materialization owner
upstream design ../../documents/design/skill-tool-invocation-graph.md generated skill/tool graph owner
upstream design ./agent-orchestration.md routing owner
upstream design ./task-routing.md route selection owner
upstream design ./document-canon-cleanup.md document canon reuse owner
upstream design ./worktree-health.md worktree evidence reuse owner
upstream design ./agent-log-analysis.md log analysis reuse owner
upstream design ./runtime-log-repair.md runtime log repair reuse owner
upstream design ./result-artifact-writeout.md result evidence reuse owner
downstream implementation ../../.agents/skills/skill-cleanup/SKILL.md runtime discovery shim
downstream implementation ./catalog.yaml public skill registry
downstream implementation ./skill-dependencies.yaml public skill dependency DAG
downstream implementation ../../.codex/config.toml host skill configuration
downstream implementation ../../tools/agent_tools/skill_shim_materializer.py generated shim materializer
downstream implementation ../../tools/agent_tools/skill_dependency_map.py generated graph materializer
downstream implementation ../../tools/agent_tools/check_skill_tool_invocation_graph.py graph readback checker
@dependency-end
-->

## Purpose

canonical skill doc、catalog、dependency DAG、route、tool command、generated shim、host config、
graph/readback を一つの source-to-generated cleanup unit として既存 owner へ渡します。
共通 unit schema と統合/rollback は [`responsibility-cleanup`](../../documents/design/responsibility-cleanup.md)
の RC-05、RC-06、RC-07、RC-08 を参照します。

## Use When

- public skill を追加、整理、分割、統合、rename、route変更する
- canonical doc と catalog/DAG/route/tool command/generated shim/host config/graph の整合を直す
- generated artifact と readback の stale、欠落、projection mismatch を修復する

## Route

1. canonical skill doc と catalog/dependency/route/tool command の source owner を固定する。
2. `.codex/config.toml` を host-wiring の source/input として読み、catalog skill id に対する
   entry set、source order、path、enabled を readback する。
3. 既存 materializer は `.agents/skills/<skill>/SKILL.md` だけを生成する。
4. `skill_dependency_map.py graph` で graph JSON/Mermaid を生成し、既存 checker で source/readback equality を確認する。
5. 文書は `document-canon-cleanup`、worktree は `worktree-health`、log は `agent-log-analysis`/`runtime-log-repair`、結果は `result-artifact-writeout` を再利用する。

## Tool Commands

```bash
python3 tools/agent_tools/check_agent_runtime_alignment.py
python3 tools/agent_tools/skill_shim_materializer.py materialize --root . --all
python3 tools/agent_tools/skill_shim_materializer.py readback --root . --all
python3 tools/agent_tools/skill_dependency_map.py graph --root . --output documents/runtime/skill-dependency-graph.md
python3 tools/agent_tools/check_skill_tool_invocation_graph.py --root .
```

## Boundary

generated shim と graph は source owner から生成し、手書き projection を authority にしません。
`.codex/config.toml` は materializer の生成 target ではなく、host-wiring の source/input と
set/order readback owner です。
個別の document/worktree/log policy は既存 skill を読み、この skill では新しい代替 skill を作りません。
