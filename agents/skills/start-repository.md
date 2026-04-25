# start-repository
<!--
@dependency-start
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

`git clone <template>` 直後に、新しい repo として使い始めるための初期化手順を固定します。
project slug、display name、project bare repo、project-local `agent-canon` bare repo の登録を同じ入口で扱います。

## Use When

- template clone を新 repo として初期化する
- `/mnt/git/<project>.git` のような新しい bare repo に向ける
- clone 直後の `agent-canon` subtree snapshot と project-local `agent-canon` bare repo の関係を揃えたい
- `make agent-canon-ensure-latest` が別 repo 向け remote で安全判定に止まるのを bootstrap 時点で避けたい

## Core References

- `documents/template-bootstrap.md`
- `scripts/README.md`
- `scripts/start_repository.sh`
- `scripts/init_from_template.sh`
- `documents/agent-canon-subtree-migration.md`
- `tools/sync_agent_canon.sh`

## Default Sequence

1. `git status --short --branch` で clone 直後の状態を確認します。
1. 必要なら dry run します。

```bash
bash scripts/start_repository.sh \
  --project-slug your-project \
  --display-name "Your Project" \
  --dry-run
```

1. 初期化します。wrapper は clean clone なら実 init の前に `make agent-canon-ensure-latest` を実行し、そのあと `/mnt/git/<project-slug>-agent-canon.git` を作成して `vendor/agent-canon/` snapshot を `main` として seed します。dirty state なら preflight の未実行理由を出して init を続行します。

```bash
bash scripts/start_repository.sh \
  --project-slug your-project \
  --display-name "Your Project"
```

1. project-local agent-canon bare repo 名を固定したい場合は明示します。

```bash
bash scripts/start_repository.sh \
  --project-slug your-project \
  --display-name "Your Project" \
  --agent-canon-bare-repo your-project-agent-canon.git
```

1. shared `agent-canon` remote を使い続ける場合だけ opt out します。

```bash
bash scripts/start_repository.sh \
  --project-slug your-project \
  --display-name "Your Project" \
  --skip-agent-canon-bare-repo
```

1. 初期化変更を commit したあとに確認します。

```bash
bash scripts/start_repository.sh --validate-only
```

## Safety Rules

- `--dry-run` では bare repo を作成しません。
- 既存の `agent-canon` bare repo に `refs/heads/main` がある場合、その history は上書きしません。
- `/mnt/git` が存在しない環境では bare repo seed を skip し、通常の file rewrite だけ行います。
- template 固有の clone bootstrap は `scripts/` に置き、shared automation の `tools/` へ移しません。
