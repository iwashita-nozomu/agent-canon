# AgentCanon GPU admission R5 source packet

<!--
@dependency-start
contract design
responsibility Records the reviewed GPU admission and managed-run handshake.
upstream design ../runtime/runtime-profiles-and-check-matrix.md validation routing
downstream implementation ../../tools/experiments/execution_resource_plan.py admission owner
downstream implementation ../../tools/experiments/run_managed_experiment.py managed-run composition root
@dependency-end
-->

## 目的と境界

この packet は、review で `APPROVE` された GPU/MIG admission と managed-run
handshake の実装正本です。AgentCanon の managed-run 実装は親の
`ExperimentRunner`、Dockerfile、topic の Python module に import 依存しません。
generic runner lifecycle は外部 CLI が所有し、AgentCanon は request/result artifact、
admission、検証、terminal evidence、closeout の境界だけを所有します。

hooks/resource projection の public schema はこの packet の変更対象ではありません。
`pstree` は capability detection と bounded diagnostic に限り、proc が完全なら
`pstree` 不在でも admission を継続します。

## GPU/MIG の証拠と状態

- XML の topology/process hierarchy が physical UUID と MIG UUID の唯一の binding authority です。
- `query-compute-apps` は XML PID へ一意に join できた場合だけ memory/name の補助です。
  join が ambiguous または unavailable でも、XML が完全な unit を UNKNOWN へ落としません。
- 各 caller allocation unit は `BUSY`、`UNKNOWN`、`FREE` のいずれかです。`FREE` だけを
  eligible とし、`UNKNOWN` は選択しません。
- MIG の unknown は MIG と physical parent を、physical の unknown は physical と
  descendants を UNKNOWN に閉じます。XML binding が不明なら caller allocation 全体を
  UNKNOWN にします。
- physical holder は physical と全 descendants を、MIG holder は MIG と physical parent
  を占有として扱います。integer index、UUID prefix、CPU fallback は admission route にありません。

## process ancestry

admission の process root は `(pid, starttime, pid namespace, cgroup)` です。holder と
ancestor は `/proc/<pid>/stat` の starttime、`stat` と `status` の PPid 一致、namespace、
cgroup を検証します。cycle、bounded depth、read race、PID reuse、namespace/cgroup の
不一致は typed fail-closed です。admission probe は signal/kill を送信しません。

## fingerprint と順序

snapshot fingerprint は snapshot 内容 hash、freshness は event ID です。同一内容の
新しい観測を fingerprint 差だけで stale としません。

lock-held observation (`S_lock`)、reservation receipt、lock の device/inode、selected
UUID を結合して composite admission fingerprint を作ります。この composite は
`GPUAllocation`、plan freeze、`build_admitted_environment`、task context、result、
terminal/closeout evidence で同一値を参照します。terminal evidence の追記は admission
composite 自体を変更しません。

実行順序は次の固定 sequence です。

```text
S0
 -> candidate
 -> UUID lock
 -> lock-held fresh S_lock
 -> XML/process validation
 -> composite admission fingerprint
 -> plan freeze
 -> admitted environment
 -> CUDA/NVIDIA visibility
 -> experiment-runner-admitted
 -> terminal evidence
 -> lock release
```

plan freeze 前に selected visibility を生成しません。reservation lock は外部 CLI の
worker と descendants の quiescence、terminal result、completion coverage が provider
result で成立するまで保持します。CLI が存在しない、result schema が異なる、result が壊れて
いる、request fingerprint が不一致、または quiescence/completion coverage が証明できない
場合は typed fail です。

## 固定 CLI handshake

実行は shell なしの `subprocess` で次を起動します。

```text
executable = experiment-runner-admitted
argv       = [experiment-runner-admitted, --request, <path>, --result, <path>]
request    = agentcanon-managed-run/v1 (provider field: schema)
result     = agentcanon-managed-run-result/v1 (provider field: schema)
```

CLI identity、argv、request fingerprint は receipt に束縛します。別の `--version`
ToolCall は行いません。request は provider の approved v1 wire field と、request
fingerprint に含まれる AgentCanon metadata extension から構成します。

| field | 内容 |
| --- | --- |
| `schema` | `agentcanon-managed-run/v1` |
| `run_id` | managed context の run identity |
| `task` | `module` と `callable`。parent process は module を import しない |
| `cases` | provider task に渡す case。argv と canonical entrypoint は各 case に保持 |
| `environment` | admitted 後の exact environment |
| `capacity` | provider の `max_workers`、host memory、`gpu_devices` |
| `resource_estimate` | host memory、GPU count、GPU memory、GPU slots |
| `selected_gpu_ids` | provider v1 の selected device field |
| `fingerprint` | provider canonical request 内容 hash。metadata の admission composite を含む |
| `metadata` | AgentCanon の admission/plan/source/lifecycle references。provider v1 の拡張 field |

result は `schema`、`request_fingerprint`、`run_id`、`worker_pid`/`worker_pids`、provider
`lifecycle`、`quiescence`、`exit`/`exit_code`/`error`、`completions` を持ちます。lifecycle
の `quiescence_complete`、`completion_coverage_complete`、`direct_children_quiescent`、
`descendant_quiescence`、cleanup failure、worker/process-group IDs を実値で検証します。
result に AgentCanon 独自の `admission_fingerprint` や `result_fingerprint` は要求しません。

provider v1 は GPU ID を非負整数に固定し、task callable を `(case, context)` に固定します。
AgentCanon の full physical/MIG UUID と topic `main(argv)` を意味を失わずに表現するには、
provider 側に (a) opaque UUID device ID、(b) main/argv または同等 adapter task の最小 wire
拡張が必要です。consumer は UUID を整数へ縮退せず、現 provider では typed
`admitted_runner_provider_gpu_uuid_incompatible` として停止します。

## 検証と成果物

owner tests は次の7 behavior を固定します。

1. ambiguous XML/PID join の fail-closed。
2. proc race/PID reuse の fail-closed。
3. MIG/physical UNKNOWN closure。
4. lock-bound composite fingerprint の各構成要素。
5. plan freeze 前の CUDA/NVIDIA visibility 禁止。
6. admission probe の signal/kill 禁止。
7. `pstree` 不在かつ proc 完全な ancestry の継続。

fake CLI protocol test は固定 local ExperimentRunner clone や `PYTHONPATH` fallback を
使いません。実機 GPU がない場合、static/owner test pass は実機 GPU pass ではなく、
`gpu_validation_blocker=<reason>` として closeout に残します。
