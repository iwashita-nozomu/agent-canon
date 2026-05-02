<!--
@dependency-start
responsibility Documents オブジェクト指向設計方針 for this repository.
upstream design ./README.md documents index and discovery path
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror ownership
upstream design ./coding-conventions-house-style.md shared implementation style contract
upstream design ./coding-conventions-python.md Python convention entrypoint
upstream design ./design/protocols.md Protocol and type-boundary placement contract
downstream implementation ../tools/agent_tools/analyze_oop_readability.py OOP readability score gate
upstream implementation ../tools/sync_agent_canon.sh root symlink view generation
@dependency-end
-->

# オブジェクト指向設計方針

この文書は、agent-canon が共有する OOP 的な設計判断の正本です。
特定言語の syntax ではなく、責務、状態、契約、拡張点をどの単位に置くかを固定します。
Python 固有の型注釈、命名、`Protocol` 配置は
[Python コーディング規約](./coding-conventions-python.md) と
[Protocol 設計](./design/protocols.md) を併読します。

## 要約

- OOP は class を増やす技法ではなく、責務と契約の境界を明示するために使います。
- まず関数、値オブジェクト、既存 `Protocol`、既存 class を再利用し、新しい class は最後に追加します。
- 状態を持たない処理は class にせず、関数または小さい module-level helper に保ちます。
- helper は極力、使う関数の内側へ局所内包します。public / module-level helper は domain の射として読める名前と型を持つ場合だけ許可します。
- 不変の設定、結果、通知は `@dataclass(frozen=True)` などの値オブジェクトで表します。
- 差し替え境界は具象 class ではなく、最小の振る舞い契約で受けます。
- 継承は契約の特殊化に限定し、実装共有のための深い継承階層を禁止します。
- composition を既定にし、所有する部品と lifecycle を明示します。
- `None` を渡して内部で runtime 分岐する設計より、型、値オブジェクト、`Protocol`、`Optional` を外した別 entrypoint、または variant boundary で静的解析へ委譲します。

## 規約

### 1. Class を作る条件

新しい class は、次のいずれかを満たす場合だけ追加します。

- 不変データに名前を与え、複数箇所で同じ意味として受け渡す。
- 変更可能な状態と、その状態を守る操作を 1 つの責務として閉じ込める。
- 外部リソース、process、session、connection の lifecycle を明示的に管理する。
- 複数の実装が同じ振る舞い契約を満たす必要がある。
- 既存 class または `Protocol` の特殊化として、domain の意味を明確にできる。

次の目的だけで class を作ってはなりません。

- 関数を名前空間にまとめたいだけ。
- 1 回しか使わない短い処理を「将来拡張できそう」という理由で包む。
- `self` を使わない static method の集合を作る。
- 既存関数や既存 dataclass で足りる処理を別名で再実装する。

### 2. 責務境界

1 つの class は、1 つの主責務だけを持たなければなりません。
入力検証、状態更新、永続化、通知、集計、表示を 1 class に詰め込むことを禁止します。
複数段階が必要な場合は、値オブジェクト、service function、writer、renderer、scheduler などに責務を分けます。

public method は class の責務語彙で命名します。
内部手順名、環境都合、暫定実装名を public method に出してはなりません。

### 3. Dataclass と値オブジェクト

設定値、結果、完了通知、検証済み入力のような値は、言語が提供する軽量な値オブジェクトで表します。
Python では `@dataclass(frozen=True)` を既定にします。

mutable object は、進行中の process state、cache、accumulator、resource handle のように更新責務が明確な場合だけ許可します。
mutable object を使う場合は、どの method が状態を変えるかを docstring または責務コメントで分かるようにします。
object は必要以上の member を抱えてはいけません。
member が増える場合は、値オブジェクト、state owner、adapter、service function へ分割できないかを先に確認します。

### 4. Protocol と抽象境界

呼び出し側が必要とする振る舞いだけを契約にします。
具象 class の全属性を `Protocol` に写してはなりません。
`Protocol` を追加する場合は、[Protocol 設計](./design/protocols.md) の条件を満たす必要があります。

実装側は、具象 class へ直接依存する前に、既存の `Protocol`、`TypeAlias`、typed dataclass で受けられないか確認します。
ただし、具象実装が 1 つしかなく、差し替え境界もない場合に `Protocol` を増やすことは禁止します。

### 5. Composition と継承

既定は composition です。
ある object が別 object を使う場合は、所有、借用、lifecycle、失敗時の責務を明確にします。

継承は次の場合に限定します。

- 契約または型 family の特殊化を表す。
- 親 class の public contract を壊さずに置換できる。
- 既存設計文書で継承関係が正本として固定されている。

実装共有だけを目的にした深い継承、mixin の多用、親 class の内部状態に依存する subclass を禁止します。
共通処理は helper function、composition された component、または小さい値オブジェクトへ切り出します。

### 6. 境界で検証する

constructor、factory、public method は入口で引数を検証します。
shape、dtype、path、resource availability、config の正規化は境界で一度だけ行います。
内部の深い処理で契約違反が偶然失敗する設計は禁止します。

