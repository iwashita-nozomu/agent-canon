# Workscope Review

## Purpose

`WORKTREE_SCOPE.md` や branch scope 文書の「境界契約」としての質を独立にレビューします。
包括レビューの代わりではなく、scope の曖昧さ、弱い禁止事項、浅い required references、弱い carry-over 設計を先に止めるための skill です。

## Use This For

- `WORKTREE_SCOPE.md` を起草した直後の quality review
- branch の目的変更や scope refresh のあとに、scope 契約を見直したいとき
- `worktree-create` / `worktree-start` のあとで、scope だけに集中して厳しく見たいとき
- `comprehensive-development` や `project-review` に加えて、scope の鋭さを独立確認したいとき

## Must Read Before Reviewing

- `documents/worktree-lifecycle.md`
- `documents/WORKTREE_SCOPE_TEMPLATE.md`
- 対象 worktree の `WORKTREE_SCOPE.md`
- topic に近い `notes/guardrails/` と `notes/failures/`

## Inputs

- 対象 worktree の `WORKTREE_SCOPE.md`
- `git status --short --branch`
- `python3 scripts/agent_tools/worktree_scope_lint.py --workspace-root <worktree-path>` の結果
- 必要なら関連する branch note / worktree log

## Outputs

- findings-first の scope review
- `scope-ready`, `needs-scope-tightening`, `handoff-unclear` のいずれかの判定
- 修正すべき section と、次に使う skill family

## Review Dimensions

1. `Purpose` が target、主目的、非ゴールを十分に固定しているか
1. `Editable Directories` と `Read-Only Or Avoid Directories` が実際の task 境界に合っているか
1. `Required References Before Editing` が concrete file で、topic-specific な正本まで届いているか
1. `Main Carry-Over Targets` と action log path が、閉じ方まで含めて追跡可能か
1. `Required Checks Before Commit` が placeholder ではなく、現実に叩く command になっているか
1. `Additional Rules` が task 固有の risk を止める内容になっているか

## Mandatory Checklist

- `Branch` と `Worktree path` が current state と一致する
- placeholder が残っていない
- `Purpose` に非ゴールが明示されている
- required references が directory 名ではなく concrete file である
- required references に topic-specific file が少なくとも 1 件ある
- runtime output を使わないなら、その理由が読める
- carry-over target が note / design / result のどこに残るか分かる
- required checks が scope の実際の変更面と整合している

## Default Commands

- `bash scripts/worktree_start.sh --current --no-log`
- `python3 scripts/agent_tools/worktree_scope_lint.py --workspace-root <worktree-path>`
- `git status --short --branch`
- `git worktree list`
- `python3 scripts/tools/check_markdown_lint.py <scope-and-note-paths>`

## Good Finding Shape

- section 単位で「何が弱いか」を指摘する
- `不足`, `曖昧`, `過剰`, `衝突`, `handoff 不明` のどれかでラベル付けする
- `fix now` と `follow-up` を分ける
- 最後に `scope-ready`, `needs-scope-tightening`, `handoff-unclear` の判定を出す

## Boundary

- worktree を新規作成するのは `agents/skills/worktree-create.md` です。
- kickoff と action log 追記まで進めるのは `agents/skills/worktree-start.md` です。
- dirty 状態、conflict risk、cleanup readiness を広く見るのは `agents/skills/worktree-health.md` です。
- repo-wide な包括レビューは `agents/skills/comprehensive-development.md` か `agents/skills/project-review.md` を使います。

## Implementation Surface

- `scripts/agent_tools/worktree_scope_lint.py`
- `scripts/tools/check_worktree_scopes.sh`
- `scripts/worktree_start.sh`
