# branch・worktree の例外運用

この文書は、`main` 以外で短期的に作業を切り分ける必要がある場合だけ参照します。
既定運用は `main` です。恒常的な branch 分割や worktree 常用は前提にしません。

## 使う場面

- 大きな refactor を安全に切り分けたい
- レビュー前に差分を明確に分けたい
- 長時間実験や破壊的な試行を一時的に隔離したい

## 作成前の確認

- `main` と対象 branch が `origin` と同期しているか確認します。
- 既存の worktree を使い回さず、新しい worktree を切ります。
- 長時間 run や巨大生成物が無いなら、まず `main` で進めることを優先します。
- 分離する topic、carry-over 先、runtime output directory を先に決めます。

## 作成直後の kickoff

新しい worktree を切った直後、または stale な worktree を再開した直後は、`worktree-start` を使って次を閉じます。

- [WORKTREE_SCOPE_TEMPLATE.md](/mnt/l/workspace/project_template/documents/WORKTREE_SCOPE_TEMPLATE.md) を基に、worktree root の `WORKTREE_SCOPE.md` を current state へ合わせます。
- `WORKTREE_SCOPE.md` の `Branch` と `Worktree path` を current branch と current filesystem path に一致させます。不一致のまま編集を始めません。
- [WORKTREE_LOG_TEMPLATE.md](/mnt/l/workspace/project_template/notes/worktrees/WORKTREE_LOG_TEMPLATE.md) を基に action log を作るか更新し、branch、path、purpose、次の一手を最初に残します。
- 継続ログは `python3 tools/agent_tools/work_log.py --kind <kind> --request-clause-id R1 --message "<what changed>" --next "<next>"` を既定にします。
- kickoff 時に run bundle の `user_request_contract.md` を current worktree から辿れるように固定します。これにより `work_log.py` 1 回で action log と run bundle `work_log.md` を両方更新できます。
- この worktree が experiment topic を持つ場合は、`experiments/registry.toml` の `active_branch`、必要なら `active_worktree` と `scope_file` を合わせます。
- branch が複数 session 続く、または handoff 前提なら `notes/branches/` に summary を置きます。
- `notes/guardrails/README.md` と `notes/failures/README.md` を見て、今回の task で踏みやすい avoid pattern と既知 failure を確認します。
- `python3 tools/agent_tools/worktree_scope_lint.py --current` か `bash tools/worktree_start.sh --current` で scope の placeholder と kickoff 欄を確認します。
- `git status --short --branch` と `git worktree list --porcelain` を確認し、必要なら `bash tools/docs/check_worktree_scopes.sh` を実行します。
- dirty state、conflict risk、scope drift の兆候があれば、編集前に action log に残します。
- `main` へ戻すための integration worktree を切る場合は、`agents/workflows/main-integration-workflow.md` の手順を先に見ます。

## ルール

- branch は短期で閉じます。
- 統合先は常に `main` です。
- 長期に残す知見は branch 名ではなく `documents/` または `notes/` に移します。
- 1 回の実験結果を branch 固有の台帳に依存させません。
- worktree root には必要に応じて `WORKTREE_SCOPE.md` を置き、テンプレートは [WORKTREE_SCOPE_TEMPLATE.md](/mnt/l/workspace/project_template/documents/WORKTREE_SCOPE_TEMPLATE.md) を使います。
- `WORKTREE_SCOPE.md` は worktree ごとに current state へ更新します。別 branch / 別 path の scope file を流用しません。
- branch の役割と carry-over 先を残したい場合は [BRANCH_SCOPE.md](/mnt/l/workspace/project_template/documents/BRANCH_SCOPE.md) と `notes/branches/` を使います。
- 例外運用中の action log は kickoff から `notes/worktrees/` に残します。
- action log の各 entry には、いま処理している `request_clause_ids=` を残します。
- scope 更新、編集開始、テスト実行、実験開始 / 停止、carry-over 判断は action log に逐次残します。repo-changing task では同じ step を run bundle `work_log.md` にも残します。
- scope が途中で変わったら、追加編集の前に `WORKTREE_SCOPE.md` と action log を更新します。
- `Editable Directories` 外と `Read-Only Or Avoid Directories` 内は編集しません。
- runtime output は `WORKTREE_SCOPE.md` に書いた場所へ限定します。
- closeout 前に `documents/notes-lifecycle.md` を見て、action log から knowledge/theme/failure へ昇格させる項目を決めます。
- file 構成変更を含む branch を閉じる前には、integration worktree 上で `python3 tools/ci/check_merge_structure.py ...` を通します。

## 閉じる前の確認

- `main` に戻すコード、文書、知見がそろっているか
- 不要な branch 専用メモを残していないか
- 例外運用で得たルールを正本へ反映したか
- `main` に持ち帰る note と最小 final JSON の置き場が決まっているか
- worktree を消したあとも `main` から関連 note と結果を辿れるか
