# Detailed Design Brief（詳細 design brief）
<!--
@dependency-start
contract template
responsibility Documents Detailed Design Brief for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
upstream design ../../documents/design/dependency-manifest-design.md dependency evidence contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Reader Map（読者 map）

この template は implementation-facing な detailed design packet を所有します。handoff 前に
goal、abstract design frame、evidence ledger、reuse survey、requirement packet、implementation
source packet、side-effect map、reader path、clause mapping、file-by-file design、trace、naming
plan、validation、rollback、risk を埋めます。unresolved responsibility、naming、validation、
API-shape claim を owning review gate が判定できない場合だけ detailed design review を選択します。
selected gate の判定後、implementation worker はこれを source packet として使い、unresolved gap
は local implementation judgment ではなく owning design route に戻します。

## Design Review Handoff（design review handoff）

<!-- design artifact path、current revision または section set、gate が active な場合だけ design_review.md path、該当時の document_flow_review.md path、selected gate/adjudication state を記録します。candidate review artifact がないことだけで implementation を block しません。 -->

- Design artifact under review:
- Required review artifact:
- Review state:
- Implementation / handoff blocker:
- Semantic responsibility contract:
  - Run-local instance:
  - Policy reference:
  - Active-packet source reference:
  - Allocation state:

## Goals（目標）

<!-- implementation-facing な言葉で design goal を記述します。implementation が従う design document を作ることが目標です。 -->

## Abstract Design Frame（抽象 design frame）

<!-- file や patch を選ぶ前に、abstract responsibility model、concept graph、non-goal、future extension layer、evaluation axis、既存 canonical surface との関係を記述します。implementation slice は最寄りの file、helper、finding だけから選ばず、この frame から導出します。 -->

<!-- Packet entry: entry_id=abstract-design-frame。active packet の responsibility_id と exact clause_refs、owner_refs、source_refs、dependency_refs、output_refs、reviewer_refs を記録し、prose から推論しません。 -->

- Responsibility model:
- Concept or layer model:
- Non-goals:
- Future extension layers:
- Evaluation axes:
- Canonical-surface relationships:

## Algorithm Contract Before Tests（tests より前の algorithm contract）

<!-- test expectation より先に production mechanism を確定します。observable でない限り private implementation shape、mock order、helper name を contract に固定しません。 -->

- public entrypoint and input schema:
- state transition / recurrence:
- invariants and preconditions:
- stopping / acceptance rule:
- typed failure semantics and preserved state:
- selected implementation mechanism:

## Necessary-And-Sufficient Oracle Boundary（必要十分 oracle 境界）

- necessary observations:
- sufficient observations:
- oracle owner:
- not proven by this oracle:
- test activation condition or static-only reason:

## Failure Cause And Conflict Intent（failure cause と conflict intent）

- cause class: expected / infrastructure / implementation / oracle / unknown:
- evidence and owner:
- preserved user/design intent:
- conflicting source or contract:
- escalation / rejection evidence:

## Alternatives And Independent Review（代替案と独立レビュー）

| option | mechanism | evidence | cost/risk | status |
| --- | --- | --- | --- | --- |
| A | `<mechanism>` | `<evidence>` | `<risk>` | selected / rejected |
| B | `<mechanism>` | `<evidence>` | `<risk>` | selected / rejected |

- selection rule:
- rejected rationale:
- independent reviewer:
- reviewer source snapshot and readback:

## Evidence And Assumption Ledger（証拠と仮定の ledger）

<!-- design claim を current code、dependency header、既存 docs、parent document に結び付けます。file-by-file implementation design の前に first-use DSL term、problem standard form、normalization rule、governing parent-doc difference を記録します。design-doc claim check では code path、tool path、dependency-header evidence、parent document を stable path で引用します。 -->

- Evidence sources:
- Assumptions:
- Parent-doc alignment:
- Refactor handoff:

