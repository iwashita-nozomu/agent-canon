<!--
@dependency-start
contract design
responsibility Documents 設計ドキュメント for this repository.
upstream design ../SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ../dependency-manifest-design.md dependency evidence contract
downstream implementation ../../tools/agent_tools/check_design_doc_claims.py validates design-doc claim evidence
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
- [python-structure-hash.md](python-structure-hash.md)
  - Python structural duplicate analysis and module-group dependency priority
- [../remote-execution-repo-contract.md](../remote-execution-repo-contract.md)
  - remote execution を受ける repo の最小契約

## 追加の module 設計を置くとき

- 実コードに対応する詳細設計が必要になった時点で、`documents/design/<topic>/` を追加します。
- 詳細設計は、実装者がそのまま従える粒度の責務分割、公開境界、検証計画を含めます。
- 詳細設計は、current code、dependency header evidence、parent documents に支えられた `Evidence And Assumption Ledger` を持ち、初出の DSL 用語や problem standard form をそこで明示します。
- 新しい設計入口は、対応する実装 path、dependency header edge、または親文書上の governing source と一緒に追加します。

## 更新ルール

- 共有契約や `Protocol` の責務を変えた場合は [protocols.md](protocols.md) を更新します。
- `experiment_runner` の契約を変えた場合は [experiment_runner.md](../experiment_runner.md) を更新します。
- 特定 topic の設計書を新設したら、この index にも入口を追加します。

## 正本維持ルール

- 現在存在する design path だけを index から参照します。
- 削除済み階層の案内は、現在の canonical path へ更新します。
- 設計の正本は `documents/design/` と、この index が示す AgentCanon-owned design surface に集約します。
