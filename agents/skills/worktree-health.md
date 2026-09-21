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

現在の checkout の状態と差分を標準機能で確認し、継続・修正・引継ぎに必要な判断を行います。
通常の差分確認に run bundle、独自スクリプト、cleanup 検査を要求しません。

### Compact request/update projection

[request/update lifecycle](../../documents/design/request-intent-and-update-relation.md) がこの skill を呼ぶ場合、
選択された操作に必要な health、scope、linked worktree、clean status の evidence を返します。
cleanup が選択された場合だけ、merge/readback 後の tree/remote evidence を既存 executor と closeout packet に渡します。
cleanup-dispatch-ready 以降の実行、executor receipt、scratch cleanup または typed retention receipt、
CleanupProof、closeout packet readback は既存 cleanup owner に従います。通常の状態確認では起動しません。

## Use When

checkout の clean / dirty、差分、conflict risk、authority drift、carry-over、削除前の健全性を確認するとき。

## Default Sequence

確認する対象と目的を既存の作業情報から選び、対応する標準操作だけを使います。
下表は選択肢であり、毎回すべて実行するチェックリストではありません。

| 目的 | 操作 |
| --- | --- |
| branch、staged / unstaged / untracked の状態 | `git status --short --branch` |
| 未 stage の差分 | `git diff -- <paths>` |
| stage 済みの差分 | `git diff --cached -- <paths>` |
| 最新 main 取込み後の PR 相当の commit 差分 | `git diff origin/main...HEAD -- <paths>` |
| 変更ファイル名だけ、または変更量だけ | 選択した `git diff` に `--name-only` または `--stat` を付ける |
| remote の commit / PR 差分で足りる作業 | 既存 GitHub compare / PR diff action |

`<paths>` は必要な対象に絞り、`origin/main` は選択済みの remote/base を使います。
untracked の内容が必要ならそのファイルを読みます。remote の差分で local の未 commit 状態を確認したとは扱いません。

標準機能で満たせる取得・比較・集計を Python 等で再実装しません。独自処理は具体的な不足がある場合だけです。
同じ結果を再計算しても判断材料は増えず、確認対象の実装と失敗点だけが増えるためです。既存の専用検証ツールの利用は禁止しません。

同じ状態で判断できたら確認を終えます。編集、stage、merge、ref 更新、並行変更で証拠が古くなった場合だけ、
影響する範囲を取り直します。念押しの再取得、独自 hash 計算、差分の再構成は行いません。
結果と未解決事項は既存の作業記録へ残し、次の操作へ進みます。

## Conditional Checks

通常確認で必要な判断が済む場合、この節は実行しません。

| 適用条件 | 必要な確認・既存経路 |
| --- | --- |
| 選択された run bundle の authority / scope / output 診断 | `reports/agents/.active_run`、`task_authority.yaml`、`team_manifest.yaml`、run-local `work_log.md` の関係する部分を照合。write scope の検証が必要なら `python3 tools/validation/semantic/authority/validate_role_write_scope.py --report-dir reports/agents/<run-id> --workspace-root . --role <role-id>` |
| legacy scope / action log の cleanup | `python3 tools/repository/workspace/worktree_scope_lint.py --current`、配置の確認が必要なら `bash tools/validation/documentation/checks/check_worktree_scopes.sh`。対象の scope は [WORKTREE_SCOPE_TEMPLATE](../../documents/operations/WORKTREE_SCOPE_TEMPLATE.md) を参照 |
| linked / stale / duplicate worktree の診断 | `git worktree list --porcelain` と対象の [worktree 記録](../../documents/notes/worktrees/README.md) |
| 実際の drift / cleanup risk と既知事項の照合 | 関係する [guardrails](../../documents/notes/guardrails/README.md) / [failures](../../documents/notes/failures/README.md) の項目だけを参照 |
| checkout の削除・carry-over | [worktree lifecycle](../../documents/operations/worktree-lifecycle.md) と [Branch Scope](../../documents/operations/BRANCH_SCOPE.md) の対象操作。必要な note / report / result の引継ぎ先を保持 |

依存 clone を削除する場合は、exact computed path、clean / untracked-zero、remote integrated tree readback を確認します。
stale / missing membership marker は `marker-readback=membership-mismatch` として残し、それだけで cleanup hold にしません。
managed child の除去後、他成果物のない topic container も同じ cleanup receipt で除去されたことを確認します。
この削除条件を通常の差分取得へ適用しません。

## Boundary

- 未保存・未知・他者の差分を保持し、dirty だけで不整合と判断しません。自分の Git 操作を未完了のまま放置せず、修復不能な対象と次の対応を引き継ぎます。記録だけを修復済みと扱いません。
- 最新 main の取込み、必要な競合解消、公開前の最終差分確認は省略しません。branch / commit / publication は [Branch Scope](../../documents/operations/BRANCH_SCOPE.md) に従います。
- checkout の初期化・branch/worktree 作成は [repository-topic-clone](repository-topic-clone.md)、[CODEX_INTAKE / Branch Reuse Default](../canonical/CODEX_INTAKE.md)、`tools/runtime/authority/hook_safety.py` に委譲します。この skill では選択済み checkout-mode と作成時の `branch_creation_reason=<reason>` / `worktree_creation_reason=<reason>` を確認し、手動作成しません。
- repo 全体レビューや再編は、依頼の scope に含まれる場合だけ [comprehensive-development](comprehensive-development.md) を使います。
