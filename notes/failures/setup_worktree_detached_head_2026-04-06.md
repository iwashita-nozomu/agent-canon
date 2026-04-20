# setup_worktree Detached HEAD

Scope: `scripts/setup_worktree.sh` で既存 branch に対応する worktree を作ったときの kickoff 失敗

Failure Kind: workflow bug

Trigger:

- `git worktree add <path> refs/heads/<branch>` のように full ref を `commit-ish` として渡す
- そのまま `WORKTREE_SCOPE.md` や note を編集し、branch に attach されている前提で作業を進める

Why It Matters:

- 新しい worktree が detached HEAD のまま始まる
- kickoff note や scope 更新が branch ではなく孤立 commit 予備軍になる
- `worktree-start` と `worktree-health` の前提が崩れる

Current Understanding:

- `git worktree add` は branch 名そのものではなく `refs/heads/<branch>` を与えると、既存 branch checkout ではなく commit-ish checkout として扱う
- 2026-04-06 に 5 本の recreated worktree で再現した

Safe Alternative:

- `git worktree add <path> <branch>` を使う
- 作成直後に `git worktree list --porcelain` と `git -C <path> status --short --branch` を確認する
- branch / path / action log stub を生成してから kickoff する

Related:

- [tools/setup_worktree.sh](/workspace/tools/setup_worktree.sh)
- [documents/worktree-lifecycle.md](/workspace/documents/worktree-lifecycle.md)
- [agents/skills/worktree-start.md](/workspace/agents/skills/worktree-start.md)
