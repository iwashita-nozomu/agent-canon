# agent-canon PR ワークフロー
<!--
@dependency-start
responsibility Documents agent-canon PR ワークフロー for this repository.
upstream implementation ../../tools/sync_agent_canon.sh sync implementation
upstream implementation ../../tools/update_agent_canon.sh tool-first latest update and conflict handoff
upstream implementation ../../tools/ci/check_agent_canon_pr.sh PR gate implementation
upstream implementation ../../tools/ci/check_github_workflows.py GitHub workflow and PR checklist gate
upstream implementation ../../tools/agent_tools/tool_drift.py tool/convention trace gate
upstream implementation ../../tools/agent_tools/responsibility_scope.py responsibility scope gate
upstream implementation ../../tools/agent_tools/issue_sync.py local/GitHub issue sync gate
upstream implementation ../../tools/agent_tools/eval_accumulation_check.py eval accumulation gate
upstream implementation ../../tools/agent_tools/local_llm_eval.py local LLM responsibility eval gate
upstream design ../../tools/catalog.yaml structured tool catalog
upstream design ../../issues/README.md durable operational finding storage
upstream design ../../documents/dependency-manifest-design.md dependency graph and search-to-edit-scope evidence
upstream design ../../documents/agent-canon-github-remote.md defines canonical remote evidence
upstream design ../../documents/template-github-remote.md defines template remote evidence
downstream design derived-agent-canon-diff-workflow.md derived diff workflow consumes PR gates
@dependency-end
-->

この文書は、AgentCanon source change と template submodule pin change を PR に乗せるときの正本です。
standalone AgentCanon repo、template repo 側の branch、PR、merge、submodule pin 更新を 1 本の手順で扱います。

## 対象

- `vendor/agent-canon/` 配下の変更
- shared runtime surface を増減する変更
- `.github/workflows/agent-coordination.yml` のような synced root copy の変更
- `tools/sync_agent_canon.sh` の link / copy spec を変える変更
- workflow、skill、subagent、review policy、agent helper の変更

## 固定ルール

- shared canon の正本は standalone AgentCanon repo です。template 内で作業する場合は `vendor/agent-canon/` submodule worktree がその working copy になります。
- GitHub 上の canonical shared canon repo は `https://github.com/iwashita-nozomu/agent-canon.git` です。
- template の canonical repo は `https://github.com/iwashita-nozomu/project_template.git` です。
- template を GitHub 管理にする場合は、`.gitmodules` の AgentCanon URL を canonical GitHub URL にし、local bare mirror は別名 remote または明示 override として残します。
- root 側の symlink view や root copy を直接編集しません。
- shared canon 変更は dedicated branch と dedicated PR に分けます。
- shared canon 変更は dedicated commit に分けます。
- repo-local tool を AgentCanon に集約する変更は、原則 PR で行い、今回のような direct update は user が明示した特例だけにします。
- 派生 repo 由来の shared canon 差分は、`vendor/agent-canon/` 内の normal GitHub branch と AgentCanon PR に分けます。
- 派生 repo 側の local diff、AgentCanon branch、shared canon main、派生 repo submodule pin を一連で閉じる場合は、先に `agents/workflows/derived-agent-canon-diff-workflow.md` で状態分類と closeout 順を固定します。
- shared surface を増減したら `bash tools/sync_agent_canon.sh link-root` を同じ pass で実行します。
- standalone AgentCanon repo では Makefile 前提を置かず、下の explicit validation commands を使います。
- template / derived repo では `make agent-canon-pr-check` を使います。
- `make agent-canon-pr-check` は GitHub mirror / submodule / security evidence も出します。`AGENT_CANON_GITHUB_REPO` と `TEMPLATE_GITHUB_REPO` で repository name を上書きできます。
- file 構成変更を含む branch を `main` に戻すときは `agents/workflows/main-integration-workflow.md` を省略しません。
- AgentCanon source commit / PR と template parent gitlink commit / PR は別 step です。AgentCanon main を先に更新し、その後 template 側で `make agent-canon-ensure-latest`、`bash tools/sync_agent_canon.sh link-root`、template pin commit を作ります。
- push が自然な次手なら、許可待ちの提案に戻らずそのまま実行します。止めるのは user stop か external block だけです。
- PR state の inspect、PR 作成、owned branch push、PR title/body 更新、evidence comment 追加、draft 化は workflow の一部として実行できます。merge、close、ready-for-review、reviewer request、review dismissal、auto-merge、branch deletion、failing check bypass は user の current-task 明示許可または tracked maintainer policy が無い限り実行しません。
- tool addition、tool behavior change、memory addition、agent-learning update、skill eval result、feedback-loop change は standalone AgentCanon branch / PR の対象です。template / derived repo の pin PR だけで close しません。
- user、reviewer、runtime、CI が workflow defect を露出した場合は、run bundle だけでなく `issues/`、`memory/`、または `notes/failures/` に durable record を残します。
- PR / branch push では `.github/workflows/agent-improvement-guide.yml` が memory、skill eval、hook result、issues を読み、read-only improvement guide artifact を生成します。実際の skill / workflow / tool 修正は local Agent または Copilot PR が別 branch で行います。
- standalone AgentCanon PR / branch push では `.github/workflows/agent-canon-static-gates.yml` が tool catalog、tool drift、dependency review、GitHub workflow convention、container config を軽量 gate として走らせます。local の `make agent-canon-pr-check` は引き続き merge 前の広い gate です。

