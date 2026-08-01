# 設計・実装対応ルート
<!--
@dependency-start
contract agent-runtime
responsibility Documents the universal design-to-implementation correspondence routine for repository-changing work.
upstream design ../canonical/CODEX_WORKFLOW.md implementation entry and design-integrity route
downstream implementation ../../tools/agent_tools/route.py selects capability and stage routes
downstream implementation ../../tools/agent_tools/bootstrap_agent_run.py transports design fingerprints and handoff state
downstream implementation ../../tools/agent_tools/check_design_doc_claims.py validates design-backed claims
downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py validates canonical runtime references
downstream design ../skills/change-review.md consumes forward and reverse correspondence at review
upstream design ../../documents/design/request-intent-and-update-relation.md compact request/update and related-document closure contract
upstream design ../../documents/design/semantic-responsibility-contract.md semantic delta and obligation ownership contract
@dependency-end
-->

## Reader Map

このルートは、設計正本と repository-changing implementation の間に一つの対応関係を作るための内部ルートです。読者は、まず `Invariant` と `State Model` を確認し、次に `Stage Ownership`、`Handoff Record`、`Review Readback` の順に読みます。skill 個別の説明、ToolCall schema、実装レビューの詳細は各 owner surface に残し、この文書は共通の遷移と対応キーだけを持ちます。

## Responsibility / Owner Boundaries

| 責務 | 正本 owner | このルートが行うこと | 行わないこと |
| --- | --- | --- | --- |
| 設計の内容 | `documents/design/*.md` | 選択された文書を読む、clause ID と fingerprint を確定する | 設計本文をこの routine に複製しない |
| capability / skill の順序 | `agents/skills/agent-orchestration.md` と `agents/skills/skill-dependencies.yaml` | owner stage を呼び出す | prompt keyword で capability を決めない |
| implementation handoff | `agents/COMMUNICATION_PROTOCOL.md`、`agents/workflows/implementation-waterfall-workflow.md` | clause map と digest を handoff に載せる | 実装者の代わりに実装しない |
| review | `agents/skills/change-review.md` | forward / reverse coverage と drift を判定対象にする | review policy を再定義しない |
| evidence / validation | 各 design doc の validation route | clause と evidence の readback を残す | 成功メッセージだけで十分条件にしない |
| semantic responsibility allocation | `documents/design/semantic-responsibility-contract.md` と run-local instance | delta action、obligation、primary owner、hard-edge closure を対応付ける | class/module/file の構造 mandate や協調指標を導入しない |

## Related Document Closure

この節が Related Document Closure traversal policy の唯一の canonical owner です。
他の design、skill、root view はこの節の clause/ref と closure receipt を消費します。
設計 owner は handoff 前に、既存 source packet の path、section、clause/ref を使って関連文書を
閉じます。たどる順序は、選択 design の dependency header の upstream/downstream、同 directory
README の reader map、implementation target の dependency headers、validation/runtime owner
docs、parent/root projection docs です。各 request clause、design clause、implementation
target、validation route が forward/reverse で owner に接続されるまで packet を handoff-ready
にしません。

この closure は文書数、深さ、または keyword 探索で切り上げず、未読 edge が次の design/
implementation 判断を変え得る間は owner packet を閉じた状態にします。文書本文の再言語化は
行わず、既存 packet に path、section、clause/ref だけを保持します。実装 worker は owner
design と closure packet を先に読み、change-review は changed path から design、owner、root
projection の reverse drift を read-back します。

closure operation は dependency edge、reader map、target header、validation/runtime owner、
root projection をたどり、request/design/target/validation の forward/reverse join-complete
state に到達します。completion evidence は既存 source packet の path+section+clause/ref
closure receipt です。worker の design-read operation はこの receipt と selected design を
implementation-ready state にし、change-review の reverse-read operation は changed path
から design clause、owner、root projection の reverse-trace-complete state にして、各 readback
を review evidence にします。

semantic responsibility contract の closure は、実装前に active design packet の
`source_refs` から run-local instance を読み、各 delta の action と obligation を
implementation target / validation route に forward-map します。各 obligation は一つの
primary verification owner を持ち、supporting evidence は別 property/role に限ります。
reverse-read では変更 path から semantic grouping と owner evidence を戻しますが、
hard-edge closure は grouping の根拠であり class/module/file の mandate にはしません。

## Exact Data / State Model

### Record

対応レコードは `agent_canon.design_implementation_correspondence.v1` とし、論理的な値を次のように固定します。

```text
CorrespondenceRecord {
  request_id: string
  design_locator: RepoRelativeLocator
  design_sha256: Sha256
  clause_ids: unique nonempty list<ClauseId>
  clause_fingerprints: map<ClauseId, Sha256>
  owner_stage: StageId
  implementation_targets: list<RepoRelativeTarget>
  implementation_targets_sha256: Sha256
  validation_route: list<RepoRelativeCommand>
  validation_route_sha256: Sha256
  state: DICState
}
```

