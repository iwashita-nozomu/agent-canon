# gpu-execution

<!--
@dependency-start
contract skill
responsibility Routes GPU execution through AgentCanon admission and records validation evidence.
upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md admission and CLI handshake
upstream design ../../documents/experiments/gpu-admission-r5-nvidia-visibility.md NVIDIA evidence boundary
upstream design experiment-lifecycle.md experiment artifact boundary
downstream implementation ../../.agents/skills/gpu-execution/SKILL.md Codex discovery shim
upstream environment ../../agent-canon-environment.toml audited ExperimentRunner provider identity and runtime item
@dependency-end
-->

## 目的

この skill は GPU/CUDA/JAX/XLA/IREE 実行を AgentCanon の admission、固定 environment、
外部 managed-run CLI、terminal evidence に接続します。static test や CPU-only smoke を
実機 GPU validation と取り違えず、GPU が使えない場合は blocker evidence を残します。

## 適用範囲と境界

- GPU allocation、CUDA/NVIDIA visibility、MIG、`nvidia-smi`、JAX/XLA allocator、GPU
  smoke/benchmark/diagnosis が対象です。
- topic の設計と registry、run artifact は `experiment-lifecycle` が所有します。
- solver と数値 correctness は `computational-optimization`、Docker/driver/CI は
  `environment-maintenance`、Python/C++ review は各 review skill が所有します。
- AgentCanon は親 `ExperimentRunner`、その local clone、Dockerfile、topic module を
  import または `PYTHONPATH` fallback で利用しません。generic lifecycle は外部 CLI が
  owner です。
- hooks/resource projection の public schema は変更しません。

## Runtime request packet

GPU 実行前に request clause、command type、runtime budget、resource target、artifact path、
owner を記録します。GPU allocation がない、または実機が利用できない場合も、実行した
static/owner checks と未検証の claim を分けて記録します。

## 固定 admission route

managed route は次の一つだけです。

```text
S0 -> candidate -> UUID lock -> fresh S_lock -> validation
   -> composite fingerprint -> plan freeze -> admitted environment
   -> CUDA/NVIDIA variables -> experiment-runner-admitted
   -> terminal evidence -> lock release
```

XML topology/process hierarchy が UUID binding authority です。query-compute-apps は XML
PID の一意 join 後の memory/name supplement だけです。unit state は `BUSY`、`UNKNOWN`、
`FREE` で、`FREE` だけが eligible です。MIG/physical unknown の closure、proc ancestry
の starttime/PPid/namespace/cgroup 検証、cycle/depth/race/reuse fail-closed、pstree
diagnostic-only、probe の no-signal/no-kill を admission evidence に含めます。

snapshot content hash と freshness event ID を分離します。lock-held observation、
reservation receipt、lock inode/device、selected UUID から作った composite admission
fingerprint は `GPUAllocation`、frozen plan、admitted environment、request/result、
terminal/closeout で同じ値を参照します。

## 固定 CLI と request/result

AgentCanon は shell なしで次を起動します。

```text
experiment-runner-admitted --request <path> --result <path>
request field: schema = agentcanon-managed-run/v1
result field:  schema = agentcanon-managed-run-result/v1
```

AgentCanon は shell なしで単一 invocation を起動します。別の `--version` ToolCall は
ありません。request は provider v1 の `task`、`cases`、exact `environment`、`capacity`、
`resource_estimate`、`selected_gpu_ids`、`fingerprint` を使います。module/callable は task
へ、argv と snapshot/output/lifecycle references と admission/plan fingerprint は
`metadata` extension へ写像します。parent process は topic/backend module を import しません。
receipt は CLI identity/argv/request fingerprint を束縛します。

result は provider v1 の schema、request fingerprint、worker PID 列、lifecycle、quiescence、
completion coverage、exit/error を検証します。`quiescence.complete`、
`lifecycle.quiescence_complete`、`direct_children_quiescent`、`completion_coverage_complete`、
cleanup failure、worker/process-group IDs を hardcode せず実値で検証します。worker と
descendants が quiescent になり、terminal result と completion coverage が成立するまで
GPU reservation lock を release しません。CLI 不在、schema 不一致、壊れた result、request
fingerprint 不一致、quiescence/completion coverage 不明は typed failure です。

provider v1 の `selected_gpu_ids` と `capacity.gpu_devices[].gpu_id` は opaque
physical/MIG identifier を保持します。AgentCanon は admission で確定した non-empty
identifier の順序と重複禁止を維持して、そのまま wire へ転送します。provider は transport
identity と scheduler の内部 numeric key を分離するため、consumer は UUID を整数へ
再解釈しません。`task.callable=main` は provider の argv adapter 境界で実行されます。

この invocation は merged ExperimentRunner provider `71b3630266151703bdf88b11741b7492eca92fb4`
の contract identityへ束縛します。provider repository、contract SHA-256、shell-free argvは
request metadata、receipt、`agent-canon-environment.toml` の audit itemで一致しなければ
なりません。AgentCanonは親providerをimport/installせず、consumer環境の実在console scriptを
このidentityに対して監査します。

## Environment

selected full physical/MIG UUID の visibility は plan freeze 後に
`build_admitted_environment` が生成します。freeze 前に `CUDA_VISIBLE_DEVICES` または
`NVIDIA_VISIBLE_DEVICES` を作りません。GPU 実行では必要に応じて次も exact environment
へ入れます。

```text
XLA_PYTHON_CLIENT_PREALLOCATE=false
XLA_PYTHON_CLIENT_ALLOCATOR=platform
XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR=false
```

CPU fallback、integer index、UUID prefix、direct launch、固定 local runner clone、
compatibility route はありません。

## Validation と blocker

owner tests は既存7 behavior と、provider wire schema、request/result mismatch、single
invocation、実値 quiescence/completion coverage、lock release order、import/PYTHONPATH
absence を実行します。fake CLI は provider approved schema と同じ field を返し、旧 consumer
専用 schema では通しません。

実機 GPU が必要な claim は `nvidia-smi` と allocation/backend evidence で検証します。
GPU が利用不可なら `gpu_validation_blocker=<reason>`、実行できなかった claim、stderr または
diagnostic を closeout へ記録します。static pass、owner test pass、CPU-only smoke は
実機 GPU pass ではありません。

## Closeout

closeout は managed route、plan/admission fingerprint、exact environment、source snapshot、
CLI receipt、request/result/lifecycle、terminal evidence、lock release evidence、targeted
test/docs/static の結果、`gpu_validation_blocker` を参照します。
