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
worker と descendants の quiescence が result で `PROVEN` になるまで保持します。CLI が
存在しない、version が異なる、result が壊れている、request/result fingerprint が不一致、
または quiescence が証明できない場合は typed fail です。

## 固定 CLI handshake

実行は shell なしの `subprocess` で次を起動します。

```text
executable = experiment-runner-admitted
argv       = [experiment-runner-admitted, --request, <path>, --result, <path>]
version    = experiment-runner-admitted/v1
request    = agentcanon-managed-run/v1
result     = agentcanon-managed-run-result/v1
```

CLI identity、version、argv、request fingerprint は receipt に束縛します。request は
現在の TaskProtocol から次の必須 field を JSON artifact として持ちます。

| field | 内容 |
| --- | --- |
| `schema_version` | `agentcanon-managed-run/v1` |
| `run_id` | managed context の run identity |
| `module_spec` | `module`、`callable`、`argv`、`entrypoint_relative_path`。parent process は module を import しない |
| `source_snapshot_root` | source freeze 後の snapshot path |
| `environment` | admitted 後の exact environment |
| `working_directory` / `output_directory` | worker の作業場所と artifact 出力場所 |
| `capacity` | `cpu_set`、host/GPU memory、GPU count、pre-admitted selected UUID |
| `admission_fingerprint` / `plan_fingerprint` | lock-bound composite と frozen plan の参照 |
| `source_paths` | exact registry closure を含む snapshot membership |
| `lifecycle_artifact_path` | terminal lifecycle の保存先 |
| `request_fingerprint` | 上記 request 内容 hash |

result は `schema_version`、request/admission/result fingerprint、worker PID、各 descendant
の PID/starttime、quiescence、lifecycle terminal event、exit code/error を持ちます。
AgentCanon は schema/version/fingerprint、exit と CLI return code、worker/descendant
identity、quiescence、lifecycle artifact を検証してから terminal/closeout を生成します。

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
