# Derived Agent-Canon Diff Workflow

<!--
@dependency-start
upstream design ./agent-canon-pr-workflow.md defines shared canon PR gates
upstream design ../../documents/agent-canon-subtree-migration.md defines subtree migration contract
upstream implementation ../../tools/sync_agent_canon.sh synchronizes shared canon snapshots
upstream implementation ../../tools/update_agent_canon.sh pushes canon proposal branches
downstream design ../canonical/CODEX_WORKFLOW.md routes diverged canon workflows
@dependency-end
-->

この workflow は、template から作った派生 repo の `vendor/agent-canon/` に差分があるときの入口です。
目的は、派生 repo の local snapshot、repo 専用 proposal branch、shared `agent-canon` main、派生 repo の current tree head を順番に揃え、shared canon 差分を未整理のまま残さないことです。

## 適用条件

- `git status --short -- vendor/agent-canon` に差分がある
- `make agent-canon-ensure-latest` または `bash tools/sync_agent_canon.sh ensure-latest` が `diverged_local_history` / unsafe snapshot import で止まる
- 派生 repo で育った workflow、skill、subagent、tool、runtime entrypoint、shared note を shared canon へ戻したい
- root の symlink view / synced copy と `vendor/agent-canon/` のどちらを直すべきか判断が必要

## 固定ルール

- shared canon の正本は常に `vendor/agent-canon/` です。root symlink view を直接直して解決した扱いにしません。
- 派生 repo の shared canon 差分は、まず repo 専用 proposal branch に push します。既定 branch は `canon-proposal/<repo-slug>` です。
- `ensure-latest` が local divergence で止まった場合、local 差分を消して再試行せず、proposal branch push または maintainer merge で差分の行き先を決めます。
- shared canon main に取り込んだあとは、派生 repo 側で `make agent-canon-ensure-latest` を再実行し、snapshot が shared canon main と同じ tree になるまで閉じません。
- template repo で作業している場合は、template `main` と template bare remote の snapshot 更新も completion evidence に含めます。
- closeout 前に `schedule.md`、`work_log.md`、validation、commit、push、proposal branch、shared canon main、派生 repo snapshot の未完了項目が無いことを確認します。

## Stage 0. 状態固定

作業開始時に、run bundle の user request clause と TODO 正本を先に作ります。
その後、read-only command で差分の種類を記録します。

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "handle derived agent-canon diff" \
  --task-id T1 \
  --owner "codex" \
  --workspace-root "$PWD"

bash tools/update_agent_canon.sh plan
bash tools/sync_agent_canon.sh status
git status --short -- vendor/agent-canon .github/workflows .github/PULL_REQUEST_TEMPLATE
git diff --stat -- vendor/agent-canon .github/workflows .github/PULL_REQUEST_TEMPLATE
```

`plan` の route を次のように扱います。

| Route | Meaning | Required Next Step |
| ----- | ------- | ------------------ |
| `already_current_tree` / `already_current_split` | local snapshot と shared canon main が一致 | root drift だけなら `link-root` / `check` へ進む |
| `local_contains_remote` | 派生 repo に shared canon 候補がある | proposal branch へ push する |
| `subtree_pull` / `snapshot_import_*` | shared canon main が進んでいる | clean worktree にして `ensure-latest` する |
| `diverged_local_history` | 双方に履歴差分がある | proposal branch push と maintainer merge を先に行う |
| `snapshot_import_unsafe_tree_not_in_remote` | local tree が shared canon history に無い | proposal branch push か明示破棄判断まで停止する |

## Stage 1. 差分分類

`vendor/agent-canon/` 差分を 3 種類に分けます。

- shared-canon candidate: workflow、skill、subagent、runtime entrypoint、shared tool、shared validation、shared memory / note template に属する変更
- derived-repo local wrapper: project 固有 README、implementation、environment、experiment、repo-local note に留めるべき変更
- accidental drift: root symlink view の直接編集、生成物、backup、dated snapshot、旧 path、copy surface の不一致

判断に迷う場合は、`documents/agent-canon-subtree-migration.md` と `documents/SHARED_RUNTIME_SURFACES.md` の ownership を優先します。
accidental drift は `bash tools/sync_agent_canon.sh link-root` で復元し、shared-canon candidate と local wrapper を同じ commit に混ぜません。

## Stage 2. Proposal Branch へ渡す

shared-canon candidate がある場合は、派生 repo から直接 shared canon main を更新しません。
repo 専用 proposal branch を確認し、その branch へ current `vendor/agent-canon/` snapshot を push します。

```bash
bash tools/update_agent_canon.sh proposal-branch
bash tools/update_agent_canon.sh push-proposal
```

push 前に worktree が dirty なら commit するか、shared canon candidate だけを dedicated branch / commit に分けます。
`push-proposal` は `git subtree push --prefix=vendor/agent-canon` を使うため、未コミット差分は proposal に乗りません。

## Stage 3. Shared Canon Main へ取り込む

maintainer 側では `agents/workflows/agent-canon-pr-workflow.md` を primary maintenance workflow とし、proposal branch を整理用 branch へ取り込みます。

```bash
git fetch <derived-agent-canon-remote> canon-proposal/<repo-slug>
git checkout -b canon/<topic>-YYYYMMDD agent-canon/main
git merge --no-ff FETCH_HEAD
make agent-canon-pr-check
```

remote main と proposal branch の履歴が related なら通常 merge します。
履歴が diverge していても tree と出所を保持する必要がある場合は、proposal snapshot の tree を使い、shared canon main と proposal の両方を parent に持つ merge commit を作ります。

```bash
git fetch agent-canon main canon-proposal/<repo-slug>
tree_sha="$(git rev-parse agent-canon/canon-proposal/<repo-slug>^{tree})"
merge_sha="$(
  printf '%s\n' "Merge derived agent-canon proposal" |
    git commit-tree "$tree_sha" \
      -p agent-canon/main \
      -p agent-canon/canon-proposal/<repo-slug>
)"
git push agent-canon "$merge_sha:refs/heads/main"
```

この fallback は、proposal の tree を shared canon main に採用する判断が明示済みの場合だけ使います。
内容の取捨選択が必要なら、整理用 branch で通常の file-level review と `make agent-canon-pr-check` を通します。

## Stage 4. 派生 Repo を Shared Canon Main へ戻す

shared canon main へ取り込んだあと、派生 repo は current tree head を canonical snapshot に戻します。

```bash
make agent-canon-ensure-latest
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

