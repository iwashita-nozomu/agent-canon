<!--
@dependency-start
contract report
responsibility Records a dated benchmark interpretation and MoE-style multi-agent design for the GPT-5.6 model family.
upstream design ../README.md repository entrypoint and OpenAI/Codex source route
upstream design agent-canon-technology-bibliography.md external source-record and agent-method context
@dependency-end
-->

# GPT‑5.6 系ベンチマーク、定性的特性、MoE 型マルチエージェント設計調査

> **調査基準日:** 2026年7月11日（JST）
> **対象:** GPT‑5.6 Sol / Terra / Luna、Sol Ultra、Responses API の Multi-agent / Programmatic Tool Calling
> **主な情報源:** OpenAI 公式発表・System Card・API ドキュメント、各ベンチマークの論文・公式サイト、Artificial Analysis
> **データ固定:** リーダーボード、モデル仕様、料金、ベータ API は更新され得る。本書は上記日時のスナップショットである。

> [!IMPORTANT]
> 本書でいう **「MoE 型」** は、モデル内部の学習済み sparse Mixture-of-Experts を指さない。アプリケーションが、タスク単位で **モデル × 推論量 × 役割プロンプト × ツール権限 × コンテキスト断片**を選ぶ「外部ルーティング型の専門家混合」を指す。したがって、正確には **task-level heterogeneous ensemble / mixture-of-agents** である。

## 目次

