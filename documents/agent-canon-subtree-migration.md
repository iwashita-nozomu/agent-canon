# AgentCanon Submodule Update And Legacy Subtree Migration

<!--
@dependency-start
contract reference
responsibility Documents AgentCanon submodule update and legacy subtree migration for this repository.
downstream design ../agents/workflows/derived-agent-canon-diff-workflow.md consumes the subtree migration contract
upstream design ./agent-canon-github-remote.md defines GitHub canonical remote policy
upstream design ./github-first-module-and-devcontainer-policy.md defines GitHub-first module and devcontainer policy
downstream design ./dependency-manifest-design.md defines dependency manifest surface added to root
downstream implementation ../tools/sync_agent_canon.sh vendoring sync tool
downstream implementation ../tools/update_agent_canon.sh derived repo update helper
@dependency-end
-->

この文書は、`agent-canon` maintainer が template / derived repo の `vendor/agent-canon` 構成を保守するときの正本です。
新規 repo と移行済み repo では submodule pin を標準にし、legacy subtree repo は移行完了まで互換 path として扱います。
ファイル名に `subtree-migration` が残っているのは既存リンク互換のためです。通常運用の正本タイトルと本文は submodule-first です。

## この文書の読み方

この文書は、AgentCanon submodule 更新、legacy subtree 移行、root view 同期、PR 運用の境界を説明します。目的、固定構成、所有境界、編集ルール、同期ルールを先に読み、通常作業では GitHub canonical remote、PR ルール、完了条件、標準運用を使います。wrapper、worktree / submodule pin、移行フェーズ、リスク、legacy subtree appendix は、互換運用や移行判断が必要なときだけ読みます。

## 目的

- `git clone <template>` 後に submodule init で shared canon を使える状態を保つ
- shared canon の source of truth を upstream `agent-canon` repo と `vendor/agent-canon/` submodule pin に固定する
- template root には runtime discovery に必要な surface だけを残す
- template 利用者向けの入口文書は root regular file として残す
- reusable module distribution は GitHub PR / GitHub `main` SHA を正本にする

## 固定構成

- upstream repo:
  - `https://github.com/iwashita-nozomu/agent-canon.git`
- template / 派生 repo 側の pin:
  - `vendor/agent-canon/`
- submodule URL:
  - `.gitmodules` では `https://github.com/iwashita-nozomu/agent-canon.git` を標準にします。
- root 側の shared runtime surface:
  - `documents/shared-runtime-surfaces.toml` に載っている symlink view、synced copy、regular active contract、repo-local state
- root 側の shared devcontainer:
  - `.devcontainer/` は AgentCanon-owned symlink view とし、repo-local Dockerfile / runtime pack を消費する
- root 側の template entrypoint:
  - `README.md`
  - `QUICK_START.md`
  - `documents/README.md`
  - `scripts/README.md`
  - `notes/README.md`
  - `docker/README.md`

## 所有境界

- `vendor/agent-canon/` submodule:
  - workflow canon
  - skill canon
  - subagent 定義
  - shared notes template
  - shared devcontainer post-create / attach runtime ergonomics
  - shared CI / review / runtime helper
  - submodule update / PR / shared surface ownership 文書
- root 側:
  - template 利用者向けの入口
  - implementation 本体
  - repo-local Dockerfile / dependency pack / server / template bootstrap
  - repo-local experiment topic
  - repo-local notes

## 編集ルール

- shared canon を直すときは `vendor/agent-canon/` 側を編集します。
- root 側の symlink view や synced copy を直接編集しません。
- shared surface を増減したら、同じ pass で `documents/shared-runtime-surfaces.toml` と ownership 文書を更新します。
- root 側の入口文書を変える場合でも、shared canon の説明は `agent-canon` 側の正本に寄せます。

## 同期ルール

template repo 側では submodule-first の入口を使います。

```bash
make agent-canon-update-plan
make agent-canon-latest
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

- `plan`:
  - derived repo から見た AgentCanon update route を read-only で表示する
- `latest`:
  - upstream AgentCanon main を取り込み、template / derived repo の submodule pin、root views、parent TODO boundary を high-level route として処理する
- `merge-main-into-current`:
  - 通常 sequence ではなく、`vendor/agent-canon/` に local AgentCanon source commit がある場合の AgentCanon PR route で使う
- `merge-main-into-current-preserve-dirty`:
  - `vendor/agent-canon/` の dirty state を明示的に stash 退避し、GitHub main 取り込み後に戻す AgentCanon PR route 用入口
- `link-root`:
  - root の symlink view と synced copy を vendor 正本から再構成する
- `check`:
  - root surface と vendor 正本の drift を検出する
- `sync_agent_canon.sh pull` / `push`:
  - legacy subtree 互換または maintainer 低レベル操作に限る。通常の submodule repo では `update_agent_canon.sh` の route を優先する

## GitHub canonical remote

AgentCanon の source of truth は GitHub の
`https://github.com/iwashita-nozomu/agent-canon.git` です。
shared module architecture、Dockerfile boundary、devcontainer ownership を local-only
remote 名や一台の host path に合わせて変えません。

