<!--
@dependency-start
contract design
responsibility 親レポの devcontainer 所有境界と直接参照の契約を定義する。
upstream design ../../runtime/SHARED_RUNTIME_SURFACES.md shared runtime surface ownership and topology
upstream design ../../runtime/shared-runtime-surfaces.toml machine-readable shared runtime surface manifest
upstream design ../../contracts/github-first-module-and-devcontainer-policy.md devcontainer ownership boundary
downstream implementation ../../../tools/agent_tools/surface_manifest.py materializes and checks shared surface entries
downstream implementation ../../../tools/agent_tools/devcontainer_dependencies.py validates the mounted manifest and typed project extras
downstream implementation ../../../tools/sync_agent_canon.sh materializes AgentCanon root views
downstream implementation ../../../tools/agent_tools/parent_repo_readiness.py checks the minimum parent structure
downstream implementation ../../../tools/ci/container_config.py validates parent environment names without shell execution
downstream implementation ../../../.devcontainer/devcontainer.json selects the default startup profile
downstream implementation ../../../.devcontainer/generate-runtime-compose.sh renders the workspace-only default and typed optional mount profiles
downstream implementation ../../../.devcontainer/gpu-admission/devcontainer.json selects the explicit GPU-admission profile
downstream implementation ../../../.devcontainer/gpu-admission.sh owns GPU-admission host preflight/up/finalize sequencing
downstream design parent-dependency-manifest-followup.md declares the parent manifest, pin, and ordering follow-up
@dependency-end
-->

# 親レポの devcontainer 境界

## 最低限の構造

親レポの `.devcontainer/` は親が所有する regular directory です。最低限、次だけを
固定します。derived parent は `.devcontainer/devcontainer.json` を regular ファイルとして所有します。

- `devcontainer.json`、selector、script、manifest は親の environment contract が
  必要に応じて所有します。AgentCanon source からの symlink、child projection、
  自動コピーは要求しません。
- 親固有の処理がある場合だけ `.devcontainer/post-create-parent.sh` に置く。
  ファイルが無い場合は親固有の final hook なしとして扱う。
- 親固有の developer/agent tool がある場合だけ
  `.devcontainer/dependencies.toml` に置く。ファイルが無い場合は parent
  overlay なしとして vendor の canonical manifest だけを読む。
- `.devcontainer/parent-environment.sh` と `.devcontainer/parent-environment.toml`
  は既定 devcontainer の入力ではない。存在する場合の監査対象にはできるが、
  bind mount、shell startup、tool availability の前提にしない。
- AgentCanon の共有スクリプトを親 `.devcontainer/` にコピーしたり、wrapper を
  追加したりしない。

この最低限以外の親レポ固有ディレクトリやファイルを禁止しない。構造検査は
この所有境界と必要な file-kind だけを確認し、親レポの拡張余地を奪わない。

## 親環境の値と名前

監査対象として親環境の組を配置した場合、`parent-environment.sh` が親環境の値と定義の唯一の
source です。validator は symlink 自体の file type ではなく解決先の実在性を確認し、
このファイルを shell として実行せず、空行・コメントと `export NAME=value` 形式の
行だけを静的に読みます。`parent-environment.toml` は次の形で ordered variable
names だけを持ちます。

```toml
variables = ["PROJECT_TOKEN", "PROJECT_REGION"]
```

validator は export name と TOML の `variables` を順序付きで完全一致させます。
許可されない shell 行、重複名、未知の TOML key、name の不正、順序差は failure
です。構造検査でファイルが存在しても、値の定義、Compose の意味、image の zsh
startup、host premise の十分条件を証明したことにはなりません。組が存在しない
場合は親環境 contract なしとして検査を成功させます。

## 直接参照

親の regular devcontainer files は、親レポの root contract と source-root resolver
が選択する実体を直接呼び出します。

- AgentCanon 側の parent check は `parent` の `.devcontainer` に対して
  `devcontainer.json` の存在確認と JSON-object parse のみを行う。
  生成内容や packed 生成物の内容同一性、identity/lifecycle/Compose/rootless/GPU
  の projection/validation はこの owner boundary で実施しない。
  standalone 側の厳密ルールは standalone ルートで維持される。

default generator は parent environment、host credentials、SSH、Docker socket、
host runtime state を mount しない。host zshrc は `host-zshrc` optional profile が
明示され、regular file または regular fileへ解決する symlink があるときだけ
`realpath -e` の canonical absolute source から追加する。profile が選択されても
欠落・broken symlink・型違いでは同じ default runtime を生成する。

- `host-zshrc`: resolved host `~/.zshrc` -> selected runtime `HOME/.zshrc` read-only
  （resolved regular directory `~/.zsh` がある場合は selected runtime `HOME/.zsh` も
  read-only。`project` は `/home/project`。）
- `host-git`: existing `/mnt/git` -> `/mnt/git`
- `host-credentials`: existing `~/.config/gh`/`~/.ssh` -> selected runtime `HOME` read-only
  （`project` は `/home/project`。）
- `ssh-agent`: valid socket only -> `/ssh-agent`
- `host-secrets`: existing `AGENT_CANON_SECRET_DIR` -> fixed `/mnt/agent-canon-secrets`
- `docker-host`: existing Docker socket -> `/var/run/docker.sock`
- `linked-data-roots`: pack-defined repository symlinks -> their declared `/mnt/<letter>/<subpath>`
  targets as structured read-write binds

`runtime.optional_mount_profiles` は既知 profile の string array とし、pack内の順序を
保持します。`AGENT_CANON_OPTIONAL_MOUNTS` は空要素・whitespace・unknown・duplicateを
拒否する comma list です。生成時の canonical profile union は pack 順を先に置き、環境
だけに現れる profile を環境順で後置し、pack と環境の重複は pack 側を first-wins とします。
plain pack と空の環境では host mount は生成しません。

