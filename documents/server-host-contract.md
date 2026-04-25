<!--
@dependency-start
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# Server Host Contract

この文書は、repo を日常運用する main server host の最小契約をまとめます。
remote execution contract が「repo が外部 server から実行される条件」を定義するのに対し、ここでは「この repo を主に回す host 自身が満たすべき条件」を固定します。

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

## WSL / Shared Mount Rule

- WSL2 を main host にすること自体は許容します
- ただし、CIFS / 9p / network share と local ext4 を混同せず、どの path がどの filesystem かを inventory に残します
- bare repo や共有 workspace を network share に置く場合、Docker state と build cache は local ext4 側に残します
- symlink、file permission、case sensitivity、I/O 特性の差を前提にします

## Git And Mirror Rule

- bare repo root、mirror hook path、mirror remote の関係を必ず記録します
- `tools/push_origin.sh` を canonical push 入口にし、mirror は bare repo hook 側へ寄せます
- host 固有の mirror 手順は `notes/github-mirror-procedure.md` に残します

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
- `notes/github-mirror-procedure.md`
