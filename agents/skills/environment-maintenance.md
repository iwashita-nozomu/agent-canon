# environment-maintenance

## Purpose

Docker、CI、dependency、runtime guidance を同じ変更でそろえます。

## Use When

- Dockerfile 更新
- CI 更新
- dependency / runtime upgrade
- repo-wide な tool 導入提案
- host / container / CI の責務分担を決める変更

## Core References

- `documents/coding-conventions-project.md`
- `documents/WORKFLOW_INVENTORY.md`
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

- 導入理由
- 影響範囲
- host / Docker / CI のどこを正本にするか
- `docker/Dockerfile` と `docker/requirements.txt` の更新要否
- validation plan
- rollback plan

## Operating Rules

- repo の共通環境に入れる tool は、個人環境前提の host-global install を正本にしません。
- repo-wide に必要な Python tool は、原則として `docker/requirements.txt` と `docker/Dockerfile` に載せます。
- 1 回限りの手元補助なら、repo 正本に昇格させず代替案を先に検討します。
- Docker、CI、README、workflow command が変わる場合は、同じ変更でそろえます。
- 依存追加の提案だけで終わらせず、validate と rollback まで記録します。

## Validation

- `make docker-build-check`
- `make docker-build-check-host-docker`
- `make server-check`
- `make ci-quick`
- 必要なら `make ci`
- 文書更新を含む場合は `make docs-check`

## Boundary

- 実験 loop 自体の運用は `experiment-change-loop` または `research-workflow` を使います。
- 差分レビューは `change-review` を使います。
