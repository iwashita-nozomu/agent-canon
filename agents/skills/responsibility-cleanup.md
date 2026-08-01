# responsibility-cleanup
<!--
@dependency-start
contract skill
responsibility Routes responsibility-unit cleanup from structure observation through owner dispatch, integration, and re-review.
upstream design ./README.md shared public skill canon
upstream design ../../documents/design/responsibility-cleanup.md responsibility-unit cleanup contract
upstream design ./structure-refactor.md structure-first ownership repair
upstream design ./refactor-loop.md behavior-preserving refactor route
upstream design ./agent-orchestration.md dispatch and review routing owner
upstream design ./task-routing.md compact route selection owner
downstream implementation ../../.agents/skills/responsibility-cleanup/SKILL.md runtime discovery shim
downstream implementation ./catalog.yaml public skill registry
downstream implementation ./skill-dependencies.yaml public skill dependency DAG
downstream implementation ../../.codex/config.toml host skill configuration
@dependency-end
-->

## Purpose

責務単位 cleanup の入口です。`tree -a -J --noreport` を構造観測として使い、source/view/
generated/project/personal の境界、dependency closure、replaceable responsibility、
specialist dispatch、統合、再レビューを [`responsibility-cleanup`](../../documents/design/responsibility-cleanup.md)
の RC-01..RC-08 に接続します。

## Use When

- repository の責務単位を整理する
- structure、ownership、dependency closure、root/view/generated 境界を同時に判断する
- environment/code/skill の specialist dispatch と統合後の再レビューを束ねる

## Route

1. `tree -a -J --noreport` と既存 structure/scope checker で観測を作る。
2. 近接性や analyzer finding ではなく owner、dependency、公開契約、validation、rollback で unit を閉じる。
3. environment は `environment-cleanup`、code は `code-cleanup`、skill は `skill-cleanup` に渡す。
4. 文書、worktree、log は既存の `document-canon-cleanup`、`worktree-health`、`agent-log-analysis`、`runtime-log-repair`、`result-artifact-writeout` を再利用する。
5. `agent-orchestration` と `task-routing` の order を保ち、統合後に `change-review` と owner readback を行う。

## Tool Commands

```bash
tree -a -J --noreport
python3 tools/agent_tools/repo_structure_contract.py --root . --contract documents/structure/repo-structure-contract.toml
python3 tools/agent_tools/responsibility_scope.py --root .
python3 tools/agent_tools/skill_dependency_map.py check --root .
```

## Boundary

詳細な unit schema、外部 tool evidence、analyzer の扱い、validation、rollback は設計正本を読みます。
この skill は個別 owner の policy や削除 oracle を複製しません。
