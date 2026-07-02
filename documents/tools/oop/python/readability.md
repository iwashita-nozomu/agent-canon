# Python OOP Readability
<!--
@dependency-start
contract reference
responsibility Documents Python OOP readability checker behavior in Japanese.
upstream implementation ../../../../tools/oop/python/readability.py Python OOP readability checker
upstream implementation ../../../../tools/oop/shared/readability_core.py shared readability heuristics
upstream design ../../../object-oriented-design.md OOP policy source
downstream design ../../tool-docs.toml one-to-one tool/document manifest
@dependency-end
-->

この文書は `tools/oop/python/readability.py` と一対一で対応します。
同名の `readability.py` が tool、同名の `readability.md` が説明文書です。

## 何をチェックするか

Python source に対して、OOP 境界が「責務、状態、契約、公開面」を読みやすく分けているかを軽量な静的解析で確認します。

- 責務が見えない class 名: `Manager`、`Helper`、`Util`、`Thing` で終わる class を検出します。
- 巨大 class / function: 行数が閾値を超えた source region を、複数責務が混ざる可能性のある review signal として検出します。安定した境界が見えない限り抽出は要求しません。
- public method 過多: class の公開 API が広すぎる場合を検出します。
- instance state 過多: `self.*` の所有状態と class body の型付き field が多く、
  ライフサイクルや invariant が追いにくい class を検出します。Equinox
  `Module` のように typed class field が状態・契約を表す境界では、その field を
  thin-class 判定の state/contract として扱います。
- static method だけの namespace class: module function で十分な class を検出します。
- thin class: dataclass、protocol、algorithm contract ではない薄すぎる class を検出します。
- method が `self` / `cls` を使わない場合: class の凝集度が低い method を検出します。
- module-level helper 名: `helper`、`util`、`misc`、`tmp` を含む曖昧な公開関数を検出します。
- 型境界の欠落: public function / method の引数・戻り値 annotation 欠落を検出します。
- `Optional` / `Any` / `None` 分岐による runtime routing: 型で分けるべき variant が `None` 判定に逃げていないかを検出します。
- 純粋変換と副作用の混在: 値を返しながら IO、process、filesystem、外部 effect をまたぐ処理を検出します。
- 数学的に冗長な wrapper: identity function、単純 pass-through、stateless callable class、trivial format function を検出します。

## SOLID report fields

Markdown / JSON report は、finding kind を SOLID principle signal へ投影した
`solid_counts` と finding ごとの `solid_principles` を含みます。
対応表の正本は `tools/oop/shared/readability_core.py` の
`SOLID_PRINCIPLES_BY_KIND` です。Python checker では、public method 過多、
annotation 欠落、`Optional` / `None` routing、mixed effect、不要 wrapper を
SOLID の見出しで review できるようにします。

## 実行例

```bash
python3 tools/oop/python/readability.py --format markdown --include-snippets python tools tests
```

既定の `OOP_READABILITY` は score threshold ではなく signal class で判定します。
size / public surface / parameter count / complexity は boundary review signal として扱い、
数値だけで分割を要求しません。`Optional` / `None` routing、namespace class、
不要 wrapper、型境界欠落などの gate signal と分けて読みます。`--min-score 0` は
survey 用に finding を出し切る pass mode です。default より高い `--min-score` を
明示した場合だけ strict score floor として扱います。finding は design review の
補助であり、必要なら accepted boundary、false positive、改善方針を review artifact
に残します。
