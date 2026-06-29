<!--
@dependency-start
contract workflow
responsibility Documents Derived Agent-Canon Diff Workflow for this repository.
upstream design ./agent-canon-pr-workflow.md defines shared canon PR gates
upstream design ../../documents/agent-canon-subtree-migration.md defines submodule migration and legacy subtree compatibility
upstream implementation ../../tools/sync_agent_canon.sh synchronizes shared canon submodule pins and root views
upstream implementation ../../tools/update_agent_canon.sh merges GitHub main into derived AgentCanon branches
downstream design ../canonical/CODEX_WORKFLOW.md routes diverged canon workflows
@dependency-end
-->

# Derived Agent-Canon Diff Workflow

この workflow は、template から作った派生 repo の `vendor/agent-canon/` submodule に差分があるときの入口です。
目的は、派生 repo の submodule worktree、AgentCanon GitHub branch、shared `agent-canon` main、派生 repo の parent gitlink を順番に揃え、shared canon 差分を未整理のまま残さないことです。

## この文書の読み方

- この文書は、派生 repo の `vendor/agent-canon/` 差分を shared canon PR、main 取り込み、派生 repo pin 更新へ戻す route を所有します。
- 前半は適用条件、固定ルール、状態固定、差分分類を扱い、後半は AgentCanon branch、shared canon main、派生 repo 復帰、template pin、validation、closeout を扱います。
- maintainer は `## Stage 0. 状態固定` と `## Stage 1. 差分分類` で route を決めてから、shared-canon candidate の場合だけ `Stage 2` 以降へ進みます。
- chunked reading では、現在の差分状態を stage 番号に対応させ、root view と submodule worktree の正本境界を同じ chunk で確認します。

## 適用条件

- `git status --short -- vendor/agent-canon` に差分がある
- `make agent-canon-ensure-latest` または `bash tools/sync_agent_canon.sh ensure-latest` が `diverged_submodule_history` / unsafe local submodule state で止まる
- 派生 repo で育った workflow、skill、subagent、tool、runtime entrypoint、shared note を shared canon へ戻したい
- root の symlink view / synced copy と `vendor/agent-canon/` のどちらを直すべきか判断が必要

## 固定ルール

- shared canon の正本は常に `vendor/agent-canon/` です。root symlink view を直接直して解決した扱いにしません。
- 派生 repo の shared canon 差分は、まず `vendor/agent-canon/` 内の named GitHub branch に commit します。
- `ensure-latest` が local divergence で止まった場合、local 差分を消して再試行せず、AgentCanon branch / PR で差分の行き先を決めます。
- `vendor/agent-canon/` が local checkout branch を指している場合、その branch は破棄対象ではありません。shared-canon candidate があるなら `merge-main-into-current-preserve-dirty` で GitHub `main` を取り込み、同じ branch を AgentCanon PR として進めます。`agent_canon_merge_remote_main_in_post_head=yes` と `agent_canon_merge_remote_main_verified=yes` が出ない branch は PR-ready と扱いません。
- shared canon main に取り込んだあとは、派生 repo 側で `make agent-canon-ensure-latest` を再実行し、submodule worktree HEAD と parent gitlink が shared canon main と同じ commit になるまで閉じません。
- template repo で作業している場合は、template `main`、template GitHub remote、parent gitlink 更新も completion evidence に含めます。
- closeout 前に `schedule.md`、`work_log.md`、validation、commit、push、AgentCanon branch、shared canon main、派生 repo parent gitlink の未完了項目が無いことを確認します。

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
| `already_current_submodule` | parent gitlink、submodule worktree、shared canon main が一致 | root drift だけなら `link-root` / `check` へ進む |
| `submodule_update` | shared canon main が進んでいる | AgentCanon update surface が repairable なら、親 repo の無関係な dirty state があっても `make agent-canon-ensure-latest` を実行し、parent pin commit を作る。unsafe な shared-canon 差分が同時にある場合は、先に AgentCanon branch / PR に出して merge 後に再実行する |
| `diverged_submodule_history` | local submodule commit と remote main が分岐 | `merge-main-into-current-preserve-dirty` で current branch に GitHub main を取り込み、conflict は submodule 内で解消して AgentCanon PR に出す |
| `already_current_tree` / `already_current_split` | legacy subtree 互換 mode で local tree と shared canon main が一致 | legacy appendix のみ。submodule repo では使わない |
| `snapshot_import_*` / `subtree_pull` | legacy subtree 互換 mode の update route | maintainer が legacy cleanup として扱い、通常の submodule repo には持ち込まない |

## Stage 1. 差分分類

`vendor/agent-canon/` 差分を 3 種類に分けます。

- shared-canon candidate: workflow、skill、subagent、runtime entrypoint、shared tool、shared validation、shared memory / note template に属する変更
- derived-repo local wrapper: project 固有 README、implementation、environment、experiment、repo-local note に留めるべき変更
- accidental drift: root symlink view の直接編集、生成物、backup、dated snapshot、旧 path、copy surface の不一致