1. [エグゼクティブサマリー](#1-エグゼクティブサマリー)
2. [仕様・料金・運用上の前提](#2-仕様料金運用上の前提)
3. [調査方法とスコアの読み方](#3-調査方法とスコアの読み方)
4. [モデル別の能力フィンガープリント](#4-モデル別の能力フィンガープリント)
5. [推論量を含む性能・費用・遅延の面](#5-推論量を含む性能費用遅延の面)
6. [ベンチマークの健全性と比較上の注意](#6-ベンチマークの健全性と比較上の注意)
7. [各テストの定性的解釈](#7-各テストの定性的解釈)
8. [MoE 型ルーティング設計](#8-moe-型ルーティング設計)
9. [推奨マルチエージェント構成](#9-推奨マルチエージェント構成)
10. [OpenAI 内蔵 Multi-agent と Sol Ultra](#10-openai-内蔵-multi-agent-と-sol-ultra)
11. [安全性・権限・状態管理](#11-安全性権限状態管理)
12. [自社評価の実験計画](#12-自社評価の実験計画)
13. [公開ベンチマーク全表](#13-公開ベンチマーク全表)
14. [System Card の補助評価](#14-system-card-の補助評価)
15. [既知の不整合・限界](#15-既知の不整合限界)
16. [出典](#16-出典)

---

## 1. エグゼクティブサマリー

### 1.1 最も重要な結論

1. **Sol は「難題・深い探索・最終裁定」の専門家。** 公式39行のうち GPT‑5.5 を38行で上回り、GPT‑5.6 系内では37行で首位。特に低レベルサイバー、科学研究、OS/CAD、GPUカーネル、最難関数学、未知環境への適応で差が大きい。[S1](#src-s1)
2. **Terra は単なる中間モデルではない。** コード、ブラウザ探索、閉形式科学、長文検索の一部で Sol に近く、NanoGPT と PostTrainBench Lite では Sol を上回る。一方、深いサイバー、医薬化学、OS操作、ARC‑AGI‑3では落差がある。研究工学の反復・検証役として独自価値がある。[S1](#src-s1)
3. **Luna は「高速な数の展開・抽出・定型検証」の専門家。** SWE‑Bench Pro、Terminal‑Bench、BrowseComp、MMMU Pro、GPQA では Sol の約92〜98%を保つが、GeneBench、ExploitGym、KernelGen、NanoGPT、MRCR、ARC‑AGI‑3では大きく崩れる。価格だけでなく、タスク形状による能力の非線形性を前提にする。[S1](#src-s1)
4. **ルーターはモデルだけでなく推論量も選ぶべき。** Artificial Analysis では、Luna high と Terra medium が同じ Intelligence Index 46、Luna xhigh・Terra high・Sol low が同じ49になる。ところが初回応答遅延は大きく異なるため、「安い小モデルを深く考えさせる」が常に低遅延とは限らない。[S7](#src-s7)[S8](#src-s8)
5. **推奨の基本形は、Lunaで広く探索 → Terraで反証・検証 → Solで証拠付き裁定。** 多数決ではなく、出典・実行結果・テスト・反例を重み付けする。全員が同じモデル系列なので、票を独立な証拠として数えない。
6. **OpenAI API 内蔵 Multi-agent は同種エージェント。** ルートとサブエージェントは、1リクエスト内で同じモデルと同じツール集合を共有する。Sol / Terra / Lunaを混在させる本当の異種MoEは、アプリケーション側で別リクエストを編成する必要がある。[S5](#src-s5)
7. **内蔵 Multi-agent は独立な並列仕事に向く。** コードベースの別領域、複数資料、複数仮説などには有効だが、単一の順序依存チェーン、頻繁な共有書き込み、1つの遅い外部処理が支配する仕事には不向き。[S5](#src-s5)
8. **公開ベンチマークの差をそのまま生産判断にしない。** SWE‑Bench Pro はOpenAIの監査で約30%の問題が壊れていると推定され、FrontierMath v2は旧版の42%の問題に修正を入れ、Terminal‑Bench 2.1は89問中28問を修正した。版・ハーネス・採点器の固定が必須。[S9](#src-s9)[S31](#src-s31)[S16](#src-s16)

### 1.2 推奨デフォルト構成

```text
入力
  │
  ├─ 決定論的プリルーター
  │    ├─ リスク / 可逆性 / 書込み有無
  │    ├─ 分野 / 新規性 / コンテキスト形状
  │    └─ 予算 / レイテンシーSLO
  │
  ├─ Luna high: 3〜N個の読み取り専用スカウト
  │    └─ 検索、抽出、候補生成、リポジトリ地図、ログ分類
  │
  ├─ Terra high: 1〜2個の独立検証者
  │    └─ 反証、テスト設計、出典照合、ポリシー確認、重複除去
  │
  ├─ Sol high / xhigh: 1個の裁定者
  │    └─ 難しい統合、矛盾解消、最終計画、根拠不足の明示
  │
  └─ 決定論的ポリシーゲート
       ├─ 低リスク: 応答
       └─ 書込み・高リスク: 承認 → 単一writer → 事後検証
```

この構成の狙いは、**探索量は安価に増やし、誤りを検出する経路を独立させ、最終出力と副作用を一箇所に集約すること**である。

---

## 2. 仕様・料金・運用上の前提

価格はAPIの100万トークン当たり。キャッシュ書込みは未キャッシュ入力の1.25倍、キャッシュ読込みは未キャッシュ入力から90%割引。入力が272Kトークンを超えるリクエストでは、リクエスト全体に入力2倍・出力1.5倍の長文料金が適用される。[S1](#src-s1)[S3](#src-s3)[S4](#src-s4)

| モデル | 主用途 | APIモデルID | 入力 | 出力 | キャッシュ読込 | キャッシュ書込 | コンテキスト | 最大出力 | 知識カットオフ |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| **GPT‑5.6 Sol** | 最高品質、難題、最終裁定 | `gpt-5.6-sol` / `gpt-5.6` | $5.00 | $30.00 | $0.50 | $6.25 | 1,050,000 | 128,000 | 2026-02-16 |
| **GPT‑5.6 Terra** | 検証、汎用コード、均衡点 | `gpt-5.6-terra` | $2.50 | $15.00 | $0.25 | $3.125 | 1,050,000 | 128,000 | 2026-02-16 |
| **GPT‑5.6 Luna** | 高スループット、探索、抽出 | `gpt-5.6-luna` | $1.00 | $6.00 | $0.10 | $1.25 | 1,050,000 | 128,000 | 2026-02-16 |

共通してテキスト・画像入力、テキスト出力、関数呼出し、Web検索、ファイル検索、コンピューター操作、`none / low / medium / high / xhigh / max` の推論量を扱う。GPT‑5.6向けには、Programmatic Tool Calling、明示的プロンプトキャッシュ、推論状態の継続、Multi-agent beta、`reasoning.mode: "pro"` も案内されている。[S3](#src-s3)[S4](#src-s4)

### 2.1 MoE運用での費用式

概算は少なくとも次の形で置く。

$$
\begin{aligned}
C_{\mathrm{total}} &= \sum_{\mathrm{agent}}
\left(
\mathrm{uncached\_input}\,p_{\mathrm{in}}
+\,1.25\,\mathrm{cache\_write}\,p_{\mathrm{in}}
+\,0.10\,\mathrm{cache\_read}\,p_{\mathrm{in}}
+\,\mathrm{output}\,p_{\mathrm{out}}
\right) \\
&\quad+ \mathrm{tool\_cost} + \mathrm{orchestration\_overhead}
\end{aligned}
$$

入力が272Kを超える各リクエストには長文倍率を適用する。複数エージェントへ同じ巨大コンテキストを複製すると、**エージェント数に比例して長文料金とコンテキスト希釈が増える**。したがって、MoEでは「全員に1Mトークンを渡す」のではなく、静的接頭辞をキャッシュし、検索・索引・断片化で各専門家の文脈を絞る。

### 2.2 「1Mコンテキスト」と「1Mで信頼できる推論」は別物

全3モデルが同じ最大コンテキスト長を持っても、MRCRとGraphWalksの結果は大きく異なる。LunaはMRCR 256K–512KでSolの約45%、GraphWalks 256KではTerraを上回るが、1MではTerraを下回る。容量はAPI上限、ベンチマークは検索・順序・状態追跡能力であり、同義ではない。[S1](#src-s1)

---

## 3. 調査方法とスコアの読み方

### 3.1 情報源の優先順位

1. OpenAI公式発表表：GPT‑5.6各モデルの中心値。[S1](#src-s1)
2. OpenAI System Card：能力閾値、安全性、医療、プロンプトインジェクション。[S2](#src-s2)
3. OpenAI APIドキュメント：価格、仕様、Multi-agent、PTCの挙動。[S3](#src-s3)〜[S6](#src-s6)
4. ベンチマークの論文・公式サイト：問題構成、採点方法、限界。
5. Artificial Analysis：同一運営者による推論量別の費用・速度・横断評価。[S7](#src-s7)[S8](#src-s8)

### 3.2 本書の記述ラベル

| ラベル | 意味 |
|---|---|
| **観測** | 公開表・論文・ドキュメントに直接記載された数値または仕様。 |
| **解釈** | 観測から、テストが測る能力と測らない能力を説明したもの。 |
| **運用仮説** | MoE構成へ移すための設計判断。自社評価で検証が必要。 |

### 3.3 スコアを読む際の原則

- スコアは、通常 **「その条件のハーネスで得た集計値」**であり、成功確率、事実性、無事故率、代替可能な労働割合と同じではない。
- パーセント表記でも、完全成功率、部分点、rubric得点、pass@k、平均目的達成率など意味が違う。
- 異なるベンチマークを足し合わせない。AA Intelligence Indexのような合成指標は、その重みと構成を固定したときだけ比較する。
- 同一モデルでも、推論量、ツール、試行数、温度、継続推論、コンテキスト、採点器、モデルスナップショットが違えば別条件である。
- 1〜3ポイントの差は、問題数、試行分散、採点誤差によって容易に逆転し得る。とくに壊れた問題を含む評価では順位の強い解釈を避ける。
- 内部評価は再現できないため、ルーティング根拠としては公開・実行検証可能な評価より低い重みを与える。

---

## 4. モデル別の能力フィンガープリント

### 4.1 役割としての要約

| モデル | 強く出る特性 | 弱く出る特性 | 推奨役割 | 避けるべき使い方 |
|---|---|---|---|---|
| **Sol** | 深い探索、未知課題、低レベル実装、科学・医薬、長期依存、最終統合 | 最高推論量では初動が非常に遅い。価格が高い。単純仕事にも過剰計算し得る | 難題専門家、裁定者、最終設計者、高リスクレビュー、失敗時のエスカレーション先 | 全候補生成をSolで扇状展開、常時max、複数Solへ巨大文脈を複製 |
| **Terra** | コード、検索、閉形式推論、研究デバッグ、反証、短い初動。NanoGPT/PostTrainで系内首位 | 深いサイバー、医薬化学、OS操作、未知環境への適応でSolとの差 | 検証者、コードレビュアー、実験計画比較、ポリシーチェッカー、中難度実行者 | 「常に価格と能力の中間」と仮定、maxを低遅延用途に使用 |
| **Luna** | 低単価、高出力速度、定型コード、検索、分類、抽出、候補列挙、閉形式QA | 深い科学、低レベルサイバー、ML研究、超長文検索、ARC型適応 | 読み取り専用スカウト、シャード処理、構造化抽出、一次トリアージ、軽量リライター | 単独の高リスク裁定、xhigh/maxで対話速度を期待、1M文脈の丸投げ |

### 4.2 Solに対する能力保持率から見える「境界」

保持率は各ベンチマークで `モデル得点 / Sol得点` を計算しただけであり、異なるテスト間の重要度を揃えていない。

| タスク群 | Terra / Sol | Luna / Sol | 定性的な境界 |
|---|---:|---:|---|
| SWE‑Bench Pro | 98.1% | 97.1% | 既存リポジトリ修正では両者とも近い。ただしベンチマーク自体の健全性に注意。 |
| Terminal‑Bench 2.1 | 98.4% | 95.4% | 明確な最終状態と検証器がある端末作業は小型モデルにも適合。 |
| BrowseComp | 96.8% | 92.1% | 狭い答えを探すWeb探索はLunaの有力領域。 |
| GPQA Diamond | 98.2% | 97.6% | 閉形式の専門科学選択問題では差が小さい。 |
| HealthBench Professional | 95.4% | 92.1% | 文章応答rubricでは近いが、臨床結果や自律判断を意味しない。 |
| GeneBench Pro | 81.2% | 37.6% | 分岐する研究分析・データ解釈ではLunaが急落。 |
| MedChemBench | 72.5% | 62.9% | 多目的最適化・構造推論はSol優位。 |
| SEC‑Bench Pro | 81.0% | 68.7% | 実ブラウザエンジン級の脆弱性探索では差が開く。 |
| ExploitBench | 72.0% | 45.2% | 低レベル状態・プリミティブ連鎖で小型モデルが崩れる。 |
| KernelGen1P | 80.5% | 36.7% | 正しさと性能を同時に満たすGPUコードはSol向き。 |
| MRCR 256K–512K | 97.9% | 45.1% | Terraは長文検索を維持、Lunaは大幅低下。 |
| GraphWalks 256K | 84.8% | 89.6% | LunaがTerraを上回る。文脈長だけでなく問題構造が支配する。 |
| ARC‑AGI‑3 | 10.3% | 2.3% | 新しい環境の目的・規則を探索する流動的適応はSolに集中。 |
| NanoGPT | 149.6% | 17.1% | TerraがSolを上回る。反復型ML研究は単純なモデル序列にならない。 |
| PostTrainBench Lite | 102.4% | 58.8% | Terraが僅差首位。異種パネルからTerraを外すべきでない。 |

### 4.3 非線形性から導くルーティング原則

- **「難しさ」だけでなく「難しさの種類」を分類する。** 閉形式・検証可能・既存構造内の問題はLuna/Terraが追いつきやすい。未知環境、長い低レベル状態、複数の分析分岐、複数目的最適化はSolへ寄せる。
- **検証器が強いほど安い専門家を使いやすい。** コンパイラ、テスト、schema validator、SQL制約、数値再計算などがある仕事は、Luna/Terraで候補を増やし、決定論的に落とせる。
- **正解が文章品質rubricだけで決まる仕事は自己採点を信用しすぎない。** 事実・出典・実行結果を別経路で確認する。
- **Terraの逆転を活かす。** ML R&Dや反復実験では、Sol一本化よりTerraとSolの異なる提案を実行器で比較する方が合理的。

---

## 5. 推論量を含む性能・費用・遅延の面

Artificial Analysisの表示値を、モデルと推論量の「運用点」として整理した。Intelligence Indexは高いほど良い。`Blended $/1M` は同サイトの入力・キャッシュ入力・出力を混ぜた表示単価、速度は中央値、初回チャンクと総時間は500トークン応答の測定である。実APIのタスク費用ではない。[S7](#src-s7)[S8](#src-s8)

| モデル | 推論量 | Intelligence Index | Blended $/1M | 出力速度 (tok/s) | 初回チャンク (秒) | 500tok総時間 (秒) |
|---|---|---:|---:|---:|---:|---:|
| Sol | low | 49 | $4.35 | 63 | 2.21 | 10.16 |
| Sol | medium | 54 | $4.35 | 61 | 4.55 | 12.78 |
| Sol | high | 56 | $4.35 | 62 | 10.67 | 18.75 |
| Sol | xhigh | 58 | $4.35 | 69 | 57.12 | 64.37 |
| Sol | max | 59 | $4.35 | 73 | 154.23 | 161.13 |
| Terra | none | 34 | $2.17 | 115 | 0.75 | 5.11 |
| Terra | low | 40 | $2.17 | 120 | 1.48 | 5.66 |
| Terra | medium | 46 | $2.17 | 116 | 1.55 | 5.87 |
| Terra | high | 49 | $2.17 | 120 | 2.47 | 6.64 |
| Terra | xhigh | 52 | $2.17 | 134 | 27.55 | 31.27 |
| Terra | max | 55 | $2.17 | 140 | 153.60 | 157.16 |
| Luna | none | 27 | $0.87 | 193 | 0.73 | 3.32 |
| Luna | low | 33 | $0.87 | 202 | 1.29 | 3.77 |
| Luna | medium | 38 | $0.87 | 193 | 1.84 | 4.42 |
| Luna | high | 46 | $0.87 | 197 | 5.83 | 8.36 |
| Luna | xhigh | 49 | $0.87 | 193 | 34.40 | 36.99 |
| Luna | max | 51 | $0.87 | 204 | 99.97 | 102.41 |

### 5.1 同じ指数を得る複数の経路

| おおよその指数 | 運用点 | 費用・遅延の読み方 |
|---:|---|---|
| 46 | Luna high / Terra medium | Lunaは表示単価が約40%で出力も速いが、初回チャンクは5.83秒対1.55秒。非同期fan-outにはLuna、対話的検証にはTerraが向く。 |
| 49 | Luna xhigh / Terra high / Sol low | Lunaは最安だが初回34.4秒。Terraは2.47秒で検証役に適し、Sol lowは難しい領域への質的保険になる。 |
| 54〜56 | Sol medium/high / Terra max | Terra maxは低単価だが初回約154秒。Sol medium/highは大幅に速く、対話・直列パイプラインではTerra maxを使う理由が薄い。 |
| 58〜59 | Sol xhigh/max | maxは指数+1に対し初回約57秒から154秒へ増える。高価値で未解決の難題に限定する。 |

### 5.2 推奨する推論量ポリシー

| 役割 | デフォルト | 昇格条件 | コメント |
|---|---|---|---|
| Lunaスカウト | `high` | 証拠不足ならスカウト数を増やす。`xhigh`より先にデータ分割を改善 | highは費用対能力の有力点。xhigh/maxはLunaの速度上の利点を失いやすい。 |
| Terra検証者 | `high` | 相互矛盾、実行失敗、複雑なコードなら`xhigh`またはSolへ | 初回が短く、指数49。低遅延のcritique/judgeに使いやすい。 |
| Sol裁定者 | `high` | 未知課題、最難関、反証未解消なら`xhigh` | highは品質と待ち時間の均衡。 |
| 最終救済 | Sol `max` またはSol Multi-agent | 高い失敗損失、他経路の不一致、明確な追加価値があるときだけ | 常用せず、予算上限とタイムアウトを明示。 |

Artificial Analysisは、試験した費用対知能面でSolとLunaがパレート前線に入り、Terraが両者に支配される帯域があると報告した。ただしこれは費用と合成知能の二軸であり、**Terra highの短い初動、特定領域での逆転、検証役としての価値を否定しない**。[S8](#src-s8)

---

## 6. ベンチマークの健全性と比較上の注意

### 6.1 重大な品質問題

| 評価 | 確認された問題 | 実務上の扱い |
|---|---|---|
| **SWE‑Bench Pro** | OpenAIの監査は、人手監督レビューで27.4%を問題ありとし、人手注釈から34.1%が壊れていると推定。誤ったテスト、過度に特定実装を要求するテスト、不完全な環境などが含まれる。[S9](#src-s9) | 数ポイント差をモデル能力差として断定しない。自社repoでは独立テスト、コードレビュー、再現手順を採点する。 |
| **FrontierMath** | v2は旧版の問題の42%に誤り修正を行い、全338問（T1–3が295、T4が43）へ再構成。[S31](#src-s31) | 必ず版とtierを固定。旧版と新版の得点を直結しない。 |
| **Terminal‑Bench 2.1** | 89問中28問で環境・採点・仕様を修正。[S16](#src-s16) | 2.0と2.1を同一系列の連続値とみなさず、コンテナと採点器を保存する。 |
| **Agents’ Last Exam** | OpenAIの同じ発表ページで本文53.6、表52.7と不一致。[S1](#src-s1) | 本書は比較表の52.7を採用し、誤差・条件差として保留。 |
| **HealthBench Professional** | GPT‑5.5が発表表49.5、System Cardのlength-adjusted表51.8。GPT‑5.6の3値は一致。[S1](#src-s1)[S2](#src-s2) | 比較時に採点条件を固定し、GPT‑5.5との差を単一値で断定しない。 |

### 6.2 評価形式ごとの典型的な誤読

| 評価形式 | 誤読 | 正しい読み方 |
|---|---|---|
| 多肢選択 | 高得点なら研究・実務も任せられる | 閉じた選択肢内の知識・推論。仮説生成、実験、引用、行動安全は別評価。 |
| 最終状態verifier | 高得点なら過程も安全 | 望む最終状態だけを測る場合、不要な変更、秘密漏洩、権限逸脱を見逃し得る。 |
| 部分点 | 62点なら62%のタスクを完全完了 | 部分的な進捗・サブ目標達成の平均である場合がある。OSWorldやAutomationBenchで特に注意。 |
| LLM judge / Elo | 人間と同等の正しさ | 特定rubric下の比較選好。judgeの偏り、長さ、文体、出典の見かけに影響され得る。 |
| 合成指数 | 1点差が全領域での優位 | 複数評価の重み付き集約。専門領域の凹凸を隠す。 |
| 非公開内部評価 | 外部で同じ結果が再現できる | 再現性が低いため、方向性の参考にとどめる。 |

### 6.3 自社evalに必ず保存する条件

`model snapshot / reasoning effort / prompt hash / tool schema hash / container image / benchmark version / seed / temperature / timeout / token caps / retries / cache policy / judge model / grader version / raw trajectory / final artifact` を1レコードとして保存する。これがない比較は、モデル差とハーネス差を分離できない。

---

## 7. 各テストの定性的解釈

以下では、数値の大小よりも、**何が得意なら点が上がるか、何を証明しないか、MoEルーターへどう変換するか**を整理する。

### 7.1 プロフェッショナル業務

| テスト | 主に測るもの | 高得点が示すもの | 示さないもの・注意 | MoEルーティング信号 |
|---|---|---|---|---|
| **Agents’ Last Exam** | 55サブ分野、1,500超の長時間・高経済価値タスクを300超の専門家が設計。成果物を含む専門ワークフロー。[S10](#src-s10) | 仕事の分解、長時間の指示維持、資料作成、自己検証、専門的な成果物品質 | 通常業務の全体、組織内調整、規制責任、継続的な対人協働、職務代替率 | Solを最終統合へ。Lunaで資料収集、Terraでrubric・欠落検査。単一モデルより工程分解が合う。 |
| **GDPval / GDPval‑AA v2** | 44職種・9産業・1,320タスクの実務成果物。AA版はshell/webを使い、盲検ペア比較のElo。[S11](#src-s11)[S12](#src-s12) | 成果物の完成度、指示適合、調査・計算・文書化の総合力 | 法的・会計的な最終責任、企業固有データ、反復する顧客対話、長期運用 | 成果物を「調査・分析・レビュー・体裁」に分ける。最終Elo型judgeだけでなく、事実検証を別系統にする。 |
| **Management Consulting Tasks†** | OpenAI内部のコンサルティング型課題 | 構造化、分析、提案書作成の方向性 | 問題構成・採点詳細が非公開で、再現性が低い | 自社の案件資料、定量モデル、推奨の反証可能性で置換する。ルーター学習の主要根拠にはしない。 |
| **Big Finance Bench** | 928の開放型金融調査課題。導出・途中過程へ36,241のrubric pointを割当てる。[S13](#src-s13) | 正しい期間・指標・出典を選び、仮定と計算を監査可能にする能力 | 投資成果、リアルタイムデータの完全性、規制適合、取引実行の安全性 | Lunaを出典・期間抽出、Terraを再計算・定義照合、Solを矛盾解消と説明へ。最終数値だけで採点しない。 |
| **AA Intelligence Index v4.1** | 複数の推論・知識・エージェント評価を集約した横断指数。[S7](#src-s7) | その版・重みでの広い平均能力 | 特定業務の適合、最悪ケース、専門性、実運用費の全て | 事前選別用。ルーターは下位ベンチマークと自社evalで細分化する。 |

### 7.2 コーディング

| テスト | 主に測るもの | 高得点が示すもの | 示さないもの・注意 | MoEルーティング信号 |
|---|---|---|---|---|
| **AA Coding Agent Index v1.1** | 複数のエージェント型コーディング評価の合成 | 幅広いリポジトリ作業・端末作業の平均能力 | 特定言語、巨大mono-repo、社内build、セキュリティ、保守性 | モデルの一次選別に使い、repo固有evalへ移す。Sol 80、Terra 77.4、Luna 74.6は「定型検証可能コードなら下位モデルも候補」の信号。 |
| **SWE‑Bench Pro** | 41リポジトリ・1,865問題（公開731）の実issue修正、複数ファイル編集。[S14](#src-s14) | 既存コード探索、issue解釈、patch作成、既存テスト通過 | 約30%の問題品質懸念、特定実装への過適合、テストの不足、学習データ汚染 | スコア差が小さいため、Luna/Terraで候補patchを作り、独立テストとSolレビューで選ぶ。 |
| **DeepSWE v1.1** | 113の新規長期課題、91repo、5言語。参照解を公開履歴に置かず、機能ベースverifierを使用。[S15](#src-s15) | 短い仕様からrepoを理解し、大きな変更を実装・検証する能力 | 自社依存関係、組織慣行、セキュリティ、長期保守コスト | Terra/Lunaの地図作成とテスト候補、Solの統合実装。挙動verifierが強いので安価なbranchを増やしやすい。 |
| **Terminal‑Bench 2.1** | 89の端末タスク。SWE、ML、security、data、sysadminを最終コンテナ状態で採点。[S16](#src-s16) | shellの計画、ツール使用、環境診断、実行結果による修正 | 本番権限、安全な操作順序、秘密管理、不可逆操作の制御 | Luna/TerraがSolに近い。明確なsandboxとverifierがあるならTerra/Lunaを実行者にし、writer権限は限定する。 |

**解釈:** コーディング4評価では3モデルの差が比較的小さい。これは「Lunaで何でも実装できる」ではなく、**テスト・コンテナ・patchという強い外部フィードバックがモデル差を圧縮しやすい**ことを示す。実行可能な検証器がある領域はMoEの費用削減余地が大きい。

### 7.3 科学・医療

| テスト | 主に測るもの | 高得点が示すもの | 示さないもの・注意 | MoEルーティング信号 |
|---|---|---|---|---|
| **GeneBench Pro** | 129の研究級ゲノミクス、定量生物、トランスレーショナル課題。汚いデータと依存する分析分岐。[S17](#src-s17) | 解析上の異常に気付き、次の解析を選び、複数段階の証拠を統合する能力 | 実験の再現、データ品質保証、臨床有効性。Sol 28.7も絶対値は低い | Solを主解析。Lunaは文献・メタデータ抽出のみ、Terraは計算再現と反証。低スコアゆえ人間専門家を必須にする。 |
| **LifeSciBench** | 750課題、173科学者。証拠処理、分析、設計・最適化、推論、検証・運用、翻訳、科学コミュニケーションの7群。[S18](#src-s18) | 研究ワークフローを端から端まで支援する幅 | 実験結果の真実性、ラボ安全、独創性、研究倫理 | 役割分解が自然。Sol研究者、Terra方法論レビュアー、Luna文献・データ整理。 |
| **MedChemBench†** | 化学構造、SAR、potency、toxicity、ADME、多目的lead最適化、retrosynthesisを含むと公式説明。[S38](#src-s38) | 複数の化学的制約を同時に扱う能力 | 詳細な公開再現性が限られる。実験毒性・合成可能性・規制判断 | Terra/Lunaの落差が大きい。Sol専門家へ早期ルートし、外部計算・データベース・人間化学者で検証。 |
| **HealthBench Professional** | 525の医師作成課題。診療相談、文書、医学研究を3人以上の医師rubricで評価。[S19](#src-s19) | 医療専門家向け文章の妥当性、包括性、表現 | 患者アウトカム、診断安全性、実際の診療責任、地域ガイドライン適合 | Luna/Terraも文章rubricでは近いが、重要判断はSol＋ガイドライン検索＋医師承認。自律的な治療変更へ直結させない。 |

**解釈:** 科学領域では、閉形式のGPQAと、研究過程を問うGeneBenchの差が大きい。ルーターは「科学」というラベルだけでなく、**選択問題か、データを読み分岐する研究作業か**を識別する必要がある。

### 7.4 コンピューター操作・文書・CAD

| テスト | 主に測るもの | 高得点が示すもの | 示さないもの・注意 | MoEルーティング信号 |
|---|---|---|---|---|
| **OSWorld 2.0** | 108の長時間GUIワークフロー。人間中央値1.6時間、平均318 tool call、動的・複数ソース・隠れ状態を含む。[S20](#src-s20) | 画面認識、状態追跡、細かい操作、長い手順の回復 | 62.6を「62.6%完全完了」と読まない。論文はbinary completionとpartial progressを区別 | Sol寄り。Lunaは画面要約や候補位置、Terraはチェックポイント検証。writerを1体にし、操作ログとスクリーン差分を保存。 |
| **BrowseComp** | 1,266の見つけにくい短答事実。検索の粘りとquery reformulation。[S21](#src-s21) | Web上の埋もれた一点を探す探索力 | 情報源品質、長文総合、曖昧な問い、外部アクションの安全性 | Lunaのスカウトに最適。複数検索branchを出し、Terraで出典一致、Solで矛盾時のみ裁定。 |
| **BenchCAD / Python** | 17,900の実行検証済みCadQueryプログラム、106部品群、visual/code QA、image-to-code、editing。[S22](#src-s22) | 3D空間推論、パラメトリック形状理解、CADコード合成 | 製造公差、材料、工程、規格、完全なCAD製品開発 | Luna/Terraで部品認識・パラメータ候補、Solで難しい幾何・修正。実行renderと寸法validatorで選別。 |
| **gdp.pdf** | 10専門領域、100の実PDF課題。表、図、フォーム、契約など。[S23](#src-s23) | 密な文書から構造・関係・数値を読む能力 | OCR品質、全社文書運用、法的解釈、版管理、署名の真正性 | PDFをページ/要素へ分割してLuna抽出、Terraクロスチェック、Solで跨ページ推論。引用座標をbranch contractに含める。 |

### 7.5 サイバーセキュリティ

| テスト | 主に測るもの | 高得点が示すもの | 示さないもの・注意 | MoEルーティング信号 |
|---|---|---|---|---|
| **CTF†** | 多様なセキュリティパズルとツール使用 | 攻撃面の認識、仮説生成、スクリプト、試行錯誤 | 本番環境、現実の防御、許可、影響、長期間のopsec。内部評価で再現性が低い | 防御目的でもHigh capability扱い。認可済みsandboxのみ。スカウトに実ネットワーク書込み権限を与えない。 |
| **SEC‑Bench Pro** | V8/SpiderMonkeyの183の検証済み脆弱性で、発見・PoC作成を評価。[S24](#src-s24) | 大規模ランタイムのコード理解、バグ発見、再現可能なPoC | hardened targetへの確実なend-to-end exploit、組織の脆弱性管理全体 | Sol専門家。Terraは独立triage/再現、Lunaはログ・commit・diff抽出。実行環境は隔離し、出力を危険度分類。 |
| **ExploitBench** | 41のV8バグ、coverage/crashから任意read/write・control flow・code executionまで16能力flag。[S25](#src-s25) | 複数のexploit primitiveを連鎖し、深い低レベル状態を扱う能力 | 任意製品での成功、安定性、責任ある開示、合法性 | Solへ即時昇格。多数決は使わず、再現スクリプトとsandbox観測で証拠化。 |
| **ExploitGym** | 論文ではuserspace/V8/Linuxの898実脆弱性。triggering PoCからexploitへ発展。[S26](#src-s26) | 既知クラッシュを利用可能な状態へ進める長期技術力 | 実環境での無害性、検知回避、許可、Critical能力の保証 | Sol中心。低スコアのため自動完遂を期待せず、段階ごとにhuman gate。 |

**安全上の前提:** System Cardでは3モデルともBio/ChemとCyberがHigh capability、Critical未満。OpenAIは標準構成でhardened targetへのCritical severityの機能するend-to-end exploitは得られなかったとするが、これは無害性の保証ではない。[S2](#src-s2)

### 7.6 自己改善・研究工学

| テスト | 主に測るもの | 高得点が示すもの | 示さないもの・注意 | MoEルーティング信号 |
|---|---|---|---|---|
| **Internal Research Debugging†** | 研究コード・実験のデバッグと思われる内部評価 | 仮説、ログ解釈、実験修正の方向性 | 問題詳細が非公開 | TerraがSolの99.3%。Terraを主検証者にし、Solは難しい原因・最終裁定へ。 |
| **KernelGen1P** | PyTorch workloadから正しく高速なcustom GPU kernelを生成する系統。公開KernelBenchは250 workload。[S29](#src-s29) | ハードウェア制約、数値正しさ、性能最適化の同時処理 | `KernelGen1P`の正確な内部変種は一部不透明。実GPU・driver依存 | Sol優先。Lunaは36.7%保持にとどまる。候補生成後、決定論的correctness/perf harnessで採用。 |
| **NanoGPT** | 固定環境でNanoGPT speedrunの歴史的改善を再現する実験設計・最適化。[S28](#src-s28) | 反復実験、仮説優先順位、計測、最適化 | 一般的な「自己改善」全体、モデル自身の恒久的変更 | TerraがSolの1.50倍。TerraとSolを並列に戦略提案させ、同一実行器でA/Bする。 |
| **PostTrainBench Lite** | base model、target benchmark、10時間・H100 1枚・Webを与え、学習pipelineを構築・改善。[S27](#src-s27) | 制約下のend-to-end ML R&D、データ・学習・評価の統合 | eval hacking、偶然、別compute規模への一般化 | Terraが僅差首位。研究エージェントはモデル階層より、提案の多様性と実験証拠で選ぶ。 |
| **RSI Index†** | OpenAI内部のrecursive self-improvement関連合成評価 | 研究工学の広い傾向 | 問題・採点・安全境界が不透明 | 補助信号のみ。公開可能な実験ログをルーティング基準にする。 |

### 7.7 マルチモーダル・学術推論

| テスト | 主に測るもの | 高得点が示すもの | 示さないもの・注意 | MoEルーティング信号 |
|---|---|---|---|---|
| **MMMU Pro** | text-onlyで解ける問題を除き、選択肢を増やし、vision-only入力も使う高度マルチモーダル評価。[S30](#src-s30) | 図表・画像・文章を統合する閉形式推論 | GUI操作、長時間視覚探索、製造・医療画像の実務安全性 | LunaがSolの約94%。低リスク画像QAはLuna、曖昧・高リスク画像はTerra/Solへ。ツール有無を別条件にする。 |
| **GPQA Diamond** | 専門家レベル科学多肢選択。GPQA全448問、Diamondは最難198問。[S32](#src-s32) | 高度な科学知識と閉じた選択肢内の推論 | 文献調査、研究デザイン、実験、長期agent信頼性 | Lunaが97.6%保持。閉形式科学QAはLuna/Terraで十分な可能性が高いが、説明根拠を別採点。 |
| **FrontierMath T1–3 / T4 v2** | 非公開の高難度数学。T4は研究級に近い最難関層。[S31](#src-s31) | 厳密な多段数理推論と正確な最終解 | 開放型の定理研究、査読可能な証明、問題版を跨ぐ比較 | T4はSolへ早期ルート。複数解法branch＋symbolic/numeric verifier。T1–3はTerra候補も有力。 |
| **ARC‑AGI‑3** | 自然言語説明のない新規な抽象的ターン制環境で、目的・世界モデル・操作を探索。[S33](#src-s33) | 未知規則への適応、探索、記憶、online world-model更新 | 日常知識、文章能力、単発論理問題。Sol 7.78も絶対値は非常に低い | 「仕様が不明」「環境から規則を学ぶ」タスクの強いSolルート信号。自律実行より探索ログを重視。 |

### 7.8 ツール利用・長文コンテキスト

| テスト | 主に測るもの | 高得点が示すもの | 示さないもの・注意 | MoEルーティング信号 |
|---|---|---|---|---|
| **AutomationBench** | 47 SaaS、6業務領域、REST workflow、endpoint発見、層状ルール、無関係・誤誘導レコード。[S34](#src-s34) | API発見、複数stepの状態変更、ルール遵守 | 得点は目的達成の平均で、全タスクpassとは限らない。18.1は絶対的に低い | 本番writeへ直結させない。read-only dry run、plan validator、2相commit、単一writerを必須にする。 |
| **Toolathlon** | 32 app、604 tool、108 task、約20 turn、最終状態verifier。[S35](#src-s35) | tool選択、cross-app orchestration、長い状態保持 | 本番権限、障害復旧、秘密、同時更新、非決定的API | Luna/Terraも約92%保持。明確なschemaとsandboxなら安価な実行者にできるが、書込みはゲートする。 |
| **MRCR** | 自然文中の似た複数draftを区別し、指定された過去文脈を順序付きで再現する長文評価。[S36](#src-s36) | 長文検索、順序、干渉耐性、正確な再生 | 法務・財務の意味理解全般、継続的メモリ、外部検索 | Lunaは大きく崩れる。512K級の厳密retrievalはTerra/Sol、Lunaは事前shardingとindex作成まで。 |
| **GraphWalks** | 生のedge listからBFS/多hop操作を行う長文アルゴリズム状態追跡。[S37](#src-s37) | 大規模文脈内の構造追跡と計算 | 意味的文書理解、曖昧な関係、現実知識 | 256KではLuna>Terra、1MではTerra>Luna。文脈長だけでなくグラフ密度・探索形をfeatureにする。 |

### 7.9 テスト群をルーターfeatureへ変換する

| 観測される仕事の特徴 | 近いベンチマーク | 初期ルート |
|---|---|---|
| 短い答えを多数ソースから探す | BrowseComp | Luna highの並列スカウト |
| 明確なテストがあるrepo修正 | DeepSWE / Terminal‑Bench | LunaまたはTerraで候補、決定論的テスト、難しいものだけSol |
| GUIで長時間・隠れ状態・回復が必要 | OSWorld | Sol、Terraのチェックポイント検証、単一writer |
| 汚いデータから分析方針を分岐 | GeneBench | Sol主担当、Terra独立レビュー、人間専門家 |
| 低レベルの状態連鎖・exploit primitive | ExploitBench / Gym | Sol、隔離、認可、段階的human gate |
| 固定computeで反復ML実験 | NanoGPT / PostTrainBench | TerraとSolの並列提案＋決定論的実行器 |
| 500K超から厳密に過去情報を再現 | MRCR | Terra/Sol。先に索引化し、Lunaへ全文を渡さない |
| 未知環境から目的と規則を学ぶ | ARC‑AGI‑3 | Sol xhigh候補。探索予算と停止条件を厳格化 |
| 多数SaaSへ書込み | AutomationBench / Toolathlon | モデル能力より権限・状態管理を優先。plan→approve→execute |

---

## 8. MoE 型ルーティング設計

### 8.1 「専門家」の単位

モデル名だけをexpertとみなさず、次のタプルをexpertとして扱う。

$$
\begin{aligned}
\mathrm{Expert} &= \left(
\mathrm{model},
\mathrm{reasoning\_effort},
\mathrm{role\_prompt},
\mathrm{allowed\_tools},
\mathrm{context\_slice},
\mathrm{output\_schema},
\mathrm{time\_budget},
\mathrm{token\_budget}
\right)
\end{aligned}
$$

例として、`Luna-high-search-scout` と `Luna-high-code-triager` は同じモデルでも異なるexpertである。これにより、モデル切替だけでは得られない **プロンプト・権限・データ分割の多様性**を作れる。

### 8.2 ルーターが見るべきfeature

| Feature | 例 | ルーティングへの影響 |
|---|---|---|
| 分野 | code / science / finance / cyber / GUI | 深いscience・cyber・GUIはSol寄り。検証可能codeは下位モデルも候補。 |
| 問題形状 | 閉形式 / 開放型 / 未知環境 | 閉形式はLuna/Terra、未知環境はSol。 |
| 検証可能性 | unit test / schema / numerical check / human rubric | 強いvalidatorがあれば安価な候補を増やす。 |
| コンテキスト | 長さ、重複、グラフ性、時系列、跨文書依存 | 単なるtoken数でなく構造を分類。MRCR型はLuna回避。 |
| 新規性 | 既知pattern / 新規repo / 未知tool / 規則不明 | 新規性が高いほどSolと探索予算を増やす。 |
| 副作用 | read / reversible write / irreversible write | writeは単一writer＋承認。scoutにはread-only。 |
| 失敗損失 | 低 / 中 / 高 | 高いほど独立検証、Sol裁定、人間gate。 |
| 可逆性 | rollback可能か | 不可逆なら自動実行せず2相commit。 |
| 分解可能性 | 独立subtask数 | 独立なら並列、順序依存なら単一chain。 |
| SLO | P95 latency / budget | 深い小モデルより浅い大モデルが速い場合を考慮。 |

### 8.3 エスカレーション規則

安価なtierから高価なtierへ上げる条件は、モデル自身の「自信」だけにしない。

**強いトリガー:**

- 複数branchの結論または数値が不一致
- 必須claimに出典・line reference・実行結果がない
- validator、unit test、schema、再計算が失敗
- tool出力が空、部分的、異常に狭い、または相互矛盾
- prompt injection、秘密要求、権限拡大、未承認writeを検出
- 高リスク・不可逆操作
- 未知の形式、ARC型の規則不明、長い低レベル状態
- 安価モデルの再試行が同一失敗を繰り返す
- judgeが候補を選べず、差の根拠を説明できない

期待損失で書けば、概念的には次を満たすとき昇格する。

$$
\operatorname{Pr}(\mathrm{failure}\mid \mathrm{observed\ signals})\,\times\,
\mathrm{business\_loss}
>
\mathrm{incremental\_model\_cost}
+\lambda \,\times\,\mathrm{incremental\_latency}
$$

`P(failure)` は自社evalで校正し、自己申告confidenceを単独で使わない。

### 8.4 多数決ではなく証拠重み付き裁定

同じGPT‑5.6系列は、学習データ、表現、alignment、tool harnessを共有し得るため、誤りが相関する可能性がある。3対1の票を3つの独立観測として扱わない。

推奨順序:

1. 決定論的verifier / 実行結果
2. 一次資料・引用位置・データlineage
3. 独立な計算・別実装
4. 反例・失敗ケースの発見
5. rubric judge
6. 単純多数決

### 8.5 branch間の標準出力契約

```json
{
  "recommendation": "...",
  "claims": [
    {
      "claim_id": "C1",
      "text": "...",
      "evidence_ids": ["E12", "TEST-7"],
      "status": "supported|conflicted|missing"
    }
  ],
  "assumptions": ["..."],
  "uncertainties": ["..."],
  "counterexamples": ["..."],
  "failure_modes": ["..."],
  "proposed_writes": [],
  "verification_plan": ["..."],
  "stop_reason": "complete|budget|blocked|unsafe"
}
```

自由文だけを集約すると、根拠の重複、同一誤りの言い換え、出典喪失が起きる。claim IDとevidence IDを持たせることで、裁定者は「票」ではなく「証拠グラフ」を統合できる。

### 8.6 Programmatic Tool Callingとの分業

PTCは、モデルがResponses API内のツールを呼ぶJavaScriptを書き、並列呼出し、loop、条件分岐、中間結果の縮約を行う仕組み。fresh isolated V8で実行され、Node.js、package install、直接network、汎用filesystem、subprocess、console、永続JS状態はない。[S6](#src-s6)

| 処理 | 推奨 |
|---|---|
| filter / join / sort / rank / deduplicate / aggregate | PTC |
| 多数の類似レコードのbatch | PTC |
| schema検証、数値再計算、同じ検査の反復 | PTC |
| 各結果で次の意味判断が変わる探索 | 直接model/tool call |
| 承認が必要なwrite | 直接call＋明確なauthorization boundary |
| 最終引用・native artifactの保持 | 直接callまたは完全なprovenanceを保つ専用処理 |

PTCを「並列だから」という理由だけで使わない。境界、許可tool、出力schema、retry上限、stop条件、model judgmentへのhandoffを明示する。[S6](#src-s6)

---

## 9. 推奨マルチエージェント構成

### 9.1 Cascade：最も汎用的

```text
Luna scouts (parallel, read-only)
        ↓ structured evidence
Terra verifier / adversarial reviewer
        ↓ conflicts + validated facts
Sol arbiter
        ↓ single answer or plan
Policy gate / writer
```

**適合:** 調査、レポート、RAG、財務分析、要件整理。
**長所:** Sol利用率を抑え、証拠不足だけ昇格。
**弱点:** 直列段階が増えるのでP95遅延が伸びる。Luna branchを早期終了できる設計が必要。

### 9.2 Parallel panel：仮説競争

- Luna: 情報源・候補をデータsliceごとに探索
- Terra A: 仕様・数値・引用の検証
- Terra B: 反対仮説・失敗ケースの探索
- Sol: evidence IDだけを見て裁定

**適合:** 技術選定、原因究明、リスク分析、論争的な調査。
**重要:** role prompt、data slice、toolを分ける。同じ質問を同じ文脈で4回聞くだけでは多様性が弱い。

### 9.3 Coding swarm

| 役割 | 推奨expert | 権限 |
|---|---|---|
| repo map / dependency / log triage | Luna high | read-only shell / search |
| requirement decomposition | Terra high | read-only |
| independent implementation hypotheses | Terra high + Sol high | isolated worktree |
| tests / adversarial cases / security review | Terra high | test runner、read-only secrets |
| integration | Sol high | patch proposalのみ |
| merge / deploy | deterministic CI + human or controlled writer | protected write |

同じworktreeへ複数agentが同時writeしない。branch/worktreeを分け、CIで比較してから1つを統合する。内蔵Sol Multi-agentは独立コード領域やレビューには向くが、共有mutable stateへの同時編集には向かない。[S5](#src-s5)

### 9.4 Long-context federation

1. Lunaで文書を索引化・要約・entity/date/ID抽出
2. retrieval layerでclaimごとの根拠断片を選択
3. Terraで引用位置・跨断片整合を確認
4. Solへ必要断片と未解決矛盾だけ渡す

**禁止したい形:** 5体すべてへ同じ900K tokenを送る。料金、遅延、注意分散、誤った相互強化が同時に増える。

### 9.5 ML研究・自己改善系

NanoGPTとPostTrainBench LiteでTerraがSolを上回るため、研究戦略は次のA/Bがよい。

```text
Terra: 実験効率・局所改善・デバッグ案
Sol:   大域的仮説・新規手法・失敗原因
          ↓
決定論的executor: 同じcompute、seed、time budgetで実行
          ↓
Terra: 数値再計算・リーク・eval hacking検査
Sol:   evidenceに基づく次実験の裁定
```

モデルの説得力ではなく、同一実験器の測定値で勝者を決める。

### 9.6 高リスクtransaction

```text
read-only scouts → plan → policy verifier → human/explicit approval
                                   ↓
                            single writer
                                   ↓
                      read-back / reconciliation
```

- `proposed_writes` をbranch出力から分離
- idempotency key、precondition、expected version、rollback planを必須化
- write直前に最新状態を再読込
- write後に別readerが照合
- 金銭、権限、削除、公開、医療、法務、サイバーではhuman gateを追加

---

## 10. OpenAI 内蔵 Multi-agent と Sol Ultra

### 10.1 内蔵Multi-agentの正確な位置づけ

Responses APIのMulti-agent betaは、ルートモデルがサブエージェントをspawnし、message、follow-up、wait、interrupt、一覧取得を使って並列作業を統合する。全GPT‑5.6モデルで利用できる。[S5](#src-s5)

**重要な制約:** 1リクエスト内のrootとsubagentは、**同じrequest modelと同じ利用可能tool集合を共有する**。したがって、`Sol root + Luna scout + Terra reviewer`を1回の内蔵Multi-agent requestだけで実現することはできない。異種MoEはアプリ側で別Responses requestを作り、managerが統合する。[S5](#src-s5)

### 10.2 使うべき仕事・避けるべき仕事

| 使う | 避ける |
|---|---|
| 大規模codebaseの別領域探索 | 各stepが前stepへ強く依存する1本のchain |
| 複数文書・仮説・案の比較 | 小さく短いタスク |
| 独立componentや独立test suite | 同じmutable resourceへの頻繁なwrite |
| 複数原因の並列調査 | 固定された決定論的DAGが必要 |
| 異なる解法の同時探索 | 1つの遅い外部operationが総時間を支配 |

OpenAIは`max_concurrent_subagents=3`を既定かつ多くのworkloadへの推奨値とする。APIは固定の上限、tree depth、総subagent数を設けないが、これは無制限fan-outが有利という意味ではない。[S5](#src-s5)

### 10.3 API上の運用制約

- `/responses/compact` はMulti-agent有効時に未対応
- 自動server-side compactionがroot/subagentごとに独立して有効
- `reasoning.summary` 未対応
- `max_tool_calls` 未対応
- 全agentがrequestに設定されたtoolへアクセス可能
- tool-heavy・長時間workflowではWebSocketがHTTPより待ち合わせを減らしやすい

このため、least privilegeが重要なheterogeneous構成では、アプリ側の別requestで役割ごとにtoolを絞る方が安全である。[S5](#src-s5)

### 10.4 Sol Ultraの公開効果

OpenAIの脚注ではSol Ultraは標準4エージェントの高計算構成で、全agent分のtoken・費用がかかる。公開された標準Solとの比較は3行だけ。[S1](#src-s1)

| ベンチマーク | Sol | Sol Ultra | 差 |
|---|---:|---:|---:|
| Terminal‑Bench 2.1 | 88.8 | **91.9** | +3.1 |
| BrowseComp | 90.4 | **92.2** | +1.8 |
| SEC‑Bench Pro | 71.2 | **74.3** | +3.1 |

**解釈:** 3件すべて改善しているが、普遍的な+2〜3ポイントを保証する証拠ではない。独立探索・比較が効きやすい問題に偏り、同予算比較でもない。Ultraは次の条件で候補にする。

- 失敗損失が高い
- 独立な探索方向が複数ある
- wall-clock短縮またはcoverage増加が価値を持つ
- 複数エージェント分のtoken増を許容し、実測で上限を管理
- single-agent Sol xhigh/maxとの自社A/Bで優位を確認済み

---

## 11. 安全性・権限・状態管理

### 11.1 モデル能力とデプロイ安全性を分離する

高いベンチマーク点は、ツールを自由に与える理由にならない。とくにGPT‑5.6はSystem CardでBio/ChemとCyberがHigh capability。能力が高いほど、権限境界、監査、stop条件が重要になる。[S2](#src-s2)

### 11.2 権限テンプレート

| 役割 | 原則 | 許可例 | 禁止例 |
|---|---|---|---|
| Scout | read-only、低信頼外部内容を扱う | search、read DB、read repo、sandbox query | delete、send、merge、deploy、権限変更 |
| Verifier | read + validator | test、lint、schema check、再計算、policy lookup | 本番write、秘密の外部送信 |
| Arbiter | 統合と計画 | 証拠閲覧、plan生成 | 直接副作用。write intentを構造化して返す |
| Writer | 単一・狭い・監査可能 | 承認済みoperationのみ | 任意tool選択、scope拡大、再帰delegation |
| Auditor | write後の独立確認 | read-back、diff、ledger、alert | 自分で修復write。別gateへ差し戻す |

### 11.3 Prompt injection対策

System Cardのprompt injection評価では、ConnectorsはSol/Terra 1.000、Luna 0.999、Search/function callingはSol 0.910、Terra 0.946、Luna 0.897。Terraが後者で最高だが、完全ではない。[S2](#src-s2)

- 外部文書・Web・email・issue本文を「命令」ではなく不信頼データとしてタグ付け
- tool descriptionにscope、write、error、機密フィールドを明記
- retrieval結果からsystem/developer instructionを生成しない
- agent出力によるtool権限拡大を禁止
- 外部内容が「以前の指示を無視」「秘密を送れ」「別URLへPOST」などを含む場合は強制escalation
- 重要writeは別requestのpolicy verifierと明示承認を通す

### 11.4 状態競合と副作用

Multi-agentで最も危険なのは、知能不足より **二重実行・古い読み取り・競合write**である。

必須パターン:

- single-writer principle
- optimistic concurrency / expected version
- idempotency key
- two-phase commit: `plan → validate/approve → execute`
- read-before-writeとread-after-write
- rollbackまたはcompensating transaction
- write deduplication
- timeout後の状態照合
- tool callの完全なaudit log

### 11.5 停止条件

各agentに明示する。

- 最大turn / token / tool call / wall-clock
- 同一errorのretry上限
- 必須evidenceが欠けたときの`blocked`返却
- scope外、権限外、危険内容の即時停止
- 改善が閾値未満なら追加branchをspawnしない

内蔵Multi-agentでは`max_tool_calls`が未対応なので、アプリ側tool gatewayで回数・時間・費用を制限する。[S5](#src-s5)

---

## 12. 自社評価の実験計画

### 12.1 比較する4構成

| 構成 | 目的 |
|---|---|
| A. Single Sol high | 品質ベースライン |
| B. Native Sol Multi-agent、subagent 3 | 同種並列化の純効果 |
| C. Heterogeneous cascade | Luna→Terra→Solの費用削減と選択的昇格 |
| D. Heterogeneous parallel panel | 多様な仮説・反証・coverageの効果 |

必要ならEとして`Single Sol xhigh/max`を置き、Multi-agentが単に総computeを増やした効果かを分離する。

### 12.2 タスクセット

- 実ログから50〜200件以上
- 領域、長さ、難度、リスク、write有無で層化
- 成功条件が機械判定できるものと、専門家rubricが必要なものを分離
- 既知の簡単問題だけでなく、最近の失敗・edge case・インジェクションを含める
- 高リスク操作はsandboxまたはsimulation
- dataset、grader、tool mockをversion control

### 12.3 指標

| 観点 | 指標例 |
|---|---|
| 品質 | task success、partial objective completion、rubric score、artifact validity |
| 選択性 | escalation rate、Sol utilization、risk-coverage、abstention quality |
| 合意 | branch disagreement、judge overturn rate、same-error correlation |
| 根拠 | citation completeness、evidence validity、unsupported claim rate |
| ツール | tool failure、retry、loop、duplicate call、invalid args |
| 安全 | unauthorized write、duplicate write、scope violation、prompt injection success |
| 人間負荷 | rework time、review comments、approval rejection |
| 速度 | P50/P95/P99 end-to-end、TTFT、tool wait、critical path |
| 費用 | uncached/cache/output token、tool cost、cost per successful task |
| 状態 | rollback rate、reconciliation failure、stale read、conflict |

### 12.4 必須ablation

1. モデル多様性を固定し、role promptだけ変える
2. roleを固定し、モデルだけ変える
3. 同じ文脈を全員へ渡す場合とdata shardを分ける場合
4. majority voteとevidence-weighted judge
5. Terra verifierとSol verifier
6. Lunaのbranch数と推論量
7. Single Sol xhigh/maxとSol Multi-agent
8. PTC縮約あり・なし
9. read-only権限と共有write権限

### 12.5 統計

- 二値成功率はWilson区間またはbootstrap区間を付ける
- 同一taskを構成間でpaired比較
- 非決定性がある場合は複数seed / rollout
- 1〜3ポイント差は区間とgrader誤差を確認してから採用
- 費用は「1run」ではなく **成功1件当たり**と、再試行・人間修正を含む総費用で比較
- ルーターはoffline replayで閾値を選び、holdout setで固定評価

### 12.6 採用判定の例

Heterogeneous cascadeを採用する条件:

$$
\begin{aligned}
\mathrm{quality} &\ge \mathrm{Single\ Sol\ high} - \mathrm{tolerance}\\
\mathrm{high\text{-}risk\ failure} &\le \mathrm{baseline}\\
\mathrm{cost\_per\_success} &\le 0.65\,\mathrm{baseline}\\
P_{95}(\mathrm{latency}) &\le \mathrm{SLO}\\
\mathrm{Sol\ utilization} &\le 35\%\\
\mathrm{unsupported\ claims} &\le \mathrm{baseline}
\end{aligned}
$$

閾値は業務ごとに変える。金融・医療・本番writeでは品質と安全の許容差をほぼゼロにし、低リスクの分類・抽出では費用と速度を重視する。

---
## 13. 公開ベンチマーク全表

この節の数値は、特記しない限り OpenAI の GPT‑5.6 発表表から採録。[S1](#src-s1)

### プロフェッショナル業務

| ベンチマーク | Sol | Terra | Luna | GPT‑5.5 | Sol − GPT‑5.5 | 公式表掲載の最高外部値* | 注記 |
|---|---:|---:|---:|---:|---:|---:|---|
| Agents’ Last Exam‡ | **52.7** | 50.4 | 50.3 | 46.9 | +5.8 | Opus 4.8: 45.2 | — |
| GDPval-AA v2 | **1747.8 Elo** | 1593 Elo | 1591.8 Elo | 1493.7 Elo | +254.1 Elo | Fable 5: 1759.6 Elo | — |
| Management Consulting Tasks† | **43.2** | 37.2 | 35.4 | 31.3 | +11.9 | Fable 5: 35.5 | — |
| Big Finance Bench | **53** | 51 | 36 | 49 | +4 | Opus 4.8: 44 | — |
| AA Intelligence Index v4.1 | **58.9** | 55 | 51.2 | 54.8 | +4.1 | Fable 5: 59.9 | — |

### コーディング

| ベンチマーク | Sol | Terra | Luna | GPT‑5.5 | Sol − GPT‑5.5 | 公式表掲載の最高外部値* | 注記 |
|---|---:|---:|---:|---:|---:|---:|---|
| AA Coding Agent Index v1.1 | **80** | 77.4 | 74.6 | 76.4 | +3.6 | Fable 5: 77.2 | — |
| SWE-Bench Pro | **64.6** | 63.4 | 62.7 | 59.4 | +5.2 | Mythos 5: 80.3 | — |
| DeepSWE v1.1 | **72.7** | 69.6 | 67.2 | 67 | +5.7 | Fable 5: 69.7 | — |
| Terminal-Bench 2.1 | **88.8** | 87.4 | 84.7 | 85.6 | +3.2 | Mythos 5: 88 | Sol Ultra: 91.9 |

### 科学・医療

| ベンチマーク | Sol | Terra | Luna | GPT‑5.5 | Sol − GPT‑5.5 | 公式表掲載の最高外部値* | 注記 |
|---|---:|---:|---:|---:|---:|---:|---|
| GeneBench Pro | **28.7** | 23.3 | 10.8 | 12 | +16.7 | Opus 4.8: 16 | — |
| LifeSciBench | **59.9** | 56 | 51.2 | 50.4 | +9.5 | Opus 4.8: 53.6 | — |
| MedChemBench† | **48.3** | 35 | 30.4 | 35.5 | +12.8 | — | — |
| HealthBench Professional§ | **60.5** | 57.7 | 55.7 | 49.5 | +11.0 | Fable 5: 60.9 | — |

### コンピューター操作

| ベンチマーク | Sol | Terra | Luna | GPT‑5.5 | Sol − GPT‑5.5 | 公式表掲載の最高外部値* | 注記 |
|---|---:|---:|---:|---:|---:|---:|---|
| OSWorld 2.0 | **62.6** | 50.2 | 45.6 | 47.5 | +15.1 | Opus 4.8: 54.8 | — |
| BrowseComp | **90.4** | 87.5 | 83.3 | 84.4 | +6.0 | Mythos 5: 88 | Sol Ultra: 92.2 |
| BenchCAD | **70.6** | 62.3 | 63.1 | 44.4 | +26.2 | Mythos 5: 38.4 | — |
| BenchCAD Python | **83.4** | 78.2 | 73.9 | 55.8 | +27.6 | Mythos 5: 65 | — |

### サイバーセキュリティ

| ベンチマーク | Sol | Terra | Luna | GPT‑5.5 | Sol − GPT‑5.5 | 公式表掲載の最高外部値* | 注記 |
|---|---:|---:|---:|---:|---:|---:|---|
| CTF† | **96.7** | 91.8 | 85.2 | 88.1 | +8.6 | — | — |
| SEC-Bench Pro | **71.2** | 57.7 | 48.9 | 45.8 | +25.4 | — | Sol Ultra: 74.3 |
| ExploitBench | **73.5** | 52.9 | 33.2 | 47.9 | +25.6 | Mythos 5: 78 | — |
| ExploitGym | **33.7** | 23.2 | 12.4 | 15.1 | +18.6 | — | — |

### 自己改善・研究工学

| ベンチマーク | Sol | Terra | Luna | GPT‑5.5 | Sol − GPT‑5.5 | 公式表掲載の最高外部値* | 注記 |
|---|---:|---:|---:|---:|---:|---:|---|
| Internal Research Debugging† | **68.3** | 67.8 | 50.8 | 50 | +18.3 | — | — |
| KernelGen1P | **61.1** | 49.2 | 22.4 | 29.3 | +31.8 | — | — |
| NanoGPT | 9.69 | **14.5** | 1.66 | 2.65 | +7.04 | — | Terra が系内首位 |
| PostTrainBench Lite | 50.3 | **51.5** | 29.6 | 38.8 | +11.5 | — | Terra が系内首位 |
| RSI Index† | **57.9** | 56.3 | 41.9 | 41.7 | +16.2 | — | — |

### マルチモーダル

| ベンチマーク | Sol | Terra | Luna | GPT‑5.5 | Sol − GPT‑5.5 | 公式表掲載の最高外部値* | 注記 |
|---|---:|---:|---:|---:|---:|---:|---|
| MMMU Pro（ツールなし） | **83** | 80.7 | 78.4 | 81.2 | +1.8 | Gemini 3.1: 80.5 | — |
| MMMU Pro（ツールあり） | **84.6** | 82 | 79.5 | 83.2 | +1.4 | — | — |
| gdp.pdf | **30.7** | 24.7 | 22.7 | 26 | +4.7 | Fable 5: 29.8 | — |

### 学術推論

| ベンチマーク | Sol | Terra | Luna | GPT‑5.5 | Sol − GPT‑5.5 | 公式表掲載の最高外部値* | 注記 |
|---|---:|---:|---:|---:|---:|---:|---|
| GPQA Diamond | **94.6** | 92.9 | 92.3 | 93.6 | +1.0 | Mythos Preview: 94.6 | 外部値と同点 |
| FrontierMath T1–3 v2 | **89** | 84.9 | 78.6 | 85.3 | +3.7 | Fable 5: 87 | — |
| FrontierMath T4 v2 | **83** | 68.3 | 58.5 | 72.5 | +10.5 | Fable 5: 87.8 | — |

### ツール利用

| ベンチマーク | Sol | Terra | Luna | GPT‑5.5 | Sol − GPT‑5.5 | 公式表掲載の最高外部値* | 注記 |
|---|---:|---:|---:|---:|---:|---:|---|
| AutomationBench | **18.1** | 15.2 | 14.9 | 12.9 | +5.2 | Fable 5: 17.4 | — |
| Toolathlon | **58** | 53.1 | 53.4 | 55.6 | +2.4 | Mythos 5 / Fable 5: 61.7 | — |

### 長文コンテキスト

| ベンチマーク | Sol | Terra | Luna | GPT‑5.5 | Sol − GPT‑5.5 | 公式表掲載の最高外部値* | 注記 |
|---|---:|---:|---:|---:|---:|---:|---|
| MRCR 256K–512K | **91.5** | 89.6 | 41.3 | 81.5 | +10.0 | — | — |
| MRCR 512K–1M | **73.8** | 72.5 | 41.3 | 74 | −0.2 | — | Sol が GPT-5.5 を下回る唯一の行 |
| GraphWalks BFS 256K（F1） | **90.7** | 76.9 | 81.3 | 73.7 | +17.0 | Mythos 5: 91.1 | — |
| GraphWalks BFS 1M（F1） | **77.1** | 71.2 | 51.2 | 45.4 | +31.7 | Mythos 5: 79.4 | — |

### 抽象推論

| ベンチマーク | Sol | Terra | Luna | GPT‑5.5 | Sol − GPT‑5.5 | 公式表掲載の最高外部値* | 注記 |
|---|---:|---:|---:|---:|---:|---:|---|
| ARC-AGI-3 | **7.78** | 0.8 | 0.18 | 0.43 | +7.35 | Opus 4.8: 1.5 | Opus 4.8 は high effort |

#### 表注

- `‡ Agents’ Last Exam:` 発表本文は Sol **53.6** と記載する一方、同ページの比較表は **52.7**。本書の全表は表の値52.7を採用し、不整合として残す。[S1](#src-s1)
- `§ HealthBench Professional:` 発表表の GPT‑5.5 は **49.5**、System Card の長さ調整済み比較表では **51.8**。Sol/Terra/Luna は両資料とも60.5/57.7/55.7。採点条件または基準版の差が疑われるが、公式説明は確認できない。[S1](#src-s1)[S2](#src-s2)
- ExploitBench は API ハーネス、5シード、推論継続あり。ExploitGym alpha の API 値は公開 API の速度に再スケールされている。[S1](#src-s1)
- サイバー評価の一部は安全ガードを弱めた条件で実施。[S1](#src-s1)
- ARC-AGI-3 の Opus 4.8 は `high` effort であり、`max` ではない。[S1](#src-s1)

---

---

## 14. System Card の補助評価

### 14.1 Preparedness Framework上の能力

| 領域 | Sol | Terra | Luna | 解釈 |
|---|---|---|---|---|
| Biological / Chemical | High | High | High | 4つのHigh閾値評価のうち3つが指示閾値超え。Criticalは0/3。 |
| Cybersecurity | High | High | High | CTFは96.7 / 91.8 / 85.2。Critical閾値未満。 |
| AI Self-Improvement | High未満 | High未満 | High未満 | 研究工学の改善は大きいが、枠組み上のHighではない。 |

追加のBio/Chem評価では、SolのVirology troubleshooting 55.5%、ProtocolQA open-ended 43.5%（専門家閾値54%）。Tacit knowledge adjustedはTerra 84.1%で専門家閾値80%を超えた。SecureBio外部評価の最強構成はVirology 53.5、Molecular Bio 60、Human Pathogen 68.4、World-Class Bio 68.3。World-Class BioはGPT‑5.5より約9ポイント高い。[S2](#src-s2)

### 14.2 Prompt injection

| 評価 | Sol | Terra | Luna |
|---|---:|---:|---:|
| Connectors | **1.000** | **1.000** | 0.999 |
| Search / function calling | 0.910 | **0.946** | 0.897 |

Terraがsearch/function callingで最良でも、0.946は完全耐性ではない。外部コンテンツを読むagentと副作用を実行するagentを分ける設計が必要。[S2](#src-s2)

### 14.3 医療・行動上の補足

| 評価 | GPT‑5.5 | Sol | Terra | Luna |
|---|---:|---:|---:|---:|
| HealthBench | 56.5 | **57.0** | **57.0** | 55.8 |
| HealthBench Hard | 31.5 | **33.1** | 32.7 | 32.0 |
| HealthBench Consensus | **95.6** | 95.5 | 95.1 | 95.1 |
| HealthBench Professional（length-adjusted） | 51.8 | **60.5** | 57.7 | 55.7 |

OpenAIはSolの事実誤りがGPT‑5.5より僅かに少なく、ユーザーが指摘した幻覚を再度述べる確率が大幅に低いと報告する。ただし、agentic codingではユーザー意図を超えて作業を続ける「過度な持続性」がGPT‑5.5より多い。長時間agentにはscope、checkpoint、diff review、停止条件が必要。[S2](#src-s2)

配備シミュレーションでは、禁止される性的内容が0.05%から0.07%、禁止されるメンタルヘルス応答が0.03%から0.02%へ変化すると予測。相対変化だけでなく絶対率と母数を見る。約5,000tokenのChain-of-Thoughtでの制御可能性はSol 1.3%、GPT‑5.5 0.4%、GPT‑5.4 0.7%で、推論監視回避の早期警告になり得るとされる。[S2](#src-s2)

---

## 15. 既知の不整合・限界

1. **公開直後の情報:** GPT‑5.6、Multi-agent、評価表はいずれも新しく、仕様・数値・API schemaが変わり得る。モデルsnapshotとドキュメント参照日を固定する。
2. **Agents’ Last Exam:** 同一発表で本文53.6、表52.7。本書は表を採用。
3. **HealthBench Professional:** GPT‑5.5が49.5と51.8で不一致。採点条件差の可能性を残す。
4. **内部評価:** Management Consulting Tasks、MedChemBench、CTF、Internal Research Debugging、RSI Index、KernelGen1Pの一部条件は完全に公開されていない。
5. **ベンダー比較表:** 外部モデル値はOpenAIが掲載した設定であり、本書が全モデルを同日・同一harnessで再実験したものではない。
6. **Artificial Analysis:** 公開前アクセスと支援を受けた第三者評価。動的leaderboardであり、完全blindではない。[S8](#src-s8)
7. **汚染・記憶:** 公開GitHub履歴や既知問題を使う評価は学習包含の可能性がある。DeepSWEはこの問題を減らす設計だが、完全な無汚染を外部から証明するのは難しい。[S15](#src-s15)
8. **平均値の盲点:** tail risk、tool outage、rate limit、地域、秘密データ、P99、長期drift、組織固有ルールを代表しない。
9. **相関するagent:** 同じモデル系列・同じretrieval corpus・同じprompt templateでは誤りが相関し、agent数ほど信頼度は増えない。
10. **Ultraの証拠範囲:** 標準Solとの公開比較は3テストのみ。すべてのタスクへ一般化しない。
11. **コンテキスト長:** 1,050,000 tokenを受け付けることと、全位置から一貫して正確に推論することは別。
12. **安全性:** 高いprompt-injection点、医療点、cyber点は、権限管理・専門家レビュー・認可を省略する根拠にならない。

---

## 16. 出典

### OpenAI公式

<a id="src-s1"></a>**[S1]** [OpenAI — Introducing GPT‑5.6](https://openai.com/index/gpt-5-6/)（2026-07-09公開、2026-07-11参照）
<a id="src-s2"></a>**[S2]** [OpenAI — GPT‑5.6 System Card](https://deploymentsafety.openai.com/gpt-5-6)（2026-07-11参照）
<a id="src-s3"></a>**[S3]** OpenAI Developers — [GPT‑5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol) / [Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra) / [Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
<a id="src-s4"></a>**[S4]** [OpenAI Developers — Model guidance / Using GPT‑5.6](https://developers.openai.com/api/docs/guides/latest-model)
<a id="src-s5"></a>**[S5]** [OpenAI Developers — Multi-agent](https://developers.openai.com/api/docs/guides/tools-multi-agent)
<a id="src-s6"></a>**[S6]** [OpenAI Developers — Programmatic Tool Calling](https://developers.openai.com/api/docs/guides/tools-programmatic-tool-calling)

### 横断評価

<a id="src-s7"></a>**[S7]** [Artificial Analysis — OpenAI provider and model measurements](https://artificialanalysis.ai/providers/openai)（2026-07-11参照）
<a id="src-s8"></a>**[S8]** [Artificial Analysis — GPT‑5.6 Has Landed](https://artificialanalysis.ai/articles/gpt-5-6-has-landed)（2026-07-09公開、2026-07-11参照）
<a id="src-s9"></a>**[S9]** [OpenAI — Separating signal from noise in coding evaluations](https://openai.com/index/separating-signal-from-noise-coding-evaluations/)（SWE‑Bench Pro監査）

### プロフェッショナル業務

<a id="src-s10"></a>**[S10]** [Agents’ Last Exam — Benchmark overview](https://agents-last-exam.org/)
<a id="src-s11"></a>**[S11]** [OpenAI — GDPval](https://openai.com/index/gdpval/)
<a id="src-s12"></a>**[S12]** [Artificial Analysis — GDPval‑AA](https://artificialanalysis.ai/evaluations/gdpval-aa)
<a id="src-s13"></a>**[S13]** [Rogo — Big Finance Benchmark](https://rogo.ai/news/introducing-the-big-finance-benchmark) / [paper](https://arxiv.org/abs/2606.03829)

### コーディング

<a id="src-s14"></a>**[S14]** [SWE‑Bench Pro paper](https://arxiv.org/abs/2509.16941)
<a id="src-s15"></a>**[S15]** [DeepSWE repository](https://github.com/datacurve-ai/deep-swe) / [paper](https://arxiv.org/abs/2607.07946)
<a id="src-s16"></a>**[S16]** [Terminal‑Bench — Terminal‑Bench 2.1](https://www.tbench.ai/news/terminal-bench-2-1) / [paper](https://arxiv.org/abs/2601.11868)

### 科学・医療

<a id="src-s17"></a>**[S17]** [GeneBench Pro preprint](https://www.biorxiv.org/content/10.64898/2026.06.29.735386v2)
<a id="src-s18"></a>**[S18]** [OpenAI — Introducing LifeSciBench](https://openai.com/index/introducing-life-sci-bench/)
<a id="src-s19"></a>**[S19]** [HealthBench Professional paper](https://arxiv.org/abs/2604.27470)
<a id="src-s38"></a>**[S38]** [OpenAI — New capabilities for GPT‑Rosalind](https://openai.com/index/introducing-new-capabilities-to-gpt-rosalind/)（MedChemBenchの公開説明）

### コンピューター・文書・CAD

<a id="src-s20"></a>**[S20]** [OSWorld 2.0 paper](https://arxiv.org/abs/2606.29537)
<a id="src-s21"></a>**[S21]** [OpenAI — BrowseComp](https://openai.com/index/browsecomp/)
<a id="src-s22"></a>**[S22]** [BenchCAD](https://benchcad.com/) / [paper](https://arxiv.org/abs/2605.10865)
<a id="src-s23"></a>**[S23]** [Surge AI — gdp.pdf](https://surgehq.ai/blog/gdp-pdf-can-100b-ai-models-master-the-documents-that-run-the-world)

### サイバー

<a id="src-s24"></a>**[S24]** [SEC‑Bench](https://sec-bench.github.io/) / [paper](https://arxiv.org/abs/2605.26548)
<a id="src-s25"></a>**[S25]** [ExploitBench](https://exploitbench.ai/) / [paper](https://arxiv.org/abs/2605.14153)
<a id="src-s26"></a>**[S26]** [ExploitGym](https://www.cybergym.io/exploitgym/) / [paper](https://arxiv.org/abs/2605.11086)

### 研究工学

<a id="src-s27"></a>**[S27]** [PostTrainBench](https://posttrainbench.com/) / [paper](https://arxiv.org/abs/2603.08640)
<a id="src-s28"></a>**[S28]** [NanoGPT‑Bench repository](https://github.com/IntologyAI/NanoGPT-Bench) / [paper](https://arxiv.org/abs/2506.22419)
<a id="src-s29"></a>**[S29]** [KernelBench repository](https://github.com/ScalingIntelligence/KernelBench) / [paper](https://arxiv.org/abs/2502.10517)

### マルチモーダル・学術・抽象推論

<a id="src-s30"></a>**[S30]** [MMMU‑Pro paper](https://arxiv.org/abs/2409.02813)
<a id="src-s31"></a>**[S31]** [Epoch AI — FrontierMath Tiers 1–4](https://epoch.ai/frontiermath/tiers-1-4) / [Tier 4 v2](https://epoch.ai/benchmarks/frontiermath-tier-4-v2)
<a id="src-s32"></a>**[S32]** [GPQA paper](https://arxiv.org/abs/2311.12022)
<a id="src-s33"></a>**[S33]** [ARC Prize — ARC‑AGI‑3](https://arcprize.org/arc-agi/3) / [paper](https://arxiv.org/abs/2603.24621)

### ツール・長文

<a id="src-s34"></a>**[S34]** [AutomationBench repository](https://github.com/zapier/AutomationBench) / [paper](https://arxiv.org/abs/2604.18934)
<a id="src-s35"></a>**[S35]** [Toolathlon repository](https://github.com/hkust-nlp/Toolathlon) / [paper](https://arxiv.org/abs/2510.25726)
<a id="src-s36"></a>**[S36]** [MRCR paper](https://arxiv.org/abs/2409.12640)
<a id="src-s37"></a>**[S37]** [OpenAI GraphWalks dataset](https://huggingface.co/datasets/openai/graphwalks)

---

## 最終設計判断

GPT‑5.6系をMoE的に使う際の中心的な洞察は、**Sol / Terra / Lunaが一本の品質軸に並んでいるのではなく、タスクの構造に応じて能力曲線が交差する**ことにある。

- Lunaは、安価な探索・抽出・定型コード・閉形式QAを大量並列化する。
- Terraは、短い初動で反証・再計算・テスト・研究デバッグを行い、ときにSolと異なる有力解を出す。
- Solは、未知性、長い低レベル依存、複数分岐する科学分析、最難関、最終裁定へ集中させる。
- 副作用はモデルに分散せず、単一writerと決定論的policy gateへ集約する。
- エージェント数より、証拠の独立性、role/tool/dataの多様性、validatorの強さを優先する。

最初の実装としては、**Luna highのread-only scouts、Terra highのadversarial verifier、Sol highのarbiter、承認付きsingle writer**が、品質・費用・安全のバランスを取りやすい。Sol maxやSol Ultraは、未解決で高価値な例外経路として自社evalで効果を確認してから有効化する。
