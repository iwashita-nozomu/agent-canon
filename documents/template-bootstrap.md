<!--
@dependency-start
contract reference
responsibility Documents Template Bootstrap for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ./agent-canon-github-remote.md GitHub canonical remote policy
upstream design ./template-github-remote.md template GitHub canonical remote policy
@dependency-end
-->

# Template Bootstrap

この文書は、`git clone <template>` 直後に新しい repo を使い始めるときの最短 runbook です。

## この文書の読み方

- この文書は、template clone 直後の初期化、受け入れ確認、開発環境、
  作業開始までの最短 runbook を扱います。
- 主な順路は、Clone 直後、初期化、受け入れ確認、開発環境、作業開始です。
- 新しい template-derived repo を作るときに読みます。
- 境界: GitHub remote policy や shared runtime surface の詳細はリンク先の
  documents が正本です。

## 1. Clone 直後

```bash
git clone <template-repo> <your-project>
cd <your-project>
```

## 2. 初期化

repo 名、表示名、bare remote 名を変える場合は次を使います。
agent に任せる場合は `$start-repository` を指定し、この tool を呼ばせます。

```bash
bash scripts/start_repository.sh \
  --project-slug your-project \
  --display-name "Your Project"
```

GitHub-backed template では、`vendor/agent-canon` submodule は
`https://github.com/iwashita-nozomu/agent-canon.git` を canonical remote として使います。
`--force` を init に渡すと wrapper は agent-canon preflight を block 扱いで skip し、dirty worktree override を優先します。
AgentCanon は GitHub submodule を正本とし、初期化時に project-local `agent-canon` bare repo は作りません。

派生 repo から `agent-canon` だけ更新したいときは次を使います。

```bash
bash tools/update_agent_canon.sh plan
bash tools/update_agent_canon.sh apply
```

派生 repo 側で shared canon を直した場合は、`vendor/agent-canon/` 内で通常の GitHub branch を作って commit し、main を取り込んでから PR を出します。

```bash
git -C vendor/agent-canon switch -c canon-pr/<short-topic>
git -C vendor/agent-canon add -A
git -C vendor/agent-canon commit -m "<message>"
bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty
git -C vendor/agent-canon push origin HEAD
```

AgentCanon PR merge 後に派生 repo 側へ戻り、`bash tools/update_agent_canon.sh apply` と `bash tools/sync_agent_canon.sh link-root` で pin と root view を更新します。

GitHub 管理では template の canonical remote を
`https://github.com/iwashita-nozomu/project_template.git` にします。`.gitmodules` の AgentCanon URL は
`https://github.com/iwashita-nozomu/agent-canon.git` にします。
PR と security 設定の正本は GitHub 側に置きます。

最低限の確認:

```bash
gh repo view <owner>/<template-repo> --json nameWithOwner,visibility,isPrivate,defaultBranchRef
gh repo view <owner>/agent-canon --json nameWithOwner,visibility,isPrivate,defaultBranchRef
git submodule status vendor/agent-canon
```

## 3. 受け入れ確認

fresh clone と runtime surface が壊れていないことを確認します。
init 変更を commit したあと、同じ tool で確認できます。

```bash
bash scripts/start_repository.sh --validate-only
```

## 4. 開発環境

- host 前提:
  - `documents/linux-wsl-host-requirements.md`
- container:
  - `docker/README.md`
- VS Code devcontainer:
  - `.devcontainer/`
- VS Code workspace defaults and recommended extensions:
  - `.vscode/` (AgentCanon-managed root view)

## 5. 作業開始

- agent workflow:
  - `agents/README.md`
- workflow canon:
  - `agents/workflows/README.md`
- work log:
  - `python3 tools/agent_tools/work_log.py --kind <kind> --message "<what changed>" --next "<next>"`

新規作業では追加の `git worktree` を使いません。current checkout の run-local `work_log.md` に継続ログを残します。

```bash
python3 tools/agent_tools/work_log.py \
  --kind kickoff \
  --message "references and scope confirmed" \
  --next "start implementation"
```
