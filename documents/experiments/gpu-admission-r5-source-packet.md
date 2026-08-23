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

## Default devcontainer boundary

この packet は GPU admission 実験を実行する場合の source authority であり、
既定 devcontainer の起動要件ではない。default profile は host `sudo`、system
group、shared lock、`/var/lib/agent-canon/runtime` の bind、provision/readback
receipt、GPU auto-request を選択しない。`finalize-shared-runtime.sh`、scheduler、
managed experiment、receipt owner は AgentCanon source に保持し、GPU capability と
host runtime provisioning は
`.devcontainer/gpu-admission/devcontainer.json` と `.devcontainer/gpu-admission.sh`
の明示 selector/entrypoint からだけ選択する。

## Devcontainer GPU-admission profile composition

Issue [#521](https://github.com/iwashita-nozomu/agent-canon/issues/521) の opt-in owner は
`.devcontainer/gpu-admission.sh` です。entrypoint は `devcontainer` CLI と
`nvidia-smi -L` を先に確認し、`${repository_root}/.agent-canon/runtime` を primary
UID/GID の provenance を記録する source として作成して provision receipt を発行し、
profile selector の generator に渡します。profile Compose は host source を container の
`/var/lib/agent-canon/runtime` target に bind し、primary `PROJECT_UID:PROJECT_GID` を
維持して `gpus: all`、`DEVCONTAINER_GPU_MODE=enabled`、
`DEVCONTAINER_GPU_REQUEST=all`、`AGENT_CANON_RUNTIME_ROUTE=MANAGED_CONTAINER` を出力
します。default selector はこれらの fields、host path、GPU probe、receipt に依存しません。

profile output は `.agent-canon/gpu-admission-compose.generated.yml`、Compose project
identity は `-gpu-admission` suffix とし、default container/project を profile 起動で
再利用しません。`devcontainer up` が成功した後だけ entrypoint が
同じ profile `--config` の `devcontainer exec` と source-root resolver で
`finalize-shared-runtime.sh` を実行します。provision、Compose generation、up、finalize
のいずれかが失敗した場合は default へ降格せず non-zero で停止します。provision/Compose generation/up/finalize
failure は検証済み profile Compose/project だけを cleanup し、cleanup 結果と独立に元の
rc を保持します。finalize の provision/readback parse と atomic publication は
`tools/experiments/execution_resource_plan.py` が唯一の owner です。RDC-003 の bind
acceptance は `finalize-shared-runtime.sh` が container-side target で
create/write/read/remove を証明できることとし、host-visible owner、host-vs-container
UID/GID、inode owner の exact equality を oracle にしません。`host_uid`/`host_gid`/
`host_supplementary_gids` と `container_uid`/`container_gid`/
`container_supplementary_gids` は typed provenance/observation fields として receipt に
残します。

この mapping-neutral 緩和は route/path、repository-local source と canonical target、
symlink/type/mode、source/target device/inode、open-fd/path race、mount namespace と
mount id/root、closed probe、schema/fingerprint、receipt lock、atomic publication、
within-side group shape、UID non-zero/GID numeric の gate を弱めません。特に
`tools/experiments/execution_resource_plan.py` の `read_shared_runtime_provision`、
`read_shared_runtime_readback`、`RuntimeIdentityReader.read` は receipt-file-owner と
host/container numeric identity の mapping-sensitive equality だけを acceptance gate から
外し、他の typed and fingerprinted evidence を保持します。

default 境界の authority は linked design/implementation であり、default 経路からの
非選択は実験機能の wholesale deletion や R5 の runner/lifecycle semantics の変更を
意味しません。GPU profile は `group_add`、system group、sudo、session refresh、
supplementary-GID environment を使用しません。

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

以下の sequence と CLI handshake は managed experiment adapter の固定契約です。
provider-independent direct command は同じ NVIDIA evidence、BUSY/UNKNOWN/FREE
分類、full UUID lock、lock-held fresh readback、plan freeze を再利用しますが、
外部 provider protocol と completion coverage を要求しません。direct route の
正本は `documents/experiments/gpu-direct-command.md` です。

managed experiment の実行順序は次の固定 sequence です。

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

provider identity は次の merged ExperimentRunner source snapshot に固定します。consumer は
request の `metadata.agentcanon_provider_contract` と managed-run receipt の
`provider_contract` にこの値を記録し、request fingerprintへ含めます。AgentCanon は provider
をimport/installせず、監査時にこのidentityと実行環境のconsole scriptを照合します。

| item | value |
| --- | --- |
| repository | `https://github.com/iwashita-nozomu/experiment-runner` |
| merged commit | `71b3630266151703bdf88b11741b7492eca92fb4` |
| contract | `documents/experiment-runner-admission.md` |
| contract SHA-256 | `2de2b63aac3076e6aacdf1ff10b2c35a0235e835504aeff2db92a7750a720d85` |
| invocation | `experiment-runner-admitted --request <path> --result <path>` |

provider v1 は opaque GPU/MIG identifier を `selected_gpu_ids` と
`capacity.gpu_devices[].gpu_id` に保持します。AgentCanon は admission で確定した
non-empty identifier の順序と重複禁止を検証し、その値を整数 ordinal へ変換せず wire
へ転送します。provider は transport identity と scheduler の内部 numeric key を分離して
扱うため、consumer が UUID を整数へ再解釈することはありません。`task.callable=main`
は provider の argv adapter で実行され、parent process は topic module を import しません。

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
