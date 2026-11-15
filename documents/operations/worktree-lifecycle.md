# branch・worktreeの片付け

<!--
@dependency-start
contract workflow
responsibility Removes unused Git checkouts while preserving work, results, and user data.
upstream design BRANCH_SCOPE.md branch scope and Git state preservation
upstream design ../rule/repository-topic-clone.md standard Git checkout operations
downstream design ../../agents/skills/worktree-health.md state and cleanup reader
@dependency-end
-->

## cleanup前の確認

対象path、branch、現在の利用者と処理を確認します。標準Gitで必要な状態を読みます。

```bash
git worktree list --porcelain
git -C <path> status --short --branch
git -C <path> diff
git -C <path> diff --cached
git -C <path> log --oneline origin/main..HEAD
```

自分が作ったcheckoutの利用終了と、保持するcommit・結果の保存先を確認します。
statusに出る変更に加え、必要なignored成果物、submodule内の変更・local commitも
対象に応じて確認します。実験branchでは論文・結果・起点と目的を辿れる参照を保持します。
利用中または内容の所有が不明なpathは保存し、判明している独立作業を続けます。

## 削除

linked worktreeは `git worktree remove <path>` を使います。独立cloneは必要な内容の
保存・公開と利用終了を確認して、対象のexact directoryを削除します。Gitが削除を拒否したら、
示されたpathの実内容を確認して判断します。

削除後はpathと `git worktree list --porcelain` を読み戻します。branchも閉じる場合は
保存先を確認し、標準の `git branch -d <branch>` を使います。remote branchの削除は
そのbranchの完了・利用終了に対応する別の公開操作として扱います。

## legacy scope の確認

古い `WORKTREE_SCOPE.md` や作業noteは、その内容が必要な判断に関係する場合に読みます。
現在のbranch・HEAD・差分・会話と照合し、保持する知見や結果を既存文書・Issueへ移します。
確認後に利用を終えたexact pathを片付け、未解決の保持対象はその理由を結果へ残します。

## 判断根拠

Gitの状態と実際の利用・保存先が、削除で失う内容の判断材料です。追加のcleanup台帳や
形式markerの確認を省き、保存した内容と削除したpathを既存の作業結果で辿れるようにします。
