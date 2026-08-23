# start-repository
<!--
@dependency-start
contract skill
responsibility Starts a template-derived repository through the default source-free static-seed bootstrap.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/contracts/template-bootstrap.md default bootstrap contract
upstream design ../../documents/contracts/static-seed-export.md static seed ownership and provenance
@dependency-end
-->

## Purpose

`git clone <template>` 直後に、新しい repository として使い始めるための初期化手順を固定します。
project slug、display name、destination remote の登録を同じ入口で扱います。default path は
static seed を通常 file として所有し、AgentCanon source や runtime lifecycle を必要としません。

## Use When

- template clone を新 repository として初期化する
- project slug、display name、destination remote を設定する
- clone 済みの static seed を保持したまま local/offline bootstrap を行う
- 初期化後の tree が外部 AgentCanon source なしで検証できることを確認する

## Core References

- `documents/contracts/template-bootstrap.md`
- `documents/contracts/template-github-remote.md`
- `documents/contracts/static-seed-export.md`
- `scripts/README.md`
- `scripts/start_repository.sh`
- `scripts/init_from_template.sh`

## Default Sequence

1. `git status --short --branch` で clone 直後の状態を確認します。
1. repository identity と project config を初期化します。

```bash
bash scripts/start_repository.sh \
  --project-slug your-project \
  --display-name "Your Project"
```

1. 初期化変更を commit したあとに project-owned validation を実行します。

```bash
bash scripts/start_repository.sh --validate-only
```

## Safety Rules

- bootstrap は既に tracked されている static seed を再取得・再生成しません。
- AgentCanon checkout、runtime projection、latest 判定、update state、checkout secret を追加しません。
- network access は destination repository の作成・push を明示的に行う場合だけです。
- live AgentCanon integration は default bootstrap へ混ぜず、独立した opt-in architecture change として扱います。
- template 固有の clone bootstrap は `scripts/` に置き、shared automation の `tools/` へ移しません。
