<!--
@dependency-start
contract design
responsibility 親レポの devcontainer 所有境界と直接参照の契約を定義する。
upstream design ../../runtime/SHARED_RUNTIME_SURFACES.md shared runtime surface ownership and topology
upstream design ../../runtime/shared-runtime-surfaces.toml machine-readable shared runtime surface manifest
upstream design ../../contracts/github-first-module-and-devcontainer-policy.md devcontainer ownership boundary
downstream implementation ../../../tools/agent_tools/surface_manifest.py materializes and checks shared surface entries
downstream implementation ../../../tools/agent_tools/requirements_lock.py owns canonical requirements lock parsing and typed errors
downstream implementation ../../../tools/agent_tools/devcontainer_dependencies.py consumes requirements records for parent boundary validation
downstream implementation ../../../tools/sync_agent_canon.sh materializes AgentCanon root views
downstream implementation ../../../tools/agent_tools/parent_repo_readiness.py checks the minimum parent structure
downstream implementation ../../../tools/ci/container_config.py validates parent environment names without shell execution
downstream implementation ../../../.devcontainer/generate-runtime-compose.sh inventories optional host mounts and projects host zshrc
downstream design parent-dependency-manifest-followup.md declares the parent manifest, pin, and ordering follow-up
@dependency-end
-->

# 親レポの devcontainer 境界

## 最低限の構造

親レポの `.devcontainer/` は親が所有する実ディレクトリです。最低限、次だけを
固定します。

- `.devcontainer/devcontainer.json` は
  `vendor/agent-canon/.devcontainer/devcontainer.json` への symlink。
- 親固有の処理がある場合は `.devcontainer/post-create-parent.sh` に置く。
- `.devcontainer/parent-environment.sh` と
  `.devcontainer/parent-environment.toml` は legacy evidence として残っていてもよい
  が、devcontainer create、shell startup、runtime/tool availability の入力にしない。
  parent固有のruntime値は Docker `ENV`、devcontainer `containerEnv`、明示 bootstrap
  または workspace source へ移す。
- AgentCanon の共有スクリプトを親 `.devcontainer/` にコピーしたり、wrapper を
  追加したりしない。

この最低限以外の親レポ固有ディレクトリやファイルを禁止しない。構造検査は
この所有境界と symlink の健全性だけを確認し、親レポの拡張余地を奪わない。

## 直接参照

symlink 先の `devcontainer.json` は、親レポのルートから AgentCanon の実体を
直接呼び出す。

- Compose generator:
  `vendor/agent-canon/.devcontainer/generate-runtime-compose.sh`
- post-create:
  `vendor/agent-canon/.devcontainer/post-create.sh`
- post-attach:
  `vendor/agent-canon/.devcontainer/post-attach.sh`

generator は host file bind を inventory し、defaultでは `/workspace` の repository
mount と GPU device/driver runtime passthrough だけを使用します。host `${HOME}/.zshrc`
は regular file の場合だけ `/home/project/.zshrc` へ read-only projection する唯一の
optional user-customization mountです。欠落・directory・symlinkの場合は mount を省略し、
image-owned empty/default `.zshrc` で同じ機能を提供します。

host credentials/config、`parent-environment.sh`、`~/.codex`、previous container
state、Docker socket、SSH agent、private secret、`/mnt/git` は default mount では
ありません。必要な場合だけ `AGENT_CANON_OPTIONAL_MOUNTS` の明示 profile で有効化
できます。Docker-in-Docker/host daemon は `docker-host` profile に限定し、successful
create と declared tool availability の前提にしません。

validator は generated Compose の全 volume target をこの inventory と照合する。
fresh clone / CI runnerの現在のhost fileはprobeしない。runtime state は
`CONTAINER_LOCAL` を default とし、host runtime projection は明示 profileだけで
`MANAGED_CONTAINER` にする。

## Ubuntu platform-owned apt records

