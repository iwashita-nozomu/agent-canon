# Experiment Report（実験 report）
<!--
@dependency-start
contract template
responsibility Documents Experiment Report for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}
- Created At (UTC): {\{CREATED_AT}}

## Reader Map（読者 map）

この template は 1 つの experiment report の構造を所有します。question、protocol、results、
interpretation、limitations、reproducibility record、artifacts、critical review の順に埋め、
abstract は最後に書きます。run-scoped empirical evidence に使い、durable policy、workflow
change、根拠のない conclusion を昇格させる場所にはしません。

## Contract Readback（契約 readback）

- owner / responsibility and OOP boundary:
- design-to-implementation trace:
- dependency / side-effect map:
- algorithm contract before tests:
- necessary-and-sufficient oracle:
- failure-cause classification:
- conflict intent and preserved interpretation:
- independent review and source snapshot:
- result/environment provenance and cleanup readback:

## Abstract（abstract）

<!-- 最後に書きます。question、protocol、数値付きの strongest result、意味、limitation を 4〜7 文で記録します。 -->

## Question and Context（問いと context）

### Question（問い）

<!-- この run はどの empirical question を扱ったか。 -->

### Formulation（定式化）

<!-- mathematical/algorithmic setup を prose で記録します。 -->

### Comparison Target（比較対象）

<!-- main、baseline、prior method、external reference。 -->

### Metrics（metric）

<!-- accuracy、time、memory、failure rate、robustness など。 -->

## Protocol（protocol）

### Command（command）

<!-- exact command または script entry point。 -->

### Environment（environment）

<!-- branch、commit、worktree、hardware、software version、timeout、seed。 -->

### Fairness Notes（公平性メモ）

<!-- same case set、same hardware、same timeout、same dtype policy など。 -->

## Results（結果）

### Quantitative Summary（定量要約）

<!-- case count、success rate、failure kind、代表 metric、変動性。 -->

### Comparison Table（比較表）

<!-- 同じ case に対する baseline/main/reference の比較。 -->

### Main Trends（主要な傾向）

<!-- 具体的な数値とともに、観測した主要 finding を先に報告します。 -->

### Exceptions and Failures（例外と failure）

<!-- unexpected outcome、unstable region、failure pattern。 -->

### Figures（figure）

<!-- 各 figure は axis name、unit、linear/log scale、読み方を示す一文を持ちます。 -->

## Discussion（考察）

### Supported Interpretation（証拠に支えられた解釈）

<!-- 観測結果が支える内容。 -->

### Comparison with Baseline or Prior Work（baseline/prior work との比較）

<!-- finding が main、baseline、literature とどう関係するか。 -->

### Speculative Interpretation（推測的解釈）

<!-- さらに evidence が必要な可能性のある説明。 -->

## Conclusion（結論）

<!-- final takeaway を述べ、各 major claim の supporting figure/table を引用します。 -->

## Limitations（制約）

<!-- scope limit、sample size limit、hardware dependence、comparison gap。 -->

## Reproducibility Record（再現性 record）

<!-- commit、exact command、environment、final JSON、raw JSONL、renderer/plot command。 -->

## Artifacts and Carry-Over（artifact と carry-over）

<!-- main に run artifact として残す output と、durable docs、notes、summary に昇格する result。 -->

## Critical Review（批判的レビュー）

### Overclaim Risk（過大主張リスク）

<!-- この report だけではまだ正当化できない発言。 -->

### Missing Evidence（不足 evidence）

<!-- これから実行または比較する必要があるもの。 -->

### Alternative Explanation（代替説明）

<!-- 競合する妥当な interpretation。 -->

### Next Check（次の確認）

<!-- この report が正当化する次の具体的な experiment または code change。 -->
