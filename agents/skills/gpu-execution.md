# gpu-execution

<!--
@dependency-start
contract skill
responsibility Runs ordinary GPU workloads by selecting an available device and using native Docker; keeps admission and managed lifecycle opt-in.
upstream design ../../documents/experiments/gpu-direct-command.md optional admission adapter contract
upstream design experiment-lifecycle.md optional managed experiment artifact boundary
downstream design ./environment-maintenance.md consumes the ordinary GPU execution route
downstream design ../../tools/README.md project execution guidance
downstream implementation ../../.codex/personal/skills/gpu-execution/SKILL.md Codex discovery shim
downstream implementation ../../tests/agent_tools/test_gpu_execution_docker_all_contract.py native Docker command regression
@dependency-end
-->

## 通常の実行

空いているGPUを指定して、プロジェクトのimageとcommandを`docker run`します。
GPUを使うという理由だけで、専用runnerや追加の承認手順へ移りません。

Dockerが動くホストの`nvidia-smi`で、使用状況と空きメモリを確認します。
観測した空きGPUのindexまたはUUIDを`GPU`、プロジェクトのimageを`IMAGE`に設定し、
実行するcommandと引数を`"$@"`として渡します。

```bash
nvidia-smi
docker run --rm --gpus "device=$GPU" "$IMAGE" "$@"
```

`GPU`は一つのdeviceを指定します。既に空きを確認したGPUが指定されている場合は、
同じ確認や利用許可の質問を繰り返さず、その指定で実行します。indexを固定の空きGPUと
仮定せず、remote Dockerではclient側のGPU一覧をdaemon側の一覧と取り違えません。

通常経路に`run_gpu_command.py`、`run_gpu_container.sh`、XML解析、PIDの名前空間照合、
UUID lock、post-lock再観測、plan/fingerprint/receiptを要求しません。
最小空きメモリ値の手入力や、JAXを使わないcommandへのJAX/XLA設定も不要です。
必要な設定、mount、資源上限はプロジェクトの既存Docker実行設定を使います。

## 空き確認と失敗の扱い

空きの確認はその時点の観測であり、排他予約ではありません。既知の他者の計算を奪ったり、
そのprocessを停止したりせず、空きを判断できない場合は不明と伝えます。
表示用processが存在することや、別名前空間のPIDを解決できないことだけを理由に、
通常実行へ厳格なadmissionのUNKNOWN判定を持ち込みません。

Dockerの終了コードと実際のエラーをそのまま扱います。個別GPUの指定に失敗しても、
無断で`--gpus all`へ広げたり、別daemonへ切り替えたり、driver設定を書き換えたりしません。
既存の資源上限、権限境界、利用者の再実行禁止は変更しません。

## 必要な場合だけ使う経路

排他予約が明示的に必要な場合だけ、[admission設計](../../documents/experiments/gpu-direct-command.md)
の既存adapterを使います。ここではその実装や検証条件を緩めません。
managedなtopic、case、snapshot、artifact lifecycleが必要な場合だけ、
[experiment-lifecycle](experiment-lifecycle.md)へ進みます。
通常のpytest、benchmark、診断を実行するだけなら、どちらも前提にしません。

## 検証と報告

指定GPU、実行command、終了コード、必要な出力を既存の作業記録へ残します。
GPUを使ったという主張は、そのcommandが実際にGPU backendを使用した結果で確認します。
JAXを使う場合だけ、container内で`jax.default_backend() == "gpu"`を確認します。
CPU-onlyやfake commandの成功を実機GPU検証と扱わず、実機未実行ならその点を明記します。

局所回帰テスト:

```text
python3 -m unittest discover -s tests/agent_tools -p test_gpu_execution_docker_all_contract.py -v
```

Dockerのindex/UUID指定は[公式GPU文書](https://docs.docker.com/engine/containers/gpu/)を参照します。
