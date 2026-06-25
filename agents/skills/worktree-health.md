# worktree-health
<!--
@dependency-start
contract skill
responsibility Documents worktree-health for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

現在の checkout が、task authority、run bundle、branch、未コミット差分、conflict risk の観点で健全かを確認します。

## Use When

- `reports/agents/.active_run` と run bundle の task authority 確認
- `team_manifest.yaml` / `task_authority.yaml` の write scope 逸脱確認
- current checkout の clean / dirty 状態確認
- conflict risk や carry-over 漏れの確認
- 削除前の健全性チェック

## Core References

- `documents/worktree-lifecycle.md`
- `documents/WORKTREE_SCOPE_TEMPLATE.md`
- `documents/BRANCH_SCOPE.md`
- `notes/guardrails/README.md`
- `notes/failures/README.md`
- `notes/worktrees/README.md`
- `.codex/hooks/branch_worktree_guard.py`
- `tools/agent_tools/worktree_scope_lint.py`
- `tools/docs/check_worktree_scopes.sh`
- `tools/agent_tools/validate_role_write_scope.py`

## Expected Outcome

- active run bundle と実際の checkout 状態の差分が見えている
- task authority drift、runtime output drift、carry-over 漏れがあれば記録されている
- この checkout を継続してよいか、authority を直すべきか、cleanup に進むべきか判断できる

## Mandatory Checklist

- `reports/agents/.active_run` が現在の run bundle を指し、`task_authority.yaml` の allowed / forbidden paths が current state と一致する
- `git status --short --branch` で見える dirty state が説明可能である
- `git diff --name-only` の変更が `task_authority.yaml` と `team_manifest.yaml` の write scope に収まっている
- runtime output が active run bundle または明示された report directory に収まっている
- run-local `work_log.md` と必要なら branch summary が current state に追随している
- `python3 tools/agent_tools/worktree_scope_lint.py --current` が placeholder や stale kickoff field を出していない
- `notes/guardrails/README.md` と `notes/failures/README.md` の relevant item が未対応のまま残っていない
- `git worktree list --porcelain` で duplicate / stale worktree が無いか確認している
- branch / worktree 作成 route は `agents/canonical/CODEX_WORKFLOW.md` の Branch Reuse Default と `branch_worktree_guard.py` に委譲し、この skill は診断 command と `branch_creation_reason=<reason>` / `worktree_creation_reason=<reason>` の存在だけを確認している
- carry-over すべき note、report、result の置き場が消える前提になっていない

## Default Sequence

1. `reports/agents/.active_run`、run-local `work_log.md`、必要なら branch summary を読み、authority と carry-over 先を確認します。
1. legacy cleanup が scope に入る場合だけ `python3 tools/agent_tools/worktree_scope_lint.py --current` を流し、古い scope 文書の placeholder と stale field を拾います。
1. `git status --short --branch`、`git diff --name-only`、`git worktree list --porcelain` を見て drift を洗います。
1. branch / worktree 作成が必要に見える場合は `agents/canonical/CODEX_WORKFLOW.md` の Branch Reuse Default を参照し、この skill では `branch_creation_reason=<reason>` または `worktree_creation_reason=<reason>` と対応箇所の有無だけを確認します。
1. `notes/guardrails/README.md` と `notes/failures/README.md` を見直し、今回の drift や cleanup risk と関連する既知項目がないか確認します。
1. legacy cleanup が scope に入る場合だけ `bash tools/docs/check_worktree_scopes.sh` で repo 内の worktree scope 配置を確認します。
1. specialist run bundle を伴う場合は、必要に応じて `validate_role_write_scope.py` で write policy 逸脱を見ます。
1. drift や cleanup risk があれば、run-local `work_log.md` か cleanup artifact に残してから継続、修正、削除判断へ進みます。

## Default Commands

- `git status --short --branch`
- `git diff --name-only`
- `git branch --show-current`
- `git worktree list --porcelain`
- `python3 tools/agent_tools/validate_role_write_scope.py --report-dir reports/agents/<run-id> --workspace-root . --role <role-id>`

## Boundary

- stale worktree、古い `WORKTREE_SCOPE.md`、legacy action log の cleanup 診断には `worktree-start` を使います。新規作業の worktree 初期化には使いません。
- branch/worktree 作成 route は `agents/canonical/CODEX_WORKFLOW.md` の Branch Reuse Default と PreToolUse `branch_worktree_guard.py` を正本にします。
- repo 全体レビューや再編は `comprehensive-development` を使います。
