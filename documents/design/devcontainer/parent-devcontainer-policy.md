<!--
@dependency-start
contract design
responsibility 親レポの devcontainer 所有境界と直接参照の契約を定義する。
upstream design ../../runtime/SHARED_RUNTIME_SURFACES.md shared runtime surface ownership and topology
upstream design ../../runtime/shared-runtime-surfaces.toml machine-readable shared runtime surface manifest
upstream design ../../contracts/github-first-module-and-devcontainer-policy.md devcontainer ownership boundary
upstream design ../../rule/repository-topic-clone.md parent-owned ignored workspace boundary
downstream implementation ../../../tools/agent_tools/surface_manifest.py materializes and checks shared surface entries
downstream implementation ../../../tools/agent_tools/devcontainer_dependencies.py validates the mounted manifest and typed project extras
downstream implementation ../../../tools/sync_agent_canon.sh materializes AgentCanon root views
downstream implementation ../../../tools/agent_tools/parent_repo_readiness.py checks the minimum parent structure
downstream implementation ../../../tools/ci/container_config.py validates parent environment names, pack identity, generated Compose, and profile boundaries
downstream implementation ../../../tools/ci/container_runtime.py executes typed runtime packs and optional profiles
downstream implementation ../../../.devcontainer/devcontainer.json selects the default startup profile
downstream implementation ../../../.devcontainer/generate-runtime-compose.sh renders the workspace-only default and typed optional mount profiles
downstream implementation ../../../.devcontainer/gpu-admission/devcontainer.json selects the explicit GPU-admission profile
downstream implementation ../../../.devcontainer/gpu-admission.sh owns GPU-admission host preflight/up/finalize sequencing
downstream implementation ../../../.devcontainer/finalize-shared-runtime.sh owns container-side shared-runtime readback
downstream implementation ../../../tools/experiments/execution_resource_plan.py owns typed shared-runtime receipt parsing and publication
downstream design parent-dependency-manifest-followup.md declares the parent manifest, pin, and ordering follow-up
@dependency-end
-->

# 親レポの devcontainer 境界

この文書は parent devcontainer の長期 contract だけを持ち、実装の判定は
`tools/ci/container_config.py` と `.devcontainer/generate-runtime-compose.sh` の readback に結びます。
歴史的な導入経緯や個別障害の説明は正本にせず、現在の owner boundary を
`documents/contracts/github-first-module-and-devcontainer-policy.md` と整合させます。

## 所有境界

親の `.devcontainer/` は親-owned regular directory とし、最低限の file-kind は
`tools/agent_tools/parent_repo_readiness.py` が確認します。
`.devcontainer/devcontainer.json`、selector、parent hook、親固有 manifest は必要な場合だけ
親が所有し、AgentCanon source からの whole-directory symlink や自動コピーは
`tools/sync_agent_canon.sh` の shared-surface contract に含めません。
親固有 hook は `.devcontainer/post-create-parent.sh` が存在する場合だけ shared lifecycle の後に呼ばれ、
その順序は `.devcontainer/post-create.sh` と `tools/ci/container_config.py` が検証します。

親環境の legacy pair `.devcontainer/parent-environment.sh` / `.devcontainer/parent-environment.toml` は
既定 runtime の入力ではなく、存在時だけ `tools/ci/container_config.py` が shell 実行なしで監査します。
`parent-environment.sh` の `export NAME=value` と TOML の ordered names は
`tools/ci/container_config.py` が完全一致で比較し、未知 key・重複・不正 shell 行を拒否します。

## Default runtime と optional mount

既定 generator `.devcontainer/generate-runtime-compose.sh` は parent environment、credentials、SSH agent、Docker socket、
host runtime state を暗黙 mount せず、plain pack は host-independent な Compose を生成します。
optional mount は `runtime.optional_mount_profiles` と `AGENT_CANON_OPTIONAL_MOUNTS` の明示選択だけを
`.devcontainer/generate-runtime-compose.sh` と `tools/ci/container_config.py` が受理します。

