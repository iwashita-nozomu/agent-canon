# worktree-health

<!--
@dependency-start
contract skill
responsibility Uses standard Git state to continue work and safely remove unused checkouts.
upstream design ../../documents/operations/BRANCH_SCOPE.md task scope and Git state preservation
upstream design ../../documents/operations/worktree-lifecycle.md checkout cleanup procedure
@dependency-end
-->

## 手順

1. 対象checkoutで `git status --short --branch` と対象pathの `git diff`、
   `git diff --cached` を読みます。branchや配置が問題なら `git worktree list --porcelain`
   と `git rev-parse --show-toplevel` でGitの実状態を確認します。
2. 自分の変更、既存の利用者差分、途中のmergeを区別し、必要な内容を保持して作業を続けます。
   別の処理が同じcheckoutを使っている場合は書込みの順序を揃えます。
3. 競合は [integration](integration.md)、新しい作業場所は
   [標準Gitのcheckout手順](../../documents/rule/repository-topic-clone.md) に従います。
4. 片付ける場合は必要なcommit・結果・ignored内容の保存先と利用終了を確認し、
   [checkout cleanup](../../documents/operations/worktree-lifecycle.md) の標準Git操作を使います。

## 判断根拠

Gitがbranch・worktree・差分・merge状態を保持します。操作で変わった部分を読み戻し、
会話・Issueへ結果と必要な保持理由を残します。これにより独自の形式・marker・proofを
作業継続の条件にする手順を省けます。