`linked-data-roots` は profile と `runtime.linked_data_roots` inline table array の
存在を相互必須とします。各 entry は `{link, target}` の二フィールドだけで、`link` は
normalized repo-relative symlink、`target` は `/mnt/[a-z]/<nonempty-subpath>` です。
短い Docker bind 表記を安全に構成するため target に `:`、`,` は含めません。
absolute、empty、`.`、`..`、repo外、非symlink、reserved/broad root、重複 source/target
は拒否します。generator は `realpath -e` した既存 directory が declared target と
exact に一致することを確認し、`source == target`、`read_only: false` の structured
bind だけを出力します。validator は host probe を行わず、typed pack と生成 Compose
の target/source/type/read-write を照合します。

validator は profile と target の一致、bind type、resolved absolute source、read-only、
fixed secret target を静的に確認する。fresh clone / CI runnerのhost fileは必要条件ではない。
`ZDOTDIR`、`.zshenv`、`/etc/project-template/zsh`、parent environment source は
default shell startup に存在しない。user customization は image-ownedまたは
selected runtime `HOME/.zshrc`（`project` は `/home/project`）だけであり、noninteractive command、sudo、post-create は
`.zshrc`に依存しない。

generator は既存の `pack.runtime.shell` を process boundary として使います。親の
default pack は zsh を選び、明示的な bash pack と smoke shell は bash のままです。
runtime env は image と generated Compose の明示経路だけで供給し、
zsh startup に parent environment の source を隠さない。関連する Compose-owned
environment は `HOME`、`SHELL`、`AGENT_CANON_CONTAINER_USER`、
`AGENT_CANON_RUNTIME_ROUTE`、`AGENT_CANON_CODEX_SESSION_ROOT` です。後者は
runtime-log ownerが利用するcontainer-local selected `HOME/.codex/sessions` を
指し、host `~/.codex` のmountやfallbackを意味しません。
`HOME` は `project` では `/home/project` であり、zsh startupはoptional
host zshrcの有無にかかわらずimage-owned startup fileから開始します。
standalone AgentCanon source layout でも `host-zshrc` profile は parent layout と同じ
host `~/.zshrc`/`~/.zsh` optional projectionを使えます。profile未選択時は host
`~/.zshrc`、parent environment mount、`HOME`、`ZDOTDIR`、tmpfs を要求せず、
pack-derived command だけを生成します。

Compose の生成先は親レポの `.agent-canon/docker-compose.generated.yml` とする。
`.agent-canon/` は親レポの実行状態用であり、生成 Compose を追跡対象にしない。

## 既定起動プロファイルの境界

### 設計フレーム

- audience: AgentCanon maintainer と derived-repo operator
- decision context: default devcontainer の privilege/runtime boundary
- first artifact: 本節「既定起動プロファイルの境界」
- visual plan: default と保持する opt-in candidate の短い列挙（追加図は不要）
- document split: 同じ owner、reader map、source map、validation route を持つため、この設計文書から分割しない
- invalid interpretations: experiment framework の wholesale deletion、managed runner semantics の書換え、image-owned dependency lifecycle の回避
- validation gate: detailed design review と prose/docs check の後に実装 route へ進む

### ユーザー指示による superseding decision

canonical build identity は user name `project` と numeric primary GID
`PROJECT_GID` で固定する。
親の default Dockerfile は digest-pinned plain
`ubuntu:22.04` base（または同等の標準 Ubuntu 22.04 image）を使い、generator が
解決した numeric UID/GID を build args として渡す。`PROJECT_UID` は decimal の
non-zero 値、`PROJECT_GID` は decimal の non-negative 値（`0` を含む）とし、
公開 caller がこれらの値や user 名を override する経路は設けない。generator は
custom HOME tmpfs、AgentCanon-specific group、host group mutation を生成しない。

image account materialization は `project` user を `PROJECT_UID` で作成し、その
primary GID を `PROJECT_GID` に固定する。要求された numeric GID が既存 group に
割り当て済みの場合（GID `0` の `root` group を含む）は、その group を primary group
として再利用し、group name を変更・`project` に rename しない。要求された GID が
未使用の場合だけ、group name `project` をその GID で作成する。既存 group name と
要求 GID の collision は fail-closed とし、既存 group の rename や別 GID への移動で
解決しない。したがって `project` user の固定と、primary group の numeric ID の固定を
分離し、既存 GID に group name `project` があることを要求しない。

### Docker daemon と runtime identity の境界

Docker daemon の rootful、rootless、user-namespace mapping という実装 mode は
この contract の外側にあり、generator は daemon metadata または daemon mode を
probe して runtime identity を選択しません。`auto` および daemon-derived mode
environment による投影は
default/opt-in contract から除外し、default と `gpu-admission` の両方で
`project` identity だけを使用します。

Compose の解決済み `service.user`、`AGENT_CANON_CONTAINER_USER=project`、および
image の `USER project` は同じ `PROJECT_UID` / `PROJECT_GID` input を参照します。
runtime process の UID は decimal の non-zero 値、GID は numeric の non-negative 値
（`0` を含む）でなければなりません。post-create と post-attach は marker、process
uid/gid、`HOME=/home/project`、および workspace path の container-side usability /
writability を read back します。

daemon mapping mode は host-visible numeric ownership を変え得るため、host chmod/chown、
固定 subuid、`userns=host`、tmpfs、特定 workspace path の例外を生成しません。host
zshrc/credentials は明示 optional profile 時だけ selected runtime `HOME` 配下へ
read-only projection します。

### RDC-003 mapping-neutral bind / receipt acceptance

RDC-003 は default の workspace probe だけでなく、明示 `gpu-admission` profile の
shared-runtime bind、`gpu-admission.sh` の provision、`finalize-shared-runtime.sh` の
readback、および `tools/experiments/execution_resource_plan.py` の receipt parser/writer
まで到達します。default post-create と GPU finalize の bind acceptance は、実際の
container-side target で create/write/read/remove を実行できることを oracle とし、host
visible owner、host-vs-container UID/GID、または inode owner の一致を acceptance gate に
しません。UID は process/container 側で non-zero、GID は numeric（`0` を含む）という
独立した contract を維持します。

