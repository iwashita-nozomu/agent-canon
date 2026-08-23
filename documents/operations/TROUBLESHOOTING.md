<!--
@dependency-start
contract reference
responsibility Documents トラブルシューティング for this repository.
upstream design ../contracts/github-first-module-and-devcontainer-policy.md environment ownership boundary
@dependency-end
-->

# トラブルシューティング

よくある問題の入口だけを残します。詳細な手順は対応する正本を参照してください。

## チェックが通らない

- `make ci-quick` を再実行して、どの段階で落ちているかを切り分けます。
- Python 関連なら `pyproject.toml` の requested extras、現行 Python/pip、`pip check` の不整合を確認します。
- 文書関連なら `tools/bin/agent-canon docs check` を流します。
- validation test/check failure では、通すために intended behavior/test を削る、
  oracle を弱める、required validation を縮める、または blanket revert で済ませる
  ことを禁止します。先に `failing_contract`、`observation_level`、
  `cause_classification`、`intent_preservation`、`evidence` を記録します。
- `cause_classification` と `intent_preservation` の slug set は
  `documents/runtime/runtime-profiles-and-check-matrix.json` が所有します。
  `documents/runtime/runtime-profiles-and-check-matrix.md` は生成済み reader projection として
  参照します。
  approved intent を保って修正するか、intent 変更前に escalation します。

## Docker build が通らない

- `make docker-build-check` を実行して、build と container 起動のどちらで落ちるかを切り分けます。
- `docker` / `podman` がない環境では、GitHub Actions の `Docker Build` workflow を使います。
- repo-local `docker/Dockerfile`、`pyproject.toml`、AgentCanon-owned `.devcontainer/` の責務境界に更新漏れがないか確認します。固定 OS/Python capability は image、Node/npm は digest-pinned official Node OCI provider stage から Docker build 時に materialize され、tools は typed manifest の owner です。
- Linux / WSL host の前提が怪しい場合は `documents/contracts/linux-wsl-host-requirements.md` を見ます。

## WSL / host 前提が怪しい

- repo が Linux filesystem 側にあるか確認します。
- `docker version` と `id` を見て、今の shell から daemon に到達できるか確認します。
- VS Code dev container が不安定なら `.devcontainer/` と `documents/contracts/linux-wsl-host-requirements.md` を見直します。

## import や依存が壊れる

- Python package dependency は `pyproject.toml` optional extras と、親が必要とする場合の image-build project-dependency lifecycle を正本にします。Docker image は固定 OS/Python capability、digest-pinned official Node OCI provider から copy した Node/npm、manifest-selected Agent/Codex tools、親 project dependencies を所有します。post-create は `image-verify` と container runtime readback だけを実行し、editable install、pip setup、network、package mutation、workspace repair を行いません。
- `image-verify` が receipt、manifest、plan、package、または executable の drift を `rebuild-required` と報告した場合は、post-create から install や repair を試さず、manifest/providerを反映した image を再buildします。
- `python/` 前提のスクリプトでは import path の前提を確認します。

## 実験が不安定

- partial run を正式結果として扱わないことを確認します。
- run 条件、出力先、比較条件を先に固定します。
- `agents/workflows/experiment-workflow.md` と `agents/workflows/research-workflow.md` を見直します。

## agent 運用が分からない

- `agents/README.md`
- `documents/codex/AGENTS_COORDINATION.md`
- `agents/TASK_WORKFLOWS.md`
