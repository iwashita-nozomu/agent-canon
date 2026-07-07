<!--
@dependency-start
contract reference
responsibility Documents トラブルシューティング for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ./github-first-module-and-devcontainer-policy.md environment ownership boundary
@dependency-end
-->

# トラブルシューティング

よくある問題の入口だけを残します。詳細な手順は対応する正本を参照してください。

## チェックが通らない

- `make ci-quick` を再実行して、どの段階で落ちているかを切り分けます。
- Python 関連なら `docker/requirements.txt` と設定ファイルの不整合を確認します。
- 文書関連なら `tools/bin/agent-canon docs check` を流します。
- validation test/check failure では、通すために intended behavior/test を削る、
  oracle を弱める、required validation を縮める、または blanket revert で済ませる
  ことを禁止します。先に `failing_contract`、`observation_level`、
  `cause_classification`、`intent_preservation`、`evidence` を記録します。
- `cause_classification` と `intent_preservation` の slug set は
  `documents/runtime-profiles-and-check-matrix.md`、`agents/canonical/CODEX_WORKFLOW.md`、
  `agents/canonical/CODEX_SUBAGENTS.md`、`documents/REVIEW_PROCESS.md` を参照します。
  approved intent を保って修正するか、intent 変更前に escalation します。

## Docker build が通らない

- `make docker-build-check` を実行して、build と container 起動のどちらで落ちるかを切り分けます。
- `docker` / `podman` がない環境では、GitHub Actions の `Docker Build` workflow を使います。
- repo-local `docker/Dockerfile`、`docker/requirements.txt`、AgentCanon-owned `.devcontainer/` の責務境界に更新漏れがないか確認します。
- Linux / WSL host の前提が怪しい場合は `documents/linux-wsl-host-requirements.md` を見ます。

## WSL / host 前提が怪しい

- repo が Linux filesystem 側にあるか確認します。
- `docker version` と `id` を見て、今の shell から daemon に到達できるか確認します。
- VS Code dev container が不安定なら `.devcontainer/` と `documents/linux-wsl-host-requirements.md` を見直します。

## import や依存が壊れる

- Python package dependency は `docker/requirements.txt` と devcontainer post-create installer を正本にします。`docker/Dockerfile` は OS package、runtime library、build tool、image-level helper の正本です。
- `python/` 前提のスクリプトでは import path の前提を確認します。

## 実験が不安定

- partial run を正式結果として扱わないことを確認します。
- run 条件、出力先、比較条件を先に固定します。
- `agents/workflows/experiment-workflow.md` と `agents/workflows/research-workflow.md` を見直します。

## agent 運用が分からない

- `agents/README.md`
- `documents/AGENTS_COORDINATION.md`
- `agents/TASK_WORKFLOWS.md`