provision の `host_uid`、`host_gid`、`host_supplementary_gids` と readback の
`container_uid`、`container_gid`、`container_supplementary_gids` は、typed receipt の
provenance/observation fields として保存・fingerprint します。これらの数値を receipt
file owner や相手側の identity と exact に一致させる cross-boundary gate は置きません。
一方、runtime route、repository-local source と canonical target、bind source/target の
device/inode、symlink/type/mode、open-fd/path race、mount namespace と mount
id/root、supplementary-group shape、umask、closed probe、schema/fingerprint、receipt lock と
atomic publication は mapping-neutral な security/receipt gates として維持します。`GID=0`
の受理や UID non-zero はこの緩和の対象外です。

実装の bounded owner は `.devcontainer/gpu-admission.sh`、
`.devcontainer/finalize-shared-runtime.sh`、`tools/experiments/execution_resource_plan.py`
とし、`read_shared_runtime_provision`、`read_shared_runtime_readback`、
`RuntimeIdentityReader.read` の mapping-sensitive equality をこの contract に合わせて
修正します。focused validation は `tests/tools/test_gpu_admission_devcontainer.py`、
`tests/tools/test_run_codex_in_repo_container.py`、`tests/tools/test_execution_resource_plan.py`
（および選択された managed-run receipt consumer tests）で、route/path/mount/fingerprint/
atomic publication と operation-based usability を別々に read back します。

親 Dockerfile は root phase で system package、wgrib2、Python build-time setup と
`project` user、`PROJECT_GID` を primary GID とする group materialization、
container-local runtime を準備し、最後に `USER project` へ
切り替える。Node/npm は digest-pinned official OCI provider から image build 中に
取り込み、AgentCanon manifest の全 image-safe record も同じ build 中に
`/usr/local/share/agent-canon/image-dependencies` へ immutable materialize する。
post-create はその tree の read-only `image-verify` と container runtime readback だけを
行い、package install、network、sudo、workspace bind の repair を行わない。CUDA/GPU
image は default に含めず、GPU capability は明示 `gpu-admission` profile が所有する。

Standalone AgentCanon source checkout は `.devcontainer/Dockerfile` を同じ
digest-pinned Ubuntu 22.04 / `PROJECT_UID` / `PROJECT_GID` / `project` account contractで直接
buildする。official Node 22.14.0 bullseye-slim provider は固定 digest で参照する。
standalone generator は `image: ubuntu:22.04` の fallbackを生成せず、このDockerfileと
build argsをComposeに出力する。親repositoryの
`docker/packs/default.toml` がある場合は親owned Dockerfileのbuildを継続する。

### DEV-DEFAULT-001〜DEV-DEFAULT-012 / DEV-GPU-001〜DEV-GPU-005: operation -> resulting state -> completion evidence

既定の `devcontainer up` は、利用者の host セッションを変更しない
unprivileged profile とする。`devcontainer.json` の `initializeCommand` は
Compose generator だけを呼び、host の `sudo`、system group、または
`/var/lib/agent-canon/runtime` の事前作成を要求しない。
default generator は host GPU、`nvidia-smi`、Docker NVIDIA runtime を probe せず、
生成 environment は `DEVCONTAINER_GPU_MODE=disabled`、`DEVCONTAINER_GPU_REQUEST`
absent を正本とする。

