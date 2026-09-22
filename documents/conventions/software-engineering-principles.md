<!--
@dependency-start
contract policy
responsibility Defines language- and paradigm-neutral software engineering principles and decision precedence for AgentCanon design, implementation, refactor, review, and validation.
upstream design ./README.md convention index and reader route
upstream design ../../PHILOSOPHY.md top-level responsibility and source-of-truth philosophy
upstream design ../design/semantic-responsibility-contract.md semantic action and verification-owner allocation
upstream design ../design/responsibility-rationale.md mechanism rationale and activation boundary
downstream design ../design/responsibility-cleanup.md replacement retirement and necessary consumer migration
downstream design ./object-oriented-design.md OOP and SOLID specialization
downstream design ../../agents/skills/comprehensive-development.md cross-surface design and delivery consumer
downstream design ../../agents/skills/code-cleanup.md existing capability comparison and replacement consumer
downstream design ../../agents/skills/refactor-loop.md behavior-preserving refactor consumer
downstream design ../../agents/skills/change-review.md findings-first review consumer
downstream design ../../agents/skills/codex-task-workflow.md implementation and review-remedy decision consumer
downstream design ../../documents/notes/knowledge/coding_decision_methods.md external method and source note
@dependency-end
-->

# ソフトウェア工学原則

## Purpose

この文書は、AgentCanon の設計、実装、refactor、review、validation に共通する、
言語・framework・programming paradigm に依存しないソフトウェア工学原則の正本です。
原則名を網羅することではなく、複数の原則が競合したときに、現在の contract と
evidence から同じ判断へ到達できることを目的にします。

原則は checklist、score、receipt の項目ではありません。変更で実際に到達する
contract、invariant、owner、failure mode に関係する原則だけを選び、設計判断、実装、
review finding、validation route に接続します。選ばれなかった原則について
`not applicable`、negative token、空の証跡を作りません。

## Reader Map

- 最初に「所有境界」と「判断の優先順位」を読みます。
- 新しい module、API、wrapper、tool、skill、checker、schema、document を追加する前は、
  「責務と依存境界」と「単純さと抽象化の admission」を読みます。
