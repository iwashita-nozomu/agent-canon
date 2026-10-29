# branch・worktree の legacy cleanup 運用
<!--
@dependency-start
contract workflow
responsibility Documents branch・worktree legacy cleanup for this repository.
upstream design README.md durable document index
upstream design orphan-lifecycle.md defines semantic orphan classification and fail-closed cleanup admission.
upstream design ../rule/repository-topic-clone.md owns current checkout lifecycle and removal.
upstream design BRANCH_SCOPE.md owns branch scope and Git state preservation.
@dependency-end
-->


この文書は、既存の stale worktree、古い `WORKTREE_SCOPE.md`、または過去の branch/action log を片付ける場合に参照します。
新しい checkout の作成・再利用と、利用終了した作業用 checkout の回収は
[repository-topic clone ルール](../rule/repository-topic-clone.md) に従います。
この文書の orphan admission を通常の checkout 回収へ追加しません。

legacy branch / worktree の削除可否は、先に [orphan-lifecycle.md](orphan-lifecycle.md) の canonical
read-only inventory で分類します。経過日数、最終更新日時、stale という呼称だけでは cleanup を認可しません。
この文書は分類後の既存 executor と legacy evidence の扱いを所有し、意味差分判定を再実装しません。

## 使う場面

- 既存の stale worktree を棚卸ししたい
- 古い `WORKTREE_SCOPE.md` や action log が current checkout の作業を汚していないか確認したい
- 過去の branch / worktree note から current checkout へ知見だけを持ち帰りたい

## cleanup 前の確認

- `git fetch --prune origin main` 後の exact `refs/remotes/origin/main` を固定し、
  `python3 tools/repository/git/orphan_lifecycle.py inventory ...` の digest と candidate identity を残します。
  対象 branch の local/remote 状態も確認し、未公開の内容を保持します。
- `orphan_safe_to_remove` 以外、または cleanup blocker が一つでもある candidate は削除しません。
- current checkout で続けられる作業は current checkout の後続 wave に直列化します。
- carry-over 先、runtime output directory、削除または保持する legacy note を先に決めます。
- 削除対象が agent / process / container mount / runtime の入力として使われている間は保持します。
  利用停止と mount 解除の完了、必要な内容の外部保全を既存 owner で確認してから削除します。

## legacy scope の確認

stale な worktree や古い scope を見つけた場合は、作業場所として再開せず、次を確認します。

- `WORKTREE_SCOPE.md` の `Branch` と `Worktree path` が current checkout と違う場合、その scope は作業 authority ではありません。
- [WORKTREE_LOG_TEMPLATE.md](../../documents/notes/worktrees/WORKTREE_LOG_TEMPLATE.md) 由来の action log は
  legacy evidence として読み、current task record へ carry-over 判断だけを残します。
- 選択済み run bundle の継続ログは current checkout の
  `python3 tools/runtime/archive/work_log.py --kind <kind> --request-clause-id R1 --message "<what changed>" --next "<next>"`
  を使います。
- experiment topic を持つ古い worktree を見つけた場合は、`experiments/registry.toml` の stale `active_worktree` / `scope_file` を cleanup 対象として扱います。
- branch が複数 session 続いた場合でも、作業再開は current checkout の branch / wave で行い、`documents/notes/branches/` は summary evidence としてだけ使います。
- 観測した drift / cleanup risk と照合する必要がある場合だけ、関係する
  [guardrails](../notes/guardrails/README.md) / [failures](../notes/failures/README.md) を参照します。
- `python3 tools/repository/workspace/worktree_scope_lint.py --current` で stale scope の placeholder と kickoff 欄を確認します。`bash tools/repository/worktree/worktree_start.sh` は cleanup diagnostic 以外では使いません。
- `git status --short --branch` と `git worktree list --porcelain` を確認し、必要なら `bash tools/validation/documentation/checks/check_worktree_scopes.sh` を実行します。
- dirty state、conflict risk、scope drift の兆候があれば、編集前に current task record に残します。
- `main` へ戻す場合は、integration owner が準備済み checkout 上で統合します。integration
  用 checkout が必要なら `repository-topic-clone` の selected mode を使い、手動の integration
  worktree は切りません。

## ルール

- branch は短期で閉じます。
- 統合先は常に `main` です。
- 長期に残す知見は branch 名ではなく `documents/` または `documents/notes/` に移します。
- 1 回の実験結果を branch 固有の台帳に依存させません。
- `WORKTREE_SCOPE.md` は legacy cleanup / drift diagnosis 用の evidence であり、新しい task の scope authority ではありません。
- 別 branch / 別 path の scope file を流用しません。
- branch の役割と carry-over 先を残したい場合は [BRANCH_SCOPE.md](BRANCH_SCOPE.md) と `documents/notes/branches/` を使います。
- 既存 action log は `documents/notes/worktrees/` に legacy evidence として残します。
- 今回の scope 更新、編集、検証、実験開始 / 停止、carry-over 判断は、対応する request clause と
  ともに既存 current task record へ一度記録します。選択済み run bundle がある場合は
  その `work_log.md` を使い、legacy action log への二重記録はしません。
- scope が途中で変わったら、追加編集の前に current task record と handoff packet を更新します。
- editable path は current checkout の dependency-expanded write scope と handoff packet で管理します。
- runtime output は current checkout の run bundle または task 固有 output directory へ限定します。
- 持ち帰る知見がある場合は [notes lifecycle](notes-lifecycle.md) に従って保存します。
  構成変更の統合と検証は [branch integration](BRANCH_SCOPE.md#5-conflict-解決と-merge--rebase) に従います。
- cleanup 前には digest-bound `authorize-cleanup` receipt、cleanup 後には exact command、result、
  ref/path readback、保存先 main/successor、関連 Issue/PR comment locator を同じ trace に残します。
- local branch に linked worktree がある場合、worktree を独立 resource として先に処理し、再 inventory するまで branch を削除しません。

## 閉じる前の確認

- `main` に戻すコード、文書、知見がそろっているか
- 不要な branch 専用メモを残していないか
- 例外運用で得たルールを正本へ反映したか
- `main` に持ち帰る note と選択済み結果 artifact の置き場が決まっているか
- legacy worktree を消したあとも `main` から関連 note と結果を辿れるか
- inventory/admission digest と cleanup 前後の readback を関連 Issue/PR から辿れるか
