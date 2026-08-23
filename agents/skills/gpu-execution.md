# gpu-execution

<!--
@dependency-start
contract skill
responsibility Routes GPU execution through provider-independent AgentCanon admission by default and the optional managed experiment adapter only when managed lifecycle contracts are required.
upstream design ../../documents/experiments/gpu-direct-command.md direct admission state machine, exact environment, lifecycle, and route-selection contract
upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md canonical discovery, occupancy, lock, and admission evidence ownership
upstream design ../../documents/experiments/gpu-admission-r5-nvidia-visibility.md NVIDIA topology and full UUID boundary
upstream design experiment-lifecycle.md managed experiment artifact boundary
downstream design ./environment-maintenance.md consumes canonical Docker device and exact environment forwarding
downstream implementation ../../tools/experiments/run_gpu_command.py provider-independent direct-command CLI
downstream implementation ../../tools/experiments/run_managed_experiment.py optional managed provider adapter
downstream implementation ../../tools/ci/run_gpu_container.sh single-entry Docker injection adapter with internal CDI/all selection
downstream implementation ../../.agents/skills/gpu-execution/SKILL.md Codex discovery shim
downstream implementation ../../tests/agent_tools/test_gpu_execution_docker_all_contract.py single-entry Docker documentation regression contract
upstream environment ../../agent-canon-environment.toml audited managed ExperimentRunner provider identity and runtime item
@dependency-end
-->

## 目的

この skill は GPU/CUDA/JAX/XLA/IREE 実行を AgentCanon の厳格な admission、full UUID
lock、固定 environment、terminal evidence に接続します。通常の pytest、benchmark、診断、
任意 argv は provider-independent direct route を使います。topic/cases/source snapshot/
artifact/completion coverage が必要な実験だけ managed route を使います。

static test や CPU-only smoke を実機 GPU validation と取り違えず、GPU が使えない場合は
blocker evidence を残します。

## 適用範囲と owner 境界

- GPU allocation、CUDA/NVIDIA visibility、MIG、`nvidia-smi`、JAX/XLA allocator、GPU
  smoke/benchmark/diagnosis が対象です。
- NVIDIA topology、process occupancy、BUSY/UNKNOWN/FREE、full UUID reservation、fresh
  post-lock observation は `execution_resource_plan.py` が canonical owner です。
- provider-independent plan/environment/child lifecycle は `gpu_command_admission.py`、CLI は
  `run_gpu_command.py` が owner です。
- topic の設計と registry、managed run artifact は `experiment-lifecycle` が所有します。
- solver と数値 correctness は `computational-optimization`、Docker/driver/CI は
  `environment-maintenance`、Python/C++ review は各 review skill が所有します。
- hooks/resource projection の public schema は変更しません。

## Route selection

次の条件では direct route が既定です。

- pytest、benchmark、diagnostic、smoke、one-off script を一つの argv として実行する。
- 成否が child exit、stdout、stderr、GPU admission/lifecycle evidence で定義できる。
- topic registry、cases、source snapshot、provider artifact schema、completion coverage を
  必要としない。

```text
python3 tools/experiments/run_gpu_command.py \
  --gpu-count 1 \
  --min-free-memory <bytes> \
  -- <argv...>
```

次の contract が一つでも必要な場合だけ managed route を使います。

- experiment topic/variant/run identity と registry command
- case expansion と resource estimate/capacity wire schema
- source/config snapshot と provider-owned artifact manifest
- provider lifecycle result、worker coverage、completion coverage

```text
python3 -m tools.experiments.run_managed_experiment \
  --topic <topic> --variant <variant> -- <inner argv...>
```

managed route だけが `experiment-runner-admitted` の存在、contract identity、request/result
schema を検証します。direct route は provider、registry、topic、cases、snapshot、artifact、
completion coverage を参照しません。

## Direct admission contract

```text
strict nvidia-smi -L
  -> executable physical/MIG leaves
  -> S0 BUSY/UNKNOWN/FREE + memory
  -> full UUID lock
  -> distinct S_lock
  -> race/memory validation
  -> immutable plan
  -> exact environment
  -> shell=False child
  -> descendant quiescence
  -> one-attempt lock release
```

XML topology/process hierarchy が UUID binding authority です。query-compute-apps は XML
PID の一意 join 後の supplement だけです。`FREE` だけが eligible で、UNKNOWN、MIG parent
closure、topology drift、visibility drift、memory shortage、lock contention は fail-closed です。
integer index と UUID prefix は使用しません。

plan は argv/cwd、candidate inventory、MIG joins、initial/post-lock event、unit states、selected
memory、全 reservation ID、全 lock device/inode、admission fingerprint を environment 生成前に
固定して書き出します。

## Environment

selected full physical/MIG UUID の visibility は plan freeze 後にだけ生成します。

