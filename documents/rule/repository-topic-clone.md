# Gitで作業用checkoutを扱う

<!--
@dependency-start
contract policy
responsibility Owns standard Git checkout creation, reuse, main integration, and cleanup.
upstream design ../operations/BRANCH_SCOPE.md branch scope and preservation
downstream design ../../agents/skills/repository-topic-clone.md checkout procedure
downstream design ../../agents/skills/dependency-module-change.md dependency checkout procedure
@dependency-end
-->

## 既存checkoutの再利用

作業対象とbranchを会話・Issueで確認し、標準Gitで実状態を読みます。

```bash
git status --short --branch
git remote -v
git worktree list --porcelain
git diff
git diff --cached
```

同じ作業を担うbranchとcheckoutがあれば、その場所を再利用します。Gitが認識する
既存checkoutを、その実pathとbranchで扱います。作業中の差分、未公開commit、
利用者のファイルを保持し、自分の変更を対象pathで区切って公開します。

## 作成

同じrepositoryの並行作業には `git worktree add`、別の依存repositoryには
`git clone` を使います。新規配置の目安は `workspace/<topic>/<repo>` です。
既存の配置はそのまま使い、branch名には対応Issue番号を含めます。

同じrepositoryの新しい作業branchを作る例です。`<path>` は今回使うcheckout、
`<branch>` はIssue番号入りのbranch名です。

```bash
git fetch origin main
git worktree add -b <branch> <path> origin/main
```

作成済みbranchを別checkoutで使う場合は `git worktree add <path> <branch>` を
使います。Gitがそのbranchの使用中checkoutを示したら、その実pathを確認して
再利用します。別repositoryを用意する場合は次の標準操作を使います。

```bash
git clone <url> <path>
git -C <path> switch -c <branch> origin/main
```

## main取込みと競合解消

作業開始時とPR公開前に作業checkoutで最新mainを実マージします。

```bash
git fetch origin main
git merge origin/main
```

競合時は `git status`、`git diff`、`git ls-files --unmerged` で双方の内容を確認し、
解消したpathを `git add` または `git rm` で反映して `git merge --continue` を使います。
意図した削除と旧branchの編集が競合した場合は削除を採用し、必要な編集を移行先へ
反映します。既存の利用者差分と、自分が始めたGit操作の状態を保持して進めます。

## 公開

変更単位をpath指定でcommitし、`git push -u origin <branch>` と既存のGitHub接続で
PRを公開します。実branch・HEAD・公開した差分を確認し、Issueへ結果を残します。
詳しい公開責務は [pr-processing](../../agents/skills/pr-processing.md) に従います。

## クリーンアップ

利用を終えたcheckoutは、必要な変更・結果の保存先と、他の処理が使用中かを確認して
片付けます。Git statusに出る変更に加え、保持するignored成果物やsubmodule内の
状態も対象に応じて確認します。

linked worktreeは `git worktree remove <path>`、独立cloneは保存・公開と利用終了を
確認したexact directoryの削除を使います。Gitの拒否はそのpathの実状態から判断し、
未知の内容を保持します。削除後はpathと `git worktree list` を読み戻します。
local/remote branchの削除は、そのbranchの利用終了と保存を別に確認して行います。

## 判断根拠

Gitがbranch・worktree・index・merge状態を所有します。標準操作と実状態を使うことで、
作成済みcheckoutをそのまま継続し、独自の形式・marker・receiptによる停止を省けます。
作業範囲と公開判断は既存の会話・Issue・PRに残します。