判断に迷う場合は、`documents/agent-canon-subtree-migration.md` と `documents/SHARED_RUNTIME_SURFACES.md` の ownership を優先します。
accidental drift は `bash tools/sync_agent_canon.sh link-root` で復元し、shared-canon candidate と local wrapper を同じ commit に混ぜません。

## Stage 2. AgentCanon Branch へ渡す

shared-canon candidate がある場合は、派生 repo から直接 shared canon main を更新しません。
current `vendor/agent-canon/` branch に GitHub main を取り込み、その branch を GitHub へ push して AgentCanon PR を作ります。
この current branch が local checkout 由来でも、それは通常の merge 対象です。消して作り直すのではなく、
GitHub `main` を merge して conflict を解き、branch history を PR に載せます。
merge 後の evidence には少なくとも `agent_canon_merge_source_sha`、
`agent_canon_merge_post_head`、`agent_canon_merge_remote_main_in_post_head=yes`、
`agent_canon_merge_remote_main_verified=yes` を残します。

```bash
bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty
git -C vendor/agent-canon push origin HEAD
```

push 前に submodule worktree が dirty なら submodule 内で commit するか、shared canon candidate だけを dedicated branch / commit に分けます。
parent repo の root view や gitlink 変更だけを commit しても AgentCanon PR には乗りません。必ず `vendor/agent-canon/` 内の HEAD、status、target branch を evidence に残します。

## Stage 3. Shared Canon Main へ取り込む

maintainer 側では `agents/workflows/agent-canon-pr-workflow.md` を primary maintenance workflow とし、通常の GitHub PR review / merge で shared canon main へ取り込みます。
内容の取捨選択が必要なら、AgentCanon PR branch で通常の file-level review と `make agent-canon-pr-check` を通します。

## Stage 4. 派生 Repo を Shared Canon Main へ戻す

shared canon main へ取り込んだあと、派生 repo は submodule worktree と parent gitlink を canonical main へ戻します。

```bash
make agent-canon-ensure-latest
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

`ensure-latest` が `already_current_submodule` または `submodule_update` を返すことを evidence に残します。
parent gitlink commit が作られた場合は、その commit も派生 repo 側の required delivery に含めます。

## Stage 5. Template Pin を閉じる

template repo で作業している場合は、shared canon main と template parent gitlink の両方を更新してから完了します。

```bash
git status --short
make agent-canon-ensure-latest
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
make agent-canon-pr-check
make ci
python3 tools/agent_tools/github_publish.py push \
  --user-task "publish derived AgentCanon parent gitlink update" \
  --repo iwashita-nozomu/project_template \
  --branch main \
  --allow-main
```

template bare remote を使う環境では、`origin/main` が current commit を指すことも確認します。
fresh clone smoke がある場合は、更新後の remote から `--recurse-submodules` で clone し、skill mirror と `make agent-canon-ensure-latest` の entrypoint が壊れていないことを確認します。

## Validation

最低限、次を実行して evidence に残します。

```bash
bash tools/sync_agent_canon.sh check
python3 tools/agent_tools/check_dependency_headers.py --changed
bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing
bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header
make agent-checks
tools/bin/agent-canon docs check
make ci-quick
```

dependency edge を追加・変更した shared canon PR では、次を追加して graph semantics を確認します。

```bash
bash tools/agent_tools/check_dependency_graph.sh --print-edges
```

移行期間中に既存 full-repo graph failure が残る場合は、failure を `work_log.md` と `closeout_gate.md` に baseline として記録し、今回の差分が新しい旧形式 header、自己参照、reverse edge 欠落、kind mismatch、cycle を増やしていないことを review artifact に残します。

shared canon PR または template parent gitlink 更新では、`make agent-canon-pr-check` を追加します。
repo 全体の runtime 影響がある場合、または template pin を更新する場合は `make ci` を closeout gate にします。

## Closeout Checklist

- `user_request_contract.md` の active clause がすべて resolved
- `schedule.md` の planned work unit がすべて complete
- `work_log.md` に AgentCanon branch push、shared canon main update、派生 repo parent gitlink update、validation、commit、push が記録済み
- `bash tools/sync_agent_canon.sh check` が pass
- `make agent-canon-ensure-latest` が pass し、submodule worktree HEAD と parent gitlink が shared canon main と一致
- AgentCanon branch push 先と shared canon main の commit が evidence に記録済み
- template repo では `origin/main` と shared canon main の更新が evidence に記録済み
- non-canonical draft、backup copy、dated snapshot、旧 root surface 参照が tracked tree に残っていない
- `closeout_gate.md` が `unfinished_tasks_absent=yes`、`dependency_headers_complete=yes`、`mechanical_completion_loop_complete=yes`、`diff_check_agent_complete=yes`、`user_completion_report=unlocked`
- run-local diff-check artifact が現在 tracked diff ref の read-only independent approval と findings disposition を示している

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