## Existing Code And Docs To Reuse（再利用する既存 code/docs）

<!-- 再利用または mirror すべき local module、helper、test、doc、naming pattern を列挙します。 -->

## Upstream Requirement Packet（upstream 要件 packet）

<!-- designer が design を書く前に読んだ exact document path を列挙します。user_request_contract.md、schedule.md、intent_brief.md、waterfall workflow docs、その他の governing docs を含め、chat-only context に依存しません。 -->

## Installed Libraries And Existing Implementation Survey（library と既存実装の調査）

<!-- implementation shape を決める前に調べた dependency surface、installed library、既存 helper/module/test/doc を列挙します。各候補を reused、extended、replaced、rejected のどれにしたか、新規追加時に既存 library/implementation で足りない理由を記録します。 -->

## Implementation Source Packet（implementation source packet）

<!-- worker が edit 前に読む全 artifact を列挙します。user_request_contract.md、schedule.md、この design brief、active 時の design_review.md/document_flow_review.md、post-implementation test design が active な場合だけ test_plan.md、repo docs、dependency surface、code path、test、外部 reference を含めます。各 item を required または not used と記録します。 -->

<!-- semantic delta がある場合は run-local semantic_responsibility_contract.toml instance を含めます。reusable template から生成し、implementation 前に読みます。 -->

<!-- Packet entry: entry_id=implementation-source-packet。exact active-packet reference、selected graph-packet identity、materialization reader、entry:abstract-design-frame への dependency を保持します。 -->

## Design Side-Effect Map（design side-effect map）

<!-- 各 major design decision が影響する downstream implementation、document、workflow、prompt/config、validation、dependency-manifest、user-facing surface を列挙します。各 item を Abstract Design Frame responsibility、request clause ID、reuse precedent、owner stage、review gate、validation または test-plan item に接続します。 -->

<!-- Packet entry: entry_id=design-side-effect-map。exact active-packet reference と entry:abstract-design-frame への dependency を保持します。 -->

## Canonical Tree-Head Plan（canonical tree head 計画）

<!-- task 後も tracked に残せる唯一の canonical design-document path と implementation path を記載します。削除または作成禁止の non-canonical draft、snapshot、backup file、copied implementation、mirrored directory、parallel design doc をすべて列挙します。durable product state は current tree head だけだと明記します。 -->

## Patterns And Writing Style To Mirror（mirror する pattern と文体）

<!-- implementation が従う既存の coding/documentation style を記録します。 -->

## Reader Path And Term Introduction（読者経路と用語導入）

<!-- intended top-down reading order、使用前に定義する用語、reader が key decision point に到達する場所を記録します。 -->

## Request Clause Mapping（request clause の対応）

<!-- この design が満たす user-request clause ID と、この pass の外に残る clause ID を記録します。 -->

## File-By-File Design（file 単位の design）

<!-- planned file edit、boundary、interface、expected diff shape を詳しく記述します。 -->

## Design-To-Implementation Trace（design から implementation への trace）

<!-- 各 planned edit を design section、user-request clause ID、source/reuse document または code path、test-plan item、expected validation evidence に対応付けます。worker は edit 前にこの mapping を引用します。 -->

<!-- Packet entry: entry_id=design-to-implementation-trace。他の 3 entry への dependency を保持し、すべての source、generated、deletion record を 1 つの integrated responsibility unit に対応付けます。 -->

## Identifier And Naming Plan（identifier と naming の計画）

<!-- 新規または rename する variable、function、class、file、CLI flag、config key、public API surface を列挙します。各 item に chosen name、local precedent、該当する rejected alternative、name が implementation-blocking かを記録します。 -->

## Validation And Rollback Plan（validation と rollback 計画）

<!-- design の validation 方法と rollback または alternate route path を記述します。 -->

## Risks（リスク）

<!-- tradeoff、既知の risk、alternate route option を記録します。 -->
