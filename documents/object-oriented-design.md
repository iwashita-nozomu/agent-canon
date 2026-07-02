<!--
@dependency-start
contract design
responsibility Documents オブジェクト指向設計方針 for this repository.
upstream design ./README.md documents index and discovery path
upstream design ./SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ./coding-conventions-house-style.md shared implementation style contract
upstream design ./coding-conventions-python.md Python convention entrypoint
upstream design ./design/protocols.md Protocol and type-boundary placement contract
downstream implementation ../tools/oop/python/readability.py Python OOP readability score gate
downstream implementation ../tools/oop/cpp/readability.py C++ OOP readability score gate
downstream implementation ../tools/oop/python/rule_inventory.py inventories Python OOP rule surfaces
downstream implementation ../tools/oop/cpp/rule_inventory.py inventories C++ OOP rule surfaces
downstream implementation ../tools/catalog.yaml records OOP tool catalog status
downstream implementation ../tools/agent_tools/tool_catalog.py validates OOP catalog entries
upstream implementation ../tools/sync_agent_canon.sh root symlink view generation
@dependency-end
-->

# オブジェクト指向設計方針

この文書は、agent-canon が共有する OOP 的な設計判断の正本です。
特定言語の syntax ではなく、責務、状態、契約、拡張点をどの単位に置くかを固定します。
Python 固有の型注釈、命名、`Protocol` 配置は
[Python コーディング規約](./coding-conventions-python.md) と
[Protocol 設計](./design/protocols.md) を併読します。

## この文書の読み方

この文書は、class を増やすためではなく、責務、状態、契約、拡張点の境界を決めるための OOP 方針です。まず要約と SOLID との対応で判断語彙を確認し、規約で class 作成条件、責務境界、状態、公開面、継承、composition を読みます。禁止事項、機械評価、Finding から Decision への triage、例外は、checker finding や設計 review の扱いを決めるときに使います。

## 要約

- OOP は class を増やす技法ではなく、責務と契約の境界を明示するために使います。
- まず関数、値オブジェクト、既存 `Protocol`、既存 class を再利用し、新しい class は最後に追加します。
- 状態を持たない処理は class にせず、関数または focused module-level helper に保ちます。
- helper は極力、使う関数の内側へ局所内包します。public / module-level helper は domain の射として読める名前と型を持つ場合だけ許可します。
- 不変の設定、結果、通知は `@dataclass(frozen=True)` などの値オブジェクトで表します。
- 差し替え境界は具象 class ではなく、最小の振る舞い契約で受けます。
- 継承は契約の特殊化に限定し、実装共有のための深い継承階層を禁止します。
- composition を既定にし、所有する部品と lifecycle を明示します。
- `None` を渡して内部で runtime 分岐する設計より、型、値オブジェクト、`Protocol`、`Optional` を外した別 entrypoint、または variant boundary で静的解析へ委譲します。

## SOLID との対応

SOLID は、この文書の責務、状態、契約、公開面の規約をレビュー時に並べ替える見出しとして扱います。
機械 checker は finding kind を SOLID principle signal へ投影し、Markdown / JSON report に集計を出します。
投影の正本は `tools/oop/shared/readability_core.py` の `SOLID_PRINCIPLES_BY_KIND` です。

- Single responsibility: 曖昧名、state 過多、副作用混在、不要 wrapper、責務語彙の広がりを同じ責務境界の risk として読む。
- Open/closed: `Optional` / `None` / `nullptr` routing や深い分岐を、variant や entrypoint の増設で表す候補として読む。
- Liskov substitution: base class 過多を、置換可能な契約として読める継承かどうかの確認対象にする。
- Interface segregation: public method / field / parameter 過多を、利用側が必要とする最小契約へ分ける候補として読む。
- Dependency inversion: public annotation 欠落や `Optional` 境界を、具象詳細へ寄りすぎた抽象境界の risk として読む。

SOLID signal は設計レビューの入口です。最終判断では機械 finding の `path:line`、OOP dimension、周辺 contract、既存例外規約を併読します。

| Principle | Source-informed meaning | Local implementation contract | Static risk route |
|---|---|---|---|
| Single responsibility | change reason / change actor で責務を切る。 | class / function / module の主語を 1 つの責務語彙に固定し、計算、IO、persistence、rendering、orchestration、reporting を分ける。 | `mixed_morphism_effect`、`vague_class_name`、`module_helper_bucket`、`instance_attributes`、`public_methods` |
| Open/closed | 安定した policy を extension point で拡張可能にする。 | 予測済み variant は branch cascade ではなく `Protocol`、registry、adapter、variant value、別 entrypoint へ置く。 | `none_runtime_branch`、`null_runtime_branch`、`optional_boundary`、`cognitive_complexity` |
| Liskov substitution | subtype は supertype の証明済み性質を保存する。 | 継承は置換可能な契約の特殊化に限定し、入力条件、戻り値、例外、invariant、history property を保存する。 | `base_classes` と type checker / shared behavior contract |
| Interface segregation | client は使う role contract だけへ依存する。 | fat Protocol / ABC / class surface を caller role ごとの role-specific contract に分ける。 | `public_methods`、`public_fields`、`parameters` |
| Dependency inversion | high-level policy と low-level detail は stable abstraction に依存する。 | composition root / factory / adapter で具象生成を閉じ、policy layer は `Protocol`、typed value、stable interface を受ける。 | OOP primary signal は `missing_public_annotations` と `optional_boundary`。import / layer 方向は `import_responsibility.py` と dependency review の supporting evidence |