既存 repo が `agent-canon` remote や `.gitmodules` を GitHub canonical 以外に向けている場合は、AgentCanon update surface が安全に更新できるタイミングで
`documents/agent-canon-github-remote.md` の migration runbook に従います。

## PR ルール

- shared canon 変更は dedicated branch と dedicated PR に分けます。
- shared canon 変更は repo-local implementation change と同じ PR に混ぜません。
- PR 前の機械 gate は `make agent-canon-pr-check` を使います。
- dirty shared-canon 差分は pin 更新で消さず、AgentCanon branch と PR で upstream に取り込みます。
- AgentCanon PR merge 後は template / derived repo 側で `make agent-canon-ensure-latest`、`bash tools/sync_agent_canon.sh link-root`、parent pin commit を作ります。
- `bash tools/sync_agent_canon.sh push` は maintainer が direct upstream push を明示した例外だけにします。
- GitHub 管理では、template PR と AgentCanon PR / commit の対応、submodule pin、GitHub `main` SHA、security check 状態を PR 本文に残します。

## 完了条件

次をすべて満たしたときだけ AgentCanon update を完了扱いにします。

- `bash tools/sync_agent_canon.sh check` が pass
- `make agent-canon-pr-check` が pass
- root 側の shared surface が構成どおりに再同期されている
- AgentCanon GitHub `main` SHA、template submodule pin SHA、`git submodule status vendor/agent-canon` が PR / closeout evidence に残っている

## 参照先

- `README.md`
- `agents/workflows/README.md`
- `documents/SHARED_RUNTIME_SURFACES.md`
- `documents/dependency-manifest-design.md`
- `agents/workflows/agent-canon-pr-workflow.md`
- `agents/workflows/derived-agent-canon-diff-workflow.md`
- `tools/shared/error_handler.py`
- `tools/validation/triplet_validator.py`
- `tools/bin/agent-canon docs check`
- `tools/agent_tools/bootstrap_agent_run.py`
- `tools/agent_tools/smoke_test_research_perspective_pack.py`
- `tools/agent_tools/validate_role_write_scope.py`
- `tools/agent_tools/agent_team.py`
- `tools/agent_tools/worktree_scope_lint.py`
- `tools/agent_tools/worktree_start.py`
- `tools/setup_worktree.sh`
- `tools/worktree_start.sh`
- `tools/docs/check_worktree_scopes.sh`
- `tools/docs/create_worktree.sh`

## 5. wrapper の考え方

root 側は owner class ごとに薄い wrapper、symlink view、copy surface、regular active contract を分けます。

- AgentCanon-owned symlink views:
  - `AGENTS.md`, `agents/`, `.agents/`, `.codex/`, `mcp/`, `tools/`
  - AgentCanon-owned shared policy docs listed in `documents/shared-runtime-surfaces.toml`
  - AgentCanon-owned `tests/agent_tools/` and `tests/tools/` mirror tests
- GitHub path constraint copy surfaces:
  - `.github/workflows/agent-coordination.yml`
  - `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`
  - `.github/scripts/checkout_agent_canon_submodule.sh`
- Template-owned active contracts, regular at root:
  - `README.md`, `QUICK_START.md`, `documents/README.md`
  - `documents/template-bootstrap.md`
  - `documents/template-github-remote.md`
  - `documents/linux-wsl-host-requirements.md`
  - `documents/server-host-contract.md`
  - `documents/remote-execution-repo-contract.md`
  - `docker/README.md`, `scripts/README.md`, `notes/README.md`, `.gitmodules`
- Project-owned durable state:
  - `goal.md`, project-specific notes, experiments, reports, and project-specific design docs

重要:
- `vendor/agent-canon/AGENTS.md` は standalone AgentCanon repo 用 entrypoint として扱い、template root runtime は root `AGENTS.md` symlink view から入ります
- root runtime の正面入口は root に固定します
- shared canon の source of truth は root 側ではなく `vendor/agent-canon/` です
- authoritative path inventory は Markdown の長大リストではなく `documents/shared-runtime-surfaces.toml` です

## 6. worktree と submodule pin の関係

- template / 派生 repo で worktree を切ると、その branch / commit に入っている `vendor/agent-canon` gitlink が見えます
- upstream `agent-canon` の最新が自動で流入するわけではありません
- shared canon の更新は、明示的に submodule pin を更新した branch にだけ反映されます

