<!--
@dependency-start
contract policy
responsibility Documents テスト規約（共通） for this repository.
upstream design ../design/semantic-responsibility-contract.md semantic responsibility allocation and verification ownership
downstream design ../../agents/skills/test-design.md consumes reproduction evidence without widening test admission
downstream design ../../agents/skills/pr-processing.md consumes Issue-linked reproduction evidence at publication
@dependency-end
-->

# テスト規約（共通）

この文書は、`tests/` 配下のテストと、バグ再現証拠の保存・参照・整理を対象にします。

## この文書の読み方

この文書は、test placement、unit test contract、contract-only wrapper gate、実行方法、想定解と標準出力ログ、pytest fixtures、乱数・大規模テスト、禁止事項を説明します。初めての作業では Source Basis とクイックリファレンスを読み、テスト追加時は配置と Unit Test Contract へ進みます。失敗診断や fixture 設計では実行方法、標準出力ログ、fixtures、乱数の章を確認します。

## Source Basis

この方針は、次の一次資料・公式資料を repo 方針へ翻訳したものです。

- pytest official docs:
  - <https://pytest.org/en/7.4.x/explanation/goodpractices.html>
  - <https://doc.pytest.org/en/latest/how-to/fixtures.html>
  - <https://pytest.org/en/8.1.x/how-to/parametrize.html>
- Python official `unittest` docs:
  - <https://docs.python.org/3/library/unittest.html>
- Google Testing Blog / Software Engineering at Google:
  - <https://testing.googleblog.com/2014/07/testing-on-toilet-dont-put-logic-in.html>
  - <https://testing.googleblog.com/2010/12/test-sizes.html>
  - <https://abseil.io/resources/swe-book/html/ch12.html>
- Wilson et al. 2014, "Best Practices for Scientific Computing":
  - <https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.1001745>
- Test design flexibility source packet:
- [references/test-design-flexibility.md](../../references/test-design-flexibility.md)

## 🚀 クイックリファレンス

**初めての場合**: まずこのセクションをお読みください

