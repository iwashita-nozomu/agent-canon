<!--
@dependency-start
upstream design ../../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# 対象

## 要約

- 対象は `python/` 配下の checked-in Python 実装と、それに対応する `tests/` です。
- framework 固有の補足は、実際にその framework を使う場合だけ適用します。

## 規約

- この章の対象は、repo に commit される `python/` 配下の package、module、共有 runtime helper です。
- `tests/` 側の Python も、この章で定める公開境界、命名、型検査方針に従います。
- `scripts/` 配下の Python は library ほど重い抽象化を要求しませんが、型注釈、責務分離、lint の方針は共有します。
- JAX、PyTorch、C++ binding など framework / runtime 固有の補足は、それぞれの補助文書を別に作り、この章へ混ぜ込みません。
