<!--
@dependency-start
responsibility Documents Template Bootstrap for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# Template Bootstrap

この文書は、`git clone <template>` 直後に新しい repo を使い始めるときの最短 runbook です。

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

必要なら dry-run:

```bash
bash scripts/start_repository.sh \
  --project-slug your-project \
  --display-name "Your Project" \
  --dry-run
```

既定では `/mnt/git/your-project-agent-canon.git` も初期化し、clone に含まれる `vendor/agent-canon/` snapshot を seed します。
このとき proposal branch `canon-proposal/your-project` も bare repo に用意し、clone の git config に既定 branch として記録します。
`--force` を init に渡すと wrapper は agent-canon preflight を block 扱いで skip し、dirty worktree override を優先します。
既存の shared `agent-canon` remote を使い続ける場合だけ、`--skip-agent-canon-bare-repo` を付けます。

派生 repo から `agent-canon` だけ更新したいときは次を使います。

```bash
bash tools/update_agent_canon.sh plan
bash tools/update_agent_canon.sh apply
bash tools/update_agent_canon.sh proposal-branch
bash tools/update_agent_canon.sh push-proposal
```

source repo が設定されていれば、`apply` は先に remote snapshot を最新化してから local vendored snapshot を取り込みます。project-local bare repo を daily validation の正本にしたい場合は source repo を設定しません。

project-local bare repo を後から登録するときは次です。

```bash
bash tools/update_agent_canon.sh register-local-bare \
  --bare-repo /mnt/git/your-project-agent-canon.git
```

shared upstream refresh も使いたいときだけ `--source-repo /mnt/l/workspace/agent-canon` を追加します。

shared canon の変更を maintainer に渡すときは、`push-proposal` で project-local bare repo の proposal branch へ投げます。maintainer はその branch を fetch して整理用 branch に merge します。

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
- 推奨拡張:
  - `.vscode/extensions.json`

## 5. 作業開始

- agent workflow:
  - `agents/README.md`
- workflow canon:
  - `agents/workflows/README.md`
- worktree kickoff:
  - `bash tools/worktree_start.sh <branch-name> [worktree-path]`

worktree を使う場合は kickoff 後に継続ログを残します。

```bash
python3 tools/agent_tools/work_log.py \
  --kind kickoff \
  --message "references and scope confirmed" \
  --next "start implementation"
```
