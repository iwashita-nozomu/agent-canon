# Environment-resolution GPU build capability

<!--
@dependency-start
contract design
responsibility Defines the #838 environment-resolution child contract for staged GPU build capability admission without owning project Dockerfiles or CUDA provider materialization.
upstream design ../../agents/skills/gpu-execution.md runtime GPU admission and CDI wiring boundary
upstream design ../../agents/skills/environment-maintenance.md canonical image repair boundary
upstream design ../../agents/skills/dependency-design.md dependency provider and placement boundary
downstream implementation ../../tools/runtime/container/gpu_build_capability.py typed GPU build receipt classifier
downstream implementation ../../tests/agent_tools/test_gpu_build_capability.py focused staged-receipt regression
downstream implementation ../../tests/fixtures/environment_resolution/wsl2_rootless_nvml_failed.json sanitized WSL2 failure evidence
downstream implementation ../../tests/fixtures/environment_resolution/wsl2_rootless_cuda_build_repaired.json sanitized WSL2 repaired evidence
@dependency-end
-->

## 目的と現在の実装範囲

この文書は、`environment-resolution`がcommand、test、compile、benchmarkの環境をhost、
canonical container、environment repairの順で解決する際の子契約を定義します。一般の状態遷移、
exact command receipt、product failureとの分類、repair handoff全体はIssue #838が所有します。

本実装はpublic skill、catalog、shim、一般state machineを先行実装せず、Issue #878が必要とする
GPU-dependent image buildのcapability receiptだけを固定します。AgentCanonはbuilderを観測・分類し、
project Dockerfileへの`RUN --device`追加、BuildKit daemon設定変更、Kokkos/CUDA provider生成、GPU
architecture固定、project testの代行を行いません。

## GPU build capability receipt

The receipt uses schema version `2`. Every evidence object has the exact keys
`summary`, `probe_kind`, `command`, `exit_code`, and `observations`. `probe_kind`
is closed and owned by its stage; a free-form summary cannot make a probe valid.
For every attempted state, `command` is a non-empty argv whose first item is an
executable and `observations` is a non-empty bounded list. Only
`not_attempted` and `unverified` states may omit both arrays (with
`exit_code=null`).

一つのbuilderについて、次の状態を独立に記録します。

| field | closed states | success state |
| --- | --- | --- |
| `device_entitlement` | `unavailable`, `unsupported`, `supported` | `supported` |
| `cdi_inventory` | `missing`, `unresolved`, `matched` | `matched` |
| `run_device_request` | `not_attempted`, `rejected`, `accepted` | `accepted` |
| `device_nodes` | `missing`, `partial`, `present` | `present` |
| `driver_loader` | `missing`, `partial`, `complete` | `complete` |
| `cuda_driver_api` | `unverified`, `failed_initialization`, `ready` | `ready` |
| `cuda_compile_run` | `not_attempted`, `compile_failed`, `run_failed`, `passed` | `passed` |
| `runtime_cdi` | `unverified`, `failed`, `passed` | build判定には使わない |

build-time stage集合を

```text
B = {device_entitlement, cdi_inventory, run_device_request, device_nodes,
     driver_loader, cuda_driver_api, cuda_compile_run}
```

とすると、build capabilityは次の論理積だけで決めます。

```text
build_ready = AND(stage in B, state(stage) == success(stage))
```

各stageは独立した観測です。先行stageが失敗しているのに後続surfaceが観測されたreceiptを捨てず、
最初の未成立stageを`blocking_stage`、全未成立stageを`incomplete_stages`として返します。これにより、
CDI inventoryは一致しているが`RUN --device`が拒否された場合なども、矛盾へ丸めずdiagnostic evidenceを
保持できます。

`runtime_cdi`は判定式に含めません。runtime containerが同じimageとCDI deviceで成功しても、
BuildKitのbuild step内でWSL thunk/loader、CUDA Driver API、compile-and-runが成立した証拠には
なりません。逆にbuild receiptがreadyでもruntime CDIを推測して成功へ昇格しません。

## Builder identityとevidence

receiptは少なくとも次を構造化して保持します。

