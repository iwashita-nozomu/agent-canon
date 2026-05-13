# C++ OOP Readability
<!--
@dependency-start
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
- 巨大 class / function: 行数が閾値を超え、責務分割が必要そうな境界を検出します。
- public method 過多: 公開 API が広すぎる型を検出します。
- public field 過多: mutable state や invariant が外へ漏れている可能性を検出します。
- base class 過多: 継承面が広すぎ、composition へ寄せるべき候補を検出します。
- 引数過多: request/value object にまとめるべき入力境界を検出します。
- `nullptr` 分岐による runtime routing: 参照、`optional`、`variant`、prevalidated handle で表現すべき variant を検出します。
- 純粋変換と副作用の混在: 値を返しながら IO、filesystem、process、resource effect をまたぐ処理を検出します。
- pass-through / identity に近い wrapper: 役割が薄く、domain contract を持たない adapter 候補を検出します。

## 実行例

```bash
python3 tools/oop/cpp/readability.py --format markdown --include-snippets include src tests/cpp
```

この checker は build evidence ではありません。C++ 変更では project-native configure / build / test と併せて、OOP readability report を review 補助として扱います。
既定は `--min-score 95` で、単発の軽い adapter signal は review 補助に残しつつ、複合 smell が残る状態を pass にしません。
