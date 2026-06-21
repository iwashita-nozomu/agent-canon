# start-repository
<!--
@dependency-start
contract skill
responsibility Documents start-repository for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

`git clone <template>` 直後に、新しい repo として使い始めるための初期化手順を固定します。
project slug、display name、project remote の登録を同じ入口で扱います。
AgentCanon の source of truth は GitHub remote です。

## Use When

- template clone を新 repo として初期化する
- GitHub-backed project remote に向ける
- clone 直後の `vendor/agent-canon` submodule pin と GitHub AgentCanon main の関係を揃えたい
- `make agent-canon-ensure-latest` が別 repo 向け remote で安全判定に止まるのを bootstrap 時点で避けたい

## Core References

- `documents/template-bootstrap.md`
- `scripts/README.md`
- `scripts/start_repository.sh`
- `scripts/init_from_template.sh`
- AgentCanon document `documents/runtime-profiles-and-check-matrix.md`; from a template or derived repo root, resolve it as `vendor/agent-canon/documents/runtime-profiles-and-check-matrix.md`
- AgentCanon document `documents/agent-canon-github-remote.md`; from a template or derived repo root, resolve it as `vendor/agent-canon/documents/agent-canon-github-remote.md`
- `tools/sync_agent_canon.sh`

## Default Sequence

1. `git status --short --branch` で clone 直後の状態を確認します。
1. 初期化します。wrapper は AgentCanon update surface が repairable なら実 init の前に `make agent-canon-ensure-latest` を実行します。unsafe な update surface があれば preflight の route を出して init を続行します。

```bash
bash scripts/start_repository.sh \
  --project-slug your-project \
  --display-name "Your Project"
```

1. 初期化変更を commit したあとに確認します。

```bash
bash scripts/start_repository.sh --validate-only
```

## Safety Rules

- template 固有の clone bootstrap は `scripts/` に置き、shared automation の `tools/` へ移しません。
