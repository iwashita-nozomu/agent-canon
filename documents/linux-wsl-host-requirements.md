<!--
@dependency-start
responsibility Documents Linux / WSL Host Requirements for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# Linux / WSL Host Requirements

この文書は、この template を日常利用する host の前提条件をまとめます。
対象は Linux と WSL2 です。macOS や純 Windows native は正本対象にしません。

## 1. 対象

- Ubuntu などの Linux host
- WSL2 上の Linux distro
- bare repo、workspace、Docker build、VS Code dev container を扱う開発 host

## 2. 必須

- Linux filesystem 上で作業できること
- `git` が使えること
- `python3` が使えること
- `make` が使えること
- `docker` か `podman` の少なくとも 1 つが使えること
- repo workspace を置く path が決まっていること
- bare repo を置く path が決まっていること

この template の既定は次です。

- workspace root:
  - `/mnt/l/workspace`
- local bare repo root:
  - `/mnt/git`

`/mnt/git` は optional ではなく、template の local push / subtree sync / bare remote 運用の既定 path とみなします。

## 3. 推奨

- WSL2 では repo workspace を ext4 側に置く
- Docker state と build cache を Linux filesystem 側に置く
- `~/.codex/` と `~/.ssh/` を Linux 側 home に持つ
- `git config user.name` と `git config user.email` を設定する
- `rg` を入れる
- VS Code を使う場合は `.vscode/extensions.json` の推奨拡張を入れる

## 4. WSL2 Rule

- WSL2 を main 開発環境として使って構いません
- repo は `/home/...` か `/mnt/wsl/...` のような Linux filesystem 側へ置くことを推奨します
- `/mnt/c/...` のような Windows drive mount は、I/O、permission、symlink、case sensitivity の点で正本運用にしません
- `/mnt/git` は WSL Linux 側に作ります
- Docker Desktop 連携を使う場合でも、workspace と bare repo は Linux 側 path を既定にします

## 5. Docker / Container Requirement

- `docker version` か `podman version` が通ること
- Docker を使う場合、現在の shell から daemon socket に到達できること
- host で `make docker-build-check` を実行できることを推奨します
- nested Codex や dev container を使う場合、`/mnt/git` を mount できることを推奨します

補足:

- `docker` group にユーザーが入っていても、今の shell に group が反映されていない場合があります
- `getent group docker` に名前があっても `id` に `docker` が無ければ、新しい login shell を開きます

## 6. VS Code Requirement

VS Code を使う場合の既定は次です。

- Dev Containers extension
- Python extension
- Jupyter extension
- Docker extension
- C/C++ extension
- CMake Tools extension

正本は `.vscode/extensions.json` です。

dev container は `.devcontainer/` を使います。起動時に generated compose を作り、

- GPU があれば `gpus: all`
- GPU がなければ CPU-only
- `/mnt/git` があれば bind mount

で動きます。

## 7. GPU Requirement

GPU は必須ではありません。

- CPU-only host:
  - 既定でサポートします
- NVIDIA GPU host:
  - `nvidia-smi` が使えることを推奨します
  - dev container は GPU を検出したときだけ `gpus: all` を追加します

GPU が無いこと自体を failure 条件にしません。

## 8. Codex / Agent Requirement

- `codex` は host に入っていることを推奨します
- container 内の Codex CLI は `docker/Dockerfile` に同梱します
- local bare remote を使う前提なので、host から対象 repository の bare remote と `/mnt/git/agent-canon.git` へ到達できることを確認します

## 9. 最低限の初期確認

```bash
uname -a
python3 --version
git --version
make --version
docker version
test -d /mnt/git
git status --short
make ci-quick
make docker-build-check
```

WSL2 で Docker Desktop 連携を使う場合の追加確認:

```bash
grep -i microsoft /proc/version
docker context ls
```

## 10. 置き場の原則

- workspace は Linux filesystem 側に置く
- bare repo は `/mnt/git` に集約する
- `docker` state、Codex state、SSH key は Linux 側に置く
- template の canonical docs は host-global install を正本にしない

## Related

- [README.md](../README.md)
- [QUICK_START.md](../QUICK_START.md)
- [docker/README.md](../docker/README.md)
- [server-host-contract.md](server-host-contract.md)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
