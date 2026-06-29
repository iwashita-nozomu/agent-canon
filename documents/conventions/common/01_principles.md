<!--
@dependency-start
contract policy
responsibility Documents 基本方針 for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md shared documents ownership policy
@dependency-end
-->

# 基本方針

この章は、実装全体で優先する判断基準をまとめます。

## 要約

- 読みやすさと保守性を最優先にします。
- マジックナンバーは避け、意味のある定数や引数へ分離します。
- 依存関係は必要最小限に保ちます。

## マジックナンバー

数値計算コードでは「意味のある定数」を暗黙に埋め込むと、将来の比較・再現・チューニングが困難になります。

- **禁止**: マジックナンバー（由来が分からない裸の数値リテラル）を禁止します。
- **例外**: 次のように「意味が自明で、広く普遍的」なものは許容します。
  - 次元に依らない係数 `0.5`（例: 二乗項の係数）
  - `2.0` や `-1.0` のような符号・倍数
- **実装指針**:
  - チューニング可能な値（例: `m`, `s`, `sigma`, `num_trials`）は **公開APIの引数**として受け取ります。
  - 内部関数でのみ使う値は、**名前付き定数**として定義し、用途をコメントで明確にします。
  - dtype 依存値（例: `eps`）は、公開APIから受け取るか、型に合わせて `jnp.asarray(..., dtype=...)` で作ります。

## 数値ハードコード検証

Python / C++ の実装変更では、裸の数値リテラルを機械的に検査します。
既定では `-1`、`-0.5`、`0`、`0.5`、`1`、`2` と対応する小数表記だけを自明な値として許容します。
それ以外の値は、名前付き定数、typed configuration、公開 API 引数、または明示的な行コメント許可へ移します。

```bash
python3 tools/agent_tools/check_hardcoded_numbers.py \
  python include src \
  --exclude vendor \
  --exclude reports
```

意図的な式や標準由来の定数は、行末に `# hardcoded-number-ok: <理由>` または C++ では
`// hardcoded-number-ok: <理由>` を書き、なぜ名前付き定数にしないかを局所的に説明します。
許可コメントは「後で直す」逃げ道ではなく、数式・標準・プロトコル上その場に置く方が読みやすい場合だけ使います。

CI では changed source に対して同じ checker を走らせます。
テスト fixture の期待値は production source と性質が違うため、既定 CI gate では `tests/` を除外します。
ただし、テスト内でも tuning parameter、反復回数、閾値、shape などを複数箇所で使う場合は名前付き定数にします。

## 規約

- 読みやすさと保守性を最優先にします。
- 複雑な分岐は避け、シンプルな実装を心がけます。
- 依存関係は必要最小限に保ち、目的が明確な追加のみ許容します。

## 禁止事項

- マジックナンバー（由来が分からない裸の数値リテラル）を禁止します。
