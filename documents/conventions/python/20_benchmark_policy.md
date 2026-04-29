# ベンチマーク方針
<!--
@dependency-start
responsibility Documents ベンチマーク方針 for this repository.
upstream design ../README.md convention index
@dependency-end
-->


この章は、このリポジトリで行う短時間の性能計測を対象にします。
研究目的、定式化、比較対象、記録方法の正本は `agents/workflows/research-workflow.md` を参照します。

## 要約

- ベンチマークは、同一環境での前後比較を素早く行うための計測です。
- 長時間の条件探索や run 内 progress 記録が必要なものは、ベンチマークではなく experiment として扱います。
- 置き場は現在の repo 構成に合わせ、対象 topic に近い `experiments/` 配下に固定します。

## 規約

### 1. 位置づけ

- ベンチマークの目的は、実装変更の前後比較、基本的なスケーリング確認、性能退行の早期検知です。
- ベンチマークは、単一マシン上で再現しやすい小規模から中規模の計測に限ります。
- 複数条件の大規模 sweep、長時間の JSONL 蓄積、failure kind の分類が必要なものは experiment に分けます。

### 2. 配置

- ベンチマークコードは、対象となる topic に最も近い `experiments/` 配下へ置きます。
- 既存 topic が単独ディレクトリなら `experiments/<topic>/benchmarks/` または `experiments/<topic>/benchmark_*.py` を使います。
- 既存 topic が area ごとに整理されているなら `experiments/<area>/<topic>/benchmarks/` を使います。
- 汎用の subprocess 管理や GPU 割当のような再利用ロジックは、ベンチマーク側へ重複実装せず `python/experiment_runner/` へ寄せます。
- `python/benchmark/` のような新しい top-level tree は、複数 topic にまたがる共通 benchmark 群が実際に揃うまでは新設しません。

### 3. 実装スタイル

- エントリポイント名は `benchmark_*.py` または `run_*_benchmark*.py` の形にします。
- benchmark 関数は、条件を明示した JSON serializable な `dict[str, Any]` を返す形を基本にします。
- 少なくとも、timestamp、対象実装、主要条件、計測値、単位を結果へ含めます。
- benchmark を走らせる前に、問い、比較対象、主要 metric を対応する note に固定します。
- JAX の warmup や compile を含むかどうかは、結果の定義として明示します。
- 失敗を握りつぶして集計を続けるより、異常条件は早く失敗させる方を優先します。

### 4. 実行時間

- 個々の benchmark は秒から数十秒、全体でも数分以内を目安にします。
- 開発中に繰り返し回す用途を優先し、長時間化した時点で experiment へ分割します。
- benchmark では timeout 回復や partial 保存を必須にしません。
- benchmark が途中で止まった場合は、同じ出力へ継ぎ足さず fresh run でやり直します。

### 5. 出力

- 出力は JSON に固定し、後段の比較や note への転記がしやすい形にします。
- 継続参照する出力は topic ごとの結果ディレクトリに置き、巨大生成物は入口文書へ混ぜません。
- 比較用の代表結果だけを `notes/` に残します。生の繰返し結果は必要なら別保管に分離します。

### 6. Benchmark と Experiment の境界

- 「数分以内に終わる前後比較」「同一条件の基本スケーリング」は benchmark とします。
- 「多数条件の sweep」「failure kind の分類」「JSONL 逐次保存」は experiment とします。
- 詳細な使い分けは [notes/knowledge/benchmark_vs_experiment.md](../../../notes/knowledge/benchmark_vs_experiment.md) を参照します。

## 更新手順

- experiment の配置方針を変えた場合は、[30_experiment_directory_structure.md](./30_experiment_directory_structure.md) と合わせて更新します。
- 実験運用全体を変えた場合は [documents/coding-conventions-experiments.md](../../coding-conventions-experiments.md) も同時に更新します。
