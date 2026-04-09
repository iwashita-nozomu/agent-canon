# environment-maintenance

## Purpose

Docker、CI、dependency、runtime guidance を同じ変更でそろえ、どの code requirement が環境変更を要求したかを明示します。

## Use When

- Dockerfile 更新
- CI 更新
- dependency / runtime upgrade
- repo-wide な tool 導入提案
- host / container / CI の責務分担を決める変更

## Core References

- `documents/coding-conventions-project.md`
- `documents/tools/README.md`
- `docker/README.md`
- `docker/packs/`
- `docker/codex-container-profiles.toml`
- `docker/python-execution-rules.toml`
- `documents/server-host-contract.md`
- `documents/templates/server_runtime_layout.template.toml`
- `docker/`
- `README.md`
- `agents/templates/environment_change_proposal.md`

## Required Proposal Fields

- code requirement と blocked command
- 既存環境で足りない理由
- 導入理由
- 影響範囲
- host / Docker / CI のどこを正本にするか
- `docker/Dockerfile` と `docker/requirements.txt` の更新要否
- devcontainer / runtime pack / compose 相当面の更新要否
- validation plan
- rollback plan

## Operating Rules

- Docker / runtime を変える task は、先に `agents/templates/environment_change_proposal.md` に code requirement と blocked command を書きます。
- 「何となく便利だから」で repo 正本の環境を変えません。必ず code path、command、run profile のどれが詰まっているかを残します。
- code requirement を host-only の手元 install で回避できても、repo-wide に必要なものは Docker / CI / docs の正本へ入れます。
- repo の共通環境に入れる tool は、個人環境前提の host-global install を正本にしません。
- repo-wide に必要な Python tool は `docker/requirements.txt` と `docker/Dockerfile` の両方に載せます。
- 1 回限りの手元補助なら、repo 正本に昇格させず代替案を先に検討します。
- Docker、CI、README、workflow command が変わる場合は、同じ変更でそろえます。
- Docker 変更では `docker/Dockerfile` だけで閉じず、`docker/requirements.txt`、runtime pack、devcontainer、関連 README の要否を同じ pass で判定します。
- `host / docker image / CI / shared script` のどこが source of truth かを曖昧にしたまま実装へ進めません。
- 依存追加の提案だけで終わらせず、validate と rollback まで記録します。
- canonical container の `safe.directory` 方針は run-time entrypoint や ad hoc env に逃がさず、Docker image 側の明示設定として管理します。
- host `uid:gid` や `HOME` を container 実行時に差し替える場合でも効くように、git safe directory は user-local ではなく container-wide に効く方法を優先します。
- 既存 code が要求する runtime capability を満たせないなら、implementation gate の前に environment design を凍結します。

## Validation

- `python3 scripts/docker_dependency_validator.py`
- `make docker-build-check`
- `make docker-build-check-host-docker`
- `python3 scripts/ci/run_container_pack.py --pack docker/packs/default.toml --print-only`
- `make server-check`
- `make ci-quick`
- 必要なら `make ci`
- 文書更新を含む場合は `make docs-check`

## Boundary

- 実験 loop 自体の運用は `adaptive-improvement-loop` または `research-workflow` を使います。
- 差分レビューは `change-review` を使います。