## Freshness Gate Route

`check_agent_canon_latest.sh` や `make agent-canon-pr-check` が dirty shared-canon 差分を理由に止まった場合、その失敗は「pin を更新して消す」合図ではなく、PR-first route へ入る合図です。

通常の parent repo 最新化は、まず tool に任せます。

```bash
make agent-canon-update-plan
make agent-canon-latest
```

`make agent-canon-latest` は safe な AgentCanon `main` 更新、root view check、
親 repo update TODO acknowledge まで進めます。local shared-canon branch、dirty
submodule、diverged history、merge conflict がある場合は、その場で破壊的に直さず
`AGENT_CANON_LATEST_WORKFLOW=agents/workflows/derived-agent-canon-diff-workflow.md`、
`AGENT_CANON_LATEST_CONFLICT_COMMAND=bash tools/update_agent_canon.sh merge-main-into-current`、
`NEXT_ACTION=run_agentcanon_conflict_workflow` を出します。この出力を見た parent agent は
AgentCanon conflict workflow に入り、branch commit、merge-main、PR、post-merge latest を
順に処理します。

local checkout branch に shared-canon commit がある場合、その checkout は merge してよい
正規の AgentCanon PR 入力です。親 repo の gitlink を戻したり、submodule を remote
main へ checkout し直して差分を消すのではなく、current branch に GitHub `main` を
merge し、conflict を submodule 内で解消してから同じ branch を PR に出します。
この merge は任意の自己申告ではなく、`merge-main-into-current` が
`agent_canon_merge_remote_main_in_post_head=yes` と
`agent_canon_merge_remote_main_verified=yes` を出すことで保証します。

扱いは次の順に固定します。

1. `vendor/agent-canon/` の shared canon 差分を dedicated branch / commit に分ける
1. 派生 repo 起点なら `bash tools/update_agent_canon.sh merge-main-into-current` を通してから AgentCanon branch を GitHub へ push する
1. standalone AgentCanon repo へ PR を作り、merge する
1. template / derived repo 側で `make agent-canon-ensure-latest` を再実行する
1. `bash tools/sync_agent_canon.sh link-root` と `bash tools/sync_agent_canon.sh check` を通す
1. parent gitlink / root shared surface commit を AgentCanon source PR とは別に作る

pre-merge の AgentCanon source PR では、standalone validation command を正本にします。
post-merge の template / derived pin PR では、`make agent-canon-pr-check` が pass することを正本にします。

## Issues / Findings Gate

AgentCanon PR の前に、運用 finding を durable storage に残すかを必ず判断します。
この gate は「今から思い出して書く」作業ではなく、PR 作成時に機械的に確認する source-of-truth check です。

1. Durable surfaces を検索する

```bash
rg -n "topic keywords" \
  issues/open issues/closed memory notes/failures documents agents \
  2>/dev/null || true
```

template / derived repo から作業している場合は、`vendor/agent-canon/` prefix 付きで同じ surface を検索します。
run bundle は補助 evidence であり、durable storage の代替ではありません。

2. Raw search hit を dependency edit scope に展開する

```bash
rg -l "topic keywords" > reports/search_hits.txt
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --search-hits-file reports/search_hits.txt
```

`dependency_edit_scope.txt` の `DEPENDENCY_EDIT_SCOPE_PATH` を、issue または PR body の edit-scope evidence に残します。
raw `rg` hit だけで「どの file を編集・確認するか」を決めません。

3. 新しい workflow defect がある場合は issue file を作る

```text
issues/open/AC-YYYYMMDD-short-slug.md
```