| clause | operation | resulting state | completion evidence |
| --- | --- | --- | --- |
| DEV-DEFAULT-001 | `initializeCommand` から host runtime provisioning を外し、Compose generator を実行する | 既定起動が `sudo`、system group、host runtime path に依存しない | `devcontainer.json` の command readback と `devcontainer up` が sudo prompt なしで完了する |
| DEV-DEFAULT-002 | 既定 Compose の shared-runtime `group_add`、bind、provision/readback receipt environment、custom HOME tmpfs、AgentCanon-specific group を生成せず、`PROJECT_UID` / `PROJECT_GID` を canonical build args として親 image に渡す | generator は decimal `PROJECT_UID` / `PROJECT_GID` を検証し、UID は non-zero、GID は non-negative（`0` を含む）として user name `project` と numeric primary GID を固定する。要求 GID が既存 group に割り当て済みなら、その group（GID `0` の `root` を含む）を primary group として再利用し、name を変更しない。要求 GID が未使用の場合だけ group name `project` を作成し、既存 group name collision は fail-closed とする。公開 caller に override 経路はない。default の `devcontainer.json` は `containerUser`/`remoteUser` を持たず、`updateRemoteUserUID: false` で Compose の解決済み `service.user` を所有する。digest-pinned plain `ubuntu:22.04` の親 image は `PROJECT_UID` の `project` user と `PROJECT_GID` の numeric primary group を materialize し、image の `USER project` で起動する。daemon mode は probe/選択せず、container は container-local `/var/lib/agent-canon/runtime` だけを使用し、host の同名 path とは bind/shared しない。host group mutation と host sudo/password prompt は行わない | 生成 Compose/config/image inspection で `PROJECT_UID`/`PROJECT_GID` の decimal predicate、`getent passwd project`、`id -u`/`id -g`、`getent group <PROJECT_GID>`、既存 GID の group name 維持、unused GID のみ `project` group 作成、group name collision/no-rename、`USER project`、解決済み `service.user`、`updateRemoteUserUID: false` が確認できる。`containerUser`/`remoteUser` の default override、`group_add`、host runtime bind、shared receipt env、custom HOME tmpfs、AgentCanon group、daemon probe/mode env が absent であることも確認する。bind workspace は container 内で expected path の read/write/create/remove が成立すれば受理し、host-visible numeric owner の一致は要求しない。container 内 runtime path が作成される |
| DEV-DEFAULT-003 | 既定 generator は host GPU、`nvidia-smi`、Docker NVIDIA runtime の probing を一切行わず、生成 environment に `DEVCONTAINER_GPU_MODE=disabled` を設定し、`DEVCONTAINER_GPU_REQUEST` は absent とする | GPU の有無に関わらず default container creation は GPU admission から独立し、Compose に GPU request を持たない | generator の command/readback に probing が無く、生成 env が `DEVCONTAINER_GPU_MODE=disabled`、`DEVCONTAINER_GPU_REQUEST` absent、`gpus: all` absent である static inspection と no-GPU launch |
| DEV-DEFAULT-004 | source-root resolver 経由で呼ぶ post-create は image-owned immutable dependency tree の read-only verify と container runtime readback を実行する | package install、network、sudo、workspace bind repair は startup path に存在せず、stored plan/receipts と live package/executable verification が pass する。workspace bind は daemon mapping mode に関係なく container-side expected path の usability / writability を確認し、host-visible owner equality を要求しない。bind が使用可能でない場合も host repair はせず、container-local canonical runtime を使用し、parent hook は verify 後に一度だけ実行される | post-create static inspection、image-verify readback、tool availability、container-local runtime readback、workspace usability/writability probe、parent-hook order test |
| DEV-DEFAULT-005 | `finalize-shared-runtime.sh`、scheduler、managed experiment、receipt parser/writer は source に保持し、既定 profile から非選択にする | 実験機能の wholesale deletion は行わず、`gpu-admission/devcontainer.json` と `gpu-admission.sh` の明示 selector/entrypoint だけが runtime capability を選択する | default selector/config の readback が opt-in fields を持たず、profile selector が別 Compose path/project suffix を使い、Issue #521 の opt-in owner に接続する |
| DEV-DEFAULT-006 | profile boundary、dependency packet、rollback と検証コマンドを owner docs に固定する | 実装者が host runtime provisioning を復活させずに default/opt-in の責務を判定できる | 本節の DIC trace、dependency-design packet、`container_config.py`/dependency validator/launch smoke の結果を readback する |
| DEV-DEFAULT-007 | repository path を `managed-topic` または `direct-repo` layout として判定し、layout に対応する status guard を選択する | 両 layout は exact repository bind を共有し、managed-topic だけが topic marker/status guard を実行する。direct-repo は topic marker/status を要求しない | generated env `AGENT_CANON_WORKSPACE_LAYOUT` が layout 名を示し、post-attach が同じ layout と guard 結果を readback する |
| DEV-DEFAULT-008 | 両 layout で repository root 一つだけを `/workspace/<basename>` に bind し、`devcontainer up --workspace-folder .` を受理する | sibling repository、topic root、親 `~/workspace` 全体を default container に公開せず、layout 判定と mount 範囲を分離する | generated Compose の bind source が exact repo root 一つ、target が `/workspace/<basename>` であり、topic root source と `/workspace` target が absent のまま起動が完了する |
| DEV-DEFAULT-009 | pack/env の既知 optional profile を pack 順、環境-only 順で canonical union し、raw `runtime.mounts` を拒否する。`docker-host` は明示選択時だけ existing Unix socket を read-write bind する | plain pack と空の環境は host mount なしで空の selected profile を持ち、直接 runner と generator が同じ順序・拒否規則を共有する。docker socket 欠落時の直接 runner は fail-closed とする | `container_config.py`、`container_runtime.py`、generator、runtime 回帰テストで profile order、raw mount rejection、socket bind/missing、validator の pack readback を確認する |
| DEV-DEFAULT-010 | `linked-data-roots` 選択時に non-empty inline table array、normalized repo-relative symlink、`realpath -e` の既存 directory、declared target exact match を要求する | generator と直接 runner は source==target の structured read-write bind だけを生成し、missing/file/mismatch、重複、CLI destination collision を fail-closed にする | generator missing/file/mismatch tests、parent-shaped load/run/print-only tests、read-write validator finding で確認する |
| DEV-DEFAULT-011 | standalone default の未選択 profile と devcontainer-only host zsh projection の境界を保ち、host zshrc/.zsh と linked data を明示選択時だけ評価する | standalone plain default は host-independent で空の optional profileを持ち、host zshrc/.zsh は generator scope、linked data は pack-defined direct-runner scope に限定する | standalone generator/config tests と parent/runtime profile readback が profile未選択時の空 mount および selected scope を示す |
| DEV-DEFAULT-012 | project Docker runtime、parent devcontainer、AgentCanon Codex tooling を別 owner として解決し、pack/rules/profile override がない direct route は project `docker/Dockerfile` と AgentCanon source-relative profile default を使う | parent project は `docker/packs/`、`docker/codex-container-profiles.toml`、`docker/python-execution-rules.toml` を必須 surface にせず、存在する project pack/rules と明示 `--profiles` だけを optional override として検証・消費する | packless parent の `container_config.py`、stable repo-marker root resolution、AgentCanon profile path、rules/pack absent の print-only regression が pass する |

この変更の不足は、従来の linked config が host provisioning と container runtime
identity を一つの default lifecycle に結合していた点である。host group の存在や
現在セッションの supplementary group は、親レポの Python 依存や image build の
前提ではなく、利用者ごとに異なる privileged host state である。既定起動からこれを
切り離し、GPU profile でも repository-local source と primary UID/GID だけを使うことで、
権限昇格、固定 GID への依存、host `/var/lib` への永続副作用を除去し、GPU を持たない
CI/開発 host でも同じ container contract を利用できる。

GPU admission の scheduler、shared lock、runtime receipt そのものは削除しない。
これらを必要とする実験は、`gpu-admission.sh` が host capability と receipt contract
を選択したときだけ起動する。既定 profile に opt-in flag を暗黙に推測する fallback
は設けない。default selector と profile selector は異なる Compose output と
project identity を持ち、起動済み default container を profile 起動へ再利用しない。

## 明示 GPU-admission 起動 profile

GPU admission の devcontainer capability は親-owned regular
`.devcontainer/gpu-admission/devcontainer.json` を selector とし、
`.devcontainer/gpu-admission.sh` を唯一の host-side orchestrator とする。
親-owned default の `.devcontainer/devcontainer.json` は変更せず、profile selector が
`gpu-admission-compose.generated.yml` と `-gpu-admission` Compose project suffix を選ぶ。

### DEV-GPU-001〜DEV-GPU-005: operation -> resulting state -> completion evidence

