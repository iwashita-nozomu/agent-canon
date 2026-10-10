# UNIX / Linux の設計思想と実装判断

<!--
@dependency-start
contract reference
responsibility Records primary-source research, applicability limits, and rationale for UNIX/Linux-informed implementation decisions without owning coding policy.
downstream design ../../../agents/canonical/ROOT_IMPLEMENTATION.md source-side implementation decisions informed by this research
@dependency-end
-->

## 対象と読み方

調査日: 2026-10-03。対象はコードの設計・修正・レビューに使える判断であり、
Linux distribution の比較、ライセンス判断、全kernel subsystemの設計監査ではない。
古典UNIXの設計者の記述、Linux kernelの公式開発規則、実際のI/O仕様を分けて読む。
それらを一つの不変な「Linux公式哲学」として扱わない。

以下の「資料の主張」は原著の要約、「適用判断」はAgentCanonへの設計上の翻訳である。
一般原則の正本は [ソフトウェア工学原則](../../conventions/software-engineering-principles.md)、
実装時の具体的判断は [Implementation decisions](../../../agents/canonical/ROOT_IMPLEMENTATION.md#machine-facing-and-streaming-contracts)。
このnoteは任意の出典・反例資料であり、独立した実装義務やvalidation gateを追加しない。
必要な時だけ読み、常時読込や全項目checklistにしない。

## 一次資料と確認範囲

| ID | 資料・確認した節 | この調査で使う根拠 |
| --- | --- | --- |
| S1 | McIlroy, Pinson, Tague, [UNIX Time-Sharing System: Foreword](https://onlinelibrary.wiley.com/doi/10.1002/j.1538-7305.1978.tb02135.x) (1978)、Style。本文は[HTML transcription](https://danluu.com/mcilroy-unix/)で確認 | 小さな責務、次のprogramへの出力、非対話的な合成、道具による反復労力の削減 |
| S2 | Ritchie, [The Evolution of the Unix Time-sharing System](https://www.nokia.com/bell-labs/about/dennis-m-ritchie/hist.pdf)、Pipes (PDF印刷頁9–10) | 単独利用とpipelineで同じcommandを使うこと、記法と実装の改善 |
| S3 | Pike, [Notes on Programming in C](https://www.lysator.liu.se/c/pikestyle.html) (1989)、Introduction / Comments / Complexity / Programming with data。原著のHTML転載 | 読みやすさ、データ表現、測定と複雑化の費用、規則の機械的適用への警告 |
| S4 | Linux, [Coding style](https://docs.kernel.org/process/coding-style.html)、Functions / Centralized exiting / Commenting / Data structures / Function return values | 凝集した関数、理由と構造が分かる記述、解放と失敗経路、戻り値の意味 |
| S5 | Linux, [Getting the code right](https://docs.kernel.org/process/4.Coding.html)、Pitfalls / Code checking tools / Documentation | 過剰抽象化・未使用の将来機能・過剰inlineを避け、実際の欠陥と根拠に向ける |
| S6 | Linux, [The Linux Kernel Driver Interface](https://docs.kernel.org/process/stable-api-nonsense.html)、内部interfaceとStable APIの議論 | 利用者側境界とkernel内部APIの区別、内部変更時に同時に利用側を直すこと |
| S7 | Linux, [Adding a New System Call](https://docs.kernel.org/process/adding-syscalls.html)、System Call Alternatives / Designing the API | 新規公開APIより既存機構を先に検討し、既存のdescriptorや通知機構との合成を考える |
| S8 | Linux, [Handling regressions](https://docs.kernel.org/process/handling-regressions.html)、重要事項と引用集 | 形式上のABIより実際の利用を守る強い互換性方針。2026年1–2月の説明も確認 |
| S9 | Linux, [Submitting patches](https://docs.kernel.org/process/submitting-patches.html)、Describe your changes / Separate your changes | 原因・利用者への影響・理由の説明、一つの論理変更、性能主張の根拠 |
| S10 | Linux man-pages, [pipe(7)](https://man7.org/linux/man-pages/man7/pipe.7.html)、I/O on pipes and FIFOs / Pipe capacity | byte stream、EOF、SIGPIPE/EPIPE、descriptor lifetime、有限容量 |

公式Web文書は更新される。上のdateと節は確認対象を示し、kernel versionの固定や
新しい依存pinを要求するものではない。転載S1/S3は原著本文として読み、転載者や
検索結果の解説をLinux公式規則の根拠にはしていない。

## 調査結果と適用限界

### 1. 小ささの目的は、責務を理解して組み合わせられること

S1は一つの仕事をよく行うprogramと、他のprogramが入力にできる出力を結び付ける。
S2が強調するのはpipeline専用moduleではなく、普段使う同じcommandの再利用である。
小さいことだけでなく、境界を越えて同じ機能を組み合わせられることが重要になる。

**適用判断:** 新規実装は既存API・設定・合成を基準案とし、pipeline用・caller用という
名前違いの第二実装を作らない。責務と不変条件が同じならfileやprocessを増やさない。
分割によるIPC、serialization、状態同期の費用も比較対象であり、microservice化や
「一関数一file」はこの原則から導けない。既存SEP-03/06/08で判断できる部分を再所有しない。

### 2. 方針と機構を分けるが、将来のための階層を増やさない

S7はsyscall追加の前に既存のinterfaceで実現できるかを検討させ、descriptorを使う
設計では既存のI/O・通知機構との接続を考える。S5は不要な抽象層や未使用機能が
実装を難しくすることを指摘する。

**適用判断:** 誰に何を実行するか、環境・表示・利用順序はcallerの方針とし、再利用する
計算・変換の機構へ混ぜない。これは既存SEP-05とCaller and library responsibilityの
具体化であり、すべての関数へinterface/factoryを付ける指示ではない。Linux kernel向けの
OS抽象層への批判も、全製品の必要な移植境界を禁止する一般則にしない。

### 3. 制御分岐を増やす前に、データの形を見直す

S3はデータ構造と表現を先に考え、同種の規則をデータとして表せる場合を論じる。
同時に、筆者の好みを理由だけで採用せず、表したいものに合うかを考えるよう促している。
S4もデータ構造とその関係の重要性を述べる。

**適用判断:** 型、単位、状態、所有権を直接表し、同じ意味の例外分岐が不要になる形を
探す。標準collectionや小さなtableで足りれば新しいDSLやregistryは不要。
意味の違う分岐まで同じtableへ押し込んで見えなくすることも単純化ではない。
S3の短い変数名やheaderの扱いなどC固有・時代固有の助言は一括採用しない。

### 4. 出力は表示だけでなく、他のprogramとの契約

S1は次のprogramで利用しにくい装飾や対話前提を避ける。S7の既存interface検討は、
操作・型・通知の意味まで扱い、「何でも平文fileに変換すればよい」という主張ではない。

**適用判断:** 機械向けCLIではstdoutに結果、stderrに診断を分けることを基準に、既存
protocolが別のchannel契約を持つ場合はその契約に従う。入力、encoding、record境界、
escaping、順序、終了状態、部分結果の有効性を必要範囲で定める。標準parser/serializerを
使い、人間向けtableを再parseする第二実装やshell文字列への未信頼入力の埋込みを避ける。
数値の精度・型・throughputを損なうtext化や、libraryをCLIへ迂回させることは採用しない。

### 5. pipeの見た目が単純でも、容量・終了・所有権は消えない

S10ではpipeはmessage境界を持たないbyte streamである。writerがすべて閉じるとEOF、
readerがすべて閉じた状態のwriteではSIGPIPE、無視された場合はEPIPEとなる。
容量は有限で、設定や環境に依存するため特定サイズを前提にすべきでない。

**適用判断:** framing、partial I/O、backpressure、EOFとcancelを実際の接続契約に含める。
使うruntimeが既に扱う部分を作り直さず、余分なdescriptor保持による終了妨害も所有権で扱う。
短いconsumerへの送信終了が正常な用途も、全件の出力が必要な用途もあるため、一律に失敗を
握り潰したり、常に不具合扱いしたりしない。無制限buffer、固定pipe容量、万能retryや
shell optionを解決策にしない。全体sort等が全データを要するならstream化自体を目的にしない。

### 6. 明瞭な失敗と資源解放は、小さくする対象から除外しない

S4の共通終了処理は、複数の失敗箇所に必要な解放を一貫させるためのCでの手段である。
解放不要なら直接returnする説明と、途中まで取得した資源を誤って解放する例も含む。
S5は並行実行による問題を実装後の付け足しにしない。

**適用判断:** lifetime owner、borrowed/owned、部分取得、取消、並行アクセスを変更境界で
明らかにし、その言語のscoped cleanupで十分ならそれを使う。Cのgotoを他言語へ強制せず、
同じ原理をRAII、context manager等の既存機能で実現する。元の失敗を保持し、libraryから
勝手にprocessを終了させない。「静か」は失敗隠蔽ではなく、必要な情報だけを適切な境界へ返すこと。
追加guardは既存の到達可能性・既存保証の判断に従い、仮説だけで増やさない。

### 7. 利用者の互換性と、内部実装を変える自由を区別する

S6はkernel/userspace境界とkernel内部APIを明確に区別し、内部変更では必要な利用側を
一緒に修正する。S8のno-regressionはABIの署名だけの保護ではない。形式上のAPIが同じでも
既存利用が壊れれば問題になり、旧挙動が不具合だったという説明だけで免除されない。
kernel更新のために利用者へ無関係なprogramの同時更新を当然に要求する方針でもない。
重大で避けられないsecurity問題等の例外は、一般的な破壊許可ではない。

**適用判断:** AgentCanonはこのLinux固有の強さを全repositoryへの永久API固定として
輸入しない。必要なのは実callerへの影響を調べ、明示契約と依頼された変更の権限を分けること。
依頼済みの根本修正に必要な内部・公開APIの変更は、既存Public API additionsに従って
利用側・test・docを移行する。単に使用中だから止めず、逆に未文書化だから無影響とも扱わない。
実際の互換性要求と衝突する部分は具体的に報告し、独立した認可済み作業は進める。
これはLinuxの引用ではなく、AgentCanonの既存権限境界を守る適用上の区別である。

### 8. 実証的な単純さは、玩具入力向けの単純さと異なる

S3は予感による高速化で複雑にすることを戒める。S5は過剰inlineがcode sizeやcacheを
通じて逆効果になる可能性を指摘し、S9は性能主張に比較可能な根拠を求める。

**適用判断:** 既存SEP-06のWorkload and scale before mechanismを使い、要求規模で
成立する方式の中で単純なものを選ぶ。解析上破綻する方式を「あとで測る」と採用せず、
計算量だけで定数因子・I/O・copy・保持状態を無視もしない。実測が判断や高速化主張に
必要なら規定環境の対象検証を使い、実行不能ならその主張を未検証とする。
すべての変更へbenchmarkや環境再構築を追加する規則にはしない。

### 9. 小さな変更単位は、必要な修正を途中で切ることではない

S9の単位は一つの論理変更であり、一つのfileではない。問題、影響、原因、選択理由を
読み手が理解できる説明にする。S1の早い試行と不出来な部分の再設計も、完成品に要求済みの
振る舞いを欠落させる根拠ではない。

**適用判断:** 原因箇所と必要な利用側、回帰例、削除対象、docを同じ完成単位で閉じる。
独立した変更は分けるが、stubや第二実装を残すための分割はしない。レビューは実際の
契約・結果・失敗へ向け、checklist、行数、style checkerの合格だけを品質の証明にしない。
既存の指定formatterは使う一方、kernelのtab幅・C構文・投稿作法を全言語へ複製しない。

## 既存規則との対応と限定的な追記

| 判断対象 | 既存の正本 | この調査の位置づけ |
| --- | --- | --- |
| 責務と再利用 | SEP-03/05/08、Simplest complete implementation | 既存正本の判断を参照する。新しい一般則は追加しない |
| 入力、出力、失敗、資源 | SEP-01/02/07/13/14、Contract and valid domain、Reachable abnormal conditions | 既存契約を維持する。機械向けCLI/streamの境界だけを次行で具体化する |
| 機械向けCLIとstream | [Machine-facing and streaming contracts](../../../agents/canonical/ROOT_IMPLEMENTATION.md#machine-facing-and-streaming-contracts) と実際のcaller契約 | 結果とdiagnosticの区別、framing/end-of-input、status、partial結果、streamのEOF/backpressure/cancelを必要な場合だけ扱う |
| API互換性、移行、検証 | Public API additions、SEP-09/10/11、RC-09 | 既存のAPI、移行、検証ownerが引き続き正本。研究noteは別のgateを作らない |

機械向けCLIと実際のstream境界に関する上記の条件付き判断だけを、既存のsource-side
implementation ownerへ接続する。その他の調査項目はSEPと既存ownerの根拠・適用限界を
説明するもので、新しいsource-free consumer要件、skill、checker、schema、配布adapter、
execution routeは作らない。

## 適用例と反例

以下は設計を比較する仮想例であり、実在APIの能力やtest成功を主張するものではない。

### 行単位の変換command

要求: 各recordを独立に変換し、失敗recordがあれば成功扱いにしない。
望ましい接続は `既存parser -> 既存の変換API -> 既存serializer` とし、CLIが
引数・診断・終了状態を所有する。progressをstdoutへ混ぜて下流parserを壊す案、
全件を無条件にbufferする案、例外を空の成功結果へ変換する案は、この要求を満たさない。
既に出力したrecordの有効性も定める。全件原子的な出力が要求なら、単純な逐次出力は
不適合であり、既存のtransaction/publication機構を検討する。

### 数値計算libraryと表示

要求: 配列のdtype・shape・精度・有効入力を保って合成計算する。
同じ計算APIを呼び出し、表示はcallerに残す。UNIXらしさのために配列を文字列にし、
subprocessへ送り、表示を再parseする案には変換・精度・実行経路の余計な契約が生じる。
組合せ可能性はpipe記法ではなく、必要な意味を保つAPIの接続で判断できる。

### 二段階の資源取得

要求: Aの取得後にBの取得が失敗してもAを解放し、未取得のBや借用資源を解放しない。
既存のscoped lifetimeでその責務を閉じる案を優先する。各callerに同じguardやcleanupを
複写する案や、catchして成功を返す案は不要な所有者と誤った成功を作る。
ここでの検証対象は現行契約で到達する部分取得・取消経路であって、存在しない状態を
private helperへ注入して新しいproduction guardを要求することではない。

## 調査の限界

資料から実装判断の根拠と反例を整理したもので、これらの文章によってエージェントの
遵守率・欠陥率・コード量が改善したという実測ではない。リンク先を全文保存したarchiveや
全Linux設計の網羅検証でもない。個々のPRでは変更した契約の実検証を別に示す必要がある。
資料の権威や用語だけで修正範囲を増やさず、現在の要求・既存能力・反例で判断する。