`ensure-latest` が `already_current_tree` または `already_current` を返すことを evidence に残します。
snapshot import / subtree pull で commit が作られた場合は、その commit も派生 repo 側の required delivery に含めます。

## Stage 5. Template Snapshot を閉じる

template repo で作業している場合は、shared canon main と template snapshot の両方を更新してから完了します。

```bash
git status --short
make agent-canon-pr-check
make ci
git push origin main
bash tools/update_agent_canon.sh push-proposal
make agent-canon-ensure-latest
```

template bare remote を使う環境では、`origin/main` が current commit を指すことも確認します。
fresh clone smoke がある場合は、更新後の bare remote から clone し、skill mirror と `make agent-canon-ensure-latest` の entrypoint が壊れていないことを確認します。

## Validation

最低限、次を実行して evidence に残します。

```bash
bash tools/sync_agent_canon.sh check
python3 tools/agent_tools/check_dependency_headers.py --changed
bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing
bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header
python3 tools/docs/mirror_skill_shims.py --target .claude/skills --prune --check
make agent-checks
make docs-check
make ci-quick
```

dependency edge を追加・変更した shared canon PR では、次を追加して graph semantics を確認します。

```bash
bash tools/agent_tools/check_dependency_graph.sh --print-edges
```

移行期間中に既存 full-repo graph failure が残る場合は、failure を `work_log.md` と `closeout_gate.md` に baseline として記録し、今回の差分が新しい旧形式 header、自己参照、reverse edge 欠落、kind mismatch、cycle を増やしていないことを review artifact に残します。

shared canon PR または template snapshot 更新では、`make agent-canon-pr-check` を追加します。
repo 全体の runtime 影響がある場合、または template snapshot を更新する場合は `make ci` を closeout gate にします。

## Closeout Checklist

- `user_request_contract.md` の active clause がすべて resolved
- `schedule.md` の planned work unit がすべて complete
- `work_log.md` に proposal push、shared canon main update、派生 repo snapshot update、validation、commit、push が記録済み
- `bash tools/sync_agent_canon.sh check` が pass
- `make agent-canon-ensure-latest` が pass し、local snapshot が shared canon main と一致
- proposal branch の push 先と shared canon main の commit が evidence に記録済み
- template repo では `origin/main` と shared canon main の更新が evidence に記録済み
- non-canonical draft、backup copy、dated snapshot、旧 root surface 参照が tracked tree に残っていない
- `closeout_gate.md` が `unfinished_tasks_absent=yes`、`dependency_headers_complete=yes`、`user_completion_report=unlocked`
