# main 統合ワークフロー
<!--
@dependency-start
@dependency-end
-->


この文書は、`main` へ戻すときの統合手順の正本です。
特に branch 側で file 構成を変えたときに、その変更を落とさず `main` へ持ち帰ることを目的にします。

## 対象

- file の追加
- file の削除
- rename / move
- symlink 化や file type 変更
- ディレクトリ再編

## 原則

- file 構成変更を含む branch は、`main` へ直接手作業で拾い直しません。
- `git checkout <file>`、手動 copy、partial cherry-pick で構成変更を戻しません。
- 構成変更を含む統合では、source branch の tree shape をそのまま持ち帰ることを優先します。
- `main` への統合は、専用 integration worktree で一度閉じます。

## 推奨手順

1. source branch を閉じる
   - branch 側で必要な review と check を完了します。
   - `make ci-quick` 以上を通します。
   - branch の action log と branch note を更新します。
1. integration worktree を切る
   - `origin/main` から短期の integration branch を作ります。
   - 例:

```bash
bash tools/worktree_start.sh integrate/<topic>-YYYYMMDD .worktrees/integrate-<topic>
```

1. integration worktree で source branch を merge する
   - `main` 直系の integration branch 上で、source branch を Git の merge として取り込みます。
   - 構成変更がある場合は `--no-ff` を既定にします。

```bash
git merge --no-ff work/<topic>-YYYYMMDD
```

1. 構成変更が落ちていないかを確認する
   - source branch と integration commit の tree shape を比較します。

```bash
python3 tools/ci/check_merge_structure.py \
  --source work/<topic>-YYYYMMDD \
  --target origin/main \
  --compare-commit HEAD
```

1. 統合後の validation を走らせる

```bash
make ci-quick
make docs-check
```

1. `main` へ持ち帰る
   - root 側の `main` を最新化します。
   - integration branch が妥当なら、`main` はその統合 commit へ fast-forward で進めます。

```bash
git checkout main
git pull --ff-only origin main
git merge --ff-only integrate/<topic>-YYYYMMDD
```

## 禁止事項

- 構成変更がある branch を、`main` 側で file 単位に拾い直して close してはいけません。
- rename / delete を含む差分で `squash` だけを使い、tree check なしで close してはいけません。
- branch 側で消した path が `main` 側に残ったまま完了扱いにしてはいけません。
- symlink 化や file type 変更を、content 差分だけ見て close してはいけません。

## 判定基準

次がそろっていれば、構成変更の統合として合格です。

- source branch で structural path として変わった path が integration commit でも同じ state にある
- `python3 tools/ci/check_merge_structure.py ...` が pass
- `make ci-quick` が pass
- 必要な note、doc、test が `main` から辿れる
