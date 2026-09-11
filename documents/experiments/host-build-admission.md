# Compiler/linker host admission

<!--
@dependency-start
contract design
responsibility Defines GPU-independent host build admission, effective limits, bounded termination, and durable interrupted-run evidence.
upstream design ./gpu-direct-command.md separates GPU allocation from host build safety
upstream design ../runtime/bootstrap-runtime.md existing runtime and host/product execution boundary
upstream implementation ../../tools/experiments/execution/execution_resource_plan.py canonical shared host runtime and lock namespace
downstream implementation ../../tools/experiments/execution/host_build_admission.py host build admission transaction
downstream implementation ../../tests/tools/test_host_build_admission.py fixture-only safety regression
downstream design ../../agents/skills/cpp-review.md ordinary C++ build admission reader
@dependency-end
-->

## 責務と起動境界

通常の C/C++、Clang/Enzyme、linker build は GPU allocation と独立に host RAM、CPU、
PIDs、並列度、期限を admission します。実装は既存 execution owner 配下の
[host_build_admission.py](../../tools/experiments/execution/host_build_admission.py) に閉じ、
[execution_resource_plan.py](../../tools/experiments/execution/execution_resource_plan.py) の
`HOST_RUNTIME_ROOT` と `LOCK_ROOT` を使います。第二 GPU scheduler、実験 case runner、
host reservation DB、consumer model/build graph は追加しません。

これは consumer が所有する既存 product image の実行です。共有 AgentCanon tool container
を増設する機能ではなく、image の build/pull、daemon の起動、認証・権限修復は行いません。
[cpp-review](../../agents/skills/cpp-review.md) は project-native build argv をこの入口へ渡します。
consumer の source、toolchain、target、数値実装、必要な検証範囲は変更しません。

```text
python3 tools/experiments/execution/host_build_admission.py --request <approved-build-request.json>
python3 tools/experiments/execution/host_build_admission.py --result <host-run-directory>/events.jsonl
```

request は実行前に承認済み task/environment から固定します。失敗を回避するために
socket、daemon ID、image、authorization を作り替えることは禁止です。全 field が必須です。

| Field | 意味 |
| --- | --- |
| `image` | consumer の既存 image digest。mutable tag は不可 |
| `docker_host`, `daemon_id` | 指定済み local Unix socket と daemon ID。remote/context fallback は不可 |
| `source_root`, `argv` | 実在する exact checkout と shell-free build argv。container 内の checkout は `/workspace` |
| `jobs` | outer build の並列度。正整数、CPU/PIDs 予算以下 |
| `compiler_peak_bytes`, `linker_peak_bytes`, `overhead_bytes` | 一 build job の保守的 RAM 予算と固定 overhead |
| `estimate_basis` | 上記予算の既存 evidence/工学的根拠。空欄や事故時 RSS を上限とみなす推測は不可 |
| `memory_bytes`, `cpu_count`, `pids_limit` | 要求する有限 hard limit。swap は追加使用を許さない |
| `host_reserve_bytes` | 他 task、OS、監視に残す正の RAM 余裕 |
| `timeout_seconds` | 待機ゲートを含む正の有限時間。停止猶予は最大追加 5 秒 |
| `rerun_authorized` | 今回の workload 実行許可。literal `true` 以外は開始拒否 |

初期対応は `cmake --build`、Make、Ninja、単一 compiler/linker argv です。`--parallel` / `-j`
は request の `jobs` から一度だけ付与し、caller の重複指定や任意 shell wrapper は拒否します。
未知の entrypoint、configure、独自 launcher を無制限 host で実行する fallback はありません。
既存の configured build tree と image 内の path の対応は consumer が所有します。

## 予算と同時 admission

並列数を $J$、compiler/linker の一 job の予算を $C,L$、固定 overhead を $O$ とし、
保守的な作業予算を $B=O+J\max(C,L)$ とします。compile と link の非重複は仮定しません。
job 内部の threads、再帰 build、子 process の資源も一 job の見積りに含めます。
これは観測から自動的に得られる厳密上界ではなく、根拠付きの admission 入力です。
見積りが外れても kernel hard limit を越えて host へ逃がす実装にはしません。

admission は $B\le M$、実効 leaf/ancestor memory limit が $B$ 以上、実効 CPU/PIDs limit
が要求を越えないことを必要とします。共通 `host-build.lock` を取得してから、host 全体の
`MemAvailable >= M + host_reserve_bytes` を再観測し、ゲート直前にも確認します。

単純化のため、同一 host のこの route の build は別 task/session を含め **一つずつ** admit
します。待機 queue や別 allocator は作りません。実行中は host memory/swap/pressure を
記録し、reserve 割れ、実効制限の変化、読取り失敗で自分の container を停止します。
既に動く他 workload の消費は host 観測に含まれますが、この route を使わない process の
将来の割当まで原子的に予約する保証ではありません。無関係な process を停止しません。