- `host-zshrc` は host `~/.zshrc` / `~/.zsh` が実在するときだけ selected `HOME` へ read-only 投影し、`.devcontainer/generate-runtime-compose.sh` が source を `realpath -e` します。
- `host-git` は existing `/mnt/git` だけを `/mnt/git` へ投影し、`.devcontainer/generate-runtime-compose.sh` が profile 選択を要求します。
- `host-credentials` は existing `~/.config/gh` / `~/.ssh` だけを selected `HOME` へ read-only 投影し、`.devcontainer/generate-runtime-compose.sh` が profile 選択を要求します。
- `ssh-agent` は valid socket だけを `/ssh-agent` へ投影し、`.devcontainer/generate-runtime-compose.sh` が socket type を確認します。
- `host-secrets` は existing `AGENT_CANON_SECRET_DIR` だけを `/mnt/agent-canon-secrets` へ投影し、`tools/ci/container_config.py` が fixed target を検証します。
- `docker-host` は existing Docker socket だけを `/var/run/docker.sock` へ read-write 投影し、`tools/ci/container_runtime.py` が missing socket を fail-closed にします。
- `linked-data-roots` は pack-defined repository symlink だけを declared `/mnt/<letter>/<subpath>` へ read-write 投影し、`.devcontainer/generate-runtime-compose.sh` と `tools/ci/container_config.py` が source/target/type を照合します。

`runtime.optional_mount_profiles` は既知 profile の ordered string array とし、pack-first / environment-only-second の union を
`.devcontainer/generate-runtime-compose.sh` と `tools/ci/container_runtime.py` が共有します。
raw `runtime.mounts` は shared generator では受理せず、`.devcontainer/generate-runtime-compose.sh` が明示 profile への移行を要求します。
`linked-data-roots` は non-empty inline-table array と profile の両方を必要とし、normalized repo-relative symlink、
`realpath -e` directory、declared target exact match、unique source/target を `tools/ci/container_config.py` が検証します。

## Runtime shell、HOME、Compose identity

runtime shell は `pack.runtime.shell` を正本とし、`.devcontainer/generate-runtime-compose.sh` が absolute executable path として読みます。
Compose-owned `HOME`、`SHELL`、`AGENT_CANON_CONTAINER_USER`、`AGENT_CANON_RUNTIME_ROUTE`、
`AGENT_CANON_CODEX_SESSION_ROOT` は `.devcontainer/generate-runtime-compose.sh` が生成し、host startup file へ hidden source しません。
生成 Compose は parent の `.agent-canon/docker-compose.generated.yml` に置き、`tools/ci/container_config.py` が pack と Compose の platform / target / runtime identity を照合します。

repository layout は `managed-topic` と `direct-repo` の二つだけを `.devcontainer/generate-runtime-compose.sh` が判定します。
両 layout は exact repository root 一つだけを `/workspace/<basename>` に bind し、`tools/ci/container_config.py` が sibling / topic-root / broad `/workspace` mount を拒否します。
`managed-topic` の marker/status guard は `.devcontainer/post-attach.sh` が維持し、`direct-repo` では同 guard を要求しません。

## Default account と daemon-neutral boundary

canonical runtime user は `project`、build identity は host process 由来の `PROJECT_UID` / `PROJECT_GID` とし、
`.devcontainer/generate-runtime-compose.sh` が caller override を拒否します。
`PROJECT_UID` は non-zero decimal、`PROJECT_GID` は non-negative decimal とし、`.devcontainer/generate-runtime-compose.sh` と `.devcontainer/Dockerfile` が同じ predicate を使います。
要求 GID が既存 group にある場合は `.devcontainer/Dockerfile` がその group を rename せず primary group として再利用し、未使用 GID の場合だけ `project` group を作成します。
Compose の resolved `service.user`、`AGENT_CANON_CONTAINER_USER=project`、image `USER project` は
`.devcontainer/generate-runtime-compose.sh`、`.devcontainer/Dockerfile`、`tools/ci/container_config.py` が同じ numeric identity に結びます。

Docker daemon の rootful/rootless/userns mode は runtime identity selector にせず、`.devcontainer/generate-runtime-compose.sh` は daemon metadata を probe しません。
default と `gpu-admission` の bind acceptance は host-visible owner equality ではなく container-side create/write/read/remove とし、
`.devcontainer/post-create.sh` と `.devcontainer/finalize-shared-runtime.sh` が usability を read back します。

## Image-owned dependency lifecycle

