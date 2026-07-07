# environment-maintenance
<!--
@dependency-start
contract skill
responsibility Documents environment-maintenance for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../CONTAINER_OPERATIONS.md canonical container and devcontainer ownership boundary
@dependency-end
-->


## Reader Map

- Purpose: routes Docker, CI, dependency, and development-environment changes
  through explicit proposal, validation, and rollback evidence.
- Use When: touching runtime images, dependency manifests, CI, devcontainer, or
  environment compatibility guidance.
- Section path: Purpose, Use When, and Core References set scope; Required
  Proposal Fields, Operating Rules, and Validation are the operational rules;
  Boundary limits environment authority.
- Boundary: environment-dependent tools should not become hidden local
  prerequisites.

## Purpose

Docker、CI、dependency、runtime guidance を同じ変更でそろえ、どの code requirement が環境変更を要求したかを明示します。

## Use When

- Dockerfile 更新
- CI 更新
- dependency / runtime upgrade
- repo-wide な tool 導入提案
- host / container / CI の責務分担を決める変更

## Core References

- `CONTAINER_OPERATIONS.md`
- `documents/coding-conventions-project.md`
- `documents/github-first-module-and-devcontainer-policy.md`
- `documents/tools/README.md`
- `docker/README.md`
- `docker/packs/`
- `docker/codex-container-profiles.toml`
- `docker/python-execution-rules.toml`
- `documents/server-host-contract.md`
- `documents/templates/server_runtime_layout.template.toml`
- `docker/`
- `.devcontainer/`
- `README.md`
- `agents/templates/environment_change_proposal.md`

## Required Proposal Fields

- code requirement と blocked command
- 既存環境で足りない理由
- 導入理由
- 影響範囲
- host / Docker / CI のどこを正本にするか
- `docker/Dockerfile`、`docker/requirements.txt`、`.devcontainer/` の更新要否
- devcontainer / runtime pack / compose 相当面の更新要否
- validation plan
- rollback plan

## Operating Rules

- Treat `CONTAINER_OPERATIONS.md` as the source of truth for Dockerfile,
  `docker/`, `.devcontainer/`, validator, and Makefile target ownership. This
  skill is only the routing checklist.
- Docker / runtime を変える task は、先に `agents/templates/environment_change_proposal.md` に code requirement と blocked command を書きます。
- 「何となく便利だから」で repo 正本の環境を変えません。必ず code path、command、run profile のどれが詰まっているかを残します。
- code requirement を host-only の手元 install で回避できても、repo-wide に必要なものは Docker / CI / docs の正本へ入れます。
- repo の共通環境に入れる tool は、個人環境前提の host-global install を正本にしません。
- repo-wide に必要な Python tool は `CONTAINER_OPERATIONS.md` の Python dependency rule に従い、repo-local installer contract に載せます。
- Codex CLI、agent 用 npm / Node、GitHub CLI / `gh`、auth、host mount 方針は `CONTAINER_OPERATIONS.md` の devcontainer boundary に従います。
- environment gate、Docker validation、venv prohibition check は Python に依存しない shell entrypoint を優先します。
- repo の canonical image では `python3.11-venv` を同梱し、container runtime 内の canonical `.venv` だけを `tools/ci/python_env_policy.py --runtime container --create` で許可します。host runtime では repo-local `.venv` を作らず、`virtualenv`、`conda create`、`uv venv`、`pipenv`、`poetry env` を既定手順にしません。
- 1 回限りの手元補助なら、repo 正本に昇格させず代替案を先に検討します。
- Docker、CI、README、workflow command が変わる場合は、同じ変更でそろえます。
- Docker 変更では `docker/Dockerfile` だけで閉じず、`docker/requirements.txt`、runtime pack、AgentCanon-owned devcontainer、関連 README の要否を同じ pass で判定します。
- `host / docker image / CI / shared script` のどこが source of truth かを曖昧にしたまま実装へ進めません。
- 依存追加の提案だけで終わらせず、validate と rollback まで記録します。
- canonical container の `safe.directory` 方針は `CONTAINER_OPERATIONS.md` と repo-local Docker runbook に従います。
- 既存 code が要求する runtime capability を満たせないなら、implementation gate の前に environment design を凍結します。

## Validation

- `bash tools/docker_dependency_validator.sh`
- `python3 tools/ci/container_config.py`
- `make docker-build-check`
- `make docker-build-check-host-docker`
- `python3 tools/ci/run_container_pack.py --pack docker/packs/default.toml --print-only`
- `make server-check`
- `make ci-quick`
- 必要なら `make ci`
- 文書更新を含む場合は `tools/bin/agent-canon docs check`
- environment / CI validation failure を修復へ回す場合は、変更前に
  validation-failure-response packet の `failing_contract`、
  `observation_level`、`cause_classification`、`intent_preservation`、
  `evidence` を記録し、pass 目的の validation downscope や oracle weakening を避けます。

## Boundary

- 実験 loop 自体の運用は `adaptive-improvement-loop` または `research-workflow` を使います。
- 差分レビューは `change-review` を使います。