issue file は `issues/README.md` の required fields を持ちます。
finding の粒度は、affected surfaces と dependency-expanded edit scope を書ける大きさまで分割します。

4. PR template に issue status を書く

- standalone AgentCanon repo では `.github/PULL_REQUEST_TEMPLATE.md` の `Operational Findings / Issues` に記入します。
- template / derived repo では `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` の `Operational Findings / Issues` に記入します。
- 新規 durable finding が不要な場合は、検索した surface と不要判断の理由を PR body に書きます。
- `python3 tools/agent_tools/issue_sync.py` を実行し、GitHub mirror が未作成の local issue は `ISSUE_SYNC_PLAN=` を PR body に貼るか、明示的に defer します。
- GitHub Actions の Agent Improvement Guide がある場合は、その artifact / step summary を確認し、memory、eval、hook、issues 由来の改善候補を PR body に反映します。

## Branch ルール

- branch 名は `canon/<topic>-YYYYMMDD` を使います。
- 派生 repo から始まる branch も GitHub 上の normal branch として扱い、`canon-pr/<topic>` または `canon/<topic>-YYYYMMDD` に寄せます。
- shared canon 以外の implementation change と同じ branch に混ぜません。
- shared canon 変更と repo-local implementation change の両方が必要な場合は branch と PR を分けます。

## 標準手順

1. AgentCanon source worktree または `vendor/agent-canon/` branch を編集する

- workflow doc、skill、subagent、script は standalone AgentCanon repo、または template 内の `vendor/agent-canon/` submodule worktree を編集します。
- root 側の symlink view は編集しません。
- tool addition、memory addition、skill eval result、feedback loop change はこの source worktree 側で commit し、template pin PR だけには閉じ込めません。

3. shared surface を再同期する

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

4. PR 前の validation を流す

standalone AgentCanon repo:

```bash
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing
python3 tools/agent_tools/tool_catalog.py
python3 tools/agent_tools/tool_drift.py
python3 tools/agent_tools/responsibility_scope.py
python3 tools/agent_tools/issue_sync.py
python3 tools/agent_tools/eval_accumulation_check.py
python3 tools/agent_tools/local_llm_eval.py
python3 tools/ci/check_github_workflows.py
bash tools/ci/run_docs_checks.sh
bash tools/ci/run_all_checks.sh --quick
```

template / derived repo:

```bash
make agent-canon-pr-check
```

template / derived repo でこの段階の `make agent-canon-pr-check` が `AGENT_CANON_LATEST_NEXT_ACTION=commit_agentcanon_branch_then_open_agent-canon_PR_then_after_merge_run_make_agent-canon-ensure-latest` を出した場合は、failure を PR-first handoff evidence として扱います。
そのまま pin を戻したり `sync_agent_canon.sh push` で bypass せず、AgentCanon PR merge 後にこの check を再実行します。

`make agent-canon-pr-check` は次をまとめて実行します。

- shared surface drift check
- agent runtime checks
- `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`
- `python3 tools/agent_tools/tool_catalog.py`
- `python3 tools/agent_tools/tool_drift.py`
- `python3 tools/agent_tools/responsibility_scope.py`
- `python3 tools/agent_tools/issue_sync.py`
- `python3 tools/agent_tools/eval_accumulation_check.py`
- `python3 tools/agent_tools/local_llm_eval.py`
- `python3 tools/ci/check_github_workflows.py`
- docs checks
- quick CI

5. commit を分ける

- AgentCanon source commit と template parent gitlink / root copy commit を分けます。
- template 側では `vendor/agent-canon` の gitlink、`.gitmodules`、root copy / link spec の変更だけを commit します。
- unrelated change を同じ commit に混ぜません。

6. PR を作る

- standalone AgentCanon repo へ shared canon source change を出す PR では `.github/PULL_REQUEST_TEMPLATE.md` を使います。
- template / derived repo 側で `vendor/agent-canon/` の pin、root copy、または shared surface を変える PR では `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` を使います。
- 変更した surface、validation、upstream sync result または block reason を PR 本文に書きます。
- issue file または durable finding 不要判断、dependency-expanded edit scope、tool / memory / eval route を PR 本文に書きます。
- standalone AgentCanon PR で GitHub CLI を使える場合は `gh pr create --base main --head <branch> --template .github/PULL_REQUEST_TEMPLATE.md` を使います。
- template / derived repo の AgentCanon PR で GitHub CLI を使える場合は `gh pr create --base main --head <branch> --template .github/PULL_REQUEST_TEMPLATE/agent_canon.md` を使います。
- default template / repo-local PR では `gh pr create --base main --head <branch> --template .github/PULL_REQUEST_TEMPLATE.md` を使います。
- `goal.md` が `pr_mutation_authority: github_copilot_merge_when_green`
  を持つ場合、PR body の `Copilot / Automation Output` に authority と
  `gh pr checks` summary を残し、merge は GitHub-hosted Copilot / PR
  automation の visible evidence に委譲します。

