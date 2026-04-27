# agent-canon PR ワークフロー
<!--
@dependency-start
upstream implementation ../../tools/sync_agent_canon.sh sync implementation
upstream implementation ../../tools/ci/check_agent_canon_pr.sh PR gate implementation
downstream design ../../documents/agent-canon-subtree-migration.md subtree migration contract consumes PR workflow
downstream design derived-agent-canon-diff-workflow.md derived diff workflow consumes PR gates
@dependency-end
-->

この文書は、`vendor/agent-canon/` を source of truth とする shared canon 変更を PR に乗せるときの正本です。
template repo 側の branch、PR、merge、upstream `agent-canon` sync を 1 本の手順で扱います。

## 対象

- `vendor/agent-canon/` 配下の変更
- shared runtime surface を増減する変更
- `.github/workflows/agent-coordination.yml` のような synced root copy の変更
- `tools/sync_agent_canon.sh` の link / copy spec を変える変更
- workflow、skill、subagent、review policy、agent helper の変更

## 固定ルール

- shared canon の正本は `vendor/agent-canon/` です。
- root 側の symlink view や root copy を直接編集しません。
- shared canon 変更は dedicated branch と dedicated PR に分けます。
- shared canon 変更は dedicated commit に分けます。
- 派生 repo 由来の shared canon 差分は、まず repo 専用 proposal branch へ push して出所を分けます。
- 派生 repo 側の local diff、proposal branch、shared canon main、派生 repo snapshot を一連で閉じる場合は、先に `agents/workflows/derived-agent-canon-diff-workflow.md` で状態分類と closeout 順を固定します。
- shared surface を増減したら `bash tools/sync_agent_canon.sh link-root` を同じ pass で実行します。
- PR 前の validation は `make agent-canon-pr-check` を使います。
- file 構成変更を含む branch を `main` に戻すときは `agents/workflows/main-integration-workflow.md` を省略しません。
- template repo の PR merge と upstream `agent-canon` push は別 step です。merge 後に `bash tools/sync_agent_canon.sh push` を実行します。
- push が自然な次手なら、許可待ちの提案に戻らずそのまま実行します。止めるのは user stop か external block だけです。

## Branch ルール

- branch 名は `canon/<topic>-YYYYMMDD` を使います。
- 派生 repo から集める受け口 branch は `canon-proposal/<repo-slug>` を既定にします。
- shared canon 以外の implementation change と同じ branch に混ぜません。
- shared canon 変更と repo-local implementation change の両方が必要な場合は branch と PR を分けます。

## 標準手順

1. 派生 repo から proposal branch がある場合は先に取り込む

```bash
git fetch <derived-agent-canon-remote> canon-proposal/<repo-slug>
git checkout -b canon/<topic>-YYYYMMDD
git merge --no-ff FETCH_HEAD
```

2. `vendor/agent-canon/` 側を編集する

- workflow doc、skill、subagent、script は vendor 側の正本を編集します。
- root 側の symlink view は編集しません。

3. shared surface を再同期する

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

4. PR 前の validation を流す

```bash
make agent-canon-pr-check
```

この command は次をまとめて実行します。

- shared surface drift check
- `make agent-checks`
- `make docs-check`
- `make ci-quick`

5. commit を分ける

- `vendor/agent-canon/` と root copy / link spec の変更だけを commit します。
- unrelated change を同じ commit に混ぜません。

6. PR を作る

- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` を使います。
- 変更した surface、validation、upstream sync result または block reason を PR 本文に書きます。

7. merge する

- file 構成変更がある場合は integration worktree で merge します。
- `python3 tools/ci/check_merge_structure.py --source <branch> --target origin/main --compare-commit HEAD` を通します。

8. merge 後に upstream `agent-canon` を更新する

```bash
git checkout main
git pull --ff-only origin main
bash tools/sync_agent_canon.sh push
```

9. local working clone がある場合は fast-forward する

```bash
git -C /mnt/l/workspace/agent-canon pull --ff-only
```

## 派生 repo 側の shared canon 提案

派生 repo では、shared canon の差分を直接 `main` へ push しません。
repo ごとの proposal branch に積み、maintainer が整理用 branch へ merge します。
local history divergence や unsafe snapshot import で `ensure-latest` が止まった場合も、この proposal branch 経由で出所を固定してから shared canon main へ取り込み、派生 repo 側で `make agent-canon-ensure-latest` を再実行します。

```bash
bash tools/update_agent_canon.sh proposal-branch
bash tools/update_agent_canon.sh push-proposal
```

## PR 完了条件

次をすべて満たしたときだけ shared canon PR を完了扱いにします。

- `make agent-canon-pr-check` が pass
- root shared surface が `bash tools/sync_agent_canon.sh check` で clean
- PR 本文に changed surface と validation が記録されている
- file 構成変更がある場合は integration worktree merge と tree check が完了
- template `main` へ merge 後、`bash tools/sync_agent_canon.sh push` の実行結果、または external block / user stop による未実行理由が残っている

## 禁止事項

- root 側の symlink view を直接編集して shared canon 変更を close してはいけません。
- shared canon 変更を repo-local implementation change と同じ PR に混ぜてはいけません。
- `make agent-canon-pr-check` を省略して PR を close してはいけません。
- `vendor/agent-canon/` の構成変更を file 単位の拾い直しで `main` に戻してはいけません。
- template `main` merge 後に upstream `agent-canon` sync の有無を曖昧なままにしてはいけません。

## 使う入口

- `documents/SHARED_RUNTIME_SURFACES.md`
- `documents/agent-canon-subtree-migration.md`
- `agents/workflows/main-integration-workflow.md`
- `tools/sync_agent_canon.sh`
- `tools/ci/check_agent_canon_pr.sh`
- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`
