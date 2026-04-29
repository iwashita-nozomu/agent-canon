<!--
@dependency-start
responsibility Documents アルゴリズム数理・実装境界方針 for this repository.
upstream design ./README.md durable document index
upstream design ./REVIEW_PROCESS.md review gate for equation/spec alignment
upstream design ./experiment-critical-review.md mathematical validity review
upstream design ../agents/workflows/research-workflow.md research workflow equation-to-code mapping
upstream design ./coding-conventions-python.md Python implementation policy entrypoint
upstream design ./coding-conventions-cpp.md C++ implementation policy entrypoint
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror ownership
upstream implementation ../tools/sync_agent_canon.sh root symlink view generation
@dependency-end
-->

# アルゴリズム数理・実装境界方針

この文書は、アルゴリズムの数理上の分解と実装上の module / function / class / API 境界を一致させるための共通方針です。
対象は、数式、擬似コード、仕様記述、method contract、数値法、最適化、シミュレーション、推論、変換 pipeline を伴うすべての実装です。

## 基本原則

- 実装境界は、先に固定した数理境界、仕様境界、state boundary の写像として設計します。
- runtime success、smoke pass、性能改善だけをもって、数理と実装が一致したとは扱いません。
- 数式や仕様が変わったのか、数値近似が変わったのか、実装構造だけが変わったのかを同じ iteration に混ぜません。
- class や helper を作る前に、どの式、変数、constraint、assumption、state transition を担うかを明示します。
- 近似、省略、guard、fallback、cache、vectorization、parallelization は、数理境界からの逸脱として記録します。

## 実装前に固定する境界

アルゴリズム実装へ入る前に、設計 artifact へ次を書きます。

- `Mathematical Object:` 対象の集合、空間、変数、状態、目的関数、制約、単位。
- `Inputs / Outputs:` 入力、出力、shape、dtype、unit、valid range、error condition。
- `State Boundary:` mutable state、derived state、cache、randomness、seed、lifecycle、ownership。
- `Update / Transform:` 更新式、変換式、停止条件、収束判定、初期条件、境界条件。
- `Assumptions:` 成り立つ条件、近似の条件、数値安定性、conditioning、dtype 依存性。
- `Non-Mathematical Boundary:` IO、serialization、logging、CLI、parallel runtime、adapter。

数理境界が未固定なら実装へ進みません。
仕様が自然言語だけの場合も、仕様項目を数式の代わりに境界項目として扱います。

## Boundary Map

設計 artifact には、少なくとも次の表を置きます。

| Math / Spec Item | Implementation Boundary | Inputs | Outputs | State Owner | Approximation / Omission / Guard | Validation |
| ---------------- | ----------------------- | ------ | ------- | ----------- | -------------------------------- | ---------- |
| 式、制約、変数、仮定、仕様項目 | path と module / function / class / method | shape、dtype、unit | shape、dtype、unit | state を保持する boundary | 近似、省略、guard、fallback | test、reference、review evidence |

この表は reader と reviewer が数理から code へ辿るための正本です。
実装者の頭の中にだけある対応や、実装後に説明を合わせる後付け mapping は不可です。

## 境界設計ルール

- 1 つの実装 boundary が複数の数理 boundary を跨ぐ場合は、合成 boundary である理由を書きます。
- 1 つの数理 boundary が複数の実装 boundary へ分割される場合は、分割軸と中間表現を明示します。
- adapter、serializer、CLI、runtime integration は数理 boundary とは別の non-mathematical boundary として扱います。
- optimization、vectorization、batching、memoization は数理を変えない構造変更か、近似を伴う変更かを分けます。
- public API は数理 object と state lifecycle を隠し過ぎないようにし、必要な invariant を型、docstring、test で露出します。
- object-oriented design を使う場合、class は数理 entity、protocol、state owner、adapter のどれかとして分類します。

## 変更種別

変更計画と review artifact では、各差分を次のどれかに分類します。

- `Mathematical Change`: 目的関数、制約、更新式、停止条件、仮定、定義域、単位を変える。
- `Numerical Change`: 離散化、近似、solver、tolerance、dtype、stability guard を変える。
- `Implementation Boundary Change`: module、function、class、state ownership、cache、data flow を変える。
- `API / Runtime Change`: CLI、serialization、config、parallel runtime、external boundary を変える。
- `Test / Evidence Change`: reference case、property test、analytical solution、snapshot、report を変える。

1 iteration では原則 1 種類の変更だけを入れます。
混ぜる場合は、なぜ分離できないかと、どの validation がどの変更種別を確認するかを書きます。

## テストとレビュー

アルゴリズム実装の validation は、次を分けます。

- `Boundary Mapping Review:` Boundary Map の全項目に実装 boundary があり、逆に実装 boundary が未対応の数理責務を持っていないこと。
- `Reference Correctness:` analytical solution、trusted implementation、small hand-computable case、既知解との比較。
- `Invariant Test:` shape、dtype、unit、conservation、monotonicity、symmetry、bounds、state lifecycle。
- `Numerical Risk Test:` tolerance、conditioning、overflow / underflow、boundary condition、dtype 差。
- `Runtime Evidence:` smoke、benchmark、throughput、memory、profiling。

runtime evidence は最後の分類であり、前四つの代替ではありません。
reviewer は、run が通っていても Boundary Map と implementation がズレていれば `fix now` とします。

## Closeout 条件

数式、擬似コード、仕様、method contract を伴う task は、closeout 前に次を満たします。

- 設計 artifact に Boundary Map がある。
- 変更後の実装 boundary が Boundary Map の path / function / class と一致している。
- 近似、省略、guard、fallback が文書化されている。
- test または review evidence が、数理境界と実装境界の対応を直接確認している。
- README、workflow、docstring、report が古い数理境界や旧実装 boundary を案内していない。

これらが欠ける場合、task は未完了です。
