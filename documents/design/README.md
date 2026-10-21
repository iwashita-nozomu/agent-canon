<!--
@dependency-start
contract design
responsibility Documents 設計ドキュメント for this repository.
upstream design ../rule/README.md document rule canon
upstream design dependency-manifest-design.md dependency evidence contract
@dependency-end
-->

# 設計ドキュメント

このディレクトリは、設計の正本を集約する入口です。
存在しない旧パスを経由せず、ここから現在の設計文書へ直接辿れる状態を保ちます。

Target-State-First の設計schemaとworkflow契約は
[codex-spark-implementation-routing.md](codex-spark-implementation-routing.md) が所有します。
同文書の過去のreceipt記録と、現在のhandoffで選ぶ検証済みpacketを区別します。

文書の filename、配置、構成判断は [文書規約](../rule/README.md) を参照します。
この index は配置規則を複製せず、個別設計の target state と実装境界への reader route を提供します。

## 現在の正本

- [algorithm-implementation-boundary.md](algorithm-implementation-boundary.md)
  - 数学的アルゴリズムと production 実装の責務境界
- [api-surface-traversal-policy.md](api-surface-traversal-policy.md)
  - API surface の探索範囲とたどり方
- [jax_util/algorithm_module_contract.md](jax_util/algorithm_module_contract.md)
  - JAX algorithm module の契約
- [protocols.md](protocols.md)
  - Protocol 層の責務分割
  - 型パラメータ化の方針
- [cpp-build-layout.md](cpp-build-layout.md)
  - C++ build の配置と構成
- [runtime-debugging.md](runtime-debugging.md)
  - 標準 system / Python 診断の選択、規定実行境界、既存 C++ 診断への導線
- [agent-canon-bootstrap-tool-runtime.md](agent-canon-bootstrap-tool-runtime.md)
  - standalone bootstrap と共有 tool runtime の設計
- [devcontainer/parent-devcontainer-policy.md](devcontainer/parent-devcontainer-policy.md)
  - 親root と AgentCanon source の devcontainer 境界、wrapper 順序、compose 出力、
    親 hook 契約を定義します。
  - `tools/runtime/container/devcontainer_dependencies.py` が `pyproject.toml` の
    optional-dependencies extras の名前・順序・重複と存在を検証し、標準 editable
    install / `pip check` を所有します。pack/env の typed extras は
    `tools/runtime/container/devcontainer_dependencies.py` から Compose 境界へ
    projection されます。
- [experiment_runner.md](experiment_runner.md)
  - `experiment_runner` の契約と実行モデル
- [experiment-topic-template.md](experiment-topic-template.md)
  - single-source experiment topic scaffold、case/visualization owner、raw/summary result layout
- [python-structure-hash.md](python-structure-hash.md)
  - Python の structural duplicate analysis と module-group dependency priority
- [agentcanon-hook-simplification-wave3.md](agentcanon-hook-simplification-wave3.md)
  - hook-event / semantic-event の所有境界、移行、readback

- [entrypoint-owner-map.md](entrypoint-owner-map.md)
  - repository entrypoint の責務と canonical owner への接続
- [tool-skill-routing-refactor.md](tool-skill-routing-refactor.md)
  - tool と Skill の routing 責務分割
- [skill-tool-invocation-graph.md](skill-tool-invocation-graph.md)
  - skill / capability / phase / tool / edge の identity、参照、coverage、readback
- [skill-runtime-shim-materialization.md](skill-runtime-shim-materialization.md)
  - catalog-defined discovery adapter、所有境界、materialization、移行、readback

- [responsibility-rationale.md](responsibility-rationale.md)
  - 責務配置の判断根拠
- [responsibility-scope-management.md](responsibility-scope-management.md)
  - 責務の scope 管理
- [responsibility-cleanup.md](responsibility-cleanup.md)
  - 責務単位の完結、owner dispatch、置換・廃止、統合、検証

- [runtime-log-repository-lifecycle.md](runtime-log-repository-lifecycle.md)
  - AgentCanon-log #4 と AgentCanon #461 の runtime-log repository owner split
- [request-intent-and-update-relation.md](request-intent-and-update-relation.md)
  - 質問回答、明示 write clause、sparse update、既存 cleanup route の compact flow
- [source-owned-dependency-validation.md](source-owned-dependency-validation.md)
  - tracked source を dependency correctness の正本とし、PR receipt を `source` / `skipped` の二値で writer/parser/consumer 間に渡す境界
- [dependency-manifest-design.md](dependency-manifest-design.md)
  - manifest DSL、relation semantics、source-derived projection、および明示 graph analysis の reader route
- [dependency-reference-relation.md](dependency-reference-relation.md)
  - `reference` relation の repository-contained evidence semantics と、parent / authority 経路からの分離
- [parent-repository-audit.md](parent-repository-audit.md)
  - AgentCanon を利用する親 repository 全体の責務別 audit unit、legacy checklist 移行、
    finding 修正と close の設計
- [semantic-responsibility-contract.md](semantic-responsibility-contract.md)
  - semantic delta、obligation、一次検証 owner、hard-edge closure、run-local instance の契約
- [agent-team-module-boundaries.md](agent-team-module-boundaries.md)
  - AgentTeam runtime orchestration の Python module boundary、公開 facade、migration wave、検証責任
- [rust-agent-tool-migration.md](rust-agent-tool-migration.md)
  - Agent tool の Rust 移行設計
- [static-seed-consumer-static-projection.md](static-seed-consumer-static-projection.md)
  - static seed から consumer への静的 projection の設計
- [semantic-index-module-boundaries.md](semantic-index-module-boundaries.md)
  - semantic-index CLI/cache/report pipeline の Rust module boundary、schema、atomic publish、検証責任
- [../contracts/remote-execution-repo-contract.md](../contracts/remote-execution-repo-contract.md)
  - remote execution を受ける repo の最小契約

## 追加の module 設計を置くとき

- 実コードに対応する詳細設計が必要になった時点で、`documents/design/<topic>/` を追加します。
- 詳細設計は、実装者がそのまま従える粒度の責務分割、公開境界、検証計画を含めます。
- 詳細設計は通常の prose と Markdown links で current code、dependency context、parent documents を参照し、重要な判断を支える根拠と前提をその場で説明します。固定した ledger 見出しや claim-token 形式は要求しません。
- 新しい設計入口は、対応する実装 path、dependency header edge、または親文書上の governing source と一緒に追加します。

## 更新ルール

- 共有契約や `Protocol` の責務を変えた場合は [protocols.md](protocols.md) を更新します。
- `experiment_runner` の契約を変えた場合は [experiment_runner.md](experiment_runner.md) を更新します。
- experiment topic scaffold、module boundary、または raw/summary layout を変えた場合は
  [experiment-topic-template.md](experiment-topic-template.md) と直接結合する registry/retention docs を更新します。
- 設計書の追加・分割・移動・削除は [参照と到達性](../rule/directory-structure.md#参照と到達性)
  に従い、この index と直接の consumer の読取経路を更新します。

## 正本維持ルール

- 現在存在する design path だけを index から参照します。
- 削除済み階層の案内は、現在の canonical path へ更新します。
- 設計の正本は `documents/design/` と、この index が示す AgentCanon-owned design surface に集約します。