standalone `.devcontainer/Dockerfile` と parent-owned Dockerfile は image build 中に OS/tool dependencies を materialize し、
`tools/agent_tools/devcontainer_dependencies.py image-install` が immutable plan/receipts を作ります。
post-create は `tools/agent_tools/devcontainer_dependencies.py image-verify` と runtime readback だけを行い、package install、network、sudo、workspace repair を行いません。
CUDA/GPU capability は default image/runtime から外し、明示 `.devcontainer/gpu-admission/devcontainer.json` が所有します。

Node/npm は digest-pinned provider から image build 中に取得し、`.devcontainer/Dockerfile` が provider identity を固定します。
固定 OS/Python/Node capability と Agent/Codex/LSP tool availability は `.devcontainer/dependencies.toml` と
`tools/agent_tools/devcontainer_dependencies.py` の plan/readback に結びます。

## DEV-DEFAULT contract

| clause | operation / owner | resulting state / completion evidence |
| --- | --- | --- |
| DEV-DEFAULT-001 | `.devcontainer/devcontainer.json` は initialize で `.devcontainer/generate-runtime-compose.sh` だけを呼ぶ | `tools/ci/container_config.py` が host sudo/system-group/runtime provisioning 不在を確認する |
| DEV-DEFAULT-002 | `.devcontainer/generate-runtime-compose.sh` と `.devcontainer/Dockerfile` は `PROJECT_UID` / `PROJECT_GID` / `project` を一つの identity として materialize する | `tools/ci/container_config.py` と `tests/tools/test_container_config.py` が UID/GID predicate、existing-GID reuse/no-rename、`USER project`、resolved `service.user`、override absence を検証する |
| DEV-DEFAULT-003 | `.devcontainer/generate-runtime-compose.sh` は default で GPU probe/request を生成しない | `tools/ci/container_config.py` が `DEVCONTAINER_GPU_MODE=disabled`、`DEVCONTAINER_GPU_REQUEST` absent、`gpus: all` absent を検証する |
| DEV-DEFAULT-004 | `.devcontainer/post-create.sh` は image verify → runtime readback → workspace usability の順で実行する | `tests/tools/test_container_config.py` と lifecycle tests が package/network/sudo/host-owner repair 不在と order を検証する |
| DEV-DEFAULT-005 | scheduler/receipt/finalize source は保持し、default selector から非選択にする | `.devcontainer/gpu-admission/devcontainer.json` と `.devcontainer/gpu-admission.sh` だけが opt-in capability を選択する |
| DEV-DEFAULT-006 | `tools/ci/container_config.py` と dependency validators が default/opt-in boundary を検証する | focused validator/test readback が closeout evidence になる |
| DEV-DEFAULT-007 | `.devcontainer/generate-runtime-compose.sh` は `managed-topic` / `direct-repo` を判定する | `.devcontainer/post-attach.sh` が同じ layout と guard result を read back する |
| DEV-DEFAULT-008 | `.devcontainer/generate-runtime-compose.sh` は exact repository root を `/workspace/<basename>` へ bind する | `tools/ci/container_config.py` が broad workspace/sibling/topic-root exposure を拒否する |
| DEV-DEFAULT-009 | `.devcontainer/generate-runtime-compose.sh` と `tools/ci/container_runtime.py` は typed optional profile union を共有し raw mount を拒否する | `tests/tools/test_container_config.py` が profile order、Docker socket、missing/collision を検証する |
| DEV-DEFAULT-010 | `.devcontainer/generate-runtime-compose.sh` は `linked-data-roots` の symlink/realpath/target を検証する | `tools/ci/container_config.py` が structured RW bind、duplicate、mismatch、file/missing case を検証する |
| DEV-DEFAULT-011 | `.devcontainer/generate-runtime-compose.sh` は standalone plain default で host zsh/data profile を選択しない | standalone/parent profile tests が empty default mount と explicit selection を read back する |
| DEV-DEFAULT-012 | `tools/ci/container_config.py`、`tools/ci/container_runtime.py`、`tools/ci/run_codex_in_repo_container.py` は project Docker runtime / parent devcontainer / Codex tooling を別 owner として解決する | pack/profile/rules absent の direct route と ignored nested-Codex HOME を focused tests が検証する |

## Mapping-neutral shared-runtime receipt

