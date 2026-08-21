<!--
@dependency-start
contract reference
responsibility 日常作業、branch、PR、worktree、checklist、troubleshooting、legacy cleanup の文書入口。
upstream design ../README.md documents 索引と正本境界。
@dependency-end
-->

# 作業運用

この directory は、設計そのものではなく、作業を開始・進行・終了するときの運用を
扱います。作業対象の責務や実装境界は `../design/` または該当する契約文書を参照します。

## 構成

- `BRANCH_SCOPE.md`: branch と Git の作業境界。
- `orphan-lifecycle.md`: branch・PR・worktree の意味差分 inventory、有限分類、cleanup admission の正本。
- `FILE_CHECKLIST_OPERATIONS.md`: 作業別 checklist。
- `TROUBLESHOOTING.md`: 障害対応の入口。
- `WORKTREE_SCOPE_TEMPLATE.md`、`worktree-lifecycle.md`: worktree の記録とcleanup。
- `notes-lifecycle.md`: notes の lifecycle。
- `issue-label-taxonomy.md`: Issue の分類。

運用文書は、実装・設計の正本を複製せず、参照先と完了条件を示します。
