# Detailed Design Review（詳細 design レビュー）
<!--
@dependency-start
contract template
responsibility Documents Detailed Design Review for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
upstream design ../../documents/design/dependency-manifest-design.md dependency evidence contract
upstream implementation ../../tools/agent_tools/check_design_doc_claims.py verifies design-doc evidence claims
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

{{>findings_area_table}}

{{>review_contract}}

## Reader Map（読者 map）

この template は owning gate だけでは判定できない独立した unresolved design claim がある場合に
だけ materialize します。選択時は implementation 前の detailed design artifact 自体の review を
所有します。対象の exact design artifact を記録し、document completeness、reuse/style、cross-doc
coverage、upstream requirement、abstract design frame、evidence、assumption、parent-doc alignment、
source packet、side effect、canonical tree head、naming、design-to-implementation trace、readiness
を確認してから approve、revise、escalate を判定します。top-down の読者経路は document-flow
review artifact が別に確認し、この template は hidden assumption なしに reviewed design から
implementation を進められるかを確認します。approve は以下に記録した current artifact だけに
適用します。

## Design Artifact Under Review（review 対象 design artifact）

<!-- この gate が選択されたら exact design_brief.md path、revision または section set、source packet、reviewer separation evidence を記録します。review target が chat summary、implementation diff、worker summary、stale design artifact なら revise とします。 -->

- Design artifact path:
- Design revision or section set:
- Source packet reviewed:
- Reviewer separation:
- Review validity:
- Semantic responsibility contract:
  - Run-local instance:
  - Policy reference:
  - Delta actions and obligation owners read back:
  - Hard-edge grouping read back:

## Document Completeness Review（文書完全性レビュー）

<!-- hidden assumption なしに implementation できるだけ design document が具体的か確認します。 -->

## Reuse And Style Review（reuse と style のレビュー）

<!-- 既存 code、naming、API、test、docs style に従っているか確認します。 -->

## Cross-Doc Coverage Review（文書横断 coverage レビュー）

<!-- design が parent document chain の外も調べ、review policy、guardrail、notes lifecycle、learning workflow、migration/integration docs など関連する cross-cutting docs を含めたか確認します。1 つの document branch に閉じて隣接する governing docs を逃した場合は revise とします。 -->

## Upstream Requirement Packet Review（upstream 要件 packet レビュー）

<!-- design が request contract、schedule、intent brief、waterfall docs、その他 governing document からなる upstream documented requirement packet を明示的に引用するか確認します。chat-only memory に依存している場合は revise とします。 -->

## Abstract Design Frame Review（abstract design frame レビュー）

<!-- implementation file、helper、current finding を選ぶ前に、abstract responsibility model、concept/layer model、non-goal、future extension layer、evaluation axis、既存 canonical surface との関係を design が確定するか確認します。file-by-file design や validation が frame から導出されていなければ revise とします。 -->

## Evidence Coverage Review（evidence coverage レビュー）

<!-- major design claim が current code、dependency-header evidence、既存 docs、parent document を引用するか確認します。新規または変更した design doc では `python3 tools/agent_tools/check_design_doc_claims.py --root . <design-doc>` と artifact path を記録します。 -->

## Assumption Definition Review（仮定定義レビュー）

<!-- first-use DSL term、problem standard form、canonical form、normalization rule が implementation choice を導く前に design の Evidence And Assumption Ledger に現れるか確認します。 -->

## Parent-Doc Alignment Review（parent doc 整合レビュー）

<!-- upstream parent document との差分が current choice の governing source とともに記録されるか確認します。 -->

## Refactor Tool Alignment Review（refactor tool 整合レビュー）

<!-- structure または responsibility shift が dependency-expanded evidence とともに dependency-analysis と structure-refactor に handoff されるか確認します。 -->

## Implementation Source Packet Review（implementation source packet レビュー）

<!-- design が selected read-before-edit artifact をすべて命名するか確認します。request contract、schedule、design、active 時の design review/document flow review、post-implementation test design が active な場合だけ test plan、repo docs、code path、test、external reference を含めます。worker が chat context や未記載の仮定を必要とするなら revise とします。 -->

design に semantic delta がある場合、review は run-local semantic responsibility contract を
含めます。delta ごとに 1 action、obligation ごとに 1 primary verification owner、distinct な
supporting property があることを確認します。hard-edge closure は semantic grouping evidence
としてだけ readback し、class、module、file shape を強制しません。

## Design Side-Effect Map Review（design side-effect map レビュー）

<!-- design が各 major design decision を影響先の implementation、document、workflow、prompt/config、validation、dependency-manifest、user-facing surface に対応付けるか確認します。各 side-effect item が Abstract Design Frame、request clause ID、reuse precedent、owner stage、review gate、validation または test-plan item に接続することを確認します。design 承認後に implementation が secondary surface を発見する必要があれば revise とします。 -->

## Canonical Tree-Head Review（canonical tree head レビュー）

<!-- tracked tree に残す canonical design-document path と implementation path を design が確定し、non-canonical draft、snapshot、mirrored directory、backup file、copied implementation を明示的に削除または作成禁止にするか確認します。current tree head を超える複数の truth を残すなら revise とします。 -->

## Identifier And Naming Review（identifier と naming のレビュー）

<!-- 新規または rename する identifier、path、CLI flag、config key、public API が design または local precedent で確定しているか確認します。worker が reusable または user-facing name を発明する必要があれば revise とします。 -->

## Design-To-Implementation Trace Review（design-to-implementation trace レビュー）

<!-- 各 planned edit が design section、user-request clause ID、reuse precedent または source document、test-plan item、validation evidence に対応付くか確認します。implementation slice がこの trace を引用できなければ revise とします。 -->

## Implementation Readiness Review（implementation readiness レビュー）

<!-- design が実際に implementation-ready で、最重要の pre-implementation gate を通るか確認します。top-down document readability は document_flow_review.md が別に扱います。 -->

## Revision Loop（改訂ループ）

<!-- designer が改訂する内容、issue を detailed design に留めるか、task を planning に戻すかを記録します。 -->

{{>decision_approve_revise_escalate}}