- platform、builder name、closed rootless/rootful/desktop mode、closed Buildx driver;
- Docker、Buildx、BuildKit version;
- exact requested CDI device列とbuilderが返したexact inventory;
- 各stageのclosed state;
- stage-specific `probe_kind`;
- bounded single-line summary、実行可能なargv、exit code、non-empty observed paths/messages。

`cdi_inventory=matched`は要求した全device identityがinventoryに存在する場合だけ受理します。
stateをstdoutの部分一致、PATH上の`nvidia-smi`の有無、runtimeの成功から推測しません。未知のstate、
欠けたstage、余分なstage、unbounded summary、success/non-zeroやexecuted-failure/zeroの矛盾は
receipt不正としてfail closedにします。

CUDA Driver APIの`ready`は、`probe_kind=cuda_driver_api` の
`cuInit status=0` と `cuDeviceGetCount status=0 count=N`、または
`probe_kind=nvml` の同等の `nvmlInit` / `nvmlDeviceGetCount` success
observation がある場合だけです。`nvidia-smi`のPATH解決、runtime CDI、または
`probe_kind=cuda_runtime_api` の `CUDA_COUNT` / `cudaGetDeviceCount` は、
`ready`の代用になりません。runtime API failureは失敗診断として typed
`cuda_runtime_api` evidence に保持できます。

## 2026-08-24 WSL2/rootless readback

### Generated NVIDIA CDIだけのfailure

sanitized failure fixtureは次の観測を保持します。

```text
device_entitlement  = supported
cdi_inventory       = matched (nvidia.com/gpu=all)
run_device_request  = accepted
device_nodes        = present (/dev/dxg)
driver_loader        = partial (libcuda.so.1.1 body only; WSL thunk absent)
cuda_driver_api     = failed_initialization (probe_kind=cuda_runtime_api; cudaGetDeviceCount status 35)
cuda_compile_run    = run_failed
runtime_cdi         = passed
```

結果は`gpu_build_environment_unavailable`、`blocking_stage=driver_loader`です。entitlement、CDI、
`RUN --device`、`/dev/dxg`の正のreceiptは保持され、runtime CDI passはbuild readinessを変更しません。
不足surfaceはgenerated CDIの`createContainer` hookがruntimeで作るWSL thunk/loader状態です。

### Parent-owned read-only WSL addonを含むpositive occurrence

parent側で`local.wsl/cuda-build=all`を追加して`/usr/lib/wsl/lib`をread-only mountした実機evidenceも、
別のsanitized receiptとして保持します。

```text
requested_devices   = nvidia.com/gpu=all, local.wsl/cuda-build=all
driver_loader        = complete
cuda_driver_api     = ready (probe_kind=cuda_driver_api; cuInit status=0; cuDeviceGetCount status=0 count=2; capability=7.5)
cuda_compile_run    = passed (CUDA/Kokkos provider, GPU-profile tests 3/3)
runtime_cdi         = passed
```

これはAgentCanonがaddonやDockerfileを所有する根拠ではありません。negative/positiveの差分から不足phaseを
一意に分類し、project ownerが採用した修理をtyped receiptでread backできることだけを示します。

## Owner handoff

ready/unavailableのどちらでも、provider artifactとGPU-dependent layer cacheはproject ownerの責務です。
decisionは常に次のowner/readback requirementを返し、未成立時だけfindingを追加します。

```text
owner = project-environment-or-cppdev-provider
required readback = provider_artifact_identity, detected_compute_capability
finding when unavailable = gpu_build_environment_unavailable
```

AgentCanonはDockerfileへ`RUN --device`やWSL addonを自動挿入せず、runtime CDI、CPU fallback、別providerを
build successとして代用しません。GPU-dependent cacheを再利用する場合のartifact identityとdetected
compute capabilityはproject ownerが固定します。

## Focused validation

```text
python3 -m unittest tests.agent_tools.test_gpu_build_capability -v
```

実機再確認では同じschemaでbuilder identityと全stageを再取得します。実機へ接続できないcloseoutでは、
2026-08-24のsanitized readbackと今回のfocused regressionを区別し、live probeを未確認のまま
`need verification`として残します。
