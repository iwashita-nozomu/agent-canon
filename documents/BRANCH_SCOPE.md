<!--
@dependency-start
contract workflow
responsibility Documents Branch Scope と Git ワークフロー for this repository.
upstream design README.md durable document index
downstream design ../agents/canonical/CODEX_WORKFLOW.md consumes commit correctness closeout contract
downstream design ../agents/workflows/agent-canon-pr-workflow.md consumes branch, commit, and PR scope split contract
downstream design ../agents/skills/codex-task-workflow.md exposes commit correctness workflow guidance
downstream design ../.agents/skills/codex-task-workflow/SKILL.md exposes commit correctness runtime guidance
downstream design ../agents/skills/pr-processing.md exposes PR merge scope review
downstream design ../.agents/skills/pr-processing/SKILL.md exposes PR merge scope review
@dependency-end
-->

# Branch Scope と Git ワークフロー


この文書は、branch 名、branch の責務、commit / push、merge / rebase の判断をまとめた正本です。
worktree の作成と carry-over の流れは [worktree-lifecycle.md](worktree-lifecycle.md) を参照します。

## この文書の読み方

- この文書は、branch 名、branch scope、commit/push、merge/rebase、
  削除前チェックの Git workflow を定めます。
- 主な順路は、基本方針、branch 名、Scope の固定、コミット・プッシュ、
  Conflict 解決と merge / rebase、削除前チェックです。
- branch や PR の責務を固定する前、または merge 判断時に読みます。
- 境界: worktree 作成と carry-over の詳細は `worktree-lifecycle.md` が扱います。

## 1. 基本方針

- 1 branch = 1 topic に固定します。
- topic は独立した設計単位として扱い、branch と PR の scope もこの単位に揃えます。
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

### 範囲分割契約

コミット範囲と PR 範囲は別々のレビュー単位として扱います。

- コミットは Git 上で再実行できる実行単位です。
- PR はレビュー担当者が一つの問題、設計意図、正本 owner、振る舞いまたは
  契約の差分、根拠経路として受け入れられるレビュー単位です。
- commit または PR 作成 / 更新へ進む前に、差分が複数の問題、canonical
  owner、behavior or contract delta、validation route にまたがる場合は、
  run bundle または PR body に範囲表を置きます。範囲表には差分単位、
  目的、canonical owner、編集 path、validation route、依存する差分単位を
  書きます。
- 複数の差分単位を一つの PR に載せる判断は、同じ設計意図と同じレビュー判断で
  扱える場合に限ります。独立して main に入れられる差分単位は、merge 前に別
  PR または別 commit に分けます。
- AgentCanon source 変更と template / derived repo の submodule pin、root view
  変更は、source merge 後の parent PR / commit として分けます。

### Commit Correctness Contract

Git 上の code が正しく動くとは、fresh checkout の tracked tree から選択した
validation route を同じ entrypoint で再実行できることを指します。

- commit は Git 上の runnable unit です。`git checkout <commit>` と submodule 初期化で得られる tracked tree だけで、選択した validation route が再実行できる状態にします。
- validation が読んだ source、config、schema、fixture、文書、tool entrypoint は、その commit の tracked tree に含めます。ignored / generated runtime output は artifact、cache、log、result のどれかに分類して evidence に残します。
- code 変更では、file-level の code dependency scan と、言語 tool が対応する関数 / public entrypoint 単位の call-site evidence を commit evidence に含めます。Python では `python3 tools/agent_tools/helper_function_inventory.py --changed --all-functions --format json` を関数単位 evidence に使います。
- commit evidence には branch、commit SHA、submodule SHA、validation command、validation 対象 path、残った dirty / untracked path の分類を含めます。
- `WORKTREE_SCOPE.md` を更新した場合は、早い段階で commit します。
- push 前に、その branch で必須の test / lint / document check を実行します。
- 初回 push と PR 作成は `python3 tools/agent_tools/github_publish.py publish-pr --user-task "<current user task>" --repo <owner/name> --title "<title>" --body-file <body.md>` を使います。branch push だけなら `github_publish.py push` を使います。
- user-facing の完了報告は、原則として commit と push を終えてから行います。
- さらに `verification.txt` が `status=pass`、`closeout_gate.md` が `auditor_status=resolved`、`mechanical_completion_loop_complete=yes`、`diff_check_agent_complete=yes`、`user_completion_report=unlocked` になり、run-local diff-check artifact が現在 tracked diff ref の read-only independent approval を示すまで完了報告を出しません。
- push を行わない task が許されるのは、review-only、no-change、または user が明示的に commit / push を止めた場合です。
- push が自然な完了条件に含まれる task では、agent は push の許可を取りに戻りません。required review と validation が揃い、repo policy 的に自然ならそのまま push します。
- push に失敗した場合は、完了扱いにせず、branch、commit、`github_publish.py` の `NEXT_ACTION` と失敗理由を明記して報告します。literal URL push や remote 推測の alternate route は使いません。

## 5. Conflict 解決と merge / rebase

- `main` 取り込みは、branch の目的に必要な最小限に留めます。
- 履歴を読みやすく保つため、ローカル整理には `rebase` を使って構いません。
- 統合時の安全性と文脈保持を優先する場合は `merge` を選びます。
- 別 branch と同じファイルを触っている場合は、先に `notes/branches/` と `notes/worktrees/` で衝突リスクを明示します。
- file 追加、削除、rename、symlink 化、type 変更、ディレクトリ再編がある branch は、`agents/workflows/main-integration-workflow.md` の手順で統合します。
- 構成変更がある branch は、`main` 側で file 単位に拾い直して close してはいけません。
- 構成変更がある統合では、current checkout 上の integration branch で merge commit を作り、`python3 tools/ci/check_merge_structure.py --source <branch> --target origin/main --compare-commit HEAD` を通します。
- integration branch が妥当なら、`main` へは `git merge --ff-only integrate/<topic>-YYYYMMDD` で持ち帰ります。

## 6. 削除前チェック

- branch の目的が `notes/branches/` から辿れる
- `main` に持ち帰る note / final JSON が整理済み
- raw 結果を残す場所が決まっている
- `git worktree list` と `git branch -v` で後片付け対象が分かる