RDC-003 の provision は `.devcontainer/gpu-admission.sh`、container readback は `.devcontainer/finalize-shared-runtime.sh`、
receipt parser/writer は `tools/experiments/execution_resource_plan.py` が所有します。
`host_uid` / `host_gid` と `container_uid` / `container_gid` は provenance/observation として保存し、
`tools/experiments/execution_resource_plan.py` は cross-boundary numeric equality を acceptance gate にしません。
route/path、source/target device/inode、symlink/type/mode、mount namespace、fingerprint、lock、atomic publication、closed probe は
`.devcontainer/finalize-shared-runtime.sh` と `tools/experiments/execution_resource_plan.py` が fail-closed で維持します。

## Explicit GPU-admission profile

GPU capability selector は parent-owned regular `.devcontainer/gpu-admission/devcontainer.json`、host orchestrator は
`.devcontainer/gpu-admission.sh` に限定します。
profile は default と別 generated Compose / project identity を使い、`.devcontainer/gpu-admission.sh` が同じ `--config` を up/exec/finalize に渡します。
profile failure は default へ降格せず、`.devcontainer/gpu-admission.sh` が検証済み exact Compose/project に `down --remove-orphans` を実行して元 rc を保持します。

| clause | operation / owner | resulting state / completion evidence |
| --- | --- | --- |
| DEV-GPU-001 | `.devcontainer/gpu-admission.sh` は `.devcontainer/gpu-admission/devcontainer.json` を up/exec 共通 selector にする | GPU profile は default と別 Compose output/project/container を持ち、focused lifecycle tests が selector identity を検証する |
| DEV-GPU-002 | `.devcontainer/gpu-admission.sh` は CLI/GPU/repository/selector/runtime path を preflight し provision receipt を発行する | invalid capability/path/type/race は non-zero、numeric GID 0 は受理、host UID/GID は provenance として receipt tests が検証する |
| DEV-GPU-003 | `.devcontainer/generate-runtime-compose.sh` は repository-local runtime bind、`PROJECT_UID:PROJECT_GID`、`gpus: all`、GPU receipt env を profile にだけ生成する | `tools/ci/container_config.py` と GPU tests が operation-based usability と default absence を検証する |
| DEV-GPU-004 | `.devcontainer/gpu-admission.sh` は up 後に `.devcontainer/finalize-shared-runtime.sh` を同じ profile container で実行する | finalize tests が mount/route/path/fingerprint/atomic publication/usability と exact cleanup/original rc を検証する |
| DEV-GPU-005 | `tools/experiments/execution_resource_plan.py` は receipt parse/read/write の唯一 owner になる | receipt tests が schema/fingerprint/lock/atomic publication を検証し、profile script に第二 parser/writer を持たせない |

## Failure response と rollback

Default identity/workspace failure は host privilege や daemon-mode probe を復活させず、`.devcontainer/Dockerfile` と
`.devcontainer/generate-runtime-compose.sh` の same-intent owner repair に戻します。
GPU provision/finalize failure は default へ降格せず、`.devcontainer/gpu-admission.sh` の exact profile cleanup と original rc を read back します。

## Reader flow: runtime から Compose へ

runtime shell / account / optional profile の入力は `.devcontainer/generate-runtime-compose.sh` が一度 typed に解決し、
その同じ解決値を generated Compose へ投影して `tools/ci/container_config.py` が pack と照合します。
したがって shell/runtime paragraph と Compose-output paragraph の間に第二 configuration owner はありません。

## Reader flow: source update から parent operation へ

AgentCanon 共有実装の変更は `tools/update_agent_canon.sh` の source PR route で `main` へ統合した後、
親 repo の gitlink/root views を `tools/sync_agent_canon.sh` が更新します。
container の起動・停止・image 操作はこの source-update route に吸収せず、
`documents/parent-repository/CONTAINER_OPERATIONS.md` の parent operation owner に接続します。

## 禁止する重複

- `.devcontainer` 全体 symlink は `tools/agent_tools/parent_repo_readiness.py` の parent-owned regular boundary に反します。
- AgentCanon 共有 script の parent copy/wrapper は `tools/sync_agent_canon.sh` の direct source-view boundary に反します。
- generated Compose の複数追跡先は `.devcontainer/generate-runtime-compose.sh` の `.agent-canon/docker-compose.generated.yml` owner に反します。
- parent environment value の別 shell/Compose copy は `tools/ci/container_config.py` の single audited source boundary に反します。