CorrespondenceRecord の top-level field order は厳密に `[request_id,design_locator,design_sha256,clause_ids,clause_fingerprints,owner_stage,implementation_targets,implementation_targets_sha256,validation_route,validation_route_sha256,state]` とする。field の追加、削除、並べ替えは schema drift であり、digest を再計算せず受理しない。

`RepoRelativeTarget` と `RepoRelativeCommand` は次の object field order を持つ。`RepoRelativeTarget=[path,owner_stage,change_kind]`、`RepoRelativeCommand=[argv,cwd,owner_stage]`。target の `path` と command の `cwd` は repository root 基準 `/` 区切りの logical locator とし、`..`、`.`、empty segment、絶対 path、NUL を拒否する。`owner_stage` は lower hyphen-case の `StageId`、`change_kind` は `add|modify|delete` の enum、`argv` は shell command string ではなく順序を持つ token list とする。

canonical scalar は「Unicode NFC 正規化後の UTF-8 string、NUL/CR/LF/control character なし、schema が trim を指定しない限り byte-preserving の文字列」とする。`path`/`cwd` は locator validation、`owner_stage` は lower hyphen-case validation、`change_kind` は enum validation、`argv` 各 token は case を保持して scalar validation を行う。object は上記 field order、target/command list は handoff における意味のある順序を保持し、compact JSON、`ensure_ascii=false`、UTF-8、末尾改行なしで一度だけ serialize する。handoff、manifest、ToolCall、review finding はこの値の ID、digest、論理 locator だけを参照し、同じ identity payload を再シリアライズしません。

`implementation_targets` は変更を許可された `RepoRelativeTarget` の ordered list、`validation_route` はその変更を検証する `RepoRelativeCommand` の ordered list です。各 list は上記 object field order と canonical scalar を使い、canonical JSON の top-level field order `[items]` で一度だけ serialize する。`clause_ids` は NFC 後の canonical ClauseId の bytewise lexical order で重複なく並べ、`clause_fingerprints` は canonical ClauseId key の lexical order で serialize する。全ての list/map は NFC UTF-8 の compact JSON、`ensure_ascii=false`、末尾改行なしとし、空 list/map はそれぞれ exact bytes `[]` / `{}`（whitespace なし）とする。それぞれ domain-separated に `SHA-256(UTF8("agent-canon/design-implementation-correspondence/v1\0implementation_targets\0") + bytes)`、`SHA-256(UTF8("agent-canon/design-implementation-correspondence/v1\0validation_route\0") + bytes)` を計算する。handoff は list の payload 再掲を必要とせず、list reference と対応 digest を運ぶ。実装 owner と reviewer は実際に選択・実行した logical list を read-back して digest と比較し、target の追加・削除・順序変更または validation command の変更を `packet_scope_drift` として扱う。

### State

```text
unresolved -> resolved -> read -> fingerprinted -> handed_off
handed_off -> implementing -> review_ready -> accepted
read|fingerprinted|handed_off|implementing|review_ready -> drifted|blocked
```

`drifted` は設計文書の bytes、clause の text、clause order、owner mapping、または validation route のいずれかが selected fingerprint と異なる状態です。`blocked` は必要な owner / file / evidence が欠けている状態です。

## Invariants

- `DIC-001` repository-changing implementation の前に、変更対象を所有する design document を解決して全文を read-back する。
- `DIC-002` design document が absent、reader path 不明、責務境界不明、clause ID 欠落、implementation trace 欠落、または validation route 欠落なら、implementation handoff を作らず、design を先に create/fix して review する。
- `DIC-003` selected document の bytes と各 clause の canonical text から fingerprint を一度だけ計算し、handoff と review はその ID/digest を参照する。
- `DIC-004` implementation handoff の各 change target は一つ以上の clause ID と一つ以上の validation/evidence locator に対応し、`implementation_targets_sha256` と `validation_route_sha256` を持つ。digest のない list は handoff として不完全である。
- `DIC-005` implementation review は forward coverage（design clause → implementation/evidence）と reverse coverage（changed behavior/path → design clause）の両方を確認する。
- `DIC-006` design fingerprint、owner、target、state、validation route が変わったときは `drifted` とし、design の更新・再読・再レビューまで implementation を停止する。
- `DIC-007` routine は capability owner、adapter、implementation owner の順序を保持し、prose keyword、近接 filename、既存の stale artifact を route verdict にしない。
- `DIC-008` durable artifacts は repository-relative locator を持ち、absolute runtime path は execution state にしか現れない。
- `DIC-009` この routine は case-based loophole、compatibility fallback、第二の design policy、個別 skill への全文複製を追加しない。
- `DIC-010` related-document closure は path/section/clause/ref の source-packet evidence と forward/reverse owner join が揃った時点で handoff-ready になる。

## Side Effects

読取り、clause fingerprint 計算、handoff への参照追加、review readback は deterministic な side effect です。設計修正、implementation write、branch mutation、remote publication は各 owner stage の side effect であり、この routine が直接実行する副作用ではありません。design docs が複数あるときも、所有境界ごとに canonical document を選び、同一 clause payload を複数の artifact に埋め込みません。

## Failure Semantics