| 用途 | コマンド | 詳細 |
|---|---|---|
| **最初の pytest 実行** | `pytest tests/<subdir>/test_*.py -v` | → [実行方法](#4-実行方法) |
| **ユニットテスト作成** | bounded behavior example + 明示 expected | → [Unit Test Contract](#3-unit-test-contract) |
| **契約だけの wrapper** | static contract validation + canonical command evidence | → [Contract-Only Wrapper Gate](#32-contract-only-wrapper-gate) |
| **統合テスト設計** | 異なるレイヤー・複数ケース | → [分類](#2-配置と分類) |
| **エッジケーステスト** | 乱数 seed 固定 + 悪条件 | → [乱数](#7-乱数大規模テスト) |
| **テスト失敗の診断** | JSON ログを `tests/logs/` 確認 | → [実行方法](#4-実行方法) |

---

## 1. 対象と目的

- 対象は `tests/` 配下のテストです。
- 目的は、behavior を bounded、決定的、保守しやすい形で検証することです。
- 科学計算・数値コードでは、unit test、small smoke、reference comparison、
  task automation を組み合わせ、変更のたびに同じ検証を再実行できるようにします。

## 2. 配置と分類

- テストは `tests/` に集約します。
- 分類は次の通りです。
  - `tests/<package>/`: library / package 単位の unit test。
  - `tests/tools/`: repo script や補助 tool の test。
  - 外部 `experiment_runner` package 側の tests: 汎用 experiment runtime の test。
  - `tests/integration/`: package をまたぐ結合 test。
- 大規模ケースは `case` や `*_large` の名称で明示します。
- unit test は Google の small test 相当として扱います。つまり、狭い対象、
  fast、deterministic、order-independent を既定にします。
- 外部 process、network、GPU 長時間計算、large fixture、複数 subsystem の接続を
  前提にする場合は、unit test ではなく smoke / integration / experiment validation
  として明示します。

### 2.1 C++ test ownership

- derived project の C++ adapter/integration test source は `tests/cpp/` に置きます。
- `cpp/CMakeLists.txt` は `${ROOT}/tests/cpp` を source directory、
  `${CMAKE_CURRENT_BINARY_DIR}/tests/cpp` を binary directory として指定した
  out-of-tree `add_subdirectory` で `cpp-test-<name>` executable、`cpp-tests` aggregate、
  CTest registration を同じ configure graph へ接続します。
- AgentCanon runtime/template tests は AgentCanon の `tests/`、cppdev の数値・数学・NN
  oracle tests は cppdev の owning repository に置き、derived project の `tests/cpp/` に
  複製しません。production subtree には test compatibility path を作成しません。
- 各 individual test executable は `cpp-core` を consume します。`cpp-tests` は build
  grouping を提供し、CTest が execution と failure output を所有します。
- C++ test validation は同じ profile cache を使います。

```bash
cmake --build "$ROOT/build/cpp/<profile>" --target cpp-tests
ctest --test-dir "$ROOT/build/cpp/<profile>" --output-on-failure
```

### 2.2 Bug reproduction evidence

再現証拠を保存することと、新しい恒久回帰 test を採用することは別の判断です。
Issue を判断・経緯の入口、Git を必要な再現ソースの保存先にします。まず既存 test、
static checker、integration evidence の組み合わせが対象 failure を識別し、契約を
保証できるか確認します。十分なら新しい Issue 専用 test は要求せず、その根拠と
既存 validation の参照を Issue に残します。新規 test の admission は既存 owner に
従い、再現コードの有無や Issue 番号だけでは activation しません。

#### 保存先の選択

| 再現の形 | 保存・参照先 |
| --- | --- |
| 既存 test 基盤で再現・判定できる | 必要な case を既存の責務別 test に統合し、その case 自体を再現コードとする。既存 case で十分なら参照だけにする。 |
| 特殊な環境や操作が必要で通常 test に載せにくい | 所有 repository の既存 test root を使い、必要時だけ `tests/repro/issue-123/` 等に最小ソースと実行説明を置く。 |
| 既存コマンドだけで再現できる | 新しいソースや wrapper を作らず、Issue に対象 SHA、条件、コマンド、結果を残す。 |

`tests/repro/issue-123/` は必要時の配置例であり、既存 directory という主張や
一律の作成義務ではありません。consumer が `test/` または別の canonical 配置を
持つ場合はそれに従い、改名や第二の test root を要求しません。standalone repro は
通常 test discovery へ意図せず載せず、必要な環境と明示的な実行コマンドを README
等の一箇所に記録します。専用 runner、framework、registry は追加しません。

#### 再現・判定と Issue evidence

再現コードは問題の製品実装をコピーせず、実際の公開 API、CLI、build/compiler
entrypoint 等を呼びます。可能な限り同じ入力・同じ oracle を修正前後へ適用し、
期待する契約と対象 failure を区別します。単なる non-zero exit は再現成功では
ありません。依存取得失敗、環境不足、別の compile error、未実行は対象バグの再現や
修正確認と分け、確認できた範囲だけを報告します。

既存の Issue 本文または evidence comment に、次を一続きで残します。新しい
packet、台帳、固定 schema を作る必要はありません。

- repository-qualified Issue、対象製品コードの commit SHA、再現ソースの commit
  SHA とファイル固定リンクを区別する。既存 test が再現なら、その case を指す。
- 再現に影響する環境・依存 version、入力または取得手順、cwd と実行コマンド、
  期待結果と実結果を残す。別 SHA の再現ソースを使う場合は適用方法も明示する。
- 修正後に検証した exact SHA と同じ oracle の結果、継続的に保証する既存 test /
  checker / integration evidence、未検証範囲と理由を残す。

ファイルリンクは浮動する `main` / branch ではなく commit SHA 固定にします。
PR 未完成でも、再現ソースが得られた時点で Issue 番号入りの作業 branch に commit・
push し、完了報告や引継ぎの前に Issue から辿れるようにします。既存ソースや
コマンドだけで十分な場合は、このためだけの commit は作りません。
秘密情報・個人情報・大型実データ・生成ログを再現ソースとして commit せず、
最小の安全な入力、生成方法、または既存のアクセス制御された保存先を参照します。

#### 修正後の整理

恒久 test は Issue 番号ではなく保証する機能・性質の owner に配置します。
統合後に standalone repro を重複維持せず、Issue に元の固定リンクと統合先を残して
不要なコピーを削除します。特殊環境の再調査など独立した用途がある場合だけ、
保持理由と実行条件を残して維持します。未 merge の branch を唯一の保存先とする
場合は、branch を処分する前に必要なソースと参照を維持対象の履歴へ引き継ぎます。
履歴保存のために既知 failure を通常 CI へ恒久登録したり、skip / xfail を理由なく
残したりしません。検証不能時の status と publication は既存の GitHub lifecycle
owner に従い、証拠を保存しただけで修正検証済みとは扱いません。

## 2.5 Semantic responsibility test ownership

実装前に active design packet が参照する run-local semantic responsibility
contract で、delta の obligation と一次検証 owner を割り当てます。既存 test を
primary owner にする場合は、contract、changed mechanism、observable assertion、
decidable oracle、removal witness を一続きで記録します。supporting evidence は
異なる property または role の証拠に限ります。実装 mechanism の確立後にも
test-owned runtime risk が残る場合だけ `test_designer` を起動し、checker-owned
property や内部形状を test へ移しません。

## 3. Unit Test Contract

unit test は「1 つの観測可能 behavior に対する concrete example」です。
実装内部の call sequence や private helper の存在を固定するものではありません。
単に script、CLI、checker、import、compile、type check、format check が
exit code 0 で終わることだけを見る test は unit test ではありません。
その性質を static analysis / checker / CI gate が所有している場合は、
pytest wrapper を作らず、その checker を validation route に入れます。

変更耐性のある test design は、次の 8 軸を先に固定します。

- `Contract Source`: user request、approved design、documented external contract、public behavior、regression evidence のどれを根拠にするか。
- `Behavior Contract`: どの observable behavior、failure mode、diagnostic key を固定するか。
- `Observation Level`: unit、service/API、CLI、integration、acceptance のどこで見るか。
- `Observable Outcome`: expected value、exception class/category、documented public response shape、public state mutation、diagnostic key、public failure mode のどれを見るか。
- `Oracle`: literal expected、known reference、exception type、state change、property、metamorphic relation のどれか。
- `Input Space`: concrete regression、boundary table、random/property generator、metamorphic follow-up input のどれか。
- `Adequacy Evidence`: branch/edge coverage、mutation score、regression replay、manual review のどれで assertion の強さを確認するか。
- `Do Not Freeze`: private helper、internal call sequence、mock order、全文 error prose、stdout 全文一致など、public contract でない実装詳細を固定しない根拠。

### 3.1 数値テスト採用ゲート

数値テストは、変更の behavior contract が数値的な性質を持つ場合だけ追加します。
solver、optimizer、floating-point approximation、residual、tolerance、random sampling、
convergence、reference comparison、scientific experiment contract のどれにも関係しない
docs、routing、metadata、string parsing、configuration、structure refactor では、
数値 smoke、large random case、benchmark 風 test を追加しません。

この判断は `mathematical necessity gate` として扱います。数値または数理的な
判定・oracle・assertion は、`Numerical Trigger`、`Non-Numerical Alternative`、
checker-owned property、proof obligation、または approved design の acceptance
criterion に接続できる場合に採用します。

数値テストを提案する前に、test plan で次を固定します。

- `Numerical Trigger`: 数値テストが必要な具体的契約、既知 regression、acceptance
  criterion、または proof / experiment requirement。
- `Non-Numerical Alternative`: static contract、parser example、diagnostic key、
  property、metamorphic relation、snapshot で同じリスクをより bounded に検証できない理由。
- `Oracle`: closed-form value、known reference、invariant、residual bound、convergence
  flag など、production path と同じ bug を複製しない expected。
- `Budget`: unit test に置ける最小 dimension、固定 seed、fixture size、runtime。
- `Execution Target`: 数値計算、solver、optimizer、JAX / XLA / IREE lowering、
  convergence、residual、benchmark、experiment validation を実行する GPU target。
  CPU は計算テストの代替 target にしません。

`Numerical Trigger` がない場合は、数値テストを省きます。その場合も test plan には
「数値テストを省いた理由」と、代わりに固定する observable behavior を 1 行で残します。
数値 validation が必要でも、既定は GPU 上の最小 deterministic case です。
long-running、broad benchmark、large random sweep は unit test ではなく experiment
validation として profile、理由、ログ保存先を記録します。GPU backend で起動する
child は先に空き GPU slot を探索します。slot が得られない場合は
`gpu_validation_blocker=<reason>` と slot evidence を残します。CPU backend は
user request、runtime profile、または明示 env で固定された validation target として扱います。

### 3.2 Contract-Only Wrapper Gate

`contract-only wrapper` は、既存の public contract を名前付け、型付け、設定化、
薄い adapter 化、または canonical command へ接続するだけの変更です。入力 schema、
型境界、設定 key、documented entrypoint、dependency header、routing marker、
checker command のような static contract validation が主な evidence になります。

実行テストの admission 条件は、新しい observable behavior、branch、parser error path、
state mutation、diagnostic key、serialization shape、external process contract のいずれかです。
該当する条件がある場合は、Contract Source、Behavior Contract、Observation Level、
Observable Outcome、Oracle、Input Space、Adequacy Evidence、Do Not Freeze を test plan に
固定してから最小の behavior example を作ります。

contract-only wrapper の validation evidence は次のように固定します。

- type checker、lint、formatter、docs check、dependency review、convention checker、
  tool catalog、route-surface check の canonical command。
- `static-analysis-duplicate-test` や `meaningless-generated-execution-test` の
  finding がある既存 test は、削除、behavior regression への置換、
  canonical checker validation への移行を repair route として扱います。
- pytest smoke、execution-only test、no-crash test、exit-code wrapper、数値 smoke は
  該当 checker command の直接実行を validation route に置きます。
- SOLID / OOP boundary assertion は checker-owned property として扱います。
  Single responsibility、Open/closed、Liskov substitution、Interface segregation、
  Dependency inversion の risk は `$oop-readability-check`、
  `tools/validation/code/oop/python/readability.py` / `tools/validation/code/oop/cpp/readability.py`、
  `import_responsibility.py`、type checker、dependency review の evidence route に置きます。
  実行テストは observable behavior、shared behavior contract、または public API regression
  を固定する場合に限ります。

Validation repair scope は、changed contract、changed lines、または task plan が名指しした
checker-owned property に結び付く finding です。formatter、lint、test-design checker、
convention checker が既存 style debt や周辺 debt を表出した場合、その finding は residual
evidence として記録し、現在の diff は requested contract に沿った semantic change に保ちます。

Validation test/check が失敗した場合は、通すために intended behavior/test を削る、oracle を弱める、
必要な validation を縮める、または blanket revert で済ませることを禁止します。先に
`failing_contract`、`observation_level`、`cause_classification`、
`intent_preservation`、`evidence` を記録します。`cause_classification` と
`intent_preservation` の slug set と route semantics は
`documents/runtime/runtime-profiles-and-check-matrix.json` が所有します。
[documents/runtime/runtime-profiles-and-check-matrix.md](../runtime/runtime-profiles-and-check-matrix.md) は生成済み reader projection として
参照します。
`cause_classification=implementation_bug` で contract と oracle が安定している場合は、
追加 test planning で止めず owning code / config / docs / workflow repair へ進みます。

実装詳細に強く結合する test は、adapter 境界や protocol 境界を固定する場合だけ許可します。
private member、内部 call sequence、全文 error prose、stdout 全文一致を固定する場合は、
その対象が public contract である理由を test 名か test plan に残します。

parser、formatter、normalizer、serializer、graph builder、router、mapping では、
hand-picked example だけで終えず、契約に合う property / metamorphic relation を検討します。
例: round-trip、idempotence、ordering、preservation、equivalent-input relation。

必須方針:

- 新規 test を作る前に、その test が検証する性質を既存の static analysis、
  checker、formatter、dependency review、type checker、lint、docs check が
  既に所有していないか確認します。所有している場合は、test を生成せず、
  canonical command と evidence を validation に残します。
- 1 test は 1 behavior / 1 failure reason を主語にします。
- test 名は、対象 behavior と期待結果が読める名前にします。
- Arrange / Act / Assert を読み分けられる構造にします。
- expected value、exception class/category、documented public response shape、public state mutation、diagnostic key、public failure mode のどれを固定するかを明示します。
- test body で expected を計算する複雑な logic、loop、branch を増やしません。
  必要なら helper へ出し、非自明 helper は別途 test します。
- production と同じ bug を複製しうる derived expected は避け、literal、
  hand-computed value、small reference implementation、または domain invariant を
  expected として置きます。
- 乱数は固定 seed と bounded dimension を既定にします。
- どの順で実行しても通るようにし、前の test が残した state に依存しません。

許可される helper / fixture:

- 重複する Arrange を短くする helper。
- costly でない object construction を共有する pytest fixture。
- 同じ assertion shape で複数 explicit case を走らせる `pytest.mark.parametrize`。

禁止される helper / fixture:

- assertion の意味を隠す万能 fixture。
- production path と同じ計算で expected を作る helper。
- 1 つの test body に複数 behavior を混ぜるための branch / mode flag。

## 4. 実行方法

- **pytest を基本**にし、一括実行を標準とします。
- テストは `tests/` を対象に収集します。
- `if __name__ == "__main__":` による単体実行は **補助的に許可**します。
- 新規 test file に `_run_all_tests()` は要求しません。既存 file の補助実行を保つ場合だけ、
  `if __name__ == "__main__":` から pytest を呼ぶ薄い wrapper に留めます。

### 4.1 標準出力を表示する

- ファイル単位: `pytest -q -s tests/tools/test_run_managed_experiment.py`
- 全体: `pytest -q -s`

### 4.2 `python file.py` での補助実行

- どうしても単体で回したい場合は、`if __name__ == "__main__":` から `_run_all_tests()` を呼び出します。
- この補助実行で数値 experiment の結果を出す場合は、**計算結果は標準出力へ 1 行 JSON** で出力します。
- pytest fixture が必要な場合でも、`_run_all_tests()` から呼べる補助関数へ分離して両方から使えるようにします。

## 5. 想定解と標準出力ログ

- **想定解のあるテストは、必ず想定解を用意**します。
- unit test では、想定解は assertion に直接置きます。標準出力への出力は要求しません。
- experiment / benchmark / broad smoke では、想定解や結果を **標準出力に出力**し、
  結果と比較できるようにします。
- log を出す場合は、1 行 1 レコードの辞書出力を基本にします。

### 5.1 推奨キー

- `case`: テスト名
- `expected`: 想定値
- `actual`: 実測値
- `rel_err` / `abs_err`: 誤差
- `seed`: 乱数 seed
- `dim` / `m` / `s` / `g`: 条件

## 6. pytest Fixtures And Parametrization

- pytest fixture は、明示的に必要な test 関数の引数として使います。
- `autouse` fixture は、repo-wide 環境制御など明示的な理由がある場合だけ使います。
- fixture は Arrange を共有するためのものです。Act / Assert を fixture に隠しません。
- 同じ behavior を複数 input / expected で検証する場合は、
  copy-paste より `pytest.mark.parametrize` を優先します。
- case ごとに期待結果や failure mode が大きく違うなら、parametrize で分岐するより
  test を分けます。
- fixture や helper が非自明な計算を持つ場合は、その helper 自体を focused test で固定します。

## 7. 乱数・大規模テスト

- 乱数を使う場合は **固定 seed** を使用します。
- 悪条件・大規模ケースは **明示的に区別**し、ログに条件を出力します。
- unit test の既定 dimension は、failure を局所化できる最小サイズにします。
- GPU / long-running numerical validation は、unit test とは分けて profile と実行理由を記録します。
- 数値計算、solver、optimizer、JAX / XLA / IREE lowering、convergence、residual、
  benchmark、experiment validation の計算テストは GPU backend と slot evidence を
  validation record に残します。slot が得られない場合は `gpu_validation_blocker`
  を残します。CPU backend は明示 env / profile の時だけ validation target にします。

## 8. 禁止事項

- `test_runs`、`test_smoke`、`test_generated_*`、`test_can_run` などの名前で、
  process success、import success、no-crash、exit code 0 だけを見る generated
  placeholder test を追加しません。
- `py_compile`、`compileall`、`ruff`、`pyright`、`mypy`、`cargo check`、
  `cargo clippy`、`shellcheck`、AgentCanon checker、dependency/header check、
  docs check の成功を pytest で包むだけの static-analysis duplicate test を
  追加しません。必要な場合は該当 checker を validation route に直接入れます。
- 本体モジュール内の `if __name__ == "__main__":` にテストを書きません。
- 例外のみを根拠にせず、**既知解・残差・反復回数**で検証します。
- repo 固有の directory 例を正本扱いせず、実在する `tests/` 配下だけを案内します。
- test body に production と同等の algorithm を再実装して expected を作りません。
- private implementation detail だけに結合した brittle test を増やしません。
- skip、tolerance 緩和、expected 値の追従変更で数値 failure を緑化しません。
