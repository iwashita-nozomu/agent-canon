# worktree-health
<!--
@dependency-start
contract skill
responsibility Documents worktree-health for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/design/request-intent-and-update-relation.md compact merge/readback and existing cleanup projection
@dependency-end
-->


## Purpose

現在の checkout が、task authority、run bundle、branch、未コミット差分、conflict risk の観点で健全かを確認します。

### Compact request/update projection

`../../documents/design/request-intent-and-update-relation.md` の lifecycle flow は merge
と readback の直後にこの skill の health/readback route へ接続します。health、scope、linked
worktree、clean status の evidence を既存 cleanup executor と closeout packet に返します。
merge/readback operation は tree/remote evidence を確認し、cleanup-dispatch-ready state に
到達します。completion evidence は selected existing cleanup executor の receipt、scratch
cleanup または typed retention receipt、CleanupProof、closeout packet readback です。cleanup
executor の選択と実行は各 owner route が行い、この skill は health/readback evidence を返します。

## Use When

- `reports/agents/.active_run` と run bundle の task authority 確認
- `team_manifest.yaml` / `task_authority.yaml` の write scope 逸脱確認
- current checkout の clean / dirty 状態確認
- conflict risk や carry-over 漏れの確認
- 削除前の健全性チェック

## Core References

- `documents/operations/worktree-lifecycle.md`
- `documents/operations/WORKTREE_SCOPE_TEMPLATE.md`
- `documents/operations/BRANCH_SCOPE.md`
- `documents/notes/guardrails/README.md`
- `documents/notes/failures/README.md`
- `documents/notes/worktrees/README.md`
- `tools/runtime/authority/hook_safety.py`
- `tools/repository/workspace/worktree_scope_lint.py`
- `tools/validation/documentation/checks/check_worktree_scopes.sh`
- `tools/validation/semantic/authority/validate_role_write_scope.py`

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
- `python3 tools/repository/workspace/worktree_scope_lint.py --current` が placeholder や stale kickoff field を出していない
- `documents/notes/guardrails/README.md` と `documents/notes/failures/README.md` の relevant item が未対応のまま残っていない
- `git worktree list --porcelain` で duplicate / stale worktree が無いか確認している
- branch / worktree 作成 route は `agents/canonical/CODEX_WORKFLOW.md` の Branch Reuse Default と `tools/runtime/authority/hook_safety.py` に委譲し、この skill は診断 command と `branch_creation_reason=<reason>` / `worktree_creation_reason=<reason>` の存在だけを確認している
- carry-over すべき note、report、result の置き場が消える前提になっていない
- dependency clone cleanup では、exact computed path、clean / untracked-zero
  state、remote integrated tree readback を health evidence として確認する。
  stale / missing membership marker は `marker-readback=membership-mismatch` として
  残る旧 evidence であり、それだけで cleanup hold にしない。managed child の除去後に
  他成果物の無い topic container が同じ cleanup receipt で除去されたことを確認する。

## Default Sequence

1. `reports/agents/.active_run`、run-local `work_log.md`、必要なら branch summary を読み、authority と carry-over 先を確認します。
1. legacy cleanup が scope に入る場合だけ `python3 tools/repository/workspace/worktree_scope_lint.py --current` を流し、古い scope 文書の placeholder と stale field を拾います。
1. `git status --short --branch`、`git diff --name-only`、`git worktree list --porcelain` を見て drift を洗います。
1. branch / worktree 作成が必要に見える場合は `agents/canonical/CODEX_WORKFLOW.md` の Branch Reuse Default を参照し、この skill では `branch_creation_reason=<reason>` または `worktree_creation_reason=<reason>` と対応箇所の有無だけを確認します。
1. `documents/notes/guardrails/README.md` と `documents/notes/failures/README.md` を見直し、今回の drift や cleanup risk と関連する既知項目がないか確認します。
1. legacy cleanup が scope に入る場合だけ `bash tools/validation/documentation/checks/check_worktree_scopes.sh` で repo 内の worktree scope 配置を確認します。
1. specialist run bundle を伴う場合は、必要に応じて `validate_role_write_scope.py` で write policy 逸脱を見ます。
1. drift や cleanup risk があれば、run-local `work_log.md` か cleanup artifact に残してから継続、修正、削除判断へ進みます。

## Default Commands

- `git status --short --branch`
- `git diff --name-only`
- `git branch --show-current`
- `git worktree list --porcelain`
- `python3 tools/validation/semantic/authority/validate_role_write_scope.py --report-dir reports/agents/<run-id> --workspace-root . --role <role-id>`

## Boundary

- stale worktree、古い `WORKTREE_SCOPE.md`、legacy action log の cleanup 診断には `worktree-start` を使います。新規作業の worktree 初期化には使いません。
- branch/worktree 作成 route は `agents/canonical/CODEX_WORKFLOW.md` の Branch Reuse Default と PreToolUse safety owner `tools/runtime/authority/hook_safety.py` を正本にします。
- repo 全体レビューや再編は `comprehensive-development` を使います。