| failure | state | next action |
| --- | --- | --- |
| `design_missing` / `design_incomplete` | `blocked` | owner document を作成・補完し、design review 後に再読する |
| `owner_ambiguous` | `blocked` | canonical owner map を解決するまで target を選ばない |
| `clause_fingerprint_mismatch` | `drifted` | design を更新して fingerprint を再発行する。実装を継続しない |
| `implementation_target_digest_mismatch` / `validation_route_digest_mismatch` | `drifted` | 実行前に packet を再生成し、対象と検証 route を再レビューする |
| `forward_coverage_missing` / `reverse_coverage_missing` | `blocked` | handoff または design trace を補完して review を再実行する |
| `absolute_locator_in_durable_artifact` | `blocked` | logical locator に置換し、execution-time resolver の readback を行う |
| `keyword_only_capability_route` | `blocked` | typed capability owner の route packet を使い、prose route を破棄する |

失敗時は既存の設計、実装、manifest、readback を上書きせず、typed finding と対象の ID/digest を返します。失敗を warning に格下げする条件はありません。

## Stage Ownership and Procedure

1. `agent-orchestration` が request mode、owner、replaceable unit、implementation mechanism、validation route を固定する。
2. 選択された owner が `design_locator` を解決し、DIC-001/002 と `Related Document Closure` に従って design、dependency edges、reader map、target/validation/root owner refs を読む。
3. `oop-type-design` または該当 design owner が clause IDs、責務境界、state/invariant、implementation trace を固定する。
4. handoff owner が `design_sha256`、clause fingerprints、allowed targets と `implementation_targets_sha256`、validation route と `validation_route_sha256`、reverse-coverage expectation を一つの参照 packet にする。
5. implementation owner は各 change を clause ID に結び付け、追加の design divergence を作らない。
6. change-review owner が forward/reverse coverage、fingerprint、logical locator、owner order を read-back する。
7. drift または coverage gap があれば `blocked` とし、design update/review を経てから handoff を再発行する。

## Validation / Readback

最小の validation route は次です。

```bash
python3 tools/agent_tools/check_design_doc_claims.py --root . --recursive-depth 3 <design-doc>
python3 tools/agent_tools/check_dependency_headers.py --changed
python3 tools/agent_tools/check_agent_runtime_alignment.py
tools/bin/agent-canon docs check
```

レビュー時の readback は、(a) selected design bytes と `design_sha256`、(b) clause ID 集合と個別 fingerprint、(c) changed path/behavior と clause ID、(d) `implementation_targets` とその digest、(e) `validation_route` とその digest、(f) evidence locator の six-way join が完全であることを確認します。未実装の planned owner は `planned` と明記し、current evidence と混同しません。

## Evidence And Assumption Ledger

| kind | statement | evidence / owner | status |
| --- | --- | --- | --- |
| assumption | `正規化` は canonical scalar に定義した Unicode NFC、UTF-8、control/NUL 拒否、schema-defined validation の手順を指す | `RepoRelativeTarget` / `RepoRelativeCommand` canonical scalar contract above | explicit |

## Design-To-Implementation Trace

| clause | current/planned implementation owner | file / symbol | evidence / reverse rule |
| --- | --- | --- | --- |
| `DIC-001..DIC-009` | current workflow and review owners | `agents/skills/agent-orchestration.md`, `agents/skills/oop-type-design.md`, `agents/skills/change-review.md`, this routine | changed path must cite one DIC clause; missing design readback blocks |
| `DIC-003..DIC-004` | planned transport owner | `tools/agent_tools/bootstrap_agent_run.py`, `agents/COMMUNICATION_PROTOCOL.md` | handoff identity、`implementation_targets`、`validation_route` は各 digest で参照し、実行 readback は両 digest を再計算する |
| `DIC-005..DIC-006` | current/planned review owner | `agents/skills/change-review.md`, `tools/agent_tools/check_design_doc_claims.py` | every accepted finding has forward and reverse evidence; drift is a blocker |
| `DIC-007..DIC-008` | current routing/path owners | `tools/agent_tools/route.py`, `tools/agent_tools/agent_canon_source_root.py` | capability and locator changes map back to the clause that authorized them |
| `DIC-009` | current canonical-document owners | `agents/internal-routines/`, `agents/skills/`, `documents/design/` | a new policy copy or loophole maps to a rejected design change |
| `DIC-010` | current DIC routine | this routine only; owner surfaces consume `DIC-010` path/section/clause/ref receipts | dependency headers, README map, target headers, validation/runtime docs, and root projections close the forward/reverse source packet |

Reverse mapping rule: any future implementation change that touches a path, schema, state transition, owner order, serialization, or validation command named by this routine must select a clause ID before editing; any clause with no current/planned owner or evidence is a design gap, not an implementation TODO. This table is the universal correspondence index; stage documents add only their owner-specific route.

## Clause IDs

この routine の clause ID は `DIC-001` から `DIC-010` です。新しい clause はこの文書と対応する design trace を同一変更で更新し、個別 skill に同じ規則を再掲しません。