7. merge する

- `gh` / GitHub MCP が使えることは、PR 状態確認と PR body / evidence 更新の許可です。merge / close / ready-for-review / reviewer request / auto-merge は、current task で user がその mutation を明示した場合だけ実行します。
- `github_copilot_merge_when_green` は GitHub-hosted Copilot / PR automation
  にだけ merge authority を渡します。local Codex は
  `COPILOT_PR_AUTHORITY`、`COPILOT_PR_DECISION`、`COPILOT_PR_CHECKS`、
  `COPILOT_VISIBLE_EVIDENCE`、`COPILOT_BLOCKER` が PR-visible surface に
  出るまで merge 完了扱いにせず、自分では merge しません。
- 明示許可が無い場合は、merge 可能でも PR body、run bundle、または `goal.md` に "blocked on PR mutation authority" と残して止めます。
- file 構成変更がある場合は integration worktree で merge します。
- `python3 tools/ci/check_merge_structure.py --source <branch> --target origin/main --compare-commit HEAD` を通します。

8. merge 後に template pin を更新する

```bash
git checkout main
git pull --ff-only origin main
make agent-canon-ensure-latest
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

`make agent-canon-ensure-latest` rebuilds compiled AgentCanon tools after the
pin update. If it reports `AGENT_CANON_TOOL_REBUILD_RUST=skipped_missing_cargo`,
rerun `make agent-canon-rebuild-tools` inside the DevContainer before relying
on Rust-backed `agent-canon` CLI behavior.

9. local working clone がある場合は fast-forward する

```bash
git -C /mnt/l/workspace/agent-canon pull --ff-only
```

## 派生 repo 側の shared canon 提案

派生 repo では、shared canon の差分を直接 `main` へ push しません。
normal AgentCanon branch に積み、AgentCanon PR で review / merge します。
local submodule divergence や unsafe local submodule state で `ensure-latest` が止まった場合も、この branch 経由で出所を固定してから shared canon main へ取り込み、派生 repo 側で `make agent-canon-ensure-latest` を再実行します。

```bash
bash tools/update_agent_canon.sh merge-main-into-current
git -C vendor/agent-canon push origin HEAD
```

## Repo-Local Tool Collection PR

Derived repositories often grow local scripts before they are ready for shared
canon. Collect them by PR with this sequence:

1. Inventory `tools/`, `scripts/`, `tests/tools/`, `documents/tools/`, and
   result/log/report helpers in the derived repo.
1. Compare each candidate with current AgentCanon; do not overwrite newer
   canonical tools with stale repo-local copies.
1. Promote repo-neutral tools into the nearest canonical family under
   `tools/agent_tools/`, `tools/ci/`, `tools/docs/`, `tools/data/`,
   `tools/hlo/`, `tools/audit/`, `tools/experiments/`, `tools/oop/`, or
   `tools/validation/`.
1. Keep project-specific or unsafe tools in the derived source repository, or
   delete them after review. Do not create new `tools/legacy/` paths in
   AgentCanon.
1. Update `documents/repo-local-tool-imports.md`,
   `documents/tools/README.md`, `documents/tools/tool-docs.toml`,
   `tools/README.md`, and `tools/catalog.yaml`.
1. Add or update smoke tests, help checks, or static checks before wiring a new
   tool into default CI.
1. Run the standalone explicit validation commands or `make agent-canon-pr-check`
   in template / derived repos, and include the import disposition table in the
   PR body.

Direct updates must still leave the same evidence in the commit and run bundle.

## PR Body Examples

### AgentCanon Pin-Only Update

```text
Summary:
- Updated template vendor/agent-canon pin only.

Validation:
- bash tools/sync_agent_canon.sh check: pass
- make agent-checks: pass
- make ci: pass

AgentCanon Evidence:
- AgentCanon GitHub SHA: <sha>
- template submodule SHA: <sha>
- .gitmodules reviewed: unchanged
```

### AgentCanon Source Change Plus Template Pin

```text
Summary:
- Changed AgentCanon source under vendor/agent-canon.
- Advanced template submodule pin after AgentCanon main was updated.

