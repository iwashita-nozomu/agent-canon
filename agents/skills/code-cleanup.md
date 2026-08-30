# code-cleanup
<!--
@dependency-start
contract skill
responsibility Routes public/module code cleanup by responsibility and reachability through dependency analysis, refactor loop, and change review.
upstream design ./README.md shared public skill canon
upstream design ../../documents/design/responsibility-cleanup.md responsibility-unit cleanup contract
upstream design ./dependency-analysis.md dependency and reachability owner
upstream design ./refactor-loop.md behavior-preserving refactor owner
upstream design ./change-review.md findings-first review owner
upstream design ./responsibility-cleanup.md responsibility-unit dispatch owner
downstream implementation ../../.codex/personal/skills/code-cleanup/SKILL.md runtime discovery shim
downstream implementation ./catalog.yaml public skill registry
downstream implementation ./skill-dependencies.yaml public skill dependency DAG
downstream implementation ../../.codex/config.toml host skill configuration
@dependency-end
-->

## Purpose

public/module responsibility と到達性を一つの cleanup unit として閉じ、既存の
`dependency-analysis -> refactor-loop -> change-review` route に渡します。unit schema、
analyzer の candidate 扱い、validation/rollback は [`responsibility-cleanup`](../../documents/design/responsibility-cleanup.md)
の RC-02、RC-04、RC-07、RC-08 を参照します。

## Use When

- public API、module responsibility、consumer reachability、dependency closure を整理する
- analyzer finding を候補として調査し、実装 owner と refactor boundary を確定する
- behavior-preserving refactor の後に findings-first review を行う

## Route

1. `dependency-analysis` で public/module responsibility、到達性、consumer、impact を閉じる。
2. approved mechanism を `refactor-loop` へ渡し、同じ契約の behavior-preserving change として実装する。
3. `change-review` で current snapshot、reachable path、contract、witness を readback する。

## Tool Commands

```bash
python3 tools/validation/semantic/dependencies/check_dependency_headers.py --changed
bash tools/analysis/dependencies/scan_code_dependencies.sh --changed
bash tools/analysis/dependencies/run_repo_dependency_review.sh
```

## Boundary

削除、rename、移動の oracle は analyzer ではなく public/module contract、到達性、validation、
rollback の owner evidence です。`dependency-analysis`、`refactor-loop`、`change-review` の
policy をこの skill に複製しません。
