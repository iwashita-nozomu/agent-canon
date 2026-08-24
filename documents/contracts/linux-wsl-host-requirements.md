<!--
@dependency-start
contract reference
responsibility Documents Linux / WSL Host Requirements for this repository.
upstream design ../../CONTAINER_OPERATIONS.md canonical container and mount ownership policy
upstream design ../design/devcontainer/parent-devcontainer-policy.md default and optional profile contract
upstream design ../design/devcontainer/parent-dependency-manifest-followup.md dependency and source identity contract
@dependency-end
-->

# Linux / WSL Host Requirements

この文書は、この template を日常利用する host の前提条件をまとめます。
対象は Linux と WSL2 です。macOS や純 Windows native は正本対象にしません。

## この文書の読み方

この文書は、Linux / WSL2 host の対象、必須条件、推奨設定、WSL2 rule、Docker / container、VS Code、GPU、Codex / agent、初期確認、置き場の原則を説明します。新しい host を準備するときは対象と必須から読み、devcontainer や GPU を使う場合は該当章へ進みます。macOS と純 Windows native の手順はこの文書の正本対象外です。

## 1. 対象

- Ubuntu などの Linux host
- WSL2 上の Linux distro
- workspace、Docker build、VS Code dev container を扱う開発 host

## 2. 必須

- Linux filesystem 上で作業できること
- `git` が使えること
- `python3` が使えること
- `make` が使えること
- `docker` か `podman` の少なくとも 1 つが使えること
- AgentCanon 自動同期を使う場合は、Linux / WSL の systemd user manager が使えること
- repo workspace を置く path が決まっていること

この template の既定は次です。

- workspace root:
  - `/mnt/l/workspace`
- optional confidential local Git / secret root:
  - configured per shell with `AGENT_CANON_SECRET_DIR`

## 3. 推奨

- WSL2 では repo workspace を ext4 側に置く
- Docker state と build cache を Linux filesystem 側に置く
- `~/.codex/` と `~/.ssh/` を Linux 側 home に持つ
- GitHub CLI を host 側で認証し、`~/.config/gh/` を Linux 側 home に持つ
- confidential な local Git repo や operator-local material は repository
  tree ではなく host 側 directory に置き、必要な session だけ
  `AGENT_CANON_SECRET_DIR` で dev container へ渡す
- SSH agent を使う場合は `SSH_AUTH_SOCK` が現在の shell で有効な socket を指す
- `git config user.name` と `git config user.email` を設定する
- repository 検索には Git 標準の path / `git grep` を使える状態にする
- VS Code を使う場合は AgentCanon-managed `.vscode/extensions.json` の推奨拡張を入れる

## 4. WSL2 Rule

- WSL2 を main 開発環境として使って構いません
- repo は `/home/...` か `/mnt/wsl/...` のような Linux filesystem 側へ置くことを推奨します
- `/mnt/c/...` のような Windows drive mount は、I/O、permission、symlink、case sensitivity の点で正本運用にしません
- Docker Desktop 連携を使う場合でも、workspace は Linux 側 path を既定にします

## 5. Docker / Container Requirement

- `docker version` か `podman version` が通ること
- AgentCanon の公開 runtime image は `linux/amd64` と `linux/arm64` の OCI index から
  Docker が native variant を選択します。手動 `--platform` 指定や各PCでの build は
  AgentCanon 同期経路では行いません。
- Docker を使う場合、現在の shell から daemon socket に到達できること
- host で `make docker-build-check` を実行できることを推奨します
- default devcontainer は host `sudo`、system group、または runtime directory の
  事前作成を要求しません。GPU admission `gpu-admission` opt-in profile は
  repository-local `${repository_root}/.agent-canon/runtime` を user-owned primary
  UID/GID で作成し、container の `/var/lib/agent-canon/runtime` へ bind します。

補足:

- `docker` group にユーザーが入っていても、今の shell に group が反映されていない場合があります
- `getent group docker` に名前があっても `id` に `docker` が無ければ、新しい login shell を開きます

## 6. Dev Container / VS Code Requirement

VS Code を使う場合の既定は次です。

- Dev Containers extension
- Python extension
- Jupyter extension
- Docker extension
- C/C++ extension
- CMake Tools extension

正本は AgentCanon-managed root view の `.vscode/extensions.json` です。

dev container は `.devcontainer/` を使います。起動時に generated compose を作り、
既定 profile は workspace-source-only です。parent environment、host file、host
credentials、SSH、Docker socket、secret、host runtime state のどれも既定起動の
前提にしません。これらが host に無い fresh clone / CI runner でも同じ既定 runtime
を生成します。

- default profile は host GPU/NVIDIA runtime を probe せず、
  `DEVCONTAINER_GPU_MODE=disabled` を設定し、`DEVCONTAINER_GPU_REQUEST` と
  `gpus: all` を生成しない