AgentCanon の apt records は親の canonical base `Ubuntu 22.04 linux/amd64` に固定する。
公式 package metadata は [Ubuntu Jammy archive](https://archive.ubuntu.com/ubuntu/dists/jammy/)
と [Ubuntu Jammy package index](https://packages.ubuntu.com/jammy/) を使い、各 apt record
の `platform = "linux/amd64"` と `source = "ubuntu:22.04"` が package version の
owner です。現在の固定値は manifest の record readbackで次のとおりです。

| records | version |
| --- | --- |
| `texlive-latex-*`, `texlive-fonts-recommended`, `texlive-pictures`, `texlive-xetex`, `texlive-extra-utils` | `2021.20220204-1` |
| `latexmk` | `1:4.76-1` |
| `dvisvgm` | `2.13.1-1` |
| `ghostscript` | `9.55.0~dfsg1-0ubuntu5.13` |
| `poppler-utils` | `22.02.0-2ubuntu0.13` |
| `jq` | `1.6-2.1ubuntu3.2` |
| `tree` | `2.0.2-1` |
| `clang-format` | `1:14.0-55~exp2` |

`Ubuntu 24.04` record、暗黙のdistribution fallback、platformを跨ぐ再解決は存在
しない。runtime platformがrecord platformと一致しない場合、typed dependency planは
install前にfail closedする。

generator は既存の `pack.runtime.shell` を process boundary として使います。親の
default pack は zsh を選び、明示的な bash pack と smoke shell は bash のままです。
zsh とその descendants は image `ENV` と devcontainer `containerEnv` から runtime値を
受け取ります。zsh startup は parent environment をsourceしません。関連する
Compose-owned environment は `HOME`、`SHELL`、`AGENT_CANON_CONTAINER_USER` です。
`HOME` は dedicated non-root userの `/home/project` であり、zsh startupはoptional
host zshrcの有無にかかわらずimage-owned startup fileから開始します。
standalone AgentCanon source layout では host `~/.zshrc`、parent environment mount、
`HOME`、tmpfs を要求せず、pack-derived command だけを生成します。

Compose の生成先は親レポの `.agent-canon/docker-compose.generated.yml` とする。
`.agent-canon/` は親レポの実行状態用であり、生成 Compose を追跡対象にしない。

## post-create の順序

`postCreateCommand` は AgentCanon の共有 `post-create.sh` を先に呼び、成功した
後に親固有の `post-create-parent.sh` を直接呼ぶ。共有処理が失敗した場合は親固有
処理へ進まない。親固有処理の失敗も devcontainer 作成の失敗として扱う。

shared post-create の内部順序は
fixed bootstrap、親 manifest、vendor manifest、全体 validation、
topological derived execution、親の
docker/install_python_dependencies.sh、AgentCanon build/cache/projection の順です。
この shared command の完了後に、devcontainer.json の直接参照が親の
post-create-parent.sh を最後に実行します。詳細な親側 follow-up は
parent-dependency-manifest-followup.md に従います。

AgentCanon は mounted tool のために独立した pinned PyYAML record を持ちます。
親が `docker/requirements.txt` または親 manifest で PyYAML を宣言している場合も、
その親 ownership は保持します。fixed bootstrap の packaging / tomli 契約はこの
source change で変更せず、親の Python 3.11 移行時の tomli 整理は親側 follow-up
です。依存 manifest の plan validation が pass するまで install は開始しません。

## requirements lock の parser ownership

`tools/agent_tools/requirements_lock.py` は、`docker/requirements.txt` の PEP 508
requirement、コメントと URL fragment、marker、backslash continuation、
`--hash=sha256:<64 hex>` option を logical record へ変換する唯一の parser owner
です。parser は `RequirementParseResult` と typed `RequirementParseError` を返し、
invalid option、孤立 hash、malformed hash、malformed または unterminated
continuation、malformed PEP 508 record を fail-closed で表現します。

`tools/agent_tools/devcontainer_dependencies.py` は active record の normalized
package name を親境界の required set と比較し、`tools/ci/container_config.py`
は同じ result/error を `Finding` へ projection します。後者は Dockerfile、pack、
devcontainer、VS Code などの非 requirements 設定検査を引き続き所有します。
両 consumer は line/string parser、PEP 508 parser、hash validator を持たず、
wrapper や test-only bypass を追加しません。依存方向は consumer から
`requirements_lock.py` への一方向とし、owner module は consumer を import しません。

parser の正常 pip-compile fixture と異常分岐は
`tests/agent_tools/test_requirements_lock.py` に集約し、consumer tests は
canonical `result/error` の findings projection だけを確認します。

## Evidence And Assumption Ledger

| kind | statement | evidence / owner | status |
| --- | --- | --- | --- |
| current state | `devcontainer_dependencies.py` と `container_config.py` が別々に requirements の line/string parser を持っていた | `tools/agent_tools/devcontainer_dependencies.py`, `tools/ci/container_config.py`, #490 source diff | observed |
| target state | `requirements_lock.py` が logical record、hash、marker、continuation、typed error の唯一の parser owner になり、両 consumer は projection だけを行う | `tools/agent_tools/requirements_lock.py`, dependency graph, focused owner/consumer tests | fixed |
| validation | PR #126 の `docker/requirements.txt` は `1862` lines、`147` records、`1372` hashes として両 consumer で findings 0 になる | `tests/agent_tools/test_requirements_lock.py`, parent PR #126 readback, `EnvironmentBoundaryModel`, `validate_requirements` | checked |
| assumption | `RequirementRecord.is_active` evaluates markers in the current Python environment; inactive records do not satisfy the consumer required set | `RequirementRecord.is_active`, `devcontainer_dependencies.py`, `container_config.py` | explicit |

## 禁止する重複

- `.devcontainer` 全体を symlink にする。
- AgentCanon の共有 script を親側へコピーする。
- 共有 script を呼ぶだけの親 wrapper を作る。
- 生成 Compose を `.devcontainer/` と `.agent-canon/` の両方へ作る。
- parent environment の値を Compose に複製したり、別の shell configuration
  mechanism を追加したりする。

AgentCanon の共有実装を変更するときは AgentCanon source clone で変更し、PR を
`main` に統合してから、親レポの submodule pin を更新する。

親側の container 操作と image / mounted-tool の責務は
[`../../parent-repository/CONTAINER_OPERATIONS.md`](../../parent-repository/CONTAINER_OPERATIONS.md)
に集約します。
