<!--
@dependency-start
contract reference
responsibility Documents Server Host Contract for this repository.
downstream design ../tools/html_artifact_access.md documents remote HTML artifact access commands
@dependency-end
-->

# Server Host Contract

この文書は、repo を日常運用する main server host の最小契約をまとめます。
remote execution contract が「repo が外部 server から実行される条件」を定義するのに対し、ここでは「この repo を主に回す host 自身が満たすべき条件」を固定します。

readiness は native `agent-canon server-readiness` command で確認します。Python を使う
server workflow や Docker builder は layout で選択した場合だけ host requirement になります。

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

- repository 操作に使う `git` が利用可能であること
- bare repo root と workspace root が決まっていること
- local state を置く Linux filesystem 側 path が決まっていること
- `codex`, Python runtime, container builder は host layout で必要と宣言した場合に利用可能であること
- Docker builder を選択した場合、現在の shell から daemon が利用可能であること
- `origin` push、mirror hook、artifact root の責務分担が文書化されていること

## 推奨

- bare repo root を 1 か所に集約する
- shared workspace root を 1 か所に集約する
- Docker を使う場合は state を local Linux filesystem に置き、CIFS / 9p / network share に置かない
- host inventory を
  `vendor/agent-canon/templates/documents/server_host_inventory.template.md`
  で記録する
- path / mount / builder 前提を
  `vendor/agent-canon/templates/documents/server_runtime_layout.template.toml`
  で明文化する
- `tools/bin/agent-canon server-readiness` で host の基本 readiness を確認する
- `AGENT_CANON_HOST_WORKSPACE_ROOT=/path/to/workspace tools/bin/agent-canon server-readiness`
  または `--layout <layout.toml>` で、対象 workspace と host-specific requirements を明示する

## Storage Rule

- bare repo root と shared workspace root は分けます
- network share を使う場合でも、Docker state と socket は local Linux filesystem 側に置きます
- `/workspace/.state/` に永続化したいものがある場合、host 側でもどこへ残るかを決めます

## Container Runtime Rule

- native AgentCanon command は Docker を必要としません。shared tool runtime や選択した host workflow が Docker を必要とする場合だけ builder を layout に指定します
- Docker builder を選択したら `docker version` が成功することを確認します。local socket を使う構成では現在の shell に socket access が必要です
- Docker を使わない host では Docker CLI、daemon、socket、state root は readiness の必須条件ではありません
- project が公開する `docker-build-check` command は、その project の test runner から実行します

## Remote Browser Artifact Rule

- local PC から SSH で HPC host に入り、その上の container で HTML report を生成する場合、local browser は container 内の `127.0.0.1` を直接見られません。この閲覧経路は任意で、選んだときだけ host Python を使います
- HTML artifact は、ファイルが見えている shell で `python3 -m http.server` を立て、local PC から HPC host への SSH tunnel で見る導線を既定にします
- canonical command generator は `python3 tools/experiments/artifacts/html_artifact_access.py <report.html>` です。`AGENT_CANON_SSH_HOST` または `SSH_CONNECTION` から SSH target を推定し、推定できない場合だけ tunnel command 内の `<ssh-host>` を置き換えます
- container 内だけにある report では `--use-container-ip` を使い、出力された server、tunnel、local URL を closeout evidence に残します
- default bind は `127.0.0.1` です。container-direct mode では container IP へ tunnel するため、container 内の server は `0.0.0.0` bind を使います

## WSL / Shared Mount Rule

- WSL2 を main host にすること自体は許容します
- ただし、CIFS / 9p / network share と local ext4 を混同せず、どの path がどの filesystem かを inventory に残します
- bare repo や共有 workspace を network share に置く場合、Docker state と build cache は local ext4 側に残します
- symlink、file permission、case sensitivity、I/O 特性の差を前提にします

## Git Rule

- GitHub canonical remote と authentication state を記録します
- GitHub publish / PR 作業は [GitHub publication contract](../tools/github_publish.md) の canonical entrypoint を使います

## Validation

AgentCanon standalone source root では source-root の template を指定します。

```bash
tools/bin/agent-canon server-readiness
AGENT_CANON_HOST_WORKSPACE_ROOT=/path/to/workspace \
  tools/bin/agent-canon server-readiness
tools/bin/agent-canon server-readiness \
  --layout templates/documents/server_runtime_layout.template.toml
```

Template / derived parent root では vendored AgentCanon の template を指定します。

```bash
agent-canon server-readiness
AGENT_CANON_HOST_WORKSPACE_ROOT=/path/to/workspace \
  agent-canon server-readiness
agent-canon server-readiness \
  --layout vendor/agent-canon/templates/documents/server_runtime_layout.template.toml
```

Container runtime は次の command で確認します。

```bash
make docker-build-check
make docker-build-check-host-docker
```

## Related

- [documents/contracts/linux-wsl-host-requirements.md](linux-wsl-host-requirements.md)
- [documents/contracts/remote-execution-repo-contract.md](remote-execution-repo-contract.md)
- `vendor/agent-canon/templates/documents/server_host_inventory.template.md`
- `vendor/agent-canon/templates/documents/server_runtime_layout.template.toml`