lock inode は削除せず、終了確認まで `host-build-active.json` を保持します。observer が
死んで flock が自動解放されても marker が次の admission を拒否します。同じ host で
別 lock root を作ることは禁止で、production CLI に root override はありません。

## 実効制限と独立期限

指定 daemon の `docker info` が失敗、ID が不一致、cgroup v2 でない、driver が `none` / 未知
なら、container の作成前に拒否します。起動失敗や対話認証要求から、別 daemon の起動、
cgroup 無効化、無制限 host 実行へ迂回しません。要求フラグだけでは admit しません。

consumer image を `--pull=never`、有限 memory/CPU/PIDs、memory と同じ memory-swap limit、
network 無効、capabilities drop、no-new-privileges、private cgroup namespace で一度だけ作成。
PID 1 は GNU `timeout --signal=TERM --kill-after=5s` とし、その子は host 側の read-only
GO file を待つだけです。GO の前に GNU timeout の存在、host procfs からの PID/start-time、
専用 cgroup membership、controller、`memory.max`、ancestor memory、`cpu.max`、`pids.max`、
`memory.swap.max=0` を実測します。`max`、欠落、読取り不能、予算不足、PID/limit 変化は拒否。

開始 record と実効制限を fsync してから GO を発行します。対話 client や Python observer
が消えても、container 内の期限は存続します。各 Docker 制御呼出しも 5 秒で打ち切ります。
停止対象はこの run の ID/label に一致する container だけです。全体 `pkill` は行いません。
PID namespace の init 終了に加え、観測済み cgroup の `populated=0` または kernel による
cgroup 削除を確認してから lease を解放します。root exit だけで残存子孫を無視しません。
実行中、quiescence が未証明、または cleanup に失敗した場合は marker を保持します。

これは正常に動作する Linux kernel/daemon の制約です。OS/GPU driver 障害、停止不能な
kernel I/O、host 全体の停止をユーザー空間の timeout で封じ込めたとは主張しません。
停止・監視・ログの証拠を失ったら成功にせず、未解決 lease を残します。

## host 永続ログと interrupted

保存先は canonical host runtime の `host-builds/<run-id>/` です。local durable filesystem
（ext4/xfs/btrfs/zfs）を確認し、tmpfs、overlay、読取り不能、symlink root、world-writable
root は拒否します。`/tmp`、task container 内だけのファイル、終了時 export へ fallback
しません。`events.jsonl` は host owner のみが書き、container には公開しません。

start/command、daemon/image identity、実効 limits、PID/start-time、memory/swap/pressure、
UTC 時刻、停止理由、raw exit code を逐次 flush/fsync します。stdout/stderr は host bind
先へ直接書き、sample と終了時に fsync します。application 内部の未 flush buffer を救える
という保証ではありません。ログは private に保ち、資格情報や無関係な生 journal を Issue
へ転載しません。長い event log の readback は一 event ずつ読み、全履歴を RAM に載せません。

`--result` は complete な終端 `end` が無い、途中で切れた、不整合な場合に必ず
`status=interrupted, exit_code=null, oom=unknown` を返します。exit 137、ログ不在、
WSL 再起動を OOM の根拠にしません。Docker の `OOMKilled` はその container の報告として
別 field に保持し、事故の最終原因には外挿しません。

interrupted run は自動再試行しません。active、quiescence 未証明、または cleanup 失敗の
marker は自動 lease 解除せず、引継ぎ先が marker の exact socket/daemon ID/container name、
events の container ID/label/cgroup identity を使って停止済みかを read-only に確認し、証拠を
既存 Issue に残します。journal/output の fsync 失敗だけで、かつ exact cgroup quiescence が
証明済みなら marker を解放できますが、結果の `--result` はなお
`status=interrupted, exit_code=null, oom=unknown` であり、自動再実行の許可にはなりません。
marker の存在だけを理由に削除して再実行することは不可です。readback 不能なら未解決のまま
環境 owner へ返します。

## 検証と非目標

[fixture suite](../../tests/tools/test_host_build_admission.py) は fake Docker、合成 procfs/cgroup、
小さな lock 競合だけを使います。compiler、linker、build、daemon、GPU は起動しません。

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/tools/test_host_build_admission.py -q -p no:cacheprovider
```

fixture は無効 cgroup、環境起動拒否、同時 admission、期限、監視/log 障害、残存子孫、
中断判定を対象とします。実 Docker/kernel の enforcement を実測した結果とは分離します。
再実行禁止後は縮小版を含む実 workload を検証要件にしません。consumer の model/build
修正、長時間 GPU run、kernel 分割、事故原因の断定はこの契約の終了条件ではありません。

根拠は [Docker rootless resource limiting](https://docs.docker.com/engine/security/rootless/tips/)、
[kernel cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)、
[GNU timeout](https://man7.org/linux/man-pages/man1/timeout.1.html)、
[Linux PID namespaces](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html) です。
