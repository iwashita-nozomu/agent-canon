# Notes Hub

`notes/` は、正本ではないが長く残したい知見、比較、要約、補助メモを置く場所です。
規約や設計の一次情報は `documents/` に残し、ここではそれに昇格させる前の知見や、run をまたいで残したい判断を扱います。

## カテゴリ

- [`experiments/`](./experiments/README.md)
  - 個別実験をまたぐ要約、比較、carry-over
- [`themes/`](./themes/README.md)
  - 複数実験や調査から得た話題別の知見
- [`knowledge/`](./knowledge/README.md)
  - 実務で繰り返し参照する横断的な短い知識メモ
- [`branches/`](./branches/README.md)
  - branch 例外運用時の要約と入口
- [`worktrees/`](./worktrees/README.md)
  - 削除対象 worktree から吸い上げた要約と action log
- [`guardrails/`](./guardrails/README.md)
  - 繰り返し踏みやすい avoid pattern と実務 guardrail
- [`failures/`](./failures/README.md)
  - 再発させたくない failure の短い記録

`branches/` と `worktrees/` は常用カテゴリではありません。`documents/worktree-lifecycle.md` に従って branch / worktree を例外運用した場合だけ使います。

## 置くもの

- `documents/` に昇格させるほどではないが残したい判断
- 複数 run をまたいだ比較
- 調査メモ、文献整理、設計上の注意点
- `main` に持ち帰る最小限の実験要約
- 例外的な branch / worktree 運用で失いたくない判断
- host 固有の Git mirror 手順

## 置かないもの

- 正本ルールそのもの
- 巨大な生成物や raw ログ
- branch / worktree の存在だけに依存する本文
- 本文を持たないリンク集だけのメモ

## Main Carry-Over Rule

- `main` に残したい要約、観測、判断のうち、規約、レビュー、実コードに属さないものは `notes/` に置きます。
- worktree を削除する前に、残すべき `notes/` は `main` に commit 済み、または `main` に merge 済みでなければなりません。
- `results/*` branch に raw 結果を残す場合でも、`main` から辿る要約 note は `notes/` 側へ持ち帰ります。
- `main` に持ち帰る実験結果は、完走した fresh run の最小 final JSON と要約 note に限ります。
- partial run は診断材料として扱い、`notes/` の canonical result にはしません。

## Growth Rule

- 実行中の局所ログは `notes/worktrees/` に残します。
- closeout 時に、再利用知識は `notes/knowledge/`、topic synthesis は `notes/themes/`、再発防止は `notes/failures/` へ昇格させます。
- どこへ昇格させるか迷うときは `documents/notes-lifecycle.md` を見ます。
- `notes/` は「書き捨て」ではなく、closeout ごとに再編して太らせる前提です。

## Action Log Rule

- branch / worktree を例外運用する場合は、意味のある操作を 1 か所の append-only な note に逐次残します。
- 既定の action log 置き場は `notes/worktrees/worktree_<topic>_YYYY-MM-DD.md` です。
- scope 更新、編集開始、テスト実行、実験開始 / 停止、carry-over 判断のような節目は必ず追記します。
- worktree 内で下書きするときも、最終的に `main` に置くのと同じ相対パスへ書きます。

## 書き方

- Markdown で書きます。
- タイトルは日付より topic を主にします。
- 文献由来の内容は出典を明示します。
- 自分の仮説や解釈は `Idea:`、`Interpretation:`、`Consideration:` で分けます。
- 重要情報をリンク先に逃がしすぎません。
- 一度 `main` に置いた過去の note 本文はむやみに書き換えません。補足が必要なら追記で対応します。
- host 固有の Git mirror や bare repo hook は `notes/github-mirror-procedure.md` に残します。
- 新しい note は category ごとの template から始めて構いません。
