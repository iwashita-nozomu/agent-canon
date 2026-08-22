<!--
@dependency-start
contract design
responsibility Documents 設計ドキュメント for this repository.
upstream design ../rule/README.md document rule canon
upstream design dependency-manifest-design.md dependency evidence contract
downstream implementation ../../tools/agent_tools/check_design_doc_claims.py validates design-doc claim evidence
@dependency-end
-->

# 設計ドキュメント

このディレクトリは、設計の正本を集約する入口です。
存在しない旧パスを経由せず、ここから現在の設計文書へ直接辿れる状態を保ちます。

承認済みの Target-State-First implementation contract は
[codex-spark-implementation-routing.md](codex-spark-implementation-routing.md) です。
この packet で digest は不変とし、projection は設計 artifact を複製または編集せず、そこへリンクします。

文書の filename、配置、構成判断は [文書規約](../rule/README.md) を参照します。
この index は配置規則を複製せず、個別設計の target state と実装境界への reader route を提供します。

## 現在の正本

- [protocols.md](protocols.md)
  - Protocol 層の責務分割
  - 型パラメータ化の方針
- [devcontainer/parent-devcontainer-policy.md](devcontainer/parent-devcontainer-policy.md)
  - 親root と AgentCanon source の devcontainer 境界、wrapper 順序、compose 出力、
    親 hook 契約を定義します。
  - `tools/agent_tools/devcontainer_dependencies.py` が `pyproject.toml` の
    optional-dependencies extras の名前・順序・重複と存在を検証し、標準 editable
    install / `pip check` を所有します。`container_config.py` は pack/env の typed
    extras を Compose 境界へ projection します。
- [experiment_runner.md](experiment_runner.md)
  - `experiment_runner` の契約と実行モデル
- [experiment-topic-template.md](experiment-topic-template.md)
  - single-source experiment topic scaffold、case/visualization owner、raw/summary result layout
- [python-structure-hash.md](python-structure-hash.md)
  - Python の structural duplicate analysis と module-group dependency priority
- [agentcanon-hook-simplification-wave3.md](agentcanon-hook-simplification-wave3.md)
  - Wave 3 の3 active event、`hook_dispatcher.py`→`behavior_event_assembly.py` の exactly-once caller contract、`behavior_event_assembly.record_hook_invocation(parts)` の純アセンブリ公開 API、`.codex/hooks/hook_event_log.py` が no-replace per-event spool transport の serialization/append writer、活性ハンドラ毎に1 base append、行動レコード存在時のみ monitor projection、`RETIRED_CHILD_TOMBSTONES=23` / `MOVED_SOURCE_ABSENCES=1` / retired basenames `24`、分離した semantic event / hook event、skill logger 単独 owner 化、`skill_usage.jsonl` 履歴 read-only 取扱い、PR #471後 current-main inventory gate、検証コーパス
- [skill-tool-invocation-graph.md](skill-tool-invocation-graph.md)
  - skill / capability / phase / tool / edge の identity、参照、coverage、readback
- [skill-runtime-shim-materialization.md](skill-runtime-shim-materialization.md)
  - catalog-defined Codex discovery shim の schema、単一 materializer、移行、readback、prompt 評価
  - `skill_tool_commands.py` は read-only packet producer、SKILL.md の writer は materializer
    一つだけとする command surface、shim routing と全体 `route.py` の所有境界
  - 実在する `workflow_selection_eval.toml` の 525 cases、固定 prompt/expected readback、
    graph/route/ToolID/ToolCall golden、fresh `gpt-5.4-mini` scenario と paired token contract
  - catalog-derived な全件 transaction ではなく per-file `temp + os.replace`、全件readback、同一
    materializer再実行による idempotent recovery。source/tests/eval producer は通常の
    実装diffとしてruntime write setから分離
  - determinism と idempotent fixed point の分離、2回実行時のrecord/catalog-sized projection/
    readback equality と2回目content delta=0、route argparse error mapping、厳密な
    measurement artifact schema/version/row contract
- [responsibility-cleanup.md](responsibility-cleanup.md)
  - tree 観測、source/view/generated/project/personal 境界、dependency closure、責務単位、
    environment/code/skill dispatch、既存 owner 再利用、統合、再レビュー、validation、rollback
- [runtime-log-repository-lifecycle.md](runtime-log-repository-lifecycle.md)
  - AgentCanon-log #4 と AgentCanon #461 の runtime-log repository owner split
- [request-intent-and-update-relation.md](request-intent-and-update-relation.md)
  - 質問回答、明示 write clause、sparse update、既存 cleanup route の compact flow
- [source-owned-dependency-validation.md](source-owned-dependency-validation.md)
  - tracked source を dependency correctness の正本とし、PR receipt を `source` / `skipped` の二値で writer/parser/consumer 間に渡す境界
- [dependency-manifest-design.md](dependency-manifest-design.md)
  - manifest DSL、relation semantics、source-derived projection、および明示 graph analysis の reader route
- [parent-repository-audit.md](parent-repository-audit.md)
  - AgentCanon を利用する親 repository 全体の責務別 audit unit、legacy checklist 移行、
    finding 修正と close の設計
- [semantic-responsibility-contract.md](semantic-responsibility-contract.md)
  - semantic delta、obligation、一次検証 owner、hard-edge closure、run-local instance の契約
- [agent-team-module-boundaries.md](agent-team-module-boundaries.md)
  - AgentTeam runtime orchestration の Python module boundary、公開 facade、migration wave、検証責任
- [semantic-index-module-boundaries.md](semantic-index-module-boundaries.md)
  - semantic-index CLI/cache/report pipeline の Rust module boundary、schema、atomic publish、検証責任
- [../remote-execution-repo-contract.md](../contracts/remote-execution-repo-contract.md)
  - remote execution を受ける repo の最小契約

## 追加の module 設計を置くとき

- 実コードに対応する詳細設計が必要になった時点で、`documents/design/<topic>/` を追加します。
- 詳細設計は、実装者がそのまま従える粒度の責務分割、公開境界、検証計画を含めます。
- 詳細設計は、current code、dependency header evidence、parent documents に支えられた `Evidence And Assumption Ledger` を持ち、初出の DSL 用語や problem standard form をそこで明示します。
- 新しい設計入口は、対応する実装 path、dependency header edge、または親文書上の governing source と一緒に追加します。

## 更新ルール

- 共有契約や `Protocol` の責務を変えた場合は [protocols.md](protocols.md) を更新します。
- `experiment_runner` の契約を変えた場合は [experiment_runner.md](experiment_runner.md) を更新します。
- experiment topic scaffold、module boundary、または raw/summary layout を変えた場合は
  [experiment-topic-template.md](experiment-topic-template.md) と直接結合する registry/retention docs を更新します。
- 特定 topic の設計書を新設したら、この index にも入口を追加します。

## 正本維持ルール

- 現在存在する design path だけを index から参照します。
- 削除済み階層の案内は、現在の canonical path へ更新します。
- 設計の正本は `documents/design/` と、この index が示す AgentCanon-owned design surface に集約します。
