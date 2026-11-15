# repository-topic-clone

<!--
@dependency-start
contract workflow
responsibility Uses standard Git to create, reuse, integrate, and remove task checkouts.
upstream design ../../documents/rule/repository-topic-clone.md standard Git procedure
upstream design ../../documents/operations/BRANCH_SCOPE.md branch scope and preservation
downstream implementation ./catalog.yaml public skill discovery
@dependency-end
-->

## 手順

1. [標準Gitのcheckout手順](../../documents/rule/repository-topic-clone.md) から必要な操作を選びます。
2. `git status --short --branch`、対象差分、`git worktree list --porcelain` で既存の
   作業場所とbranchを確認します。同じ作業を担うcheckoutを再利用し、既存差分を保持します。
3. 新規作成には `git worktree add` または `git clone` を使います。branch名へIssue番号を
   含め、最新mainを `git fetch` と `git merge origin/main` で取り込みます。
4. 合意した変更と必要な削除を終えてから検証し、標準Gitと既存GitHub接続でPRを公開します。
5. 利用を終えたcheckoutは必要な内容の保存先を確認し、標準Gitの削除手順で片付けます。

依存repositoryのURL・gitlink・pinの更新は
[dependency-module-change](dependency-module-change.md)、競合解消は
[integration](integration.md)、GitHub公開は [pr-processing](pr-processing.md) が所有します。

## この手順を使う理由

Gitの実path・branch・indexを使い、作成済みの作業を継続します。独自の作成コマンドや
形式確認を挟む手間と停止条件を削減します。
