<!--
@dependency-start
contract policy
responsibility Defines language- and paradigm-neutral software engineering principles and decision precedence for AgentCanon design, implementation, refactor, review, and validation.
upstream design ./README.md convention index and reader route
upstream design ../../PHILOSOPHY.md top-level responsibility and source-of-truth philosophy
upstream design ../design/semantic-responsibility-contract.md semantic action and verification-owner allocation
upstream design ../design/responsibility-rationale.md mechanism rationale and activation boundary
upstream design ../operations/notes-lifecycle.md failed verification topic recording and reuse
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
現在の要求と evidence から、実行する変更、到達状態、検証で確定した結論を導きます。
変更で実際に到達する contract、invariant、owner、failure mode に関係する原則を選び、
設計判断、実装、review finding、validation route に接続します。

## Reader Map

- 最初に「所有境界」と「判断の優先順位」を読みます。
- 新しい module、API、wrapper、tool、skill、checker、schema、document を追加する前は、
  「責務と依存境界」と「単純さと抽象化の admission」を読みます。
- 規模に応じた処理・資源コストを決める実装方式を選ぶ前は、
  [規模を先に置く方式選定](#workload-and-scale-before-mechanism) を読みます。
- 採用・却下の判断では [Reuse feasibility support](#reuse-feasibility-support)、
  refactor では「変更単位と完全性」、review では「Evidence model」を読みます。
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

1. 最新の明示的なユーザー合意と user / domain contract、safety、correctness
2. semantic invariant、state / lifecycle owner、要求上必要な public compatibility
3. root-cause closure、reachable failure handling、cleanup / recovery
4. responsibility / dependency boundary、information hiding、authority boundary
5. testability、reproducibility、operational observability
6. simplicity、change locality、reuse、abstraction cost
7. stylistic consistency

上位 contract を完全に閉じる owning unit を選び、完成後の保守対象が最小になる実装を
選びます。最初に要求された到達状態、有効入力、保証、完了証拠を肯定形で定め、
根本原因と影響する契約から変更単位を導きます。制約は user、契約、安全性、権限の
根拠とともに該当操作へ一度記載します。採用・却下・範囲の判断は調査と検証で確定し、
その結論を同じ設計・handoff・実装・review に引き継ぎます。

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

直前のチャットを含む最新の明示的なユーザー要求と、実装のために選んだ契約を区別します。
目的、有効入力、必要な結果・安全性・性能・失敗条件と明示的互換要求は守る条件です。
一方、既存の API、データ表現、状態遷移、責務分割、内部の前提・不変条件は設計変数です。
旧契約を固定してからコードだけを短くせず、要求を満たす契約と実装の組を比較し、
数理的に単純になる契約変更も通常の候補に含めます。既存コード・テスト・文書は
意味と移行影響の証拠であり、そこに記載済みというだけで変更拒否の根拠にはしません。

設計には、残す要求、変更する契約条項、新しい表現・規則から要求が導ける理由、
影響する利用側と移行を簡潔に示します。表現変更なら意味の対応を、挙動変更なら保存する
性質と認可された差を示し、意図して直す旧挙動との完全同値を要求しません。
必要な契約変更・利用側移行は認可された修正に含め、契約変更というだけで別承認待ちに
しません。ただし明示された保証・互換制約の撤回、目的変更、権限外の変更は別です。
具体的な衝突と必要な判断を示し、未承認の提案を合意扱いせず独立した作業を続けます。

実装を成立させるための入力領域縮小、前提強化、保証弱化、失敗の成功化を、契約整理と
呼び替えません。内部の前提を変えるなら、要求上有効な入力がそこへ到達するまでに
その前提を満たすことも導きます。入力・出力、停止・失敗、副作用、cleanup のうち
変更に関係するものを扱い、[SEP-11](#sep-11-testability-and-validation-selection) で
要求から検証義務を導出します。caller、移行、旧実装の削除、設計・tests の更新までを
同じ完成形として閉じ、無関係な全体改修には広げません。

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

KISS は、合意した完成形を満たす候補の中で、変更後に保守するコードスペースを最小にします。
出発点は対象責務のタスクで分けます。「常に再利用」「常に削除」の一律順序にはしません。

| 対象 | 出発点と判断 |
| --- | --- |
| 新規機能・新規実装 | 既存の抽象化・API・標準機能・採用済み依存の直接利用、設定、組合せから始める。具体的な不足だけを実装し、不要な基盤の自作や既存機能の再実装をしない。 |
| 既存機能の修正・変更・整理 | 合意した結果から、対象の既存構造を残す必要も見直す。不要・原因となる構造の削除・置換を継ぎ足しより先に検討し、正しい部品は再利用する。根本原因と影響する契約から変更単位を決める。 |

混在する作業は責務別に選び、file・helper の新旧やIssue全体の名称で一括分類しません。
必要な挙動・有効入力・安全性・明示的互換契約の保存と、現在の実装構造の保存は別です。
挙動保存のrefactorは合意した意味を維持し、修正でも無条件削除・全書換え・範囲外の掃除をしません。
新規での組合せは不要な重複を避け、修正での維持見直しは欠陥や不要な構造を支える層の増殖を避けます。
「最短の code」や「最小の diff」ではなく、完成形に残る次の実体と相互依存を比較します。
追加分だけでなく、既存実装とその維持に必要な接続も含めます。

- 実装本体、補助コード、canonical owner と source of truth
- public surface と execution route
- mutable state と lifecycle
- branch、mode、selector、special case
- dependency、invariant、schema、compatibility relation
- independent checker、workflow、receipt、generated view

数理的な単純さは、独立に保持する情報、可能な状態・分岐、別々に維持する不変条件、
構成要素間の結合と証明義務で比較します。例えば他の値から導ける重複状態をなくす、
不正な組合せを表現できない型へ変える、共通の法則から特殊分岐を導いて一本化する案を
[SEP-01](#sep-01-contract-first) の契約変更も含めて検討します。法則の成立条件を示し、
浮動小数点・副作用・順序依存へ実数の恒等式や可換性を無条件に持ち込みません。

局所の行数ではなく、利用側の変換・移行・残存互換層を含む完成形で比較し、根拠のある
削除・統合を同じ変更で実行します。別のcleanup依頼を待ちません。必要な独立性まで
一つの汎用機構へ押し込んだり、複雑さをcallerへ移したりしません。数値scoreや削除ノルマ、
行の圧縮、別fileへの移動、必要な保証の削減を成果にせず、置換時の削除と利用側移行は
[RC-09](../design/responsibility-cleanup.md#duplicate-implementation-retirement) で閉じます。

要求上必要な error handling、cleanup、migration、test、documentation を削って短くした実装は
単純ではなく、未閉鎖の責務を別の場所へ移しただけです。どの異常処理が必要かは
[到達可能性と追加修正の必要性](#reachability-and-remedy-necessity) で判断し、
重複防御を温存する理由にはしません。

#### Workload and scale before mechanism

新規実装や変更で algorithm、data structure、処理単位、状態・資源管理を選ぶ場合は、
今回の contract が要求する規模で成立する候補を調べ、最も単純な方式を選びます。
比較するのは、繰返し利用と入力増加を含む全体コストです。単純な rename 等、
これらの判断を変えない編集は既存設計を再利用します。

1. **増えるものと要求範囲を先に特定する。** 既存の仕様・設計・caller から、判断に関係する
   入力件数・要素サイズ、反復呼出、同時実行、保持期間等を選びます。既知の通常規模、
   要求上の範囲、時間・メモリ等の制約とその根拠を区別します。未指定の将来負荷は
   仮定と区別し、方式選択を左右する前提を調査します。上限を置かない要求には、
   許される成長に対する計算量・資源の根拠を示します。
2. **既存機能を使う基準案の全体コストを見積もる。** 直接利用・合成から始め、必要な時間、
   ピークメモリ、I/O・外部呼出数を規模の関数として捉えます。前処理、反復される全走査、
   コピー・中間データ、保持状態、同時実行による増幅も関係するものだけ含めます。
   例えば n 件を q 回全走査する案は、一呼出の線形性だけでなく全体の n と q の積を見ます。
   最悪時・平均時・償却の根拠と成立前提を区別し、合成後の全体コストを確認します。
3. **要求範囲で成立する最小の方式を選ぶ。** 現実に競合する候補を、支配的なコスト、
   前処理・保持・更新の負担、既存保証と照合します。棄却する場合は、破綻する要求条件と
   解析または測定結果を示します。有効入力・保証を維持する候補から選び、残る具体的な
   不足に対応する cache、並列化、分散化、新 API 等だけを検討します。

採用方式、規模の前提、支配的コストと根拠、単純な代案を退けた検証結果を、実装前に既存設計の
該当節へ簡潔に残します。十分な既存説明は参照を再利用し、task / worker handoff は同じ節に
接続します。worker が algorithm、保持方法、反復・並行構成や前提を変える場合は、
先に同じ判断を更新して引き継ぎます。review も同じ前提と実 diff の全体コストを照合します。

解析や既存 API の保証を実コードへ対応付け、定数因子や実行系の特性が選択を左右するときは
正規経路で測定します。判断に必要な規模の検証まで実行して結論を確定します。実行上の
失敗は条件と実際の結果を topic に記録し、次の認可された検証・修正操作へ接続します。
アクセス等の具体的な阻害要因はその owner に示し、独立した作業は進めます。
選択する調査・検証は、現在の要求と変更契約を満たす範囲に対応させます。

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

異常仮説から修正を導くときは、現在の有効な入口、contract が許す入力・状態、
制御・データフロー、観測される結果を対応付けます。外部境界が拒否・防御する責務を
持つ不正入力も判断対象に含めます。

保証の根拠は実際の parser、constructor、型の強制、制御フロー等に求め、その後の
mutation、別入口、並行変更、I/O による影響を確認します。同じ境界で維持される
不変条件と、外部から変化する状態を区別します。既存 owner の例外伝播、拒否、cleanup、
recovery と要求を照合し、調査と検証によって次の結論を確定します。

| 確定した判断 | 検証根拠の例 | 次の行動 |
| --- | --- | --- |
| 到達不能 | parser の非空保証と、その保証を維持する全ての関連経路を確認した | 保証と根拠を参照して既存実装を使う |
| 既存保証で対応済み | 到達する失敗に対し、既存 API の例外伝播・cleanup が要求を満たすことを確認した | 既存 owner に委譲する |
| 到達可能で契約不足あり | 現行入口・仕様上の障害から要求違反までを trace または検証で確認した | 不足を閉じる最も単純な修正と対象検証を既存 owner で実行する |

必要な前提がまだ判明していれば、その前提の調査・検証を実行して判断を確定します。
検証は実際に成立する入力・状態・外部障害を扱います。独立した契約を持つ局所 algorithm は
owner-local test を使います。外部障害の可能性は仕様や解析から立証でき、安全を守る
方法で検証します。必要な authorization、安全検証、外部境界の検証は保ちます。

検証結果と判断を既存の Issue、design、review へ接続し、失敗した検証は
[Notes Lifecycle](../operations/notes-lifecycle.md#failed-verification-record) の topic に保存します。
実装・review の利用側は同じ判断と根拠を参照します。

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

独立した実装や局所分岐を選ぶ場合は、異なる数理意味論、停止条件、unit、state owner 等を
調査・検証で特定し、その違いが要求上必要なことを示します。共通の責務は同じ owner で直し、
影響する利用側を移行します。

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

再利用可能性は、既存機能を使う具体的な呼出が合意した完成形を満たすかで判断します。
[SEP-01](#sep-01-contract-first) と [SEP-06](#sep-06-kiss) に従い、新規では組合せを
基準案にし、修正では対象構造の維持も見直します。provider の正式な設定・拡張点も利用案に
含め、一つの caller からでも実際の能力と要求の対応を検証します。

1. **要求と既存知見を読む。** 合意と設計から、有効入力、必要な結果、守る保証を取り出します。
   操作の一般名・別名、型、既存の呼出例から候補を探し、[topic 検索](../operations/notes-lifecycle.md#retrieve-before-deciding)
   で過去の失敗条件・検証結果も確認します。記録と現在の前提を照合し、同じ条件の結果を再利用します。
2. **公開機能を具体的に調べる。** 解決済みの依存版に対応する仕様・local help・公式資料で、
   引数、戻り値、設定、nested configuration、overload、拡張点を読みます。判断に必要な保証は
   仕様節、実際の caller、実装の制御・データフローへ対応付けます。
3. **利用案を検証する。** `入力 -> 必要な変換 -> 既存 API（設定） -> 必要な変換 -> 出力`
   を具体化し、合成・反復・設定で埋まる差も含めます。各呼出の前提と合成後の保証を演繹し、
   実コードへ対応付けます。判断に必要な観測は正規経路の focused test、呼出確認、測定で
   取得します。情報・精度・意味・副作用・失敗処理・性能のうち判断を左右する性質を確かめます。
4. **検証結果から結論を確定する。** 要求上の入力領域が利用案の領域に含まれ、利用案の保証から
   要求の保証が導けるかを判定します。却下する場合は、確認した設定・合成を含む候補、破る要求、
   検証条件、手順、実際の結果または仕様・実装上の反例を示し、その候補の不適合を断定します。
   判断に不足する前提や観測は同じtaskで調査・検証して解消します。

| 検証で確定したこと | 判断と次の操作 |
| --- | --- |
| 直接の呼出・設定で合意した完成形を満たす | 必要な部品をそのまま利用する |
| 最小の変換・合成が完成形でも最も単純 | その接続を実装し、provider の既存処理に委譲する |
| 既存機能が満たす部分と、具体的な不足を確定した | 必要な部品を再利用し、不足を責務のある owner で実装する。修正対象は必要なら置換する |
| 関連する変換・設定・合成を検証し、要求違反を確定した | その利用案を却下し、要求を満たす候補を選ぶ |

「保証しないとは限らない」「使えない可能性がある」等は判断途中の仮説です。
採用・却下の理由には、`条件 → 調査・検証 → 実際の結果 → 結論` を書きます。
一つの成功例による観測、仕様と実コードに基づく一般的保証、反例による棄却はそれぞれの
検証範囲で述べます。十分な候補が確定したら、その選択に影響しない候補の探索を終えます。
実行が失敗した場合も、操作と失敗した性質を確定して記録し、判断を完了するための次の
認可された検証へ進みます。具体的なアクセス・権限上の阻害要因はownerへ接続します。

**判断例（条件を指定した説明例）:**

- 秒からミリ秒への変換を使う案では、要求領域で値域・丸め誤差を調べます。要求精度を
  満たす範囲の根拠が得られれば採用し、要求精度を破る入力を確認した変換案は却下します。
- 単要素APIの反復を使う案では、順序・資源・失敗条件を検証します。全件の原子性が必要な
  場合は既存transaction / batch設定まで確認し、途中状態が公開されるtraceを示して
  原子性を破る案を却下します。
- 既存parserが構文とerrorを扱い、製品の値域規則だけが不足すると確認した場合は、parserを
  再利用し値域規則をcallerに置き、入力から結果・失敗までを検証します。

採用API、具体的利用案、決め手となった要求と保証の対応、検証結果、根拠locatorを
既存設計へ残し、`reuse_survey` / handoff は同じ参照を使います。失敗した検証は
[topic record](../operations/notes-lifecycle.md#failed-verification-record)へ直後に保存して
読み戻します。後の成功や反証も同じtopicに接続します。今回の変換・接続・残るdomain contractを
検証対象とし、providerの実装やtest suiteは既存ownerに委譲します。

## 4. 変更単位と完全性

### SEP-09 Evidence-bounded complete owning unit

要求された到達状態を満たす root mechanism の replaceable unit と、そこから
契約上の影響が確認できる consumer、effect、failure handling、cleanup、docs、tests、
validation を変更単位にします。共通の原因を所有する箇所から直し、必要な利用側へ追跡します。

実装開始前に、implementation が導かれる complete target state を固定します。この target state は
少なくとも `contract`、`responsibility/state/lifecycle`、`failure/recovery`、
`compatibility/migration`、`cleanup`、`validation` を含みます。implementation sequencing や
waves は、すでに定義された work の順序だけを決める仕組みであり、target state を後から完成させるための
段階実装には使いません。したがって「最初の実装」や `initial implementation`、temporary API、
placeholder route、required behavior の stub / no-op / hard-coded replacement、deferred-later completion
は認めません。明示的に選択した小さい product scope は target state として扱えますが、その scope 内で
同じ complete target state を閉じていなければなりません。

範囲は到達状態と確認した依存・契約から導き、userや安全性・権限が定める制約を根拠付きで
適用します。変更契約の影響が閉じたところを境界にします。局所分岐・別実装を残す場合は、
要求上の挙動や入力契約の違いを検証し、その必要性を示します。共通修正と旧分岐の削除、
必要なconsumer migrationを同じ完成条件で閉じます。reviewやrollbackのための分割も、
この完成形と必要な移行を維持する順序で行います。

### SEP-10 Compatibility and migration closure

public surface、schema、path、identity、runtime route を変更する場合、canonical target、
不要になった旧実装・alias・wrapper・selector・generated projection の削除、必要な consumer migration
を一つの完成条件として [RC-09](../design/responsibility-cleanup.md#duplicate-implementation-retirement) で閉じます。

互換経路を残すには、明示された現行の公開契約を満たす必要性を先に示します。supported period、
owner、read / write direction、removal condition はその必要性に従い、移行の手間や diff の小ささを
温存理由にしません。必要な入口も正本へ接続し、旧実装を第二の source of truth として残しません。

## 5. Verification、再現性、運用

### SEP-11 Testability and validation selection

検証は演繹を基礎とし、実装前に要求・前提から検証義務を導きます。既存設計の該当節へ
`要求 → 前提・定義 → 不変条件と導出 → 実装箇所 → 残る実行確認` を接続し、
テスト通過や観測例の積み上げを全入力・全状態の正しさの根拠にしません。

1. **主張と前提を分離する。** 有効領域、事前・事後条件、必要な不変条件と、利用する
   既存保証を明示します。前提の出典・成立・整合性を確かめ、結論を仮定に置く循環、
   矛盾した仮定や空の有効領域による空虚な成立を避けます。外部保証は何を信頼するかを
   明示し、型注釈や未実施のcheckを保証とみなしません。
2. **実装構造に沿って導く。** 初期状態での不変条件成立、各到達可能な分岐・遷移での保存、
   終了時の要求充足を示します。合成では前段の保証が後段の前提を満たすこと、loop・再帰では
   必要な停止性を整礎な減少量等で示します。停止を要求しないserviceには必要な安全性・進行性を
   選びます。式や状態表現を変えた場合は、要求領域での意味の対応を示します。必要な失敗処理、
   cleanup、原子性も同じ推論に含め、正常経路の証明で代用しません。
3. **モデルと実コードを結ぶ。** 定義・演算・遷移を実際のpath/symbolへ対応付けます。
   整数の範囲、浮動小数点の丸め・誤差、メモリ、I/O、並行変更等は関係する差だけを扱います。
   判断に必要な前提・モデルとの差・検証義務を切り出し、調査、導出、focusedな実行確認で
   解消してから結論を確定します。有効入力、許容誤差、oracleは要求から定めた条件を維持します。

契約変更では、要求上の入力が新契約で扱えること、新契約と実装の保証から必要な結果が
導けること、影響callerの前提が移行後も満たされることを確認します。旧テストの期待値は
この対応から更新し、現在の実装出力をそのまま正解にしません。一般的な主張に必要な
演繹が未完ならその主張は未証明であり、必要な論証と前提の確認を同じtaskで進めます。

テストは導出した性質から境界・反例・回帰・実際のcaller/provider接続を選び、論証の
誤りやモデルと実行のずれを検出する補完にします。実機の性能、外部サービス、実行環境等の
経験的な主張には対応する観測が必要です。演繹を理由に、選択済みの実行検証を省略したり
実測済みと報告したりしません。既存の規定経路と保証を再利用し、未選択の全suiteや
環境再構築、新checker・帳票・証明ツール導入を一律の条件にしません。

レビューでは前提から結論への各対応と未証明部分を確認します。演繹的論証、機械検証済みの
証明、実行試験、未確認を区別します。形式証明が必要な場合は既存の
[formal-proof-workflow](../../agents/skills/formal-proof-workflow.md) を使い、そのcheckerと
実コードへの対応が確認できた範囲だけを機械検証済みとします。自然言語の論証や
solverのtimeoutを、証明成功・反例・証明不能のいずれにも自動変換しません。

方法の一次資料は [Frama-C WP](https://www.frama-c.com/fc-plugins/wp.html) と
[Dafnyの前提・証明依存の説明](https://dafny.org/v4.5.0/DafnyRef/DafnyRef) を参照します。
これらは演繹と前提の扱いの根拠であり、当該ツールの採用要求ではありません。

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

失敗した検証は [Notes Lifecycle](../operations/notes-lifecycle.md#failed-verification-record) へ接続し、
目的、候補、再現条件、手順、期待と実際、確定結論、再利用・再検証条件をtopic単位で保存します。
次の採用・却下前にそのtopicを検索し、前提が一致する結果を再利用します。今回の観測、後続の
成功・反証、設計、Issue/PRから同じ記録へ辿れる状態にします。

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

設計、実装、review は、判断に影響した原則を次の evidence へ接続します。

| Decision stage | Required evidence when material |
| --- | --- |
| Design | 要求と変更可能な契約、数理的単純化の比較、前提・不変条件・検証義務、owner、migration / recovery |
| Implementation | owning unit、public / private boundary、state / effect owner、consumer migration、selected validation |
| Refactor | preserved behavior、allowed structural delta、forbidden semantic delta、abstraction admission、rollback |
| Review | 前提から結論への導出と実装対応、検証で確定した採用・却下理由、reachable failure / maintenance impact、resolution |
| Closeout | diff identity、論証・機械証明・実測の区別、実行結果と確定結論、失敗topicの保存・readback、Issue / PR trace |

finding は、具体的な duplicated owner、conflicting invariant、reachable failure、caller coupling、
testability loss と検証結果を示します。判断に必要な不足は調査・検証して解消し、実際の
アクセス・権限上の阻害要因は試行した操作と結果、そのownerに必要なactionを正確に示します。

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

- **Agreement vs existing structure**: 一つの直接経路への置換に合意したなら、旧 dispatcher を残すための adapter・mode は足しません。必要な parser は再利用し、不要な dispatcher と専用補助コードを削除します。
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
| SEP-01 | 要求と変更可能な契約の分離、correctness、failure semantics |
| SEP-02 | invariant、state、lifecycle owner |
| SEP-03 | separation of concerns、single responsibility |
| SEP-04 | cohesion、coupling、information hiding |
| SEP-05 | dependency direction、authority boundary |
| SEP-06 | 要求規模で成立する方式、契約変更を含む数理的単純化と保守コードスペースの最小化 |
| SEP-07 | YAGNI と speculative mechanism |
| SEP-08 | DRY、abstraction admission、調査・検証からの採用・却下確定 |
| SEP-09 | complete target state、evidence-bounded complete owning unit、sequencing-only waves |
| SEP-10 | compatibility と migration closure |
| SEP-11 | 演繹的な検証義務・実装対応と補完的な実行検証 |
| SEP-12 | determinism、idempotency、reproducibility |
| SEP-13 | failure classification、cleanup、recovery |
| SEP-14 | observability、失敗検証のtopic再利用、requirement-to-source traceability |

## 適用と責務

この文書の原則は、既存のtask-specific design、domain、language、validation ownerを通じて
適用します。専門reviewは変更した契約に応じて選び、責務分割は意味と依存から判断します。
変更単位は要求された完成形と根本原因の影響先で決め、採用する手順・検証はその判断に
必要な既存経路へ接続します。
