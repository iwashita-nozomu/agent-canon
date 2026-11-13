# Worktree Notes

<!--
@dependency-start
contract reference
responsibility Provides existing worktree knowledge and carry-over references.
upstream design ../README.md notes lifecycle index
upstream design ../../operations/notes-lifecycle.md optional knowledge outputs
@dependency-end
-->

このディレクトリには、過去の worktree から引き継いだ知見と参照を保持します。
必要な内容を探すときに読みます。現在の作業状態は `git status --short --branch`、
対象の `git diff -- <paths>`、`git worktree list --porcelain` と会話の handoff で確認します。

worktree を削除する前に、必要な知見や結果が削除対象の外から取得できることを確認します。
保存する内容と置き場は [notes lifecycle](../../operations/notes-lifecycle.md) に従います。
