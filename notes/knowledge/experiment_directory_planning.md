# Experiment Directory Planning
<!--
@dependency-start
upstream design README.md notes lifecycle index
@dependency-end
-->


実験コードの配置は、再現に必要な入口を 1 か所で辿れるかを基準に決めます。

## 先に結論

- reusable runtime は `python/experiment_runner/` のような共通 runtime 層に置く
- topic 固有コードは `experiments/<topic>/` に置く
- 長時間 run の raw 結果は `results/*` branch か別の隔離場所に置く
- `main` には code、最小 final JSON、note を持ち帰る

## なぜ実験共通部を topic から分けるか

`python/experiment/` のような広い共通実験 module を作りたくなることがあります。
ただしこの案は、runner 共通部と topic 固有の実験ロジックを同じ層へ混ぜやすく、実験ごとの入口も遠くなります。

共通基盤は runtime 層へ残し、topic 固有コードは `experiments/` 側へ寄せる方が分かりやすいです。

## 標準配置

- `experiments/<topic>/README.md`
- `experiments/<topic>/cases.py`
- `experiments/<topic>/experimentcode.py`
- `experiments/<topic>/result/<run_name>/`
- `experiments/report/<run_name>.md`

この形にすると、topic ごとの入口、条件定義、実装本体、結果、1 回分 report が同じ場所から辿れます。

## 運用上の分離

- 短い smoke run や code/test 更新は `main` に近い tree で扱います。
- 長時間 run や raw JSONL 保持は `results/*` branch などの隔離場所へ逃がします。
- benchmark と long experiment は、置き場と責務を分けたほうが整理しやすいです。

## Surviving Lessons

- experiment 実装は topic の近くに置いたほうが保守しやすいです。
- reusable process lifecycle は runtime モジュールへ寄せるべきです。
- 結果 branch と code branch を分けると衝突が減ります。
- directory 構造は、再現に必要な入口を 1 か所で辿れる形にするべきです。

## References

- [benchmark_vs_experiment.md](./benchmark_vs_experiment.md)
- [../../documents/conventions/python/30_experiment_directory_structure.md](../../documents/conventions/python/30_experiment_directory_structure.md)
