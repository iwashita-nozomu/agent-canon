# C++ OOP Readability
<!--
@dependency-start
contract reference
responsibility Documents C++ OOP readability checker behavior in Japanese.
upstream implementation ../../../../tools/oop/cpp/readability.py C++ OOP readability checker
upstream implementation ../../../../tools/oop/shared/readability_core.py shared readability heuristics
upstream design ../../../object-oriented-design.md OOP policy source
downstream design ../../tool-docs.toml one-to-one tool/document manifest
@dependency-end
-->

この文書は `tools/oop/cpp/readability.py` と一対一で対応します。
同名の `readability.py` が tool、同名の `readability.md` が説明文書です。

## 何をチェックするか

C / C++ source に対して、class / struct / function が責務と所有境界を読みやすく保っているかを軽量な静的解析で確認します。

- 責務が見えない class / struct 名: `Manager`、`Helper`、`Util`、`Thing` で終わる型名を検出します。
- 巨大 class / function: 行数が閾値を超えた source region を、複数責務が混ざる可能性のある review signal として検出します。安定した境界が見えない限り抽出は要求しません。
- public method 過多: 公開 API が広すぎる型を検出します。
- public field 過多: mutable state や invariant が外へ漏れている可能性を検出します。
- base class 過多: 継承面が広すぎ、composition へ寄せるべき候補を検出します。
- 引数過多: request/value object にまとめるべき入力境界を検出します。
- `nullptr` 分岐による runtime routing: 参照、`optional`、`variant`、prevalidated handle で表現すべき variant を検出します。
- 純粋変換と副作用の混在: 値を返しながら IO、filesystem、process、resource effect をまたぐ処理を検出します。
- pass-through / identity に近い wrapper: 役割が薄く、domain contract を持たない adapter 候補を検出します。
- 未完了の brace body: class / struct / function の `{ ... }` が閉じていない場合は `syntax_error` として検出します。

## SOLID report fields

Markdown / JSON report は、finding kind を SOLID principle signal へ投影した
`solid_counts` と finding ごとの `solid_principles` を含みます。
対応表の正本は `tools/oop/shared/readability_core.py` の
`SOLID_PRINCIPLES_BY_KIND` です。C++ checker では、public surface、base class、
public field、`nullptr` routing、mixed effect、不要 wrapper を SOLID の見出しで
review できるようにします。

## 許容する境界

この checker はすべての public field、長い primitive 引数列、identity
function を一律に落とすものではありません。C++ では ABI、schema、
式 DSL、数値 scalar wrapper が実装上の正当な境界になるため、次は警告対象から外します。

- schema / DTO / manifest / metrics / config のような named aggregate value object。
  `RunConfig`、`StepMetrics`、`LayerInfo`、`PacketRecord` など、名前が
  data contract を示し、behavior と state ownership を混ぜない aggregate は
  public field 過多として扱いません。
- `NATIVE_AD_AUGMENT`、`NATIVE_AD_JVP`、`NATIVE_AD_PRIMAL`、
  `NATIVE_AD_VJP` で注釈された primitive ABI function、および
  `__nad_` prefix の exported ABI function。これらは request object へ
  畳むと ABI contract が崩れるため、primitive 引数列を許容します。
- `apply_compile_bindings` のように、式 DSL の terminal node をそのまま返す
  identity morphism。domain rewrite boundary として意味がある場合は
  identity function warning を出しません。
- `float32x2`、`uint64x4` のような compact numeric scalar value object。
  arithmetic operator が public API の本体であるため、operator-heavy
  surface を public method 過多として扱いません。

許容は名前と周辺注釈に基づく機械判定です。state owner と behavior を混ぜた
struct、domain contract のない pass-through wrapper、`nullptr` runtime routing
は引き続き finding として扱います。

## 実行例

```bash
python3 tools/oop/cpp/readability.py --format markdown --include-snippets include src tests/cpp
```

混在 source を 1 回で見たい場合は、shared Python entrypoint に `--language all` を渡します。
この場合、file suffix で Python / C++ を自動選択します。

```bash
python3 tools/oop/python/readability.py --language all --format markdown python include src tests/cpp
```

この checker は build evidence ではありません。C++ 変更では project-native configure / build / test と併せて、OOP readability report を review 補助として扱います。
既定の `OOP_READABILITY` は score threshold ではなく signal class で判定します。
size / public surface / parameter count / complexity は boundary review signal として扱い、
数値だけで分割を要求しません。`nullptr` routing、public state owner、不要 wrapper、
継承境界などの gate signal と分けて読みます。`--min-score 0` は survey 用に finding
を出し切る pass mode です。default より高い `--min-score` を明示した場合だけ strict
score floor として扱います。accepted boundary、false positive、改善方針は review
artifact に残します。
