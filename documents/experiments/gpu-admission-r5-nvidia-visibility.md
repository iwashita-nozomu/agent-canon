# AgentCanon GPU admission R5 NVIDIA visibility boundary

<!--
@dependency-start
contract design
responsibility Defines the NVIDIA XML topology, process join, and unit-state boundary.
upstream design ./gpu-admission-r5-source-packet.md fixed R5 admission packet
downstream implementation ../../tools/experiments/execution/execution_resource_plan.py NVIDIA and occupancy owners
@dependency-end
-->

## XML topology を正本とする理由

GPU/MIG の UUID binding は `nvidia-smi` XML の topology/process hierarchy だけを正本と
します。physical UUID、MIG UUID、parent-child topology、XML PID の関係を一つの完全な
graph として検証し、graph が完全な unit を示す限り補助コマンドの欠落だけで unit を
UNKNOWN にしません。

`query-compute-apps` は XML PID への一意な join に成功した行だけを memory/name の
補助 evidence として採用します。PID が複数候補に join する、XML に存在しない、または
join の一意性を証明できない場合、その補助値を捨てます。補助値は XML の UUID binding
authority を置き換えません。

## unit state

caller allocation の各 unit は次の状態を持ちます。

| state | admission の扱い |
| --- | --- |
| `BUSY` | holder と topology 境界上の親子を eligible から除外 |
| `UNKNOWN` | 証拠不足として topology 境界全体を eligible から除外 |
| `FREE` | memory、reservation、caller allocation の条件を満たす場合だけ選択候補 |

MIG unit の unknown は MIG と physical parent、physical unit の unknown は physical と
全 descendants に閉じます。XML binding が不明なときは caller allocation 全体を
UNKNOWN に閉じます。compute-only の process list、短い UUID、integer GPU index は
absence の証明になりません。

observation が保持する `unknown_gpu_ids` は、候補外も含む観測済み inventory の
uncertainty を保持します。candidate filter で UNKNOWN を捨てた後に full inventory を
再分類してはいけません。allocation-scoped な `unit_states` と visibility witness は
選択範囲を示すものであり、候補外の FREE を証明しません。full-inventory projection は
元の UNKNOWN を保持し、scope が未証明の unit を FREE として補完しません。

`accounted_processes` は NVIDIA の accounting mode が保持する終了済みを含む履歴であり、
現在の GPU 占有を表す process inventory ではありません。したがって parser はこの要素を
未知の process scope として拒否せず、`processes`、`compute_processes`、
`graphics_processes` の active container だけを current holder として数えます。active
container が欠落する場合や permission/unknown marker がある場合の fail-closed は維持します。

## process identity

各 holder は full opaque UUID、PID、starttime、namespace、cgroup と結び付きます。
`/proc/<pid>/stat` starttime、`stat`/`status` PPid、namespace、cgroup を同じ observation
で検証し、read race、PID reuse、cycle、depth 超過、不一致を typed failure にします。
`pstree -sp` は bounded diagnostic と capability detection だけであり、proc が完全なら
実行継続できます。probe は signal/kill を実行しません。

### WSL の namespace 境界

WSLg system distro は user distro と異なる PID namespace を持ちます。NVIDIA XML の
PID に対応する local `/proc/<pid>` がないことは、process の不在や GPU の空きを
意味しません。現行の local-namespace identity contract で結合できない holder は
UNKNOWN のままとし、同じ数値 PID の別 namespace process とも同一視しません。

`/Xwayland` という名前、type `G`、used memory `N/A`、empty compute-app query は
cross-namespace completeness の証明でも graphics-sharing の許可でもありません。
現行の conservative occupancy は検証できた graphics / compute holder を BUSY とし、
未証明の identity は UNKNOWN とします。対応する host observation を追加する場合は、
既存 owner 内で namespace-qualified identity、UUID binding、観測範囲の完全性と
freshness を実機 evidence により確立する必要があります。graphics-sharing policy の
導入を observation 修正に隠してはいけません。

WSLg の namespace 構成は [Microsoft WSLg architecture](https://github.com/microsoft/wslg#wslg-system-distro)、
WSL の NVML query 制約は [NVIDIA CUDA on WSL guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)
を参照します。これらの資料だけで特定 host の observation capability が成立したとは
扱いません。

## 実行時の evidence

snapshot 内容 hash は content fingerprint、freshness の判定は event ID で行います。
lock-held fresh observation、reservation receipt、lock inode/device、selected UUID を
composite admission fingerprint に束縛し、その値を plan、exact environment、CLI
request/result、terminal/closeout へ伝播します。