| clause | operation | resulting state | completion evidence |
| --- | --- | --- | --- |
| DEV-GPU-001 | 親-owned profile selector を derived repository で選択し、`gpu-admission.sh` から profile selector を `devcontainer up --config` と `devcontainer exec --config` の両方に渡す | default selector/config/output/container と GPU-admission selector/config/output/container が分離し、exec が別 profile container を選ばない | regular selector、up/exec の exact selector、別 `dockerComposeFile`、`name` suffix、生成 Compose `name` の readback |
| DEV-GPU-002 | `gpu-admission.sh` が `devcontainer`、`nvidia-smi -L`、active repository、selector を確認し、`${repository_root}/.agent-canon/runtime` を `project` の primary UID/GID で作成して provision receipt を発行する | GPU 不在、CLI 不在、selector 不在、runtime UID 0、非 numeric GID、repository-local source、filesystem、umask、receipt precondition は fallback なしで non-zero fail になる。GID `0` は numeric input として受理し、既存 GID の group は再利用して rename しない。provision の host UID/GID は provenance として記録するが、container identity との exact equality は bind acceptance に使わない。daemon probe/mode env は profile に存在しない | preflight stderr/exit、provision receipt、`project` user、primary UID/GID、`getent group <PROJECT_GID>`、既存 group name 維持/no-rename、repository-local source、symlink/type/mode/device/inode/race、umask readback |
| DEV-GPU-003 | profile generator が repository-local runtime source、container target、receipt を Compose に投影し、`project` の primary UID/GID、`gpus: all`、GPU/profile environment を生成する | container primary identity は non-zero UID と numeric GID（`0` を含む）を持ち、requested GID の既存 group を再利用し、unused GID のときだけ `project` group を作成する。runtime bind は実際の container-side target で create/write/read/remove が成立する場合だけ受理し、host-visible owner、host-vs-container UID/GID、inode owner の一致は要求しない。GPU request は profile にだけ存在し、`group_add` と supplementary-GID env は存在しない。daemon probe/mode env と `AGENT_CANON_RUNTIME_IDENTITY_MODE` は存在しない | profile Compose scenario validation、source/target、`user: UID:GID`、`getent passwd/group`、numeric primary-group readback、operation-based runtime usability probe、group collision/no-rename、receipt route/path/device/inode/fingerprint、`DEVCONTAINER_GPU_MODE=enabled`、`DEVCONTAINER_GPU_REQUEST=all`、canonical receipt paths |
| DEV-GPU-004 | `devcontainer up` 完了後に同じ orchestrator が同じ `--config` の `devcontainer exec` と source-root resolver で `finalize-shared-runtime.sh` を一度呼び、up/finalize failure では生成 Compose の検証済み profile project name を指定して `docker compose down --remove-orphans` を実行する | finalize は derived/standalone の AgentCanon source ownerへ解決され、route/path/mount namespace、source/target device/inode、symlink/type/mode/race、receipt fingerprint、atomic publication、closed probe、UID non-zero/GID numeric を fail-closed で検証する。host/container numeric identity の exact equality は要求しない。失敗時は default へ降格せず exact profile project だけを cleanup し、cleanup 成否と独立に元の rc を保持する | exact exec/finalize command、container-side create/write/read/remove probe、namespace/mount readback、finalize receipt、exact cleanup command、original rc、default/opt-in lifecycle scenario tests |
| DEV-GPU-005 | receipt の parse/read/write を `tools/experiments/execution_resource_plan.py` に委譲する | profile script は receipt parser/writer や identity repair を複製せず、scheduler/managed-run R5 semantics は保持される。`read_shared_runtime_provision` / `read_shared_runtime_readback` の receipt-file-owner equality と `RuntimeIdentityReader.read` の host/container UID/GID equality は mapping-sensitive acceptance gate ではなく、typed provenance/observation と route/path/mount/fingerprint/security checks を分離して扱う | dependency header、symbol readback、provision/readback field classification、schema/fingerprint/lock/atomic-publication tests、focused receipt parser/writer tests |

profile failure は default 起動へ降格しない。image capability or preflight failure、Compose generation
failure、`devcontainer up` failure、finalize failure のいずれもその段階で停止し、
provision/readback receipt の欠損または不一致を成功として扱わない。profile は
up を試行した後の failure で、生成 Compose の `-gpu-admission` project identity を
検証して exact Compose/project に `down --remove-orphans` を実行する。cleanup failure
は typed evidence として報告し、entrypoint は常に元の up/finalize rc を返す。
profile は repository-local source を Compose の `/var/lib/agent-canon/runtime` target
へ bind し、primary `PROJECT_UID:PROJECT_GID` identity を維持する。この projection は
`.devcontainer/gpu-admission.sh`、`.devcontainer/generate-runtime-compose.sh`、
`.devcontainer/finalize-shared-runtime.sh`、`tools/ci/container_config.py`、
`tests/tools/test_container_config.py`、`tests/tools/test_gpu_admission_devcontainer.py`
で readback される。finalize は source/target path、mount namespace、device/inode、
receipt fingerprint、container-side create/write/read/remove usability を検証するが、
host/container numeric identity の exact equality を要求しない。`group_add` と
supplementary-GID environment は GPU profile にも生成しない。

## Dependency-design / environment-maintenance packet

