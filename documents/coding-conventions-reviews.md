<!--
@dependency-start
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# レビュー文書の運用規約

この文書は、コードレビュー報告、実装進捗報告、静的解析メモなどのレビュー成果物を対象にします。
レビュー文書を散在させず、Git 管理された補助資料として保つことを目的にします。

## 1. 置き場所

- レビュー文書はリポジトリ root の `./reviews/` に置きます。
- レビュー文書をリポジトリの root に直置きしません。
- `./reviews/README.md` を入口にし、深い階層へ入れません。
- 新規のレビュー文書は `./reviews/` に置きます。`./reviews/` 以外へ置くことを禁止します。

## 2. ファイル名

- 新規のレビュー文書ファイル名には、作成したエージェントまたはツールの識別子を必ず入れます。
- 新規のファイル名は `<TOPIC>__<agent>.md` に固定します。
- 現在有効なレビューであることを前面に出す場合に限り、`CURRENT_<TOPIC>__<agent>.md` を許可します。
- 例:
  - `LINEAROPERATOR_REVIEW__codex.md`
  - `TEST_GAP_ANALYSIS__copilot.md`
  - `STATIC_ANALYSIS_NOTE__claude.md`
  - `CURRENT_REVIEW__codex.md`
  - `CURRENT_TEST_REVIEW__copilot.md`
- 既存の歴史的文書は直ちに改名しません。今後追加する文書はこの規則に従います。

## 3. Git 管理

- レビュー文書は Git 管理します。
- 実装を伴うレビューでは、レビュー文書とコード修正を同じ branch 上で管理できます。
- ただし、レビュー文書だけでなく、対応した実コードの commit も別途残します。
- 過去のレビュー時点そのものは Git 履歴で追うことを前提にし、`reviews/` を履歴保管庫として使いません。

## 4. 文書の種類

- レビュー文書は次のいずれかの状態を先頭で明記します。
  - `Verified`: 現在のリポジトリ状態と整合している確認済み文書
  - `Working Note`: 作業途中のメモや provisional な所見を含む文書
- AI や外部ツールを使って作成した場合は、作成日と生成元を明記します。
- 新しい `Historical Artifact` は作りません。
- 過去時点のレビューを残したい場合でも、通常は別ファイルを増やさず Git 履歴で追います。

## 5. 内容の書き方

- レビュー文書は「何を見たか」「何を見つけたか」「何を修正したか」を分けて書きます。
- 実装済みと未実装を混ぜる場合は、状態を箇条書きで明示します。
- 現在の実装と一致しない可能性がある所見は、断定せず `Working Note` として扱います。
- レビュー文書から実装パスを参照できます。ただし、文書自体が単独でも読めるように保ちます。
- 各レビュー文書には、少なくとも次を明記します。
  - `Reviewed date`
  - `Reviewed main commit`
  - `Reviewed worktrees`
  - `Scope`
- 既存のレビュー文書を置き換える場合は、先頭に少なくとも次を明記します。
  - `Supersedes: ...`
  - `Replaces: ...`
- どのレビューを読むべきかが分かるよう、置き換え関係は本文内にも明示します。
- レビュー結果は、少なくとも次の区分で書きます。
  - `Main Findings`
  - `Worktree Findings`
  - `Conflict Risk` または `Merge Risk`
  - `Recommended Actions`

## 6. レビュー対象の基準

- 通常のレビューは `main` workspace から実施します。
- レビュー文書が表す「現在のコード状態」は、`main` にあるコードを基準にします。
- ただしレビュー時には `./.worktrees/` 配下の active な worktree も確認し、将来の統合や競合のリスクを評価します。
- `main` に未統合の worktree 内容を、現在の実装の事実として書きません。
- worktree 由来の指摘は、`main` の不具合と混ぜず、`Conflict Risk`、`Merge Risk`、`Divergence Risk` などとして区別して書きます。
- 通常レビューでは、`main` だけを見て終わりにしません。active な worktree があるなら、それらもレビュー対象に含めます。

## 7. 粒度

- `main` だけを粗く見て、worktree は軽く眺める、という運用はしません。
- active な各 worktree も、`main` と同じ粒度で確認します。
- 少なくとも次の観点は `main` と worktree の両方で見ます。
  - 同じファイルを並行して触っていないか
  - API の方向がずれていないか
  - merge 時にコンフリクトしそうな変更がないか
  - テストや規約変更が branch 間で食い違っていないか
  - ある worktree の修正が、別の worktree や `main` の前提を壊していないか
  - 同じ不具合が複数 branch に分散していないか

## 8. 更新方針

- `reviews/` には、その時点で有効なレビューだけを残します。
- 再レビューしたら、既存のレビュー文書を更新して最新状態に合わせます。
- 役目を終えたレビュー文書は削除してよく、過去版は Git 履歴で追います。
- review directory 内に過去版を増やしません。
- `main` のコードが変わってレビュー結果が古くなったら、レビュー文書もそれに合わせて更新します。
- 更新時は、古い文章を抱えたまま追記して膨らませません。本文を整理して現在有効な状態だけを残します。
- 複数のレビュー文書を統合する場合は、残す側の文書に `Supersedes` / `Replaces` を書き、統合後に不要な文書は削除します。

## 9. 関連文書

- 実験結果のような生成物は `./reviews/` ではなく `experiments/.../results/` で管理します。
- 実験環境の運用ルールは `coding-conventions-experiments.md` に書きます。
- プロジェクト全体の branch / worktree 運用は `coding-conventions-project.md` に書きます。
