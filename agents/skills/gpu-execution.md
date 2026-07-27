# gpu-execution
<!--
@dependency-start
contract skill
responsibility Documents GPU execution routing, ExperimentRunner delegation, and GPU validation evidence.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/design/experiment_runner.md ExperimentRunner responsibility boundary
upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md exact R5 admission owner and fallback boundary
upstream design ../../documents/conventions/python/15_jax_rules.md JAX GPU preallocation and CPU fallback policy
upstream design ../workflows/experiment-workflow.md managed experiment workflow
upstream design experiment-lifecycle.md experiment protocol and result artifact boundary
upstream design computational-optimization.md numerical correctness and benchmark validation boundary
downstream implementation ../../.agents/skills/gpu-execution/SKILL.md Codex discovery shim
@dependency-end
-->

## Reader Map

- Purpose: route GPU/CUDA/JAX/XLA/IREE execution through a managed runtime,
  disable JAX/XLA preallocation where required, and preserve GPU validation
  evidence without CPU fallback.
- Section path: Purpose and Use When define scope; Boundary separates
  experiment, numerical, and environment ownership; Runtime Request Packet,
  Python Execution Contract, Environment Contract, Blocker Evidence, and
  Closeout Evidence define the operational contract.
- Use when: GPU execution, CUDA backend availability, `nvidia-smi`,
  `CUDA_VISIBLE_DEVICES`, JAX/XLA allocator settings, ExperimentRunner Python
  execution, GPU validation blockers, or GPU-backed benchmark/evaluation is in
  scope.
- Boundary: this skill owns the GPU runtime route and evidence. It does not own
  experiment design, solver math, Docker/driver installation, or language-level
  code review.

## Purpose

GPU を使う実行を、場当たり的な shell / Python 直実行ではなく、runner の責務境界と
artifact evidence に接続します。特に Python 実行は `experiment_runner` の
`StandardWorker`、`StandardFullResourceScheduler`、`StandardRunner` へ委譲し、
JAX / XLA の GPU 実行では import 前に preallocation を無効化します。

## Use When

- GPU / CUDA / JAX / XLA / IREE backend で実行、検証、benchmark、diagnosis を行う。
- `CUDA_VISIBLE_DEVICES`、`NVIDIA_VISIBLE_DEVICES`、GPU slot、GPU memory、worker
  slot、`nvidia-smi` evidence を扱う。
- `XLA_PYTHON_CLIENT_PREALLOCATE=false`、allocator 設定、JAX import 順序、
  CPU fallback 禁止を明示する。
- Python 実験、GPU smoke、formal run、server-side run、rerun decision を
  ExperimentRunner 経由にしたい。
- GPU が使えず `gpu_validation_blocker=<reason>` を残す必要がある。

## Boundary

- 実験 topic、run / rerun protocol、registry、run artifact は
  `$experiment-lifecycle` が所有します。
- solver、optimizer、residual、convergence、tolerance、数値 benchmark の数学契約と
  correctness evidence は `$computational-optimization` が所有します。
- Docker、driver、dependency、CI runner、system package 更新は
  `$environment-maintenance` が所有します。
- Python / C++ の実装差分 review は `$python-review` / `$cpp-review` が所有します。
- この skill は、GPU 実行 route、environment handoff、blocker evidence、artifact
  closeout を所有します。

## Runtime Request Packet

GPU / CPU 数値実行、benchmark、formal experiment を予定する前に、タスクに結び付いた
実行前記録を作るか引用します。

- `request_clause`: 依頼のどの部分に対応する実行か。
- `command_type`: GPU validation、GPU benchmark、formal experiment、smoke run、
  backend diagnosis など。
- `lightweight_evidence`: 先に確認した static check、config、registry、design doc。
- `runtime_budget`: 見込み時間、timeout、stop condition。
- `resource_target`: GPU 数、GPU memory、worker 数、dtype、backend、allocator。
- `artifact_path`: run manifest、logs、stdout/stderr、environment、summary の保存先。
- `owner`: 実行責務を持つ skill / workflow / agent。

この packet がない GPU 実行は、結果を validation evidence として扱いません。

## Python Execution Contract