この表は Martin の SOLID 系 article、Liskov/Wing の behavioral subtyping、
Parnas の information-hiding modularity、Python の PEP 544 Protocol から得た
設計語彙を、AgentCanon の operational guidance と static risk signal に写像したものです。
checker は semantic proof ではなく静的な risk signal を出し、review は source contract、
caller graph、design artifact と合わせて判断します。

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
共通処理は helper function、composition された component、または focused value object へ切り出します。

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
- 合成可能な focused 変換を作り、巨大な手続きで複数の射を隠さない。
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

OOP 的な可読性は reviewer の判断を必要としますが、危険な形は機械的な signal として先に報告します。
Python surface では次を baseline として使います。

```bash
python3 tools/oop/python/readability.py python tools tests --min-score 95
python3 tools/oop/python/rule_inventory.py
```

C++ surface では次を baseline として使います。

```bash
python3 tools/oop/cpp/readability.py include src tests/cpp --min-score 95
python3 tools/oop/cpp/rule_inventory.py
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

Markdown / JSON report は、上記 finding を SOLID principle signal としても集計します。
この集計は reviewer が risk を Single responsibility、Open/closed、Liskov substitution、Interface segregation、Dependency inversion の見出しで読むための機械分類です。

C++ checker は schema / DTO / config / metrics などの named aggregate value
object、annotated primitive ABI / `__nad_` exported ABI function、式 DSL の
terminal identity morphism、compact numeric scalar wrapper を意図的な境界として扱います。
これらの許容は `documents/tools/oop/cpp/readability.md` に固定し、behavior を持つ
public state owner や domain contract のない wrapper の finding とは区別します。

score は設計判断の補助であり、pass / fail の主判定ではありません。
`OOP_READABILITY` は error / gate / review の signal class で決めます。
`public_methods`、`parameters`、`instance_attributes`、`public_fields`、
`cognitive_complexity` のような surface / control-flow finding は boundary
review signal として扱い、数値だけで split / extract を要求しません。
`--min-score 0` は survey 用に finding を出し切る pass mode として扱い、
default は signal 判定を使います。明示的に default より高い score floor を
指定した場合だけ strict score gate として扱います。分割は caller contract、
state ownership、既存責務語彙、または周辺 source shape から安定した境界が
読める場合だけ行います。
`OOP_READABILITY=pass` は behavior correctness や設計妥当性を保証しません。
重要な変更では、機械 report の status、count、path、line を正本にします。

```bash
python3 tools/oop/python/readability.py \
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

OOP policy、analyzer、reviewer、test の配置確認は、言語別の
`tools/oop/python/rule_inventory.py` と `tools/oop/cpp/rule_inventory.py`
を使います。旧 `tools/legacy/` provenance は廃止済みであり、workflow や
CI の正本入口には戻しません。canonical analyzer と inventory の tool
status は `tools/catalog.yaml` に記録し、`tool_catalog.py` の検査対象にします。

`oop_readability_reviewer` は `oop_readability_report.md` を読み、score、threshold、count、path、line、pass/fail を変えずに文書化します。
false positive / allowed warning は reviewer の推測ではなく、機械 finding に `path:line` で紐づけて design artifact に書きます。

## Finding から Decision への Triage

`tools/oop/*/readability.py` の finding は、chat の感想や自動 backlog 化で終わらせず、次の decision へ triage します。機械 finding は signal であり、境界変更、split、extract の指示ではありません。

- boundary change with evidence: caller contract、state ownership、domain vocabulary、effect boundary、validated decision point、または stable reusable behavior がある場合だけ境界を変える。
- flatten / name decision while keeping code contiguous: `cognitive_complexity` は、分岐意味の命名や flatten で読めるなら、新しい helper や class を増やさず同じ source region に保つ。
- inline / delete wrapper: `identity_function`、`pass_through_function`、`trivial_format_function` は、domain contract が無ければ削除または caller へ inline する。
- accept as intentional boundary: value object、adapter、ABI、framework contract、DSL terminal など、周辺 contract が境界の意図を説明する場合は許容する。
- false positive: test-only organization、generated shape、typed protocol、schema / DTO など、checker の静的 heuristic が設計 intent を読めない場合は false positive として記録する。
- defer with rationale: 呼び出し contract、ownership、validation が足りない場合は、予定する境界変更を書かず、必要な evidence と owner を記録して defer する。

decision record には、少なくとも `path:line`、finding kind、tool fact、agent judgment、選んだ outcome、根拠、validation または defer 理由を含めます。
機械 finding を許容する場合も、許容理由を design artifact か run bundle に残し、score を改善した事実と混同しません。

## 例外

- CLI entrypoint や短い運用 script では、class 化せず関数で閉じてよいです。
- 外部 framework が class-based interface を要求する場合は、その adapter class を許可します。ただし domain logic は adapter へ閉じ込めず、既存の関数、値オブジェクト、service layer に委譲します。
- performance-critical path では、allocation を避けるために tuple や array を使うことを許可します。ただし public 境界では意味のある型名または docstring で契約を説明します。