つまり:
- worktree は親 repo の gitlink を使う仕組み
- shared canon 更新は submodule pin commit で行う仕組み

## 7. 標準運用

### 7.1 root symlink surface を修復

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

### 7.2 互換 alias

既存の `snapshot` command は後方互換のため `link-root` の alias として残します。

```bash
bash tools/sync_agent_canon.sh snapshot
```

### 7.3 初回 clone / recovery

```bash
git clone --recurse-submodules <template-url> <repo>
cd <repo>
git submodule sync vendor/agent-canon
git submodule update --init --recursive vendor/agent-canon
bash tools/sync_agent_canon.sh check
```

### 7.4 upstream から更新取得

```bash
make agent-canon-update-plan
make agent-canon-latest
```

derived repo で `agent-canon` だけ更新したい場合の既定入口は `update_agent_canon.sh` です。
通常の動線は high-level `plan -> latest` です。
`sync_agent_canon.sh ensure-latest` は task 開始時の freshness gate、`link-root` は root view drift 修復、`push` は shared canon を直接 upstream に戻す保守者向け低レベル入口です。
通常の派生 repo update で `sync_agent_canon.sh pull` を直接選びません。
derived repo の `vendor/agent-canon/` に local commit または source dirty state がある場合は、`bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty` で dirty state を保護しながら GitHub `main` を current branch に取り込み、validation 後にその branch を GitHub へ push して AgentCanon PR を開きます。
`plan` は read-only で route を示します。
submodule repo では `already_current_submodule` / `submodule_update` を通常 route として扱います。legacy subtree metadata がある branch での `subtree_pull` や `snapshot_import_no_subtree*` 系 route は compatibility appendix だけの扱いです。

`ensure-latest` は task 開始時の入口です。
submodule repo では親 repo の無関係な dirty state だけを理由に skip せず、upstream `agent-canon` と local submodule pin / worktree を比較します。
clean な submodule worktree が remote main を指していて parent gitlink だけ古い場合は、parent pin を更新対象として扱います。
`agent-canon` remote が未設定の場合は、GitHub canonical remote
`https://github.com/iwashita-nozomu/agent-canon.git` を自動追加します。
submodule repo では通常 `git subtree pull --squash` を使いません。
fresh clone などで subtree metadata がなく `git subtree pull --squash` が失敗した場合は、local subtree split が remote の祖先である fast-forward 更新に限って snapshot import へ切り替えます。
local subtree split が remote と diverge していても、current prefix tree そのものが remote history に存在する場合は `snapshot_import_tree_match` route を使って安全に更新します。これは subtree split commit hash だけが synthetic に diverge している normal update を救済する route です。
local split も current prefix tree も remote history に無い場合は、shared canon の上書きを避けるため fail-closed で停止します。shared canon change を AgentCanon PR で upstream へ戻したあとで再実行します。
unsafe な AgentCanon update surface で stale が見つかった場合は、作業差分を保護するため停止します。

### 7.4.1 local submodule branch の main 追従

親 repo の tree diff だけで AgentCanon 差分を判断しません。`vendor/agent-canon/` の current branch を明示し、GitHub main を取り込んでから PR にします。

```bash
bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty
```

- `blocked_dirty`: uncommitted AgentCanon work があるため、commit / stash 後に再実行します。
- `blocked_detached_head`: named branch が無いため、AgentCanon PR branch を作ってから再実行します。
- `already_current` / `already_contains_main`: validation 後に branch push または parent pin update へ進みます。
- `fast_forwarded` / `merged`: validation 後に current AgentCanon branch を GitHub へ push し、AgentCanon PR を開くか更新します。
- `conflict`: `vendor/agent-canon/` 内で conflict を解消し、commit してから validation と push に進みます。
- `merge-main-into-current` は clean worktree を要求する strict 入口です。dirty state がある通常運用では、手作業 stash ではなく `merge-main-into-current-preserve-dirty` を使います。
- `merge-main-into-current-preserve-dirty` は merge が成功した場合だけ stash を戻して drop します。main merge が conflict した場合は stash を保持し、conflict 解消後に出力された stash ref を適用します。

### 7.5 subtree から submodule への移行

既存 subtree repo を submodule へ移すときは、repo ごとに専用 commit を作ります。
commit message には `AgentCanon subtree-to-submodule migration` と、local worktree 利用者が `git fetch` / merge / conflict resolution で追従できることを書きます。

標準 pin は `vendor/agent-canon` の submodule URL
`https://github.com/iwashita-nozomu/agent-canon.git`、branch `main` です。
親 repo の root symlink view は維持し、`bash tools/sync_agent_canon.sh link-root` と `bash tools/sync_agent_canon.sh check` で検証します。

