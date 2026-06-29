<!--
@dependency-start
contract reference
responsibility Documents Server Host Contract for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md shared documents ownership policy
downstream design ./tools/html_artifact_access.md documents remote HTML artifact access commands
@dependency-end
-->

# Server Host Contract

この文書は、repo を日常運用する main server host の最小契約をまとめます。
remote execution contract が「repo が外部 server から実行される条件」を定義するのに対し、ここでは「この repo を主に回す host 自身が満たすべき条件」を固定します。

## この文書の読み方

- この文書は、main 開発 host の必須条件、推奨事項、storage/container/browser/WSL/Git
  rules、validation、関連文書を定めます。
- 主な順路は、対象、必須、推奨、Storage Rule、Container Runtime Rule、
  Remote Browser Artifact Rule、WSL / Shared Mount Rule、Git Rule、Validation、Related です。
- repo を日常運用する server host を準備または監査するときに読みます。
- 境界: remote execution contract は外部 server から repo を実行する条件を扱います。

## 対象

- main 開発 host
- nested Codex や Docker build を回す host
- bare repo、shared workspace、mirror hook を持つ host

## 必須

- `git`, `python3`, `codex`, `docker` か `podman` の少なくとも 1 つが利用可能であること
- bare repo root と workspace root が決まっていること
- local state を置く Linux filesystem 側 path が決まっていること
- Docker を使う場合、daemon socket へ実際にアクセスできる shell を持つこと
- `origin` push、mirror hook、artifact root の責務分担が文書化されていること

## 推奨

- bare repo root を 1 か所に集約する
- shared workspace root を 1 か所に集約する
- Docker state は local Linux filesystem に置き、CIFS / 9p / network share に置かない
- host inventory を `documents/templates/server_host_inventory.template.md` で記録する
- path / mount / builder 前提を `documents/templates/server_runtime_layout.template.toml` で明文化する
- `python3 tools/ci/check_server_readiness.py` で定期的に readiness を確認する

## Storage Rule

- bare repo root と shared workspace root は分けます
- network share を使う場合でも、Docker state と socket は local Linux filesystem 側に置きます
- `/workspace/.state/` に永続化したいものがある場合、host 側でもどこへ残るかを決めます

## Container Runtime Rule

- Docker を既定にする場合、`docker` group にユーザーが追加されているだけでは不十分です
- 現在の shell がその group を有効にしていることを確認しなければなりません
- `getent group docker` にユーザーが出ても `id` に `docker` が出ない場合は、新しい login shell を開くか group refresh が必要です
- 一時確認だけなら `sg docker -c 'docker version'` で daemon 到達性を切り分けられます
- main server host では、`make docker-build-check` と `make docker-build-check-host-docker` を実行できる状態を推奨します

## Remote Browser Artifact Rule

- local PC から SSH で HPC host に入り、その上の container で HTML report を生成する場合、local browser は container 内の `127.0.0.1` を直接見られません
- HTML artifact は、ファイルが見えている shell で `python3 -m http.server` を立て、local PC から HPC host への SSH tunnel で見る導線を既定にします
- canonical command generator は `python3 tools/experiments/html_artifact_access.py <report.html>` です。`AGENT_CANON_SSH_HOST` または `SSH_CONNECTION` から SSH target を推定し、推定できない場合だけ tunnel command 内の `<ssh-host>` を置き換えます
- container 内だけにある report では `--use-container-ip` を使い、出力された server、tunnel、local URL を closeout evidence に残します
- default bind は `127.0.0.1` です。container-direct mode では container IP へ tunnel するため、container 内の server は `0.0.0.0` bind を使います

## WSL / Shared Mount Rule

- WSL2 を main host にすること自体は許容します
- ただし、CIFS / 9p / network share と local ext4 を混同せず、どの path がどの filesystem かを inventory に残します
- bare repo や共有 workspace を network share に置く場合、Docker state と build cache は local ext4 側に残します
- symlink、file permission、case sensitivity、I/O 特性の差を前提にします

## Git Rule

- GitHub canonical remote と authentication state を記録します
- GitHub publish / PR 作業は `python3 tools/agent_tools/github_publish.py ... --user-task "<current user task>" --repo <owner/name>` を canonical 入口にします

## Validation

```bash
python3 tools/ci/check_server_readiness.py
python3 tools/ci/check_server_readiness.py --layout documents/templates/server_runtime_layout.template.toml
make docker-build-check
make docker-build-check-host-docker
```

## Related

- `documents/linux-wsl-host-requirements.md`
- `documents/remote-execution-repo-contract.md`
- `documents/templates/server_host_inventory.template.md`
- `documents/templates/server_runtime_layout.template.toml`