| field | decision |
| --- | --- |
| requirement | 既定 devcontainer は host `sudo`、system group 作成、host `/var/lib/agent-canon/runtime`、shared-runtime bind/receipt environment、GPU auto-request、finalize、readback receipt に依存せず起動できる |
| insufficiency | 現在の linked config は Compose 生成前に host runtime provisioning を呼び、生成 Compose/post-create/post-attach を host group、bind、receipt に結合している。親レポで観測した失敗はこの結合に由来する |
| rationale | 既定開発は container-local の product/runtime setup とし、GPU admission は異なる host 権限・lifecycle 契約を持つ実験 capability として分離する |
| security/runtime impact | 既定経路の host privilege escalation、固定 GID/セッション結合、host runtime 永続化を除去する。container-local logs/state と明示 opt-in 実験 capability は保持する |
| owner / surfaces | Standalone AgentCanon は自身の `.devcontainer/` source を所有する。Template/derived parent は `.devcontainer/` regular environment、image、`docker/`、selector、parent hook を所有し、必要な AgentCanon entrypoint は source-root resolver 経由で呼ぶ。Issue #521 の opt-in owner は parent GPU-admission selector/orchestrator とし、既定境界の authority は本設計と実装の clause に置く |
| dependency/install order | standalone AgentCanon image build は `python3`、`python3-pip`、`pipx`、`python3-packaging`、Node/npm と manifest の全 image-safe record を直接準備し、plan と receipts を canonical immutable image root に freeze する。post-create は shared entrypoint から read-only `image-verify` と container runtime readback だけを実行する |
| validation | default/opt-in generated Compose scenario を `container_config.py` で別 profile として検証し、dependency manifest の validate/dry-run、image-install/image-verify、Docker dependency validator、対象 devcontainer/lifecycle tests、host password prompt なしの親 root default `devcontainer up` を実行する。GPU profile は `nvidia-smi -L`、selector、profile-specific Compose/project、`project` の non-zero primary UID と numeric GID、既存 GID group の再利用/no-rename、unused GID のみ `project` group 作成、provision、finalize readback を確認する。固定 capability は Dockerfile の `gpg`/`cc`/`gcc`/`pipx`、Node provider digest、apt package、immutable image metadata を確認してから operation を行い、親 image は base digest、`PROJECT_UID/GID/USER=project`、`USER project`、`getent passwd/group`、`id -u`/`id -g`、numeric primary-group readback、default Compose の解決済み service user、bind workspace の container-side usability / writability を確認する。公開 override が無いこと、managed-topic と direct-repo の layout/mount/readback を検証する。Python/wgrib2 の container smoke は親側 ownership とする |
| rollback | GPU profile の up/finalize 失敗は default profile へ降格せず、検証済み profile Compose/project identity を指定してその container/project だけを停止する。cleanup failure は別の typed evidence とし、entrypoint は元の rc を保持する。default profile へ host runtime provisioning を戻さない。rollback evidence は profile selector、host capability contract、別 Compose/project identity、cleanup command/result、元の rc、receipt readback を含む |

GPU lifecycle validation は `tests/tools/test_gpu_admission_devcontainer.py` と
`tests/tools/test_run_codex_in_repo_container.py` で selector、up/exec/finalize、exact
cleanup、mount namespace、operation-based bind usability を確認し、receipt parser/writer
validation は `tests/tools/test_execution_resource_plan.py`（必要な managed-run consumer
tests を含む）で schema、field classification、fingerprint、lock、atomic publication、
same-file/device/inode/race gates を確認する。これらの tests は host/container owner
equality を acceptance oracle にしない。

## Design-To-Implementation Trace

