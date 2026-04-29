<!--
@dependency-start
responsibility Documents 設計ドキュメント for this repository.
upstream design ../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# 設計ドキュメント

このディレクトリは、設計の正本を集約する入口です。
存在しない旧パスを経由せず、ここから現在の設計文書へ直接辿れる状態を保ちます。

## 現在の正本

- [protocols.md](protocols.md)
  - Protocol 層の責務分割
  - 型パラメータ化の方針
- [experiment_runner.md](../experiment_runner.md)
  - `experiment_runner` の契約と実行モデル
- [../remote-execution-repo-contract.md](../remote-execution-repo-contract.md)
  - remote execution を受ける repo の最小契約

## 追加の module 設計を置くとき

- 実コードに対応する詳細設計が必要になった時点で、`documents/design/<topic>/` を追加します。
- 詳細設計は、実装者がそのまま従える粒度の責務分割、公開境界、検証計画を含めます。
- 実体のない package 名や将来案だけで空ディレクトリを増やしません。

## 更新ルール

- 共有契約や `Protocol` の責務を変えた場合は [protocols.md](protocols.md) を更新します。
- `experiment_runner` の契約を変えた場合は [experiment_runner.md](../experiment_runner.md) を更新します。
- 特定 topic の設計書を新設したら、この index にも入口を追加します。

## 禁止事項

- `documents/design/base_components.md` のような存在しない旧パスを正本として参照することを禁止します。
- `documents/design/apis/` のような削除済み階層を案内することを禁止します。
- 設計の正本を `notes/` や `reports/` に置くことを禁止します。