Python の GPU 実行は、正式な validation / smoke / formal / server-side run では
`tools/experiments/run_managed_experiment.py` を通します。topic が実装する
public entrypoint は canonical `experiments/<topic>/run.py::main()` だけです。
managed adapter は exact registry closure と fd-bound source snapshot からその
entrypoint と argv を 1 つの immutable case に束縛します。live source callable、
topic-owned scheduler、injected task/cases/context builder、direct subprocess、または
別 lifecycle wrapper は admission route ではありません。

GPU admission は独立 owner の collaboration です。

- `NvidiaInventoryProbe`: exact NVIDIA list/XML/driver と physical/MIG topology。
- `GpuProcessOccupancyProbe`: physical/MIG parent-child occupancy exclusion。
- `GpuReservationTransaction`: candidate-local flock、fd readback、busy continuation、
  tamper/infrastructure fail-closed、total rollback。
- `SourceFreezeOwner`: exact registry を含む source membership と fd-bound snapshot。
- `RuntimeIdentityReader`: namespace、UID/GID/groups、umask、Compose/bootstrap/finalize
  receipt join。
- `build_admitted_environment`: frozen full UUID set から run 前 environment を作成。
- `RunGpuAdmissionContext`: composition order と reverse release だけ。

`experiment_runner` 側へ委譲するものは次です。

- fresh child process lifecycle
- timeout、terminate、kill、cleanup
- parent / child diagnostics
- scheduler-owned `ExecutionResult` completion
- generic worker slot と host memory lifecycle
- `TaskContext["environment_variables"]` の child 反映
- worker start / finish / timeout / signal の観測

fixed ff97 route は 1 つの `StandardFullResourceScheduler`、1 つの
`StandardRunner`、1 回の `run(worker)` だけです。`run(worker)` は `None` を返し、
completion は scheduler から読みます。実験 script、Context、Adapter、Store、Owner
は launch lifecycle、completion、cleanup policy を吸収しません。

## Environment Contract

GPU device と allocator の環境変数は、admission 済み frozen plan から
`build_admitted_environment` が runner construction 前に作り、
`TaskContext["environment_variables"]` と child initializer で反映します。task body や
case loop の中で `CUDA_VISIBLE_DEVICES`、`NVIDIA_VISIBLE_DEVICES`、`XLA_*` を直接組み立てません。
GPU ID は full physical UUID または full MIG UUID だけです。CPU fallback、integer
index、UUID prefix、direct launch、compatibility route はありません。

managed container identity は次の exact artifact からだけ読みます。

```text
/var/lib/agent-canon/runtime/shared-runtime-provision.json
/var/lib/agent-canon/runtime/shared-runtime-readback.json
```

JAX / XLA GPU 実行では、JAX import より前に次を反映します。

```text
XLA_PYTHON_CLIENT_PREALLOCATE=false
```

project-local helper が allocator knob を持つ場合は、同じ env dict に次も載せます。

```text
XLA_PYTHON_CLIENT_ALLOCATOR=platform
XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR=false
```

closeout では `preallocation_disabled=yes` を残します。CUDA backend 初期化失敗は
preallocation 設定の成否と混同せず、backend blocker として分けます。

## Blocker Evidence

GPU が使えない場合は、CPU 計算へ切り替えず次を記録します。

- `gpu_validation_blocker=<reason>`
- `nvidia-smi` または runner / scheduler が返した GPU allocation evidence
- backend import / initialization の stderr、traceback、diagnostic record
- どの claim、test、benchmark、experiment を未検証として残すか

CPU-only smoke は GPU validation の代替 evidence ではありません。GPU backend claim、
JAX / XLA / IREE lowering claim、solver / optimizer correctness on GPU、GPU benchmark
claim は、GPU 実行 evidence か blocker evidence のどちらかで閉じます。

## Closeout Evidence

GPU execution closeout には次を含めます。

- `gpu_execution_route=experiment_runner`
- `preallocation_disabled=yes`
- `gpu_validation_blocker=none` または `gpu_validation_blocker=<reason>`
- command / Make target / managed wrapper path
- run manifest、environment、source snapshot、artifact manifest、logs path
- GPU id / GPU slot / worker slot / backend / dtype / allocator metadata
- stdout、stderr、runner diagnostics、`ExecutionResult` summary
- correctness evidence と performance evidence の分離