| clause | implementation route | reverse evidence / drift block |
| --- | --- | --- |
| DEV-DEFAULT-001 | `.devcontainer/devcontainer.json`: select generator-only default initialization | exact command readback; any host runtime provisioning invocation is a drift blocker |
| DEV-DEFAULT-002 | default selector `.devcontainer/devcontainer.json` and generator `.devcontainer/generate-runtime-compose.sh` resolve decimal UID/GID, reject UID zero or non-numeric/negative GID, pass `PROJECT_UID`/`PROJECT_GID` with fixed user name `project`, omit static `containerUser`/`remoteUser`, set `updateRemoteUserUID: false`, and let generated Compose own resolved `service.user`; standalone `.devcontainer/Dockerfile` and parent Dockerfile materialize the `project` user at `PROJECT_UID` and reuse an existing primary group at `PROJECT_GID` (including GID 0) without rename, creating group `project` only for an unused GID; `tools/ci/container_config.py` statically validates the account and `tests/tools/test_container_config.py` supplies focused identity oracles; post-attach reads back process and group identity plus bind usability | generated Compose/config/image/Dockerfile inspection plus resolved `service.user`, `getent passwd/group`, `id -u`/`id -g`, `PROJECT_UID/GID` decimal predicates, existing-GID reuse/no-rename, unused-GID group creation, name-collision failure, process UID/GID, workspace usability/writability, and container path readback; any missing/mismatched build arg, public identity override, daemon probe, daemon-mode env (including `AGENT_CANON_RUNTIME_IDENTITY_MODE`) in default or gpu-admission, host runtime source, host bind, custom HOME tmpfs, or AgentCanon group is a drift blocker |
| DEV-DEFAULT-003 | generator GPU branch: default は host GPU/`nvidia-smi`/Docker NVIDIA runtime を probe せず、`DEVCONTAINER_GPU_MODE=disabled` を出力し、`DEVCONTAINER_GPU_REQUEST` を出力しない | command/env readback と no-GPU launch; probing、`DEVCONTAINER_GPU_REQUEST`、または `gpus: all` が default に現れれば drift blocker |
| DEV-DEFAULT-004 | `.devcontainer/post-create.sh` runs read-only `image-verify` first, then container runtime readback and a create/write/read/remove workspace usability probe after image build owns manifest installation; post-attach performs the corresponding process/group and workspace usability readback | lifecycle/static validator checks and image metadata/tool readback; image-verify precedes the workspace probe, and package/network mutation, project-install, sudo, workspace repair, host-owner equality, daemon probe, or daemon-mode env is a drift blocker |
| DEV-DEFAULT-005 | retain scripts and experiment owners; route managed runtime capability through the explicit `gpu-admission` selector/orchestrator | source existence, separate selector/output/project identity, and issue linkage; deletion of scheduler/managed experiment is out of scope and a review blocker |
| DEV-DEFAULT-006 | update validators/tests and run the packet-selected validation route | command receipts and parent launch readback; missing evidence blocks closeout |
| DEV-DEFAULT-007 | layout detector and post-attach readback: select managed-topic or direct-repo without changing topic guard semantics, and read back `project` process UID/GID plus workspace create/read/write/remove usability | layout env/readback matches source path; a direct repo must not be rejected for missing topic marker, a managed topic must not bypass its marker/status guard, and any daemon probe/mode env or host-owner equality acceptance is a drift blocker |
| DEV-DEFAULT-008 | common mount projection: bind exact repository root to `/workspace/<basename>` for both layouts and exclude topic root/parent workspace/siblings | Compose source/target inspection plus `devcontainer up --workspace-folder .`; any topic root, sibling, parent workspace, or `/workspace` bind target is a drift blocker |
| DEV-GPU-001 | Parent-owned `.devcontainer/gpu-admission/devcontainer.json` and `.devcontainer/gpu-admission.sh`: select a distinct config/output/project and bind up/exec to that config while retaining only the `project` identity | derived parents keep the selector as regular project content and neither the default selector/output/container nor another profile container can be reused; daemon probe/mode env, including `AGENT_CANON_RUNTIME_IDENTITY_MODE`, is absent from the GPU selector and lifecycle | regular selector, selector JSON, exact up/exec commands, output path, project suffix, project UID/GID, lifecycle order |
| DEV-DEFAULT-009 | `.devcontainer/generate-runtime-compose.sh`, `tools/ci/container_runtime.py`, and `tools/ci/container_config.py`: parse canonical optional profiles, reject raw runtime mounts, and resolve explicit `docker-host` socket bind | generator/runtime/config tests show pack-first union, empty plain default, raw-mount rejection, and socket missing/collision failure; a profile order, socket, or bypass mismatch is a drift blocker |
| DEV-DEFAULT-010 | linked root parser/resolver and direct runner: validate typed list, repo-root symlink ownership, `realpath -e` directory/target equality, and collision-free RW binds | missing/file/mismatch, parent-shape, print-only, and CLI collision tests plus generated Compose readback; any host probe bypass, target mismatch, duplicate, or read-only linked bind is a drift blocker |
| DEV-DEFAULT-011 | standalone/parent generator profile boundary: keep host zsh projection in generator and linked data in explicit pack/runtime routes | standalone plain output and selected profile tests; default host mount or implicit experiment/runtime profile is a drift blocker |
| DEV-DEFAULT-012 | `tools/ci/container_config.py`, `container_runtime.py`, `run_codex_in_repo_container.py`, `run_python_in_dockerfile.py`, `run_repo_program.py`, and AgentCanon-owned `tools/ci/codex-container-profiles.toml` implement the three-owner optional-config boundary | focused tests reverse-map absent parent pack/profile/rules and source-relative default resolution; requiring a parent TOML or resolving the default profile from the parent is a drift blocker |
| DEV-GPU-002 | `.devcontainer/gpu-admission.sh`: validate host GPU/CLI/capability, create the repository-local runtime with the `project` user and numeric `PROJECT_UID/GID` primary identity, reuse an existing GID without rename, and publish the provision receipt before Compose | project primary identity and exact repository-local source are established or the profile stops; host UID/GID fields remain provenance, while daemon probe/mode env is absent and no host/container owner equality is required | preflight, source path/type/mode/device/inode/race, provision receipt, `getent passwd/group`, primary UID/GID and no-rename readback |
| DEV-GPU-003 | `.devcontainer/generate-runtime-compose.sh` plus `tools/ci/container_config.py`: profile branch projects repository-local bind source, canonical container target, `project` primary user/group identity, `gpus: all`, and receipt environment; focused tests validate the profile | profile Compose carries the admitted project runtime and GPU request; container-side target create/write/read/remove is the bind oracle; default generation remains disabled and receipt-free; no `group_add`, supplementary-GID env, daemon probe, or daemon-mode env is present | default/opt-in scenario validator, generated Compose readback, project UID/GID/group readback, operation-based usability probe, route/path/source-target device/inode/fingerprint, and focused GPU identity tests |
| DEV-GPU-004 | `.devcontainer/gpu-admission.sh`, source-root resolver, then `.devcontainer/finalize-shared-runtime.sh`: run profile-bound up/exec/finalize and exact profile cleanup on failure | finalize resolves through AgentCanon source, verifies route/path, mount namespace, source/target device/inode, symlink/type/mode/race, receipt fingerprint, atomic publication, closed probe, UID non-zero/GID numeric, and operation-based bind usability; failure cleans only the verified profile project and preserves the original rc without host/container owner equality | finalize receipt/exit, container-side create/write/read/remove, namespace/mount readback, exact cleanup command/result, original rc; default lifecycle remains without finalize |
| DEV-GPU-005 | `tools/experiments/execution_resource_plan.py`: preserve receipt parser/writer owner and classify numeric identity fields as provenance/observation | no second parser/writer or receipt repair path is introduced; `read_shared_runtime_provision`, `read_shared_runtime_readback`, and `RuntimeIdentityReader.read` do not impose mapping-sensitive receipt-file-owner or host/container UID/GID equality gates; schema, fingerprint, lock, atomic publication, and race/device/inode checks remain normative | dependency headers, symbol readback, field-classification readback, provision/readback fingerprint owner, focused parser/writer tests |

### Layout selection contract

devcontainer の source path は次の二つだけを持つ。

- `managed-topic`: `workspace/<topic-slug>` lifecycle にある source clone。repository
  root だけを `/workspace/<basename>` に bind し、dependency-module topic marker と
  status guard を実行する。marker が欠落した managed topic は fail-closed とする。
- `direct-repo`: `~/workspace/data_download` のように topic lifecycle の外側にある
  repository root。repository root だけを `/workspace/<basename>` に bind し、親の
  `~/workspace` 全体、sibling repository、推測した別 root を mount しない。topic
  marker/status は要求も実行もしない。

generator は `AGENT_CANON_WORKSPACE_LAYOUT=managed-topic|direct-repo` を Compose
environment に出力する。post-attach は同じ layout を
`DEPENDENCY_MODULE_CONTAINER_LAYOUT=managed-topic|direct-repo` として readback し、
`DEPENDENCY_MODULE_CONTAINER_SOURCE` と `DEPENDENCY_MODULE_CONTAINER_TARGET` を
source/target fields として出力する。direct-repo の readback は topic guard を skip
した理由と exact repository root/source target を含み、managed-topic の readback は
同じ exact source/target と marker/status receipt を含む。これらは guard layout の
可視化であり、topic root、sibling、parent workspace の mount や topic guard の
weakening を許可する fallback ではない。

### DEV-DEFAULT-002/004 validation-failure-response

ユーザー指示で supersede した root runtime、標準 `vscode`、default の static
`containerUser`/`remoteUser`、または unresolved `user: ':'` を再導入しない。default は
`updateRemoteUserUID: false` を維持し、生成 Compose の解決済み `service.user` を
Dev Container CLI の numeric identity source とする。
digest-pinned plain Ubuntu 22.04 の `project` user、decimal `PROJECT_UID/GID` build args、
`USER project`、numeric primary group、container-local sudo を確認する。`dependency capability setup failed:
root or sudo is required`、host password prompt、UID zero、非 numeric/negative GID、または
container-side workspace usability/writability failure を観測した場合は、host privilege の
復活や daemon-mode probe の追加ではなく親 image contract の failure として扱う。

