# Branch Scope と Git ワークフロー
<!--
@dependency-start
upstream design README.md durable document index
@dependency-end
-->


この文書は、branch 名、branch の責務、commit / push、merge / rebase の判断をまとめた正本です。
worktree の作成と carry-over の流れは [worktree-lifecycle.md](worktree-lifecycle.md) を参照します。

## 1. 基本方針

- 1 branch = 1 topic に固定します。
- branch の責務が広がったら、branch を分けるか `WORKTREE_SCOPE.md` を更新します。
- 実装コードと長時間実験の生成物は、必要に応じて branch を分けます。
- `main` は統合先であり、試行錯誤や途中生成物の置き場にはしません。

## 2. branch 名

- 通常の実装 branch は `work/<topic>-YYYYMMDD` を使います。
- 結果保存 branch は `results/<topic>` を使います。
- branch 名は目的が読める英語句で付けます。

## 3. Scope の固定

- branch を切ったら、必要に応じて対応する worktree root に `WORKTREE_SCOPE.md` を置きます。
- `WORKTREE_SCOPE.md` には editable directories、carry-over target、action log を明記します。
- branch で experiment topic を継続的に触る場合は、`experiments/registry.toml` の `active_branch` と必要なら `scope_file` を更新します。
- branch の入口が必要な場合は `notes/branches/<branch_topic>.md` に置き、scope と関連 note をそこから辿れるようにします。

## 4. コミット・プッシュ

- commit は branch の責務に収まる差分だけを含めます。
- `WORKTREE_SCOPE.md` を更新した場合は、早い段階で commit します。
- push 前に、その branch で必須の test / lint / document check を実行します。
- 初回 push は `git push -u origin <branch-name>` を使います。
- user-facing の完了報告は、原則として commit と push を終えてから行います。
- さらに `verification.txt` が `status=pass`、`closeout_gate.md` が `auditor_status=resolved` かつ `user_completion_report=unlocked` になるまで完了報告を出しません。
- push を行わない task が許されるのは、review-only、no-change、または user が明示的に commit / push を止めた場合です。
- push が自然な完了条件に含まれる task では、agent は push の許可を取りに戻りません。required review と validation が揃い、repo policy 的に自然ならそのまま push します。
- push に失敗した場合は、完了扱いにせず、branch、commit、失敗理由を明記して報告します。

## 5. Conflict 解決と merge / rebase

- `main` 取り込みは、branch の目的に必要な最小限に留めます。
- 履歴を読みやすく保つため、ローカル整理には `rebase` を使って構いません。
- 統合時の安全性と文脈保持を優先する場合は `merge` を選びます。
- 別 branch と同じファイルを触っている場合は、先に `notes/branches/` と `notes/worktrees/` で衝突リスクを明示します。
- file 追加、削除、rename、symlink 化、type 変更、ディレクトリ再編がある branch は、`agents/workflows/main-integration-workflow.md` の手順で統合します。
- 構成変更がある branch は、`main` 側で file 単位に拾い直して close してはいけません。
- 構成変更がある統合では、専用 integration worktree 上の merge commit を作り、`python3 tools/ci/check_merge_structure.py --source <branch> --target origin/main --compare-commit HEAD` を通します。
- integration branch が妥当なら、`main` へは `git merge --ff-only integrate/<topic>-YYYYMMDD` で持ち帰ります。

## 6. 削除前チェック

- branch の目的が `notes/branches/` から辿れる
- `main` に持ち帰る note / final JSON が整理済み
- raw 結果を残す場所が決まっている
- `git worktree list` と `git branch -v` で後片付け対象が分かる