- GPU が必要な場合の device / driver runtime passthrough は明示的に選択した
  `gpu-admission` profile の責務とし、profile が選択されない場合は CPU-only の既定起動を
  継続する。profile が選択されて host capability が無い場合は default へ降格せず
  fail-closed とする。profile の実装と validation の正本は
  [`CONTAINER_OPERATIONS.md`](../../CONTAINER_OPERATIONS.md) と
  [`parent-devcontainer-policy.md`](../design/devcontainer/parent-devcontainer-policy.md)、
  selector は `.devcontainer/gpu-admission/devcontainer.json`、orchestrator は
  `.devcontainer/gpu-admission.sh` とする
- credentials、SSH agent、Docker socket、secret、host git は、それぞれ明示選択した
  optional profile の対象が存在するときだけ追加する。欠落した host path、socket、
  directory は mount/forward を行わず、既定 runtime を failure にしない
- optional profile の名前、target、read-only、fixed secret target の表は
  [`CONTAINER_OPERATIONS.md`](../../CONTAINER_OPERATIONS.md) と
  [`parent-devcontainer-policy.md`](../design/devcontainer/parent-devcontainer-policy.md)
  が所有する。この host contract は同じ表を複製しない
- subnet / gateway は固定せず、Docker Compose の default network 自動割当に任せる

で動きます。

## 7. GPU Requirement

GPU は必須ではありません。

- CPU-only host:
  - 既定でサポートします
- NVIDIA GPU host:
  - `nvidia-smi` は GPU 実験を明示的に選択する場合だけ確認します。default generator は probe しません
  - default dev container は GPU を検出しても `gpus: all` を追加せず、`DEVCONTAINER_GPU_MODE=disabled` を出力します
  - device、driver runtime、shared lock、runtime receipt、GPU scheduler は default の
    host requirement ではありません。これらを使う場合は明示 `gpu-admission` profile
    が `nvidia-smi -L`、repository-local user-owned source、primary UID/GID bind、
    receipt lifecycle、absence/failure semantics を所有します。

GPU が無いこと自体を failure 条件にしません。

## 8. Codex / Agent Requirement

- `codex` は host に入っていることを推奨します
- AgentCanon の Codex/tool runtime は source clone の `bootstrap.sh` が管理する共有非 root
  container で起動します。親の `.devcontainer` はこの runtime の installer/fallback ではありません
- container 内の Codex state は container-local です。認証に使う
  `OPENAI_API_KEY` と `OPENAI_BASE_URL` は runner の明示的な環境 forward で渡します。
- `gh` は host に入っていることを推奨します。AgentCanon tool container には GitHub 認証や
  host credentials を暗黙に渡しません。Issue/PR 操作は host workflow の責務です
- 初回 `gh auth login`、SSH key、GitHub host key 登録は host 側で行います。container
  から credentials または SSH を再利用する場合は、明示 optional profile を選択し、
  対象が存在するときだけ read-only mount または valid socket forward を使います。
- Docker socket と confidential secrets も既定では渡しません。必要な session だけ
  owner docs の `docker-host` または `host-secrets` profile を明示し、対象が無い場合は
  mount を省略します。
- AgentCanon source PR、eval archive、Issue/PR 操作を行う場合だけ、host から対象 GitHub remote へ到達できることを確認します。親は AgentCanon submodule を要求しません
- Linux / WSL の AgentCanon 自動同期は `agent-canon-sync.service` の one-shot 実行と
  `agent-canon-sync.timer` のみを使います。`scheduler enable` が systemd user manager
  を利用できない場合は `systemd_user_unavailable` を返し、手動の one-shot `sync` は継続して
  利用できます。
- confidential local Git remote を dev container から使う場合は、起動前に
  `AGENT_CANON_SECRET_DIR` と、書き込みが必要なときだけ
  `AGENT_CANON_SECRET_DIR_MODE=rw` を設定します。container 側 path は
  `AGENT_CANON_SECRET_MOUNT` で上書きできます。

## 9. 最低限の初期確認

```bash
uname -a
python3 --version
git --version
make --version
docker version
git status --short
make ci-quick
make docker-build-check
```

`gh auth status`、`ssh -T git@github.com`、secret directory、Docker socket、
`nvidia-smi` の確認は、対応する optional profile を明示選択した session だけで
行います。profile を選択しない既定確認は host file、credential、socket、GPU の
存在を要求しません。

WSL2 で Docker Desktop 連携を使う場合の追加確認:

```bash
grep -i microsoft /proc/version
docker context ls
```

## 10. 置き場の原則

- workspace は Linux filesystem 側に置く
- confidential local Git repo や secret material は repo tree に置かず、
  `AGENT_CANON_SECRET_DIR` で明示した host directory に置く
- `docker` state、Codex state、SSH key は Linux 側に置く。container への mount は
  owner docs の明示 optional profile に限定する
- template の canonical docs は host-global install を正本にしない

## Related

- [README.md](../README.md)
- Template-derived repositories may add root-local `QUICK_START.md` and `docker/README.md`.
- [server-host-contract.md](server-host-contract.md)
- [CONTAINER_OPERATIONS.md](../../CONTAINER_OPERATIONS.md)
- [parent-devcontainer-policy.md](../design/devcontainer/parent-devcontainer-policy.md)
- [TROUBLESHOOTING.md](../operations/TROUBLESHOOTING.md)