| field | value |
| --- | --- |
| `failing_contract` | `DEV-DEFAULT-002/004 digest-pinned Ubuntu project identity` |
| `observation` | `devcontainer up` は container を起動したが、post-create が non-zero UID と numeric GID（`0` を含む）の `project` user、container-local sudo、または container-side usable/writable workspace bind を得られず失敗した |
| `cause_classification` | `plain Ubuntu 22.04 base, UID/GID build args, project account, USER project, or container-local sudo contract missing` |
| `intent_preservation` | `same-intent owner repair`: parent Dockerfile/devcontainer settings を digest-pinned Ubuntu `project` contract に戻し、default の host unprivileged boundary、GPU除外、scripts保持を変更しない |
| `evidence` | base image digest、Node provider digest、decimal `PROJECT_UID/GID` build args（UID non-zero、GID は `0` を含む）、`getent passwd project`、`id -u`/`id -g`、`getent group <PROJECT_GID>`、`USER project`、existing-GID reuse/no-rename、unused-GID-only `project` group creation、group-name collision fail-closed、Dockerfile/image-install/image-verify capability pass、immutable image tree、bind workspace の container-side usability/writability readback、host sudo/group mutation/password prompt と daemon-mode probe が無いこと |

GPU profile の provision/readback failure は同じ mapping-neutral response を使う。
`gpu-admission.sh`、`finalize-shared-runtime.sh`、receipt parser/writer のいずれかが
route/path、source/target device/inode、symlink/type/mode、race、mount namespace、receipt
fingerprint、lock/atomic publication、closed probe、UID non-zero/GID numeric、または
container-side create/write/read/remove を証明できない場合は profile を non-zero で停止し、
default へ降格しない。host/container UID/GID または receipt file owner の不一致だけを
理由に reject せず、数値 fields は provenance/observation として read back する。

## post-create の順序

Template / derived parent の `postCreateCommand` は source-root resolver 経由で shared
AgentCanon の `.devcontainer/post-create.sh` を呼ぶ。shared lifecycle が成功した後に存在する場合だけ親固有の
`post-create-parent.sh` を直接呼ぶ。standalone-source 処理が失敗した場合は親固有処理へ
進まない。親固有処理の失敗も devcontainer 作成の失敗として扱う。

resolver 経由で呼ぶ standalone-source post-create の内部順序は
image build での（存在する場合の）親 manifest、vendor manifest、全体 validation、
topological image-safe execution、immutable plan/receipts freeze、続く read-only
`image-verify`、container runtime readback、container-side workspace usability probe
（create/write/read/remove）の順です。`image-verify` は workspace probe より先に完了し、
probe が成功した後だけ親 hook を選択します。
host runtime provisioning と GPU admission finalize は既定順序の外側にあり、
既定の public lifecycle からは選択しません。GPU-admission profile では
`gpu-admission.sh` が `devcontainer up` 完了後に finalize を実行します。この resolver-invoked
standalone-source command の完了後に、devcontainer.json
の resolver 経由呼び出しが、存在する場合だけ post-create-parent.sh を最後に実行します。
詳細な親側 follow-up は
parent-dependency-manifest-followup.md に従います。

AgentCanon の default manifest は検証済み LSP と小さな構造確認ツールに限定します。
PyYAML、browser、TeX/PDF、proof、full Rust、security scanner は default startup
の入力ではなく、選択した workflow または CI image が所有します。固定 OS/Python capability は
image、Node/npm、Agent/Codex tools は image build と `dependencies.toml` が所有し、
依存 manifest の plan validation が pass するまで image publication は開始しません。

Image build が typed engine の build-only `image-install --records` を選ぶ場合、選択は
provider closure まで閉じ、role-based plan fingerprint は絶対 manifest path を含めません。
standalone source root と fresh clone は同じ image identity を生成し、immutable な plan と
receipts を `/usr/local/share/agent-canon/image-dependencies/{plan.json,receipts}` に公開します。
image-install は APT package/repository、npm-global、release-asset の whitelist に限定し、
既存の mounted `install` CLI は互換のため保持しますが、active post-create/runners から到達不能とします。対応する
production publication は euid 0 と canonical path を要求し、CLI の root override を持たず、
公開 tree を root-owned の directory `0555`、file `0444` に freeze します。
`image-verify` は network、mutation、repair を行わない read-only gate で、plan、receipt、
package、または executable の drift を `rebuild-required` として返します。

## legacy project extras compatibility

`tools/agent_tools/devcontainer_dependencies.py` は既存 caller のため requested extras API と
`project-install` CLI を互換維持します。ただし image-only lifecycle では runtime pack、
generated Compose、post-create、runner からこの経路へ到達せず、project dependency は
image build または親 image の owner route で準備します。

## Evidence And Assumption Ledger

| kind | statement | evidence / owner | status |
| --- | --- | --- | --- |
| current state | project install policy was split between profile-based custom installers and image capability checks | `tools/agent_tools/devcontainer_dependencies.py`, `tools/ci/container_config.py` | observed |
| target state | image build validates the merged manifest and performs one full image-safe plan, then freezes root-owned plan/receipts; active runtime surfaces do not serialize project extras | `tools/agent_tools/devcontainer_dependencies.py`, `.devcontainer/Dockerfile`, `tools/ci/container_runtime.py`, focused owner tests | fixed |
| validation | image-install/image-verify preserve plan order and provider closure; post-create and runners contain no package install or project-install callsite | `tests/agent_tools/test_devcontainer_dependencies.py`, `tests/tools/test_container_config.py`, `tests/tools/test_run_repo_program.py` | checked |
| assumption | fixed OS/Python and Node/npm capabilities belong to the image; manifest-selected Agent/Codex/LSP tools are immutable image receipts | `.devcontainer/Dockerfile`, `.devcontainer/devcontainer.json`, `.devcontainer/dependencies.toml` | explicit |

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
