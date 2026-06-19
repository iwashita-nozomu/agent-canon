# branch・worktree の legacy cleanup 運用
<!--
@dependency-start
contract workflow
responsibility Documents branch・worktree legacy cleanup for this repository.
upstream design README.md durable document index
@dependency-end
-->


この文書は、既存の stale worktree、古い `WORKTREE_SCOPE.md`、または過去の branch/action log を片付ける場合だけ参照します。
新規 repo-changing task では追加の `git worktree`、separate worktree、integration worktree を作成・使用しません。既定運用は current checkout 上の branch / wave です。

## 使う場面

- 既存の stale worktree を棚卸ししたい
- 古い `WORKTREE_SCOPE.md` や action log が current checkout の作業を汚していないか確認したい
- 過去の branch / worktree note から current checkout へ知見だけを持ち帰りたい

## cleanup 前の確認

- `main` と対象 branch が `origin` と同期しているか確認します。
- 新しい worktree は切りません。
- current checkout で続けられる作業は current checkout の後続 wave に直列化します。
- carry-over 先、runtime output directory、削除または保持する legacy note を先に決めます。

## legacy scope の確認

stale な worktree や古い scope を見つけた場合は、作業場所として再開せず、次を確認します。

- `WORKTREE_SCOPE.md` の `Branch` と `Worktree path` が current checkout と違う場合、その scope は作業 authority ではありません。
- [WORKTREE_LOG_TEMPLATE.md](../notes/worktrees/WORKTREE_LOG_TEMPLATE.md) 由来の action log は legacy evidence として読み、current checkout の run-local `work_log.md` へ carry-over 判断だけを残します。
- 継続ログは current checkout の `python3 tools/agent_tools/work_log.py --kind <kind> --request-clause-id R1 --message "<what changed>" --next "<next>"` を既定にします。
- experiment topic を持つ古い worktree を見つけた場合は、`experiments/registry.toml` の stale `active_worktree` / `scope_file` を cleanup 対象として扱います。
- branch が複数 session 続いた場合でも、作業再開は current checkout の branch / wave で行い、`notes/branches/` は summary evidence としてだけ使います。
- `notes/guardrails/README.md` と `notes/failures/README.md` を見て、今回の task で踏みやすい avoid pattern と既知 failure を確認します。
- `python3 tools/agent_tools/worktree_scope_lint.py --current` で stale scope の placeholder と kickoff 欄を確認します。`bash tools/worktree_start.sh --current` は cleanup diagnostic 以外では使いません。
- `git status --short --branch` と `git worktree list --porcelain` を確認し、必要なら `bash tools/docs/check_worktree_scopes.sh` を実行します。
- dirty state、conflict risk、scope drift の兆候があれば、編集前に action log に残します。
- `main` へ戻す場合も integration worktree は切らず、`agents/workflows/main-integration-workflow.md` の current-checkout branch 手順を使います。

## ルール

- branch は短期で閉じます。
- 統合先は常に `main` です。
- 長期に残す知見は branch 名ではなく `documents/` または `notes/` に移します。
- 1 回の実験結果を branch 固有の台帳に依存させません。
- `WORKTREE_SCOPE.md` は legacy cleanup / drift diagnosis 用の evidence であり、新しい task の scope authority ではありません。
- 別 branch / 別 path の scope file を流用しません。
- branch の役割と carry-over 先を残したい場合は [BRANCH_SCOPE.md](BRANCH_SCOPE.md) と `notes/branches/` を使います。
- 既存 action log は `notes/worktrees/` に legacy evidence として残します。
- action log の各 entry には、いま処理している `request_clause_ids=` を残します。
- scope 更新、編集開始、テスト実行、実験開始 / 停止、carry-over 判断は action log に逐次残します。repo-changing task では同じ step を run bundle `work_log.md` にも残します。
- scope が途中で変わったら、追加編集の前に current checkout の run-local `work_log.md` と handoff packet を更新します。
- editable path は current checkout の dependency-expanded write scope と handoff packet で管理します。
- runtime output は current checkout の run bundle または task 固有 output directory へ限定します。
- closeout 前に `documents/notes-lifecycle.md` を見て、action log から knowledge/theme/failure へ昇格させる項目を決めます。
- file 構成変更を含む branch を閉じる前には、current checkout 上で `python3 tools/ci/check_merge_structure.py ...` を通します。

## 閉じる前の確認

- `main` に戻すコード、文書、知見がそろっているか
- 不要な branch 専用メモを残していないか
- 例外運用で得たルールを正本へ反映したか
- `main` に持ち帰る note と最小 final JSON の置き場が決まっているか
- legacy worktree を消したあとも `main` から関連 note と結果を辿れるか
