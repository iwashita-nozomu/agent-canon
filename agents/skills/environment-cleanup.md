# environment-cleanup
<!--
@dependency-start
contract skill
responsibility Routes environment dependency and runtime-capability cleanup through dependency design and environment maintenance.
upstream design ./README.md shared public skill canon
upstream design ../../documents/design/responsibility-cleanup.md responsibility-unit cleanup contract
upstream design ./dependency-design.md dependency design owner
upstream design ./environment-maintenance.md environment maintenance owner
upstream design ./responsibility-cleanup.md responsibility-unit dispatch owner
downstream implementation ../../.agents/skills/environment-cleanup/SKILL.md runtime discovery shim
downstream implementation ./catalog.yaml public skill registry
downstream implementation ./skill-dependencies.yaml public skill dependency DAG
downstream implementation ../../.codex/config.toml host skill configuration
@dependency-end
-->

## Purpose

environment dependency と runtime capability の責務単位を閉じ、既存の
`dependency-design -> environment-maintenance` route へ渡します。共通の unit schema と
evidence/rollback は [`responsibility-cleanup`](../../documents/design/responsibility-cleanup.md)
の RC-03、RC-07、RC-08 を参照します。

## Use When

- Docker、CI、devcontainer、dependency manifest、runtime compatibility を整理する
- environment capability の dependency closure と install owner を確定する
- external tool/library の version、scope、false positive、license/security、rollback を記録する

## Route

1. `dependency-design` で declarative dependency と capability boundary を確定する。
2. approved packet を `environment-maintenance` へ渡す。
3. 変更面の既存 environment validation と rollback readback を実行する。

## Tool Commands

```bash
python3 tools/agent_tools/devcontainer_dependencies.py validate --workspace . --format text
python3 tools/agent_tools/devcontainer_dependencies.py dry-run --workspace . --vendor-root . --format json
```

## Boundary

environment implementation policy は `dependency-design` と `environment-maintenance` が所有します。
この skill は cleanup unit の dispatch と readback を接続し、別の dependency schema を定義しません。
