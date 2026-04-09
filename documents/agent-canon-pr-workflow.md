# agent-canon PR ワークフロー

この文書は、`vendor/agent-canon/` を source of truth とする shared canon 変更を PR に乗せるときの正本です。
template repo 側の branch、PR、merge、upstream `agent-canon` sync を 1 本の手順で扱います。

## 対象

- `vendor/agent-canon/` 配下の変更
- shared runtime surface を増減する変更
- `.github/workflows/agent-coordination.yml` のような synced root copy の変更
- `scripts/sync_agent_canon.sh` の link / copy spec を変える変更
- workflow、skill、subagent、review policy、agent helper の変更

## 固定ルール

- shared canon の正本は `vendor/agent-canon/` です。
- root 側の symlink view や root copy を直接編集しません。
- shared canon 変更は dedicated branch と dedicated PR に分けます。
- shared canon 変更は dedicated commit に分けます。
- shared surface を増減したら `bash scripts/sync_agent_canon.sh link-root` を同じ pass で実行します。
- PR 前の validation は `make agent-canon-pr-check` を使います。
- file 構成変更を含む branch を `main` に戻すときは `documents/main-integration-workflow.md` を省略しません。
- template repo の PR merge と upstream `agent-canon` push は別 step です。merge 後に `bash scripts/sync_agent_canon.sh push` を実行します。

## Branch ルール

- branch 名は `canon/<topic>-YYYYMMDD` を使います。
- shared canon 以外の implementation change と同じ branch に混ぜません。
- shared canon 変更と repo-local implementation change の両方が必要な場合は branch と PR を分けます。

## 標準手順

1. branch を切る

```bash
git checkout -b canon/<topic>-YYYYMMDD
```

2. `vendor/agent-canon/` 側を編集する

- workflow doc、skill、subagent、script は vendor 側の正本を編集します。
- root 側の symlink view は編集しません。

3. shared surface を再同期する

```bash
bash scripts/sync_agent_canon.sh link-root
bash scripts/sync_agent_canon.sh check
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
- 変更した surface、validation、upstream sync plan を PR 本文に書きます。

7. merge する

- file 構成変更がある場合は integration worktree で merge します。
- `python3 scripts/ci/check_merge_structure.py --source <branch> --target origin/main --compare-commit HEAD` を通します。

8. merge 後に upstream `agent-canon` を更新する

```bash
git checkout main
git pull --ff-only origin main
bash scripts/sync_agent_canon.sh push
```

9. local working clone がある場合は fast-forward する

```bash
git -C /mnt/l/workspace/agent-canon pull --ff-only
```

## PR 完了条件

次をすべて満たしたときだけ shared canon PR を完了扱いにします。

- `make agent-canon-pr-check` が pass
- root shared surface が `bash scripts/sync_agent_canon.sh check` で clean
- PR 本文に changed surface と validation が記録されている
- file 構成変更がある場合は integration worktree merge と tree check が完了
- template `main` へ merge 後、`bash scripts/sync_agent_canon.sh push` の実行計画または実行結果が残っている

## 禁止事項

- root 側の symlink view を直接編集して shared canon 変更を close してはいけません。
- shared canon 変更を repo-local implementation change と同じ PR に混ぜてはいけません。
- `make agent-canon-pr-check` を省略して PR を close してはいけません。
- `vendor/agent-canon/` の構成変更を file 単位の拾い直しで `main` に戻してはいけません。
- template `main` merge 後に upstream `agent-canon` sync の有無を曖昧なままにしてはいけません。

## 使う入口

- `documents/SHARED_RUNTIME_SURFACES.md`
- `documents/agent-canon-subtree-migration.md`
- `documents/main-integration-workflow.md`
- `scripts/sync_agent_canon.sh`
- `scripts/ci/check_agent_canon_pr.sh`
- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`
