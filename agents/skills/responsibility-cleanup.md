# responsibility-cleanup
<!--
@dependency-start
contract skill
responsibility Routes responsibility-unit cleanup from structure observation through owner dispatch, integration, and re-review.
upstream design ./README.md shared public skill canon and source maintenance
upstream design ../../documents/design/responsibility-cleanup.md responsibility-unit cleanup contract
upstream design ./structure-refactor.md structure-first ownership repair
upstream design ./refactor-loop.md behavior-preserving refactor route
upstream design ./agent-orchestration.md dispatch and review routing owner
upstream design ./task-routing.md compact route selection owner
downstream implementation ../../.codex/personal/skills/responsibility-cleanup/SKILL.md runtime discovery shim
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

1. `tree -a -J --noreport` と既存 structure/scope checker で観測を作る。repo-wide な棚卸しを依頼された場合の観点は [project-review](../internal-routines/project-review.md) を参照する。局所 cleanup を全体監査へ拡張しない。
2. 近接性や analyzer finding ではなく owner、dependency、公開契約、validation、rollback で unit を閉じる。write-capable handoff の validation command 境界は `agent-orchestration.md#Write-Capable Handoff Validation Trust Boundary` を参照する。
3. environment は `environment-cleanup`、code は `code-cleanup` に渡す。skill の一般的な作成・改訂はホスト提供の `$skill-creator` に直接渡し、AgentCanon の登録・配布を変更する場合は操作前に [Updating Skills](README.md#updating-skills) を読む。必要な保守・検証を終えたら、この unit の統合へ戻る。
4. 文書、worktree、log は既存の `document-canon-cleanup`、`worktree-health`、`agent-log-analysis`、`runtime-log-repair`、`result-artifact-writeout` を再利用する。
5. `agent-orchestration` と `task-routing` の order を保ち、統合後に `change-review` と owner readback を行う。

## Tool Commands

```bash
tree -a -J --noreport
python3 tools/validation/semantic/structure/repo_structure_contract.py --root . --contract documents/structure/repo-structure-contract.toml
python3 tools/validation/semantic/responsibility/responsibility_scope.py --root .
python3 tools/agent/skills/skill_dependency_map.py check --root .
```

## Boundary

詳細な unit schema、外部 tool evidence、analyzer の扱い、validation、rollback は設計正本を読みます。
この skill は個別 owner の policy や削除 oracle を複製しません。
