# main 統合ワークフロー
<!--
@dependency-start
contract workflow
responsibility Documents main 統合ワークフロー for this repository.
upstream design README.md workflow catalog
@dependency-end
-->


この文書は、`main` へ戻すときの統合手順の正本です。
特に branch 側で file 構成を変えたときに、その変更を落とさず `main` へ持ち帰ることを目的にします。

## この文書の読み方

この workflow は、構成変更を含む branch を `main` へ戻すときの統合判断を
扱います。まず `対象` と `原則` でこの手順が必要な変更か確認し、
`推奨手順` を integration branch の操作順として読みます。`禁止事項` と
`判定基準` は file 構成、submodule pin、validation evidence を落としていないかの
確認に使い、`Convention Compliance Gate` は closeout 前の機械確認です。

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
- `main` への統合は、別 `git worktree` を作らず、current checkout 上の integration branch で一度閉じます。
- `vendor/agent-canon` が submodule の場合、parent tree で比較するのは gitlink SHA です。submodule 内の conflict / local commit は、parent 側で file 単位に拾い直さず、`bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty` と `agents/workflows/derived-agent-canon-diff-workflow.md` で先に分類します。

## 推奨手順

1. source branch を閉じる
   - branch 側で必要な review と check を完了します。
   - `make ci-quick` 以上を通します。
   - branch の action log と branch note を更新します。
1. current checkout 上で integration branch を切る
   - `origin/main` から短期の integration branch を作ります。
   - 例:

```bash
git switch -c integrate/<topic>-YYYYMMDD origin/main
```

1. integration branch で source branch を merge する
   - `main` 直系の integration branch 上で、source branch を Git の merge として取り込みます。
   - 構成変更がある場合は `--no-ff` を既定にします。

```bash
git merge --no-ff work/<topic>-YYYYMMDD
```

1. 構成変更が落ちていないかを確認する
   - source branch と integration commit の tree shape を比較します。
   - submodule pin が変わる branch では、source branch の gitlink SHA と integration commit の gitlink SHA が意図通り一致しているかを確認します。

```bash
python3 tools/ci/check_merge_structure.py \
  --source work/<topic>-YYYYMMDD \
  --target origin/main \
  --compare-commit HEAD

git submodule status vendor/agent-canon
```

1. 統合後の validation を走らせる

```bash
make ci-quick
tools/bin/agent-canon docs check
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
- submodule gitlink の変更を、parent repo の `git diff -- vendor/agent-canon` だけで安全判断してはいけません。submodule 内の `git status`、HEAD、remote main、proposal 要否を確認します。

## 判定基準

次がそろっていれば、構成変更の統合として合格です。

- source branch で structural path として変わった path が integration commit でも同じ state にある
- submodule pin が変わる場合、source branch、integration commit、AgentCanon GitHub main の SHA 関係が evidence にある
- `python3 tools/ci/check_merge_structure.py ...` が pass
- `make ci-quick` が pass
- 必要な note、doc、test が `main` から辿れる

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
