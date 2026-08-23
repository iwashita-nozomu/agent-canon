# Implementation Waterfall Literature Note
<!--
@dependency-start
contract workflow
responsibility Documents Implementation Waterfall Literature Note for agent workflow canon.
upstream design ../../agents/workflows/workflow-references.md workflow reference index
downstream design ../../agents/workflows/implementation-waterfall-workflow.md implemented workflow
@dependency-end
-->

## Reader Map

- Owns the literature note that justifies local waterfall-style implementation
  gates and handoff packets.
- Main path: Question, Scope, Search Log, Primary Sources, Supporting Sources,
  contrary evidence, Known/Contested/Open, and local implications.
- Read this when revisiting why the local canon separates requirements,
  design, implementation, and review gates.
- Boundary: this is rationale and evidence, not the operational workflow
  definition itself.

## Question

agent を使う repo の実装プロセスを、どのような段階ゲート付きウォーターフォールとして定義すべきか。

## Scope

- repo に持ち帰る code / docs / environment change の実装プロセス
- family 選択後の implementation pass
- security、verification、transition を含む closeout

除外:

- 研究 outer loop 全体の反復設計
- 単一 experiment run の詳細手順
- runtime 固有の prompt 設計

## Search Log

- 2026-04-07
  - `Managing the Development of Large Software Systems waterfall Royce`
  - `NIST SP 800-218 SSDF final`
  - `NASA systems engineering handbook requirements design verification validation`
  - `SEBoK sequential development approach decision gates`

## Primary Sources

### Winston W. Royce, 1970

- `Managing the Development of Large Software Systems`
- 典型的な段階列として requirements / analysis / design / coding / testing / operations を示す
- ただし単純な一方向実装は risky で failure を招くと注意している
- 設計先行、文書化、pilot model、test planning を強く要求している

### NASA Systems Engineering Handbook Rev 2, 2017

- stakeholder expectations definition
- technical requirements definition
- logical decomposition
- design solution definition
- product implementation / integration / verification / validation / transition

示唆:
- 要件、設計、実装、検証、移行は gate を分けるべき
- technical review は次段へ進む readiness 判定として使うべき

### NIST SP 800-218, 2022

- secure software development practice は各 SDLC 実装へ統合すべきと整理
- methodology 非依存なので waterfall でも verification gate に security を組み込むべき

### NIST SP 800-218A, 2024

- AI model development 向けに SSDF を拡張
- AI model development throughout the software development life cycle を明示

示唆:
- AI / agent を含む実装では、通常の verification に加えて AI 特有の risk を確認する必要がある

## Supporting Sources

### SEBoK Sequential Development Approach

- sequential development は structured, phase-based process
- large-scale / safety-critical / multi-organization efforts に向く
- ただし Royce 本来の考え方として early iteration は残すべきと整理

### SEBoK Technical Reviews and Audits

- technical reviews and audits は decision gate の readiness 判定を支える

### Google Engineering Practices

- code review では local consistency を重視し、既存コードとの整合と関連文書更新を確認すべきと整理している

### NASA Software Engineering Handbook

- existing software reuse を設計と review の観点で明示的に扱う
- 新規実装より前に、既存資産の利用可能性を確認すべきだと示唆する

## Contrary Or Narrowing Evidence

- Royce 自身は、単純化された純粋 waterfall を推奨していない
- SEBoK も、後工程での大きな戻りは高コストであり、初期段階の限定的な iteration を認めている
- したがって、採用すべきなのは no-feedback waterfall ではなく、phase-gated waterfall

## Known

- requirements freeze と design freeze を分けるのは妥当
- reviewer を decision gate に割り当てると repo 運用へ落とし込みやすい
- closeout 前の verification / validation / transition を分けると、commit / push / docs sync を統制しやすい
- detailed design review で reuse-first と local consistency を強く見るのが妥当

## Contested

- research-heavy task まで完全単線化すると探索速度は落ちる
- そのため、research loop 全体ではなく、repo に持ち帰る implementation pass だけを waterfall 化するのが現実的

## Open

- 将来、agent security 専用 review gate を独立させるべきか
- multi-agent handoff packet を gate artifact として定型化するか

## Implications For Local Canon

- workflow family 自体は維持し、implementation pass の共通ルールを追加する
- `Research-Driven Change` は iteration を禁じず、1 change = 1 waterfall pass に制約する
- `Large Delivery` は chunk ごとに waterfall pass を閉じる
- `Platform And Environment` は design gate と acceptance gate で rollout / rollback を強化する
