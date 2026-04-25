# worktree-health
<!--
@dependency-start
@dependency-end
-->


## Purpose

現在の worktree が、scope、branch、未コミット差分、conflict risk の観点で健全かを確認します。

## Use When

- `WORKTREE_SCOPE.md` の存在と内容確認
- editable directories / runtime output directories の逸脱確認
- worktree の clean / dirty 状態確認
- conflict risk や carry-over 漏れの確認
- 削除前の健全性チェック

## Core References

- `documents/worktree-lifecycle.md`
- `documents/WORKTREE_SCOPE_TEMPLATE.md`
- `documents/BRANCH_SCOPE.md`
- `notes/guardrails/README.md`
- `notes/failures/README.md`
- `notes/worktrees/README.md`
- `tools/agent_tools/worktree_scope_lint.py`
- `tools/docs/check_worktree_scopes.sh`
- `tools/agent_tools/validate_role_write_scope.py`

## Expected Outcome

- `WORKTREE_SCOPE.md` と実際の worktree 状態の差分が見えている
- scope drift、runtime output drift、carry-over 漏れがあれば記録されている
- この worktree を継続してよいか、scope を直すべきか、cleanup に進むべきか判断できる

## Mandatory Checklist

- `WORKTREE_SCOPE.md` が存在し、branch、path、editable directories、runtime output directories が current state と一致する
- `git status --short --branch` で見える dirty state が説明可能である
- `git diff --name-only` の変更が editable directories の中に収まっている
- runtime output が `WORKTREE_SCOPE.md` に書いた場所へ収まっている
- action log と必要なら branch summary が current state に追随している
- `python3 tools/agent_tools/worktree_scope_lint.py --current` が placeholder や stale kickoff field を出していない
- `notes/guardrails/README.md` と `notes/failures/README.md` の relevant item が未対応のまま残っていない
- `git worktree list --porcelain` で duplicate / stale worktree が無いか確認している
- carry-over すべき note、report、result の置き場が消える前提になっていない

## Default Sequence

1. `WORKTREE_SCOPE.md`、action log、必要なら branch summary を読み、scope と carry-over 先を確認します。
1. `python3 tools/agent_tools/worktree_scope_lint.py --current` を流し、scope 文書の placeholder と stale field を拾います。
1. `git status --short --branch`、`git diff --name-only`、`git worktree list --porcelain` を見て drift を洗います。
1. `notes/guardrails/README.md` と `notes/failures/README.md` を見直し、今回の drift や cleanup risk と関連する既知項目がないか確認します。
1. `bash tools/docs/check_worktree_scopes.sh` で repo 内の worktree scope 配置を確認します。
1. specialist run bundle を伴う場合は、必要に応じて `validate_role_write_scope.py` で write policy 逸脱を見ます。
1. drift や cleanup risk があれば、action log に残してから継続、修正、削除判断へ進みます。

## Default Commands

- `git status --short --branch`
- `git diff --name-only`
- `git worktree list --porcelain`
- `python3 tools/agent_tools/worktree_scope_lint.py --current`
- `bash tools/docs/check_worktree_scopes.sh`
- `python3 tools/agent_tools/validate_role_write_scope.py --report-dir reports/agents/<run-id> --workspace-root . --role <role-id>`

## Boundary

- worktree 開始時の初期化は `worktree-start` を使います。
- repo 全体レビューや再編は `comprehensive-development` を使います。