```text
CUDA_VISIBLE_DEVICES=<selected full UUID list>
NVIDIA_VISIBLE_DEVICES=<same list>
JAX_PLATFORMS=cuda
XLA_PYTHON_CLIENT_PREALLOCATE=false
XLA_PYTHON_CLIENT_ALLOCATOR=platform
XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR=false
```

JAX は admitted child 内で初めて import します。`JAX_PLATFORMS=cuda` により GPU backend が
ない場合の CPU fallback を成功扱いしません。継承した secret 値は plaintext evidence に
書かず、fingerprint では値を hash して exact environment に束縛します。

## Docker GPU wiring

admitted child が Docker container を起動する public 経路は一つだけです。caller は
`--gpus`、`--device`、CDI qualified device、runtime mode を選ばず、常に
repository-owned shell adapter を同じ形で呼びます。

```text
python3 tools/experiments/run_gpu_command.py \
  --gpu-count 1 --min-free-memory <bytes> -- \
  bash tools/ci/run_gpu_container.sh \
    --image <canonical-image> -- <argv...>
```

shell adapter は6変数の存在、CUDA/NVIDIA visibility一致、full UUID/MIG identityを
Docker起動前に確認します。その後、接続先Docker daemonが`docker info`の
`DiscoveredDevices`として公開するCDI inventoryだけをread-onlyで観測します。client hostの
CDI specや`nvidia-ctk`を別のauthorityにしません。

selected identityの全てについてexact `nvidia.com/gpu=<full UUID/MIG>` がdaemon inventoryに
存在する場合だけ、同じ順序の個別`--device`引数を構成します。exact mappingが一つでも欠ける、
`nvidia.com/gpu=all`しかない、index名しかない、またはinventory fieldを読めない場合は、同じ
entrypointの内部で既存の`--gpus all` injectionを選びます。UUIDをinteger indexへ推測変換せず、
partial CDIとall injectionを混在させません。

どちらのinjectionでも6個の値を同じ`docker run` argvへ`-e NAME=VALUE`として明示します。
device injectionはcontainerへdevice/libraryを渡す機構、admitted environmentはlock済みcompute
setへvisibilityを狭める機構として分離します。capability判定後のworkload `docker run`は一度だけ
実行し、失敗後に別injection方式で再実行しません。

JAX は host 側や既存 container state で先に import せず、上記 exact environment を受けた
新規 container child 内で初めて import します。container 内で `jax.default_backend()` が
`gpu` でない結果は CPU fallback であり、GPU validation pass ではありません。

## Child lifecycle

direct adapter は argv array、`shell=False`、新しい session で一度だけ child を起動します。
Linux subreaper と PID/starttime/ancestry/session/process-group/adoption evidence で
AgentCanon-started descendants の transitive closure を追跡します。既存 runner child は対象外
です。signal/kill は送りません。

`Popen` 後の内部例外も descendant quiescence が成立するまで保持します。root と全 descendant
が停止する前に lock を release しません。release は一回だけ試行し、ambiguous close を再試行
で上書きしません。

## Managed route

managed route は従来どおり shell なしで次を一度だけ起動します。

```text
experiment-runner-admitted --request <path> --result <path>
request schema: agentcanon-managed-run/v1
result schema:  agentcanon-managed-run-result/v1
```

request/result fingerprint、worker/process group、quiescence、completion coverage、cleanup、
terminal evidence が成立するまで reservation を保持します。provider repository/contract
identity は `agent-canon-environment.toml` と一致させます。direct route の導入は managed wire
schema、provider identity、既存 completion coverage を変更しません。

## Validation と blocker

provider-independent owner tests:

```text
python3 -m pytest tests/tools/test_run_gpu_command.py -q
```

実機 JAX smoke:

```text
python3 tools/experiments/run_gpu_command.py \
  --gpu-count 1 --min-free-memory 2147483648 -- \
  python3 -c 'import jax; assert jax.default_backend() == "gpu"; print(jax.devices())'
```

Docker 実機 smoke:

```text
python3 tools/experiments/run_gpu_command.py \
  --gpu-count 1 --min-free-memory 2147483648 -- \
  bash tools/ci/run_gpu_container.sh \
    --image <canonical-image> -- \
    python3 -c 'import jax; assert jax.default_backend() == "gpu"; print(jax.devices())'
```

GPU-heavy test/benchmark も同じ direct adapter の `--` 後へ argv として渡します。managed
regression は既存 `tests/tools/test_run_managed_experiment.py` で確認します。

GPU またはDocker GPU injectionが利用不可なら `gpu_validation_blocker=<reason>`、未実行 claim、
`nvidia-smi`/Docker diagnostic/stderr を closeout に記録します。fake test、static pass、CPU-only
smoke は実機 GPU pass ではありません。

## Closeout

closeout は選択した route、candidate/selected full UUID、plan/admission/environment fingerprint、
内部選択した`individual-cdi`または`gpus-all` injection、選択理由、start/end、raw exit、
stdout/stderr hash、descendant quiescence、release evidence、targeted tests、managed regression、
`gpu_validation_blocker`を参照します。
