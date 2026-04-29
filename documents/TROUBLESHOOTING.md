<!--
@dependency-start
responsibility Documents トラブルシューティング for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# トラブルシューティング

よくある問題の入口だけを残します。詳細な手順は対応する正本を参照してください。

## チェックが通らない

- `make ci-quick` を再実行して、どの段階で落ちているかを切り分けます。
- Python 関連なら `docker/requirements.txt` と設定ファイルの不整合を確認します。
- 文書関連なら `make docs-check` を流します。

## Docker build が通らない

- `make docker-build-check` を実行して、build と container 起動のどちらで落ちるかを切り分けます。
- `docker` / `podman` がない環境では、GitHub Actions の `Docker Build` workflow を使います。
- `docker/Dockerfile` と `docker/requirements.txt` の更新漏れがないか確認します。
- Linux / WSL host の前提が怪しい場合は `documents/linux-wsl-host-requirements.md` を見ます。

## WSL / host 前提が怪しい

- repo が Linux filesystem 側にあるか確認します。
- `/mnt/git` があるか確認します。
- `docker version` と `id` を見て、今の shell から daemon に到達できるか確認します。
- VS Code dev container が不安定なら `.devcontainer/` と `documents/linux-wsl-host-requirements.md` を見直します。

## import や依存が壊れる

- Python を使う場合は `docker/Dockerfile` と `docker/requirements.txt` を正本にします。
- `python/` 前提のスクリプトでは import path の前提を確認します。

## 実験が不安定

- partial run を正式結果として扱わないことを確認します。
- run 条件、出力先、比較条件を先に固定します。
- `agents/workflows/experiment-workflow.md` と `agents/workflows/research-workflow.md` を見直します。

## agent 運用が分からない

- `agents/README.md`
- `documents/AGENTS_COORDINATION.md`
- `agents/TASK_WORKFLOWS.md`