Validation:
- bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing: pass
- python3 tools/agent_tools/tool_catalog.py: pass
- python3 tools/agent_tools/tool_drift.py: pass
- python3 tools/ci/check_github_workflows.py: pass
- make ci: pass

Propagation:
- AgentCanon commit / PR: <url-or-sha>
- Template commit / PR: <url-or-sha>
- local bare mirror: not used, or compatibility-only evidence recorded
```

### Root-Only Template Workflow Change

```text
Summary:
- Changed template-local GitHub Actions or PR checklist.

Scope:
- No vendor/agent-canon source change.
- vendor/agent-canon pin unchanged because the change is template-local.

Validation:
- python3 tools/ci/check_github_workflows.py: pass
- make docs-check: pass
- make ci: pass
```

### Copilot-Only Instruction Change

```text
Summary:
- Updated .github/copilot-instructions.md routing text only.

Read packet:
- AGENTS.md
- agents/README.md
- agents/workflows/github-copilot-workflow.md

Validation:
- python3 tools/ci/check_github_workflows.py: pass
- bash tools/sync_agent_canon.sh check: pass
```

## PR 完了条件

次をすべて満たしたときだけ shared canon PR を完了扱いにします。

- standalone AgentCanon repo では explicit validation commands が pass、template / derived repo では `make agent-canon-pr-check` が pass
- root shared surface が `bash tools/sync_agent_canon.sh check` で clean
- PR 本文に changed surface と validation が記録されている
- PR 本文に `issues/` durable finding、または durable finding 不要判断と検索 evidence が記録されている
- PR 本文に search-to-edit-scope evidence、または search-to-edit-scope 不要判断が記録されている
- PR 本文に template PR、AgentCanon PR または commit、submodule pin、GitHub `main` SHA、security check 状態が記録されている
- file 構成変更がある場合は integration worktree merge と tree check が完了
- AgentCanon main へ merge 後、template 側で `make agent-canon-ensure-latest` と parent gitlink commit / push の実行結果、または external block / user stop による未実行理由が残っている

## GitHub Security Baseline

AgentCanon / template の GitHub repo は private を既定にし、少なくとも次を PR 前に確認します。

```bash
gh repo view iwashita-nozomu/agent-canon --json nameWithOwner,visibility,isPrivate,defaultBranchRef
gh api repos/iwashita-nozomu/agent-canon/branches/main/protection
gh api repos/iwashita-nozomu/agent-canon/vulnerability-alerts
gh api repos/iwashita-nozomu/agent-canon/dependabot/alerts --jq length
```

- branch protection が無い場合は `missing_or_unavailable` として PR 本文へ残し、必要なら GitHub UI で `main` 保護、required checks、delete branch on merge を設定します。
- vulnerability alert / Dependabot alert が disabled の場合は、private repo 側の security settings で有効化するか、無効の理由を PR に残します。
- `gh auth status` は host で人間が初回認証します。container は host `~/.config/gh` mount を使い、token を repo に書きません。

## 禁止事項

- root 側の symlink view を直接編集して shared canon 変更を close してはいけません。
- shared canon 変更を repo-local implementation change と同じ PR に混ぜてはいけません。
- tool addition、memory addition、skill eval result、feedback-loop change を template pin PR だけに閉じ込めてはいけません。
- workflow defect を run bundle だけに残して durable `issues/`、`memory/`、または `notes/failures/` に昇格しないまま close してはいけません。
- raw text search hit だけを根拠に edit scope を決め、dependency-expanded edit scope を省略してはいけません。
- standalone AgentCanon repo では explicit validation commands、template / derived repo では `make agent-canon-pr-check` を省略して PR を close してはいけません。
- `gh` が使えるだけで PR merge、close、ready-for-review、reviewer request、auto-merge、review dismissal、branch deletion を実行してはいけません。
- `vendor/agent-canon/` の構成変更を file 単位の拾い直しで `main` に戻してはいけません。
- template `main` merge 後に AgentCanon PR / merge と template pin 更新の対応を曖昧なままにしてはいけません。

## 使う入口

- `documents/SHARED_RUNTIME_SURFACES.md`
- `documents/agent-canon-subtree-migration.md`
- `issues/README.md`
- `documents/dependency-manifest-design.md`
- `agents/workflows/main-integration-workflow.md`
- `tools/sync_agent_canon.sh`
- `tools/ci/check_agent_canon_pr.sh`
- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
