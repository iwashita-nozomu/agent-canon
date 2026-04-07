# Branch Notes

`notes/branches/` は、branch ごとの要約と関連 note への入口をまとめるディレクトリです。
このカテゴリは例外運用用です。通常運用では branch 名そのものではなく `main` 上の code、document、note を見ます。

## 役割

- その branch が何のために存在したかを短く残す
- どこまで `main` に取り込まれたかを示す
- 先に読むべき note、result、report への入口をまとめる

## Format

- 1 branch 1 file を基本にします
- タイトルは branch 名そのものではなく topic-first で付けます
- branch 名、役割、現在の状態、読むべき note、主要な知見を最初に書きます
- active な branch は、対応する worktree action log と carry-over 先をここから辿れるようにします

## Retention Labels

- `persistent`
  - 継続的な入口または raw 結果の保管先として残します
- `keep-while-active`
  - 対応する worktree や実験が動いている間だけ残します
- `delete-ok`
  - 知見の吸収が終わっており、削除してよい branch です

## Workflow

1. branch を切ったら、必要に応じて同時にこのディレクトリへ branch summary を作ります。
1. `WORKTREE_SCOPE.md` で指定した action log と carry-over target を、この summary から辿れるようにします。
1. branch を閉じる前に、関連 note と final JSON のリンクを更新します。