契約違反の例外には、対象の引数名、期待条件、実際の値の分類を含めます。
ただし巨大 object や秘密値を例外 message に含めてはなりません。

### 7. Public API と公開面

public class、public dataclass、public `Protocol` は module docstring と `__all__` で公開面を固定します。
公開する class は docstring で責務、主要属性、主要 method、利用例を説明します。
内部 class は先頭 `_` を付け、外部から import される前提にしてはなりません。

### 8. 圏論的な読みやすさ

実装を厳密な圏論で証明する必要はありません。
ただし、読みやすい OOP 境界は「射」として読める必要があります。

- public function / method は、入力 domain、出力 codomain、失敗境界が型や名前から読める。
- 純粋な変換 `A -> B` と、IO / mutation / process 起動のような副作用境界を 1 つの関数に混ぜない。
- 合成可能な小さい変換を作り、巨大な手続きで複数の射を隠さない。
- `None` による runtime routing を domain の一部として曖昧にせず、別型、別 constructor、別 entrypoint、`Protocol`、variant で表す。
- helper は外へ増やすより、合成の内側でしか使わない局所関数や内包に閉じる。
- 数理的に情報を増やさない identity wrapper、pass-through wrapper、stateless callable class、薄い formatting wrapper は不要構造として扱います。
- 表示用 formatting は domain contract を持つ presentation boundary の場合だけ関数化し、単なる `str(x)` / f-string / `to_string(x)` の包み直しは避けます。

## 禁止事項

- class を単なる namespace として使うことを禁止します。
- `Manager`、`Helper`、`Util`、`Thing` のように責務が読めない class 名を public API に使うことを禁止します。
- `helper`、`util`、`misc` のような責務不明名を module-level public function に使うことを禁止します。
- 継承で実装都合を共有し、置換可能性を説明しないことを禁止します。
- `Protocol` を具象 class の属性一覧として複製することを禁止します。
- mutable state を持つ object を、更新責務や lifecycle なしに広く共有することを禁止します。
- 必要以上の member を object に抱え込み、値オブジェクトや state owner へ分けられる責務を残すことを禁止します。
- `None` sentinel を渡して内部 runtime 分岐で意味を変える public boundary を禁止します。型で表現できる場合は型で表現します。
- 旧 class 名と新 class 名を互換 alias で併存させることを禁止します。
- test double のためだけに production `Protocol` を増やすことを禁止します。

## 機械評価

OOP 的な可読性は reviewer の判断を必要としますが、危険な形は機械的に先に落とします。
Python / C++ surface では次を baseline として使います。

```bash
python3 tools/agent_tools/analyze_oop_readability.py python include src tests --min-score 85
```

この tool は次の risk を検出します。

- `Manager`、`Helper`、`Util`、`Thing` のような責務不明 class 名。
- 長すぎる function / class、public method 過多、引数過多。
- Python の instance attribute 過多、static method だけの namespace class、module-level helper bucket、public annotation 欠落。
- Python の `Optional` / `None` runtime 分岐、純粋変換と副作用の混在。
- C++ の public field 過多、base class 過多、巨大 function / class、`nullptr` runtime 分岐。
- control-flow が深く、人間が追う負荷が高い function。
- 数理的に不要な identity function、pass-through function、stateless callable class。
- domain contract を足さない trivial formatting function。

score は設計判断の補助です。
`OOP_READABILITY=pass` は behavior correctness や設計妥当性を保証しません。
重要な変更では、機械 report を正本にします。

```bash
python3 tools/agent_tools/analyze_oop_readability.py \
  --format markdown \
  --include-snippets \
  --exclude vendor \
  --exclude reports \
  --review-prompt-out reports/agents/<run-id>/oop_readability_reviewer_prompt.md \
  python include src tests \
  > reports/agents/<run-id>/oop_readability_report.md
```

外部 repo、bare repo snapshot、派生 template を読み取り専用で評価する場合は、commit SHA、展開方法、解析 path、除外 path を report と同じ run bundle に残します。
`vendor/`、過去の `reports/`、生成物、別 canon snapshot を混ぜると、対象 repo の OOP risk と持ち込み artifact の risk が区別できなくなります。
除外した surface を後で評価する必要がある場合は、別 report として分けます。

`oop_readability_reviewer` は `oop_readability_report.md` を読み、score、threshold、count、path、line、pass/fail を変えずに文書化します。
false positive / allowed warning は reviewer の推測ではなく、機械 finding に `path:line` で紐づけて design artifact に書きます。

## 例外

- CLI entrypoint や短い運用 script では、class 化せず関数で閉じてよいです。
- 外部 framework が class-based interface を要求する場合は、その adapter class を許可します。ただし domain logic は adapter へ閉じ込めず、既存の関数、値オブジェクト、service layer に委譲します。
- performance-critical path では、allocation を避けるために tuple や array を使うことを許可します。ただし public 境界では意味のある型名または docstring で契約を説明します。