- 規模に応じた処理・資源コストを決める実装方式を選ぶ前は、
  [規模を先に置く方式選定](#workload-and-scale-before-mechanism) を読みます。
- refactor では「変更単位と完全性」、review では「Evidence model」を読みます。
- class、stateful object、inheritance、`Protocol`、public object model が変わる場合だけ、
  [オブジェクト指向設計方針](./object-oriented-design.md) を専門規約として追加します。
- 数理・algorithm・domain semantics の action と obligation owner は
  [Semantic Responsibility Contract](../design/semantic-responsibility-contract.md) が所有します。
- skill、gate、workflow、diagnostic mechanism を残す理由と activation boundary は
  [AgentCanon responsibility rationale](../design/responsibility-rationale.md) が所有します。

## 所有境界

| Surface | Owns | Does not own |
| --- | --- | --- |
| [PHILOSOPHY.md](../../PHILOSOPHY.md) | AgentCanon 全体の top-level philosophy と最初の reader route | 個別原則の詳細、task-specific target state |
| この文書 | 一般原則、競合時の優先順位、誤用防止、evidence model | 特定 module の設計、言語 syntax、OOP 固有の形 |
| [object-oriented-design.md](object-oriented-design.md) | class、state、inheritance、composition、`Protocol`、SOLID の専門判断 | 全変更への一律 OOP activation |
| language convention | syntax、layout、language/toolchain 固有の境界 | repository-wide の意味上の owner |
| task-specific design | target state、tradeoff、assumption、implementation trace | 一般原則の第二正本 |
| Issue / PR | current snapshot 固有の要求、削減理由、実装・検証 evidence | 長期 policy の唯一の根拠 |
| `documents/notes/knowledge/` | 外部 source、method、再利用可能な調査 note | shared policy の正本 |

同じ policy、invariant、state、identity、lifecycle を複数 surface が所有してはなりません。
専門文書はこの文書の一般原則を複製せず、専門領域で追加される判断だけを所有します。

## 判断の優先順位

原則が競合する場合は、次の順序で判断します。下位の原則は上位の contract を
弱める根拠になりません。

1. 明示された user / domain contract、safety、correctness
2. semantic invariant、state / lifecycle owner、public compatibility
3. root-cause closure、reachable failure handling、cleanup / recovery
4. responsibility / dependency boundary、information hiding、authority boundary
5. testability、reproducibility、operational observability
6. simplicity、change locality、reuse、abstraction cost
7. stylistic consistency

この順序は「大きい変更を優先する」という意味ではありません。上位 contract を
完全に閉じる owning unit を選び、無関係な変更を除いたうえで、完成後の保守対象が
最小になる実装を選びます。局所性は責務の閉包であり、変更行数・file 数の最小化では
ありません。小さい diff、短い code、既存 style は correctness や root cause に優先しません。

## 原則一覧

| Principle | Protects / prevents | Activation evidence | Common misuse |
| --- | --- | --- | --- |
| Contract and invariant first | 意味、互換性、停止・失敗条件の保存 | user requirement、public contract、domain invariant、counterexample | 「単純」「小さい」を理由に必要条件を落とす |
| Separation of concerns | 独立 owner と変更理由の混線防止 | 異なる invariant、lifecycle、effect、reader、validation owner | file 数や layer 数を機械的に増やす |
| Single responsibility | 一つの replaceable responsibility と変更理由 | 同じ actor、state、invariant、lifecycle、failure owner | 1 function / 1 file を責務と同一視する |
| High cohesion / low coupling | owner 内の整合と owner 間 drift の低減 | 共有 invariant と concrete dependency graph | 見た目が似た処理を同居させる |
| Information hiding | stable contract と内部詳細の分離 | caller が必要とする role、public behavior、effect boundary | temporary path、storage、生成順序を API にする |
| Dependency direction | policy が detail に支配されることの防止 | caller/provider、composition root、adapter、import edge | 実装が一つしかないのに abstraction を増やす |
| KISS | 完全な contract に対する変更後の保守コードスペースの最小化 | 新旧実装、owner、state、branch、surface、invariant の比較 | 最短 code、minimum diff、旧実装温存、error path 省略 |
| YAGNI | speculative mechanism と未使用 invariant の増殖防止 | concrete caller、current requirement、reachable failure | 要求済み migration や cleanup を未完にする |
| DRY | 同じ knowledge / policy / state の複数正本化防止 | 同じ意味、contract、change reason、owner | textual similarity だけで異なる意味を統合する |
| Change locality | reviewable で rollback 可能な responsibility closure | owner と evidence-linked consumers / docs / tests | symptom file だけに閉じて root owner を残す |
| Testability | stable oracle と境界の検証可能性 | counterexample、pre/postcondition、observable output | implementation step をそのまま test に固定する |
| Determinism | 同じ canonical input から同じ identity / output | materializer、export、ordering、hash、selection contract | 本質的な外部非決定性を隠して成功扱いする |
| Idempotency | retry / reconcile による余分な mutation の防止 | setup、sync、migration、publication、recovery | 2回目を常に no-op にし、外部 drift を見逃す |
| Reproducibility | 結果の再構成と比較可能性 | source、config、command、environment、artifact identity | 全 producer に固定 artifact 一式を要求する |
| Failure classification | branch defect と入力・環境・外部要因の混同防止 | first failure、owner、error class、precondition | fallback、ignore、成功への変換 |
| Observability | state transition と first failure の追跡 | actionable state、input class、owner、side effect | log / report surface 自体を目的化する |
| Traceability | requirement から accepted source までの追跡 | Issue、branch、PR、diff、validation、source identity | chat や一時 report だけに判断を残す |

## 1. Contract、correctness、invariant

### SEP-01 Contract first

実装は、明示された user / domain contract と、既存の public contract を先に固定します。
入力条件、出力条件、不変条件、停止条件、失敗条件、compatibility、side effect、cleanup
のうち、変更に関係するものを実装前に特定します。

- test は code path をなぞるのではなく、contract、counterexample、stable oracle を固定します。
- validation success は、別の failure class を黙って無視した結果であってはなりません。
- public behavior を変える場合は、caller、migration、deprecated / removed surface、rollback
  を同じ target state で閉じます。
- 数理上の意味、algorithm の停止条件、数値 failure semantics は、短さや既存実装の形より優先します。

### SEP-02 Invariant and state ownership

同じ state transition、identity、transaction、lifecycle、consistency rule は、一つの
canonical owner が管理します。caller は owner の contract を消費し、同じ guard、status、
manifest、cache identity を別 schema で再所有しません。

owner を選ぶ根拠は path の近さではなく、state を生成・変更・破棄し、failure と recovery
を閉じる責務です。複数の hard edge を切ると atomicity や consistency が壊れる場合、
その edge は同じ owning unit に残します。

## 2. 責務と依存境界

### SEP-03 Separation of concerns and single responsibility

関心を分ける単位は、file、class、function の数ではありません。次のいずれかが異なる場合、
別 responsibility の候補です。

- 変更を要求する actor / reason
- 守る invariant と failure semantics
- state / resource lifecycle
- external effect、authority、rollback
- reader / caller contract
- primary validation owner

逆に、同じ invariant と atomic transition を守る処理を、行数や形式だけで分割しません。
一つの責務は複数 file にまたがってもよく、一つの file に複数の小さな stateless value / function
があっても、同じ owner contract に属するなら直ちに違反ではありません。

数理・domain computation、orchestration、I/O、persistence、rendering、configuration、
validation は、別の変更理由と failure owner を持つ場合に分離します。分離後は、各 owner が
必要な最小 contract で接続されていることを確認します。

### SEP-04 Cohesion, coupling, and information hiding

高い cohesion は、同じ invariant、state、domain vocabulary、lifecycle を守る要素が同じ owner
に集まっている状態です。低い coupling は、別 owner の内部表現、temporary path、生成順序、
concrete storage、private state に依存せず、stable role contract だけを消費する状態です。

public surface には caller が判断・実行に必要な意味だけを出します。次を public contract に
流出させません。

- temporary implementation name、compatibility shim の都合
- cache / database / filesystem の内部配置
- generator / materializer の内部 step
- tool 固有の receipt や diagnostic token
- secret、巨大 object、不要な environment detail

information hiding は観測不能化ではありません。failure owner が診断に必要な state、input class、
source identity は、stable diagnostic contract として公開できます。

### SEP-05 Dependency direction and authority

high-level policy は low-level implementation detail に従属させません。dependency は、
caller が必要とする role contract、typed value、adapter、composition boundary を通します。
ただし、具象実装が一つで、差し替え、test boundary、external integration の根拠がない場合、
将来のためだけの interface、factory、registry、wrapper を追加しません。

write、external service、process、filesystem、network、shared mutable state は effect / authority boundary
を持ちます。pure decision と mutation を分け、mutation owner は precondition、conflict、readback、
cleanup / rollback を責任範囲に含めます。

inheritance、substitutability、interface segregation、DI container、public object model の判断は、
実際に object contract が変わる場合だけ [object-oriented-design.md](object-oriented-design.md) へ委譲します。

## 3. 単純さと抽象化の admission

### SEP-06 KISS

KISS は、要求された contract を完全に満たす候補の中で、変更後に保守するコードスペースを
最小にする設計原則です。「最短の code」や「最小の diff」ではなく、完成形に残る次の実体と
相互依存を比較します。追加分だけでなく、既存実装とその維持に必要な接続も含めます。

- 実装本体、補助コード、canonical owner と source of truth
- public surface と execution route
- mutable state と lifecycle
- branch、mode、selector、special case
- dependency、invariant、schema、compatibility relation
- independent checker、workflow、receipt、generated view

差分や変更 file 数を減らすために旧実装を残す案より、不要な実装と接続を削除して完成形を
小さくする案を選びます。置換時の削除と必要な利用側移行は
[RC-09](../design/responsibility-cleanup.md#duplicate-implementation-retirement) で同じ修正として閉じます。
行の圧縮、別 file への移動、必要な意味や性能保証の削減はコードスペースの削減ではありません。

要求上必要な error handling、cleanup、migration、test、documentation を削って短くした実装は
単純ではなく、未閉鎖の責務を別の場所へ移しただけです。どの異常処理が必要かは
[到達可能性と追加修正の必要性](#reachability-and-remedy-necessity) で判断し、
重複防御を温存する理由にはしません。

#### Workload and scale before mechanism

新規実装や変更で algorithm、data structure、処理単位、状態・資源管理を選ぶ場合は、
目の前の入力例から方式を即決せず、今回の contract が要求する規模で成立する候補を
先に絞り、その中から最も単純な方式を選びます。小さい diff や短い helper が、
繰返し利用や入力増加を含む全体コストの小ささを意味するとは限らないためです。
単純な rename 等、これらの判断を変えない編集へ新しい設計作業を追加しません。

1. **増えるものと要求範囲を先に特定する。** 既存の仕様・設計・caller から、判断に関係する
   入力件数・要素サイズ、反復呼出、同時実行、保持期間等を選びます。既知の通常規模、
   要求上の範囲、時間・メモリ等の制約とその根拠を区別し、小さい fixture や今回の実行値を
   上限へ昇格させません。未知の上限や将来負荷は捏造せず、許される成長と未確認点を残し、
   方式選択を変える一点だけを確認します。
2. **既存機能を使う基準案の全体コストを見積もる。** 直接利用・合成から始め、必要な時間、
   ピークメモリ、I/O・外部呼出数を規模の関数として捉えます。前処理、反復される全走査、
   コピー・中間データ、保持状態、同時実行による増幅も関係するものだけ含めます。
   例えば n 件を q 回全走査する案は、一呼出の線形性だけでなく全体の n と q の積を見ます。
   最悪時・平均時・償却のどの根拠かと、その成立前提を区別します。既存 API を使うだけで
   合成後もスケールするとは扱いません。
3. **要求範囲で成立する最小の方式を選ぶ。** 現実に競合する候補だけを、支配的なコスト、
   前処理・保持・更新の負担、既存保証と照合します。Big-O の名前だけで優劣を決めず、
   明確に限定された規模では単純な方式を残して構いません。一方、要求範囲で破綻すると
   分かる方式を「まず動かし、後で最適化する」と採用しません。有効入力を切り捨てたり、
   固定件数や例外分岐で対象を狭めたりして成立したことにしません。cache、並列化、分散化、
   新 API、汎用化も、この比較で残る具体的な不足なしに追加しません。

採用方式、規模の前提、支配的コストと根拠、単純な代案を退けた理由を、実装前に既存設計の
該当節へ簡潔に残します。十分な既存説明は参照を再利用し、task / worker handoff は同じ節に
接続します。worker が局所都合で algorithm、保持方法、反復・並行構成や前提を変える場合は、
先に同じ判断を更新して引き継ぎ、実装後の説明付けや別の局所設計で置き換えません。
review も同じ前提と実 diff のコストを照合し、小さい成功例だけを規模への保証にしません。

解析や既存 API の保証で判断できる場合は実測を必須にしません。定数因子や実行系の特性が
選択を左右するときだけ、既存環境で実行可能な最小の検証を使います。規模を変えた検証は
主張を確かめる必要がある場合に選び、根拠なしに小規模の時間を要求上限へ外挿しません。
必要な性能確認が実行不能なら対象の主張を未検証として残し、性能不足とも検証済みとも
扱いません。そのために環境を再構築したり、独立して進められる変更を止めたりしません。
本節は方式選定の判断支援であり、全件監査、全利用箇所の移行、巨大 benchmark、新しい
checker、schema、帳票、承認段階を要求せず、現在の Issue の完了範囲を広げません。

### SEP-07 YAGNI

次の evidence がない mechanism は追加しません。

- current requirement または approved target state
- concrete caller / consumer
- reproduced または静的に到達可能な failure に対する未充足の要求
- stable extension point を必要とする複数実装
- external boundary を隔離する adapter need

YAGNI は、要求済み behavior、必要な compatibility migration、failure handling、cleanup、validation
を後回しにする理由ではありません。完成した target state に不要な将来 surface を作らない原則です。

#### Reachability and remedy necessity

異常を表す局所式が書けること、現行の実行でそこへ到達できること、到達した結果が
要求を満たさないことは別です。異常仮説から修正を導くときは、現在の有効な入口、
contract が許す入力・状態、制御・データフロー、観測される結果を必要範囲だけ
対応付けます。外部境界が拒否・防御する責務を持つ不正入力も判断対象に含めます。

保証の根拠は実際の parser、constructor、型の強制、制御フロー等に求め、その後の
mutation、別入口、並行変更、I/O が保証を壊し得るかを確認します。型注釈だけや
過去に事故がなかったことを到達不能の証拠にしません。同じ境界で維持される不変条件と、
存在確認後も外部から変化し得る状態を区別します。到達する場合も、既存 owner の
例外伝播、拒否、cleanup、recovery が既に要求を満たしていないかを先に照合します。

| 判断 | 根拠の例 | 次の行動 |
| --- | --- | --- |
| 到達不能 | parser が非空を強制し、同じ内部境界でその保証を壊す経路がない | 内部の空入力を理由に修正を要求しない |
| 既存保証で対応済み | 失敗は起こり得るが、既存 API の例外伝播や cleanup が要求どおり | 追加の catch、guard、fallback を要求しない |
| 未確認 | 入口や保証の成立・維持に関する判断前提が未確認 | 安全とも欠陥とも断定せず、判断を変える不足前提だけを調べる |
| 到達可能で契約不足あり | 現行入口からの実行や仕様上の外部障害で、要求された結果・失敗処理が満たされない | その不足を閉じる最も単純な修正と対象検証を既存 owner で選ぶ |

private helper を mock で直接呼び、実際の入口では作れない状態を注入しただけでは、
到達可能な不具合の証拠になりません。test double は成立する入力・状態・外部障害を
表現します。局所 algorithm が独立した契約を持つ場合の owner-local test は妨げません。
外部入力、存在確認後の変更、仕様上の I/O 失敗などの可能性が契約や解析で示せるなら、
実事故や危険な再現を要求しません。ただし可能性だけで追加対策を決めず、既存保証で
埋まらない要求を対応付けます。必要な authorization、安全検証、外部境界の検証は保ちます。

到達不能・既存保証済みなら、既存の Issue、design、review の記録に理由を短く残して
元作業へ戻ります。その仮説を production 対策、回帰 test、必須後続 Issue、完了条件に
変換しません。未確認も投機的な対策へ変換せず、必要な前提の調査に留めます。
これは判断支援であり、新しい checker、schema、status、帳票、approval gate、全件監査を
要求しません。実装・review の利用側は、この判断と既存の根拠を参照し、分類規則を複製しません。

### SEP-08 DRY and abstraction admission

DRY が対象にする重複は、同じ knowledge、policy、invariant、state owner、mapping、decision rule の
複数正本です。文字列、control flow、数式の形が似ているだけでは統合しません。

共通 abstraction を追加するには、少なくとも次を確認します。

1. 同じ domain meaning と contract を持つ。
2. 同じ actor / change reason で変わる。
3. 同じ invariant と failure semantics を守る。
4. 実在する複数 caller、または stable external boundary がある。
5. 共通化後も caller-specific semantics を flag / optional parameter / runtime branch で再注入しない。
6. 共通 owner と validation route が既存 owner より明確になる。

条件を満たさない場合は、局所的な重複を許容します。異なる数理意味論、停止条件、unit、state owner
を一つの helper や wrapper に押し込むことは DRY ではありません。

新しい tool、skill、workflow、checker、schema、document は、既存 owner では埋められない
responsibility gap がある場合だけ作ります。use-case 名だけの wrapper や、既存 owner の順序を
再掲する orchestration surface は追加しません。

既存の CLI、library、toolchain が所有する処理の周囲に新規または変更する helper、module、script、parser、state、
publisher を提案する場合は、設計・handoff 前に既存の `reuse_survey` を使い、bounded な local help、
local docs、official primary source の readback で provider capability を比較します。provider-owned
phase と正確な未充足 responsibility gap を対応付けます。comparison には provider の正確な input / output
boundary と選択した command / options を含め、phase 名だけでは判断しません。覆われた phase は provider
に委譲します。新規責務名の制限は [命名規約](../rule/naming.md) を参照し、ここでは重複した命名規約を定義しません。

#### Reuse feasibility support

再利用可能性は、同名 API や同じ実装構造の有無ではなく、既存機能を使う具体的な呼出が
今回の要求を満たせるかで判断します。上の共通 abstraction の新設条件を、既存 API の
利用条件へ転用しません。一つの caller でも利用でき、provider が正式に提供する設定・
拡張点は新設 wrapper の flag と区別します。この節を実装・掃除の共通の判断支援とし、
名称・配置・style の好みを能力不足にせず、新しい判定器、全項目 checklist、必須の比較表、
schema、承認段階は作りません。

1. **要求を機能の言葉へ戻す。** caller と設計から、入力の有効領域、必要な変換・結果、
   守る意味を短く取り出します。自作予定の名前だけでなく、その操作の一般名・別名、
   入出力の型、既存の呼出例から候補を探します。現在の helper の形や偶然の制約を
   要求へ昇格させず、state / lifecycle、副作用、失敗、性能は判断に関係するものだけ扱います。
2. **公開機能の使い方を読む。** current API の仕様・local help・公式資料で、実際の
   引数、戻り値、既定値以外の設定、nested configuration、overload、拡張点を確認します。
   一例や既定動作だけを能力の上限にしません。既存の依存宣言・解決版に合う根拠を使い、
   その確認のための新しい pin や環境調査を追加しません。資料だけで決まれば内部監査は不要です。
3. **最小の利用案を組み立てる。** `入力 -> 必要な変換 -> 既存 API（設定） -> 必要な変換 -> 出力`
   を実在 API の呼出例または短い擬似コードにします。直接利用だけでなく、既存 API の
   合成・反復・設定で埋まる差を先に試案へ含めます。試作の実行を一律必須にしません。
   各呼出の前提を満たし、合成後に要求を保つかを見ます。引数・型・単位の違いだけでは
   棄却せず、変換が要求に必要な情報・精度・意味を失わず、禁止された副作用を加えないかを見ます。
4. **保証の向きを比較する。** 要求上有効な入力・状態のすべてを利用案が扱え、その結果が
   必要な保証を含むことを確かめます。完全に同じ API 契約である必要はありません。
   入力領域を狭める前提、出力保証の弱化、失敗の成功化で差を隠しません。合成では
   中間状態、所有権、原子性、cleanup も関係する場合だけ含めます。性能差を理由にするなら
   現在の workload と要求上限、計算量・コピー・I/O 等の具体的な根拠を使い、予感で棄却しません。

比較の核心は「要求の入力領域が利用案の扱える領域に含まれ、利用案の保証から要求の保証が
導ける」です。これにより、表現だけの差による誤棄却と、見た目だけの類似による誤採用を
区別できます。形式証明や provider 全機能の再検証を要求するものではありません。

| 分かったこと | 判断と次の操作 |
| --- | --- |
| 直接の呼出・設定で要求を満たす | そのまま利用する。新しい helper を作らない。 |
| 最小の変換・合成で要求を満たす | 呼出側で接続する。provider の algorithm、parser、state、retry を再実装しない。 |
| 一部を満たすが、具体的な不足が残る | 満たす部分を再利用し、不足だけを責務のある owner で実装する。適合する別候補も必要範囲で比較する。 |
| 変換・設定・合成でも要求を満たせない根拠がある | 満たせない要求と仕様上の差または反例を示して、その利用案を棄却する。候補全体の無価値や全候補の不存在へ一般化しない。 |
| 判断に必要な保証が未確認 | 不適合にも適合にも変換しない。判断を変える一点だけを調べ、未確認を自作の正当化にしない。 |

未確認点は、まず該当する仕様節・既存 caller/test で解き、それでも必要な場合だけ最小の
呼出確認を使います。単一成功例は全入力の保証ではなく、実行不能は能力不存在の証明でも
ありません。十分な候補が決まれば未採用候補の調査を止めます。決められない場合も、
その選択の不明点だけを既存 task context に残し、独立して進められる変更を止めません。

**判断例（実在製品の能力を主張する例ではない）:**

- 同じ意味の時間長で caller は秒、API はミリ秒を取る場合、要求領域で範囲・精度を保つ
  変換ができれば利用可能です。丸めで必要な精度が失われるなら、その変換案は不適合です。
- 独立した要素処理は、順序・資源・失敗の要求も満たすなら単要素 API の反復で利用可能です。
  全件の原子的更新が必要なら、途中更新を公開する単純な反復では足りません。既存の
  transaction / batch 機能を確認し、それでも保証できない範囲だけを不足とします。
- 既存 parser が構文とエラーを扱い、製品固有の値域規則だけが足りないなら、parser を
  再利用し値域規則を caller 側に置きます。製品専用 API がないことは parser の再実装理由ではありません。
- 必要な順序保証が資料の一例に書かれていないだけなら未確認です。関連する保証・設定を
  読まずに「非対応」とせず、保証されないことが分かった場合も同じ出力例だけで適合としません。

採用 API と具体的な利用案、決め手となった要求・保証の対応、根拠の locator、残る不足だけを
既存設計文書の該当節へ簡潔に残し、既存 `reuse_survey` / handoff ではその参照を使います。
上の表を埋める帳票や新しい disposition enum は追加しません。既存候補が不足する場合も、
既知の library と自作の保守・依存コストを比較し、依存ゼロのための自作や再利用のためだけの
新依存を目的にしません。検証は今回の変換・接続・残る domain contract に向け、provider の
実装・test suite の複製や、全 package 探索・環境再構築を完了条件にしません。

## 4. 変更単位と完全性

### SEP-09 Evidence-bounded complete owning unit

変更範囲は symptom file や minimum diff ではなく、root mechanism を所有する replaceable unit と、
そこから evidence-linked に到達する consumer、effect、failure handling、cleanup、contract、docs、tests、
validation で決めます。

実装開始前に、implementation が導かれる complete target state を固定します。この target state は
少なくとも `contract`、`responsibility/state/lifecycle`、`failure/recovery`、
`compatibility/migration`、`cleanup`、`validation` を含みます。implementation sequencing や
waves は、すでに定義された work の順序だけを決める仕組みであり、target state を後から完成させるための
段階実装には使いません。したがって「最初の実装」や `initial implementation`、temporary API、
placeholder route、required behavior の stub / no-op / hard-coded replacement、deferred-later completion
は認めません。明示的に選択した小さい product scope は target state として扱えますが、その scope 内で
同じ complete target state を閉じていなければなりません。

同時に、次は scope に含めません。

- selected owner / mechanism に到達しない repository cleanup
- unrelated style normalization
- historical artifact の整理
- current contract に不要な future extension
- finding 数や file proximity だけで選ばれた隣接 path

これにより「局所 patch では不完全」「repo-wide cleanup では過剰」の両方を避けます。
refactor と behavior change を分けることが rollback と review を改善する場合は分離しますが、
一つの migration を中途半端な互換状態へ残すために分割しません。

### SEP-10 Compatibility and migration closure

public surface、schema、path、identity、runtime route を変更する場合、canonical target、
不要になった旧実装・alias・wrapper・selector・generated projection の削除、必要な consumer migration
を一つの完成条件として [RC-09](../design/responsibility-cleanup.md#duplicate-implementation-retirement) で閉じます。

互換経路を残すには、明示された現行の公開契約を満たす必要性を先に示します。supported period、
owner、read / write direction、removal condition はその必要性に従い、移行の手間や diff の小ささを
温存理由にしません。必要な入口も正本へ接続し、旧実装を第二の source of truth として残しません。

## 5. Verification、再現性、運用

### SEP-11 Testability and validation selection

設計時に stable input boundary、observable output、counterexample、oracle を確保します。pure computation と
external effect を分けること、clock / filesystem / network / process boundary を adapter で閉じることは、
必要な場合に testability を高めます。ただし test double のためだけの production abstraction は追加しません。

validation は変更した property と reachable risk に対応させます。

- contract / invariant は focused unit・property・reconstruction test で確認する。
- integration boundary は実際の caller / provider 組合せで確認する。
- environment 固有の contract は、その環境が観測可能な場合だけ environment validation を選ぶ。
- remote CI は clean replay または remote-only property を観測するために使い、local checker の別名にしない。
- 選ばれなかった full check、diagnostic、report に negative receipt を作らない。

#### SEP-11A Guarantee-first mechanism selection

保証を選ぶ順序は、外部に根ざした要求または観測された witness、そこから
到達できる因果的 mechanism、mechanism が保証しない残余境界、そして一次観測
owner の順です。設計文書、reviewer の主張、Issue 本文、approval、merge 状態、
label、PR 参照、または同じ主張の繰り返しは、単独では authority や guarantee
になりません。

各 owner は次を一つの local correspondence として保持します。

`authority -> mechanism transition -> not-guaranteed boundary -> primary observation -> local receipt`

同じ `(candidate_digest, property_ref, owner_ref, execution_plane,
tool_input_locator)` の receipt は再利用します。mechanism、effect/dependency
closure、入力、source snapshot が変わった場合だけ、その owner の receipt と
既存 DAG の到達可能な下流 evidence を無効化します。無関係な owner の receipt
や、同じ property を見る別名の check は再実行しません。

integration/publication owner は receipt の存在、candidate/property/owner の
互換性、既存 dependency edge の閉包だけを消費し、owner の command を再実行
しません。`verified` は owner が因果対応を観測した状態であって承認ではなく、
`advisory` / `unproven` / `refuted` は要求や blocker を生成しません。

この選択規則は checklist、承認ゲート、registry、counter、時間制限、最低 check
回数を追加するものではありません。選択した mechanism と、その property を
初めて観測する oracle だけを実装し、別境界を観測しない同型の検証は作りません。

### SEP-12 Determinism, idempotency, and reproducibility

決定性が contract の surface は、同じ canonical input、version、configuration から同じ ordering、identity、
bytes、selection を生成します。randomness、time、environment discovery が必要なら seed、clock、input snapshot、
selection rule の owner を明示します。

idempotent operation は、expected state への再適用で余分な mutation を起こしません。ただし external drift や
unexpected ownership を黙って no-op にせず、`absent / expected / unexpected` のように分類し、unexpected state を
拒否または明示的 reconcile route へ渡します。

reproducibility は固定 filename inventory ではなく、結果を再構成・比較するために必要な provenance を owner が
定義することです。source、config、command、environment、input、output artifact identity のうち必要なものを保存し、
producer が生成しない optional artifact の欠落説明を一律要求しません。

### SEP-13 Failure classification and recovery

少なくとも次を区別します。

- implementation defect / violated invariant
- invalid input / unmet precondition
- expected domain or numerical breakdown
- environment / capability unavailable
- external service / permission / rate / billing failure
- verification unavailable / inconclusive
- conflict / stale snapshot / concurrent mutation

異なる class を同じ `failed`、同じ fallback、同じ retry に流しません。error は first real failure、owner、
actionable context、safe state、retry / repair / escalation route を保持します。failure を warning、skip、success に
変換する場合は、contract がその縮退を明示的に許す必要があります。

cleanup と rollback は mutation の後付けではなく effect owner の一部です。partial success、temporary resource、
lock、branch、worktree、container、generated file の残存状態を、次の action が判断できる形で返します。

### SEP-14 Observability and traceability

observability は、障害時に「何が、どの input class / state で、どの owner のどの transition で失敗したか」を
追えることです。log 行数、dashboard、report の存在自体を quality とみなしません。秘密値や巨大 payload を出さず、
state identity、source snapshot、operation、first failure、effect / cleanup result を必要範囲で記録します。

repository change は、次の trace を保持します。

```text
request / requirement
  -> Issue or owning task state
  -> canonical contract / design clause
  -> branch / PR / diff
  -> focused and integration validation
  -> accepted source identity
  -> projection / consumer pin when applicable
```

chat、review comment、一時 report は補助 evidence であり、長期 contract の代替ではありません。Issue-backed task が
未完了で止まる場合は、branch / PR / head、完了責務、残作業、blocker、次 action を Issue から辿れるようにします。

## Evidence model

設計、実装、review は全原則を列挙せず、判断に影響した原則だけを次の evidence へ接続します。

| Decision stage | Required evidence when material |
| --- | --- |
| Design | contract / invariant、owner、dependency direction、rejected alternative、validation / recovery route |
| Implementation | owning unit、public / private boundary、state / effect owner、consumer migration、selected validation |
| Refactor | preserved behavior、allowed structural delta、forbidden semantic delta、abstraction admission、rollback |
| Review | reachable failure / maintenance impact、contract clause、owner / dependency evidence、resolution |
| Closeout | diff identity、validation result、unverified external property、Issue / PR trace |

原則名だけを finding にしてはなりません。「SRP 違反」「DRY 違反」「複雑」のようなラベルは、具体的な duplicated owner、
conflicting invariant、reachable failure、caller coupling、testability loss が示されない限り blocking finding ではありません。

## Consumer integration

### Design and delivery

cross-surface design は、先に contract / invariant、canonical owner、responsibility boundary、effect / recovery、validation を
固定し、その後で file と implementation slice に落とします。新しい surface は responsibility gap と concrete consumer を
示します。umbrella workflow はこの policy を再掲せず、選択した clause と task-specific evidence を handoff します。

### Refactor

refactor は behavior preservation と allowed structural delta を先に固定します。DRY や KISS を理由に、異なる意味を統合したり、
root mechanism、consumer migration、cleanup を未完にしたりしません。新しい abstraction は SEP-08 の admission evidence を持ちます。

### Review

review finding は、具体的な contract / invariant / owner / dependency / failure risk と、関係する clause を結びます。全 PR に
原則 checklist、SOLID report、negative receipt を要求しません。OOP-sensitive change の専門判断は
[object-oriented-design.md](object-oriented-design.md) と canonical OOP reviewer に委譲します。

## Conflict examples

- **DRY vs mathematical meaning**: control flow が似ていても、unit、停止条件、residual definition、breakdown semantics が異なるなら統合しません。
- **KISS vs error handling**: error / cleanup path を削るのではなく、owner と state transition を一つにして route を減らします。
- **YAGNI vs migration**: future extension は作りませんが、要求済み consumer migration と旧 route removal は現在の完成条件です。
- **Locality vs root cause**: caller の一行 patch で shared owner の invariant を迂回せず、owner と到達 consumer を evidence-bounded に閉じます。
- **Extensibility vs abstraction cost**: concrete caller が一つで差し替え根拠がなければ、interface / registry / factory を追加しません。
- **Style vs compatibility**: naming / layout consistency のために public contract を壊しません。変更するなら migration contract を先に持ちます。
- **Determinism vs environment truth**: unstable discovery を固定値で隠さず、snapshot / input として明示するか、環境 failure として分類します。

## Clause map

| Clause | Owner decision |
| --- | --- |
| SEP-01 | contract、correctness、failure semantics |
| SEP-02 | invariant、state、lifecycle owner |
| SEP-03 | separation of concerns、single responsibility |
| SEP-04 | cohesion、coupling、information hiding |
| SEP-05 | dependency direction、authority boundary |
| SEP-06 | 要求規模で成立する方式選定と変更後の保守コードスペースの最小化 |
| SEP-07 | YAGNI と speculative mechanism |
| SEP-08 | DRY と abstraction admission |
| SEP-09 | complete target state、evidence-bounded complete owning unit、sequencing-only waves |
| SEP-10 | compatibility と migration closure |
| SEP-11 | testability と validation selection |
| SEP-12 | determinism、idempotency、reproducibility |
| SEP-13 | failure classification、cleanup、recovery |
| SEP-14 | observability と requirement-to-source traceability |

## Non-goals

- 原則ごとの public skill、checker、workflow、schema、score、receipt を作りません。
- 全変更へ OOP / SOLID review を起動しません。
- file、class、function の数値 threshold だけで責務を分割しません。
- minimum diff または full-repository cleanup を既定の repair objective にしません。
- external engineering framework の ceremony を AgentCanon の mandatory process として複製しません。
- この文書は task-specific design、domain semantics、language convention、validation evidence を置き換えません。