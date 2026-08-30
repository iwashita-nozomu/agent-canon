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

## process identity

各 holder は full opaque UUID、PID、starttime、namespace、cgroup と結び付きます。
`/proc/<pid>/stat` starttime、`stat`/`status` PPid、namespace、cgroup を同じ observation
で検証し、read race、PID reuse、cycle、depth 超過、不一致を typed failure にします。
`pstree -sp` は bounded diagnostic と capability detection だけであり、proc が完全なら
実行継続できます。probe は signal/kill を実行しません。

## 実行時の evidence

snapshot 内容 hash は content fingerprint、freshness の判定は event ID で行います。
lock-held fresh observation、reservation receipt、lock inode/device、selected UUID を
composite admission fingerprint に束縛し、その値を plan、exact environment、CLI
request/result、terminal/closeout へ伝播します。