### 7.6 template / 派生 repo 側の shared canon 変更を upstream へ戻す

```bash
git -C vendor/agent-canon switch -c canon-pr/<short-topic>
bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty
git -C vendor/agent-canon push origin HEAD
```

通常は AgentCanon branch と AgentCanon PR 経由で戻します。AgentCanon main に取り込まれた後、template / 派生 repo 側で `make agent-canon-ensure-latest` と `bash tools/sync_agent_canon.sh link-root` を再実行して差分を持ち帰ります。`sync_agent_canon.sh push` は maintainer が direct upstream push を選ぶ場合だけ使います。

### 7.6 現在の設定確認

```bash
bash tools/sync_agent_canon.sh status
```

### 7.7 GitHub Canonical Update Route

Project-local remotes are not a user-facing AgentCanon update path. Existing
repos must migrate `.gitmodules` back to the canonical GitHub URL before normal
AgentCanon PR work. New AgentCanon changes go through GitHub branches and PRs,
with `merge-main-into-current-preserve-dirty` used before push when the branch
was created from a derived repo.

## 8. 移行フェーズ

### Phase 0. template 側の基盤整備

この template で完了していること:
- migration 正本を作る
- `vendor/agent-canon/` の submodule pin を置く
- submodule-first の sync / review script を追加する
- root `AGENTS.md` を shared runtime surface に寄せる
- root の shared docs / scripts / discovery surface を symlink view に寄せる
- root `.codex/config.toml` も shared default に寄せる

### Phase 1. upstream `agent-canon` repo を作る

完了条件:
- `https://github.com/iwashita-nozomu/agent-canon.git` を canonical remote にする
- template 側の `.gitmodules` を canonical GitHub URL にする
- AgentCanon PR / template submodule pin PR の対応を PR 本文に残す

exit 条件:
- upstream repo 単体で shared canon を保持できる
- template / 派生 repo 側に submodule pin update できる gitlink history を持てる

### Phase 2. template bootstrap command を追加する

候補:
- `scripts/bootstrap_derived_repo.py`
- `scripts/new_product.sh`

役割:
- template clone 後の repo 名差し替え
- submodule URL / GitHub branch 設定
- optional pack 選択

## 9. リスクと抑止策

### root entrypoint が壊れる

抑止:
- root `AGENTS.md` と root `.codex/` の discovery path は最後まで消さない
- wrapper は instance-local 情報だけに絞る

### shared canon と instance-local 文書が混ざる

抑止:
- `agent-canon` へ移す範囲を phase で分ける
- Docker、server、experiment の文書は root 側に残す

### template / 派生 repo 側で直した canon を upstream へ戻せない

抑止:
- `vendor/agent-canon/` の変更は専用 commit に分ける
- `bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty` で GitHub main を取り込む
- current AgentCanon branch を GitHub に push し、AgentCanon PR を開く
- AgentCanon main に取り込まれたら `make agent-canon-ensure-latest` で pin を main に揃える

## 9.1 Legacy Subtree Appendix

legacy subtree repo は移行完了まで次を互換 path として使えます。

- `bash tools/sync_agent_canon.sh pull`
- `bash tools/sync_agent_canon.sh push` (maintainer direct-push exception only)
- `git subtree pull --prefix=vendor/agent-canon`
- `git subtree push --prefix=vendor/agent-canon`
- `snapshot_import_no_subtree*` alternate route

これらは新規 repo の標準 path ではありません。submodule 化済み repo で subtree route を選ぶ場合は、互換対応である理由を PR / closeout evidence に残します。

### worktree ごとに shared canon pin がばらつく

抑止:
- それは親 repo の gitlink による意図した pin 運用とみなす
- どの branch がどの AgentCanon commit を指すかを commit history と `git submodule status vendor/agent-canon` で追えるようにする

## 10. 完了条件

- upstream `agent-canon` repo が存在する
- template repo が `vendor/agent-canon/` submodule pin を持つ
- root `AGENTS.md` と root `.codex/` は root discovery path として機能する
- template / 派生 repo で worktree を切ったとき、その時点の shared canon pin が `vendor/agent-canon/` として見える
- template / 派生 repo 側で直した shared canon を AgentCanon branch / PR で upstream へ戻せる
- `git clone --recurse-submodules <template>` 直後に `vendor/agent-canon/` を参照できる

## 11. 関連

- [README.md](../README.md)
- [AGENTS.md](../AGENTS.md)
- [WORKFLOW_GUIDE.md](../agents/workflows/README.md)
- [workflow-references.md](../agents/workflows/workflow-references.md)
- [README.md](../vendor/README.md)
- [sync_agent_canon.sh](../tools/sync_agent_canon.sh)
