# dependency-analysis

<!--
@dependency-start
contract skill
responsibility Documents dependency-analysis for this repository.
upstream design ../../documents/design/dependency-manifest-design.md defines dependency manifest format and tools
upstream design ../canonical/CODEX_WORKFLOW.md defines workflow gate usage
upstream design ./catalog.yaml registers this public skill
upstream design ../../documents/tools/lsp_code_analysis.md owns LSP relation evidence and capability limits
upstream implementation ../../tools/analysis/dependencies/scan_code_dependencies.sh extracts file-level code dependency evidence
upstream implementation ../../tools/analysis/code/helper_function_inventory.py extracts Python function-level call graph context
upstream implementation ../../tools/validation/semantic/documents/check_design_doc_claims.py validates design-document evidence claims
@dependency-end
-->

## Reader Map

- Purpose: collect dependency-header, graph, code-dependency, and
  change-impact evidence before choosing or validating edit scope.
- Section path: for every code change, start with LSP-First Recursive Context
  before editing; Cause Investigation Surface and Root-Cause Repair Scope own
  cause repair. Required Commands, Interpretation, and Change Impact Packet
  supply the selected dependency evidence and handoff details.
- Use when: preparing any code edit, or when dependency manifests, changed-file
  gates, graph edges, reverse edges, design claims, or repair packets are needed.
- Boundary: code dependency evidence and dependency-header evidence remain
  separate until summarized in a structured Change Impact Packet.
  Repository-wide dependency graph projection and rendering is owned by
  `$code-visualization`, which receives the canonical `tool_call` envelope and
  `render_dependency_manifest_graph` coverage checks.

## Purpose

依存 manifest の header / scan / format / graph tool と、実コード依存 scanner を目的別に起動します。
code dependency と header dependency は別 evidence として扱い、修正箇所選定や subagent handoff では両方を structured `Change Impact Packet` manifest に統合します。大量の依存情報そのものは artifact path に置き、LLM-visible context には判断に必要なコード本文・契約の selected excerpt、summary、source locator と artifact path を載せます。

## Use When

- コードを追加・修正・削除する前に、LSP で関連箇所を再帰的にたどり、本文・契約・tests を作業コンテキストへ取り込む
- 依存 header / manifest / graph を確認したい
- `@dependency-start` / `@dependency-end` block を追加・修正した
- dependency edge、reverse edge、kind、cycle の問題を診断したい
- closeout 前に dependency manifest evidence を揃えたい
- 修正箇所の妥当性検証のため、import / include / source 関係を header dependency と別に確認したい
- code 変更の commit evidence として、file-level dependency と関数 / public entrypoint 単位の call-site evidence を揃えたい
- repo-wide search の responsibility-based candidate と bounded `git grep` hit から、どの file を編集・確認すべきか dependency graph で展開したい
- design document の implementation-backed claim、DSL / standard-form assumption、parent-doc alignment を dependency header evidence と比較したい
- requested object / file / finding を変える前に、call site、依存先、依存元、tests、docs、config、log / Info 面をまとめた影響範囲 packet を作りたい
- refactor-loop や implementation subagent に渡す repair batch / handoff context を機械的に作りたい

## Required Commands

Code dependency surface:

```bash
bash tools/analysis/dependencies/scan_code_dependencies.sh --changed
```

Function-level Python dependency surface:

```bash
python3 tools/analysis/code/helper_function_inventory.py --changed --all-functions --format json
```

Changed-file gate:

```bash
python3 tools/validation/semantic/dependencies/check_dependency_headers.py --changed
bash tools/analysis/dependencies/scan_dependency_headers.sh --changed --fail-missing
bash tools/validation/semantic/dependencies/check_dependency_header_format.sh --changed --require-header
```

Graph check when edges changed:

```bash
bash tools/analysis/dependencies/check_dependency_graph.sh --changed --print-edges
```

Strict reverse-edge check when that is the migration target:

```bash
bash tools/analysis/dependencies/check_dependency_graph.sh --changed --print-edges --check-bidirectional
```

Full migration inventory:

```bash
bash tools/analysis/dependencies/scan_dependency_headers.sh
bash tools/analysis/dependencies/check_dependency_graph.sh --print-edges
```

Responsibility-first search-to-edit-scope expansion:

For code edits, use the LSP traversal below before choosing edit scope. Search
and header-graph results supplement its inspected code context.

```bash
printf '%s\n' "search purpose or user request" > reports/search_query.txt
agent-canon semantic-index context-pack \
  --query-file reports/search_query.txt \
  --max-cells 12 \
  --format text \
  > reports/search_responsibility_context.txt
git grep -l "search phrase" -- <responsibility-scoped dirs> > reports/search_hits.txt
bash tools/analysis/dependencies/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --search-hits-file reports/search_hits.txt
```

Design-document claim evidence gate:

```bash
python3 tools/validation/semantic/documents/check_design_doc_claims.py \
  --root . \
  --recursive-depth 3 \
  documents/design/<topic>.md
```

or through the dependency review wrapper:

```bash
bash tools/analysis/dependencies/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --check-design-doc-claims
```

For an explicit design document:

```bash
bash tools/analysis/dependencies/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --check-design-doc-claims \
  --design-doc-claim-path documents/design/<topic>.md
```

## LSP-First Recursive Context

Activate this procedure before the first code edit, including direct cause fixes,
renames, deletions, private helpers, and test changes. Its purpose is to establish
the mechanism and complete affected contract before selecting a correction.
Use the existing [LSP command owner](../../documents/tools/lsp_code_analysis.md#recursive-context-collection)
through the repository's configured execution route. Reuse already inspected LSP
context while its source and query premises remain current.

1. Seed the current source snapshot with the requested symbols and their owning
   files. For a new symbol, start from the existing owner, extension point, callers,
   and relevant tests. Invoke LSP first; use its available symbol navigation to
   resolve seeds and bound any necessary text search to missing source locations.
2. Follow supported definitions, references, and incoming/outgoing calls, plus type
   and implementation relations exposed by the selected LSP surface. Read the
   reached bodies, governing types/contracts, and affected tests. Inspect source
   for relations the tool cannot expose, keeping that evidence distinct from LSP.
3. Recursively expand each newly relevant symbol with the same queries and source
   reading. Keep a worklist and deduplicate by repository, source snapshot, path,
   and symbol/range so cycles reuse inspected context. Continue in batches until
   each relevant frontier is inspected or an inspected unchanged contract explains
   why the change cannot propagate across it. Batch/token limits organize delivery;
   continue outstanding work rather than declaring a fixed depth complete.
4. Put decisive code and contract excerpts into working context with revision,
   path, symbol, line range, relation to the target, and the behavior/obligation
   they establish. Retain the relevant tests and unresolved questions alongside
   them. Artifact paths, symbol names, and graph edges locate evidence; the actual
   inspected content and its meaning support the edit and any handoff.
5. Select the complete correction from that context, edit the owning mechanism
   and affected uses, then refresh changed symbols and their relevant relations.
   Expand newly affected paths before further edits and run targeted validation.
   Reuse unchanged context and load instruction documents at their own activation
   points; this recursion follows relevant code semantics.

Record query scope and actual capability/status. A successful empty query supports
only that scope; unsupported, failed, partial, or truncated results leave explicit
gaps. Follow the existing owner for the next required investigation or verification,
record failed attempts in the owning topic memo or authorized log, and continue
independent authorized work. Preserve the fixed execution route and distinguish
source/test evidence from LSP evidence. Close required gaps before claiming verified
coverage. Use the existing task/Change Impact Packet; this adds no schema or checker.

## Cause Investigation Surface

Dependency evidence is used to investigate the cause before it is used to
propose a fix when causal ambiguity remains unresolved, or when an
evidence-linked alternative could change the owner, fix surface, or validation
route. A straightforward finding with a type, schema, parser, compiler, state
invariant, or targeted reproduction proving one cause may use a compact direct
cause proof instead; no additional cause-evidence note is required. Rejected,
duplicate, already-covered, and unreachable findings retain their
reason/evidence without activating cause investigation.

The final goal of code-cause investigation is to pinpoint one concrete causal
location in the code for the investigated failure. Record the source snapshot,
file path, symbol, and exact expression, branch, call, state update, or smallest
relevant block with its line range in the existing cause note or direct cause
proof. For missing logic, identify the concrete point where the owning code
fails to meet its obligation. A module name, candidate list, stack frame, or
error/log emission site alone is not cause identification.

Explain the reachable triggering input/state, the governing contract, and how
that operation or omission produces the observed failure. Support this causal
chain with source/specification evidence, mathematical or engineering reasoning,
or targeted observations; a sufficient static proof does not require an extra
run. Distinguish the causal location from where its effects become visible.
Keep relevant interactions explicit and independent failures separate; do not
invent one culprit merely to satisfy the goal. An unresolved location or causal
chain remains `cause_unproven`: retain the candidates, missing evidence, and
next discriminating check instead of declaring the search complete.

Use [LSP-First Recursive Context](#lsp-first-recursive-context) while establishing
the cause and affected contract, then follow
[Root-Cause Repair Scope](#root-cause-repair-scope-after-cause-selection) to correct
the owner and related defects. A direct cause proof reuses that context; it still
precedes the first code edit. Keep evidence in the existing note and handoff.

For an activated packet, record a compact cause-evidence note before the
action. It has no fixed schema or candidate count: expand the
changed target through evidence-linked edges and record the applicable evidence
needed to establish:

- `Observation` and the current source snapshot;
- `Incoming Callers/Entrypoints`: callers, public imports, dispatchers,
  parsers, workflow triggers, and configuration entrypoints that can reach the
  target;
- `Owning Mechanism/State/Guards`: the state owner, transition/mechanism,
  invariants, guard predicates, and duplicated or over-strict checks;
- `Downstream Consumers/Side Effects/Cleanup`: consumers, writes, process or
  resource effects, failures, rollback, and cleanup paths;
- `Sibling Implementations/Tests/Docs/Config`: comparable code and all
  evidence-linked test, documentation, and configuration surfaces;
- `Temporal Evidence`: latest remote/default branch, Issue/PR, and branch
  history only when snapshot drift or a recent/stale surface is plausible;
- `Reachability and Overcheck Analysis`: proof or targeted evidence for each
  disputed branch or guard. A statically impossible branch is recorded as
  `reason_code=unreachable_branch`; an unnecessary or duplicate guard is
  recorded as `reason_code=overcheck`;
- `Alternative Disposition`, `Selected Cause`, `Expected Mechanism`, and
  `Action Derivation` connecting the cause to the owner, fix, contract, and
  validation route.

These are evidence dimensions rather than a mandatory ceremony for every
packet. Mark an inapplicable dimension as bounded when that is supported by the
evidence; do not manufacture a caller, side effect, sibling, or history search.

The breadth is evidence-driven: do not impose an arbitrary full-repository
scan or fixed candidate count. For code causes, stop only when the concrete
causal location and chain above are established and every alternative that
could change the owner, fix surface, or validation is disconfirmed or bounded.
A static type/schema/parser/compiler/state invariant may establish a single
cause; record its concrete location and why the narrower traversal is complete.
Do not turn a symptom into a fix merely because its file appears in the search
result. Derive the complete owning correction and targeted validation from the
supported cause and pre-edit LSP context. Reuse already inspected relations;
expand the remaining relevant frontier before editing.

The cause-to-action sequence is ordered, not a list of independent checks:

1. Record the observed failure or request and the source snapshot.
2. Classify the finding. A direct type/schema/parser/compiler/state-invariant
   proof may go straight to `direct_cause_proof`; a duplicate,
   already-covered, or unreachable finding may close with its reason and
   evidence. Those dispositions do not require a new cause search.
3. When the cause is not direct or a plausible alternative could change the
   owner, fix surface, or validation route, search the evidence-linked callers,
   owning mechanism, consumers, side effects, cleanup, and sibling surfaces.
4. Compare only alternatives that could change that decision and record each
   as `disconfirmed`, `bounded`, or selected with its supporting evidence.
5. Complete the relevant pre-edit LSP context, including for a direct cause
   proof, then correct the causal owner and affected uses through the sequence
   below. An unresolved cause remains investigation work until the mechanism
   and required correction are established.

## Root-Cause Repair Scope After Cause Selection

Use this order: LSP-first recursive context and cause identification, complete
owning correction, refreshed relation context, and targeted validation.

1. Use [LSP-First Recursive Context](#lsp-first-recursive-context) to inspect the
   cause, relevant callers/callees, types/implementations, and tests/contracts
   before editing. Select the complete correction from that evidence.
2. Correct the identified expression, branch, call, state update, or missing
   operation at its owner, together with affected uses. Preserve the governing
   contract with the simplest sufficient change. A relation identifies code to
   inspect; repair concrete defects while retaining sound related code.
3. Refresh the affected LSP relations after edits and inspect newly affected
   code before further repair. Correct broken calls, incompatible contracts,
   and affected state/failure behavior in the same change. Preserve the complete
   responsibility unit and explicit read-only/write-authority boundaries.
4. Run the existing formatter and targeted validation for the final changes.
   Complete the repair when the cause is fixed and the inspected related paths
   have no unresolved problems caused by that defect or its correction. Record
   actual changes, pre-edit and refreshed relation evidence, validation, and
   remaining verification in the existing Issue/PR.

LSP establishes symbol relations; actual source, contracts, and targeted checks
establish behavior. Apply the capability, failure, and coverage handling from the
pre-edit procedure throughout repair and verification.

## Interpretation

- code dependency は実 import / include / source 関係、header dependency は design / implementation / environment / test の明示文脈です。混ぜずに別々の evidence として記録します。header edge を実行・build reachability や caller の証拠に読み替えず、code edge を design ownership や文書の正本性に読み替えません。両者を結合するのは Change Impact Packet の影響範囲整理だけです。
- Python code 変更では、`helper_function_inventory.py --changed --all-functions` を関数 / class / method 単位の evidence として使います。この tool は変更 Python file を報告対象にしつつ、whole-repo call graph context から direct callers / callees を保持します。変更 Python file count が 0 件の場合は `HELPER_INVENTORY_FILES=0` を scope evidence にします。
- 最初のコード編集前に [LSP-First Recursive Context](#lsp-first-recursive-context) で関連コード・契約・tests を再帰的に読み、原因と変更単位を確定して [Root-Cause Repair Scope](#root-cause-repair-scope-after-cause-selection) へ進みます。`scan_code_dependencies.sh` の実コード依存と header dependency の design / docs / tests は区別します。
- `required_action` や solution proposal より先に causal ambiguity と owner / fix / validation を変え得る alternative の有無を判定します。該当時だけ cause-evidence note を完成させ、incoming callers/entrypoints、owning mechanism/state/guards、downstream consumers/side effects/cleanup、sibling implementations/tests/docs/config を evidence-linked にたどります。straightforward finding は direct cause proof、rejected/duplicate/already-covered/unreachable finding は reason/evidence だけで閉じます。snapshot drift が原因候補になり得る場合だけ latest remote/Issue/branch history を追加します。
- 原因探索の最終目標は、原因となるコードの具体的な一か所の特定です。[Cause Investigation Surface](#cause-investigation-surface) に従い、source snapshot、path、symbol、該当行/block と、入力/状態から現象に至る因果根拠を既存記録に残します。候補一覧・原因分類・症状の発生地点だけでは完了しません。一か所と因果関係を特定し、判断を変え得る代替を disconfirmed / bounded にしたら、その原因箇所の修正へ進みます。十分な静的根拠に追加実行を要求せず、未特定は `cause_unproven` とし、根拠なく一つに断定しません。
- activated packet の `required_action` は `Selected Cause` と `Expected Mechanism` から、straightforward packet の action は direct cause proof から導出します。症状だけの修正提案は `cause_unproven` として保留します。発生不能な分岐と過剰・重複ガードは、`reason_code=unreachable_branch|overcheck` と証拠を残して review 対象から除外します。
- コード改善の修正箇所を選ぶ task では、この skill の `LSP-First Recursive Context`、`Cause Investigation Surface`、`Root-Cause Repair Scope` に従って `Observation`、`Hypothesis`、`Expected Mechanism`、`Candidate Comparison`、`Disconfirming Evidence`、`Support Evidence`、`fix_surface_validated=yes` を実装前に固定します。
- 原因修正後は編集前の LSP context を更新し、新たに影響する関連の確認・必要な修正・対象検証を行い、`Post-Change Evidence` と `Hypothesis Decision: supported|rejected|inconclusive` を残します。`rejected` または `inconclusive` の場合は、同じ実装 pass を広げず次仮説へ戻します。
- changed-file header / scan / format failure は fix-now blocker です。
- default graph failure は孤立 manifest、自己参照、または cycle を示すため fix-now blocker です。
- `run_repo_dependency_review.sh --report-dir` は dependency header 由来の `dependency_graph.tsv` を生成します。
- search result を編集対象に変換するときは、responsibility-based context、bounded `git grep` hit、`dependency_edit_scope.txt` の `DEPENDENCY_EDIT_SCOPE_PATH` を issue / PR evidence に残します。raw text-search hit だけで編集対象を決めません。
- design document を修正または作成するときは、major claim の code / path token、初出 DSL / standard-form terms、parent-doc alignment を `Evidence And Assumption Ledger` に接続し、`check_design_doc_claims.py` の finding を design evidence gap として扱います。
- Dockerfile や environment file を universal anchor にしません。実際に Docker、CI、requirements、runtime configuration に依存する file だけ `environment` edge を使い、それ以外は [AGENTS.md](../../AGENTS.md)、`README.md`、directory README、workflow/design doc、tool index、skill guide などの nearest true canon anchor に接続します。
- `--check-bidirectional` の full-repo failure は、reverse-edge 移行期間中は baseline として扱えます。ただし pass とは呼びません。
- baseline 扱いにする場合も、今回差分で old-format header、自己参照、reverse edge 欠落、kind mismatch、cycle を増やしていないことを review artifact に残します。

## Change Impact Packet

`dependency-analysis` は、依存 evidence を集めるだけでなく、修正計画の入力になる
structured `Change Impact Packet` manifest の正本です。これは LLM が依存
graph 全体を prose 化する場所ではありません。tool output は JSON / TSV /
Markdown artifact として保存し、packet には path、count、object id、現在の
repair batch に必要な selected excerpt と structured summary を載せます。`refactor-loop`、
implementation handoff、原因仮説の fix-surface 選定では、raw text-search hit、raw
finding、単一 file 名だけを subagent に渡しません。コード変更では最初の編集前に
LSP で関連箇所を再帰的に読み、本文・契約・tests と因果根拠を同じ context / packet
へ取り込みます。編集後は影響する関連と必要な追加修正を更新します。
既存の記録へ集約し、全項目を埋める追加の帳票作成は要求しません。

Change Impact Packet の scope candidates や repair slices を形成する前に、
code-cleanup から渡された一つの shared current+historical asset universe を
受け取ります。対象は current module/helper/type/test/docs です。code split /
extraction または suspected predecessor の現行欠落なら `git log`、`-S`、deleted
paths、prior PR / Issue、predecessor tests を必ず走査し、該当 asset refs を packet
へ入れます。bounded non-split edit では historical scan を要求しません。
各 candidate は既存 handoff packet の `reuse_survey` として
`reuse`、`extend`、`restore`、`consolidate`、`replace`、`delete`、`reject` の
いずれかへ決め、`asset_path` ごとに一度だけ記録します。これは advisory
context であり、不在は dispatch / write を block しません。
責務 slice は decision 済み asset から導き、同じ asset を含む slices を merge
してから、同じ asset context と `test_paths` を `refactor-loop` と全 child へ渡します。
known な `allowed_paths` は各 child の role / module に応じて個別に導出し、context が
ない場合も既存 route は継続します。

### Conditional cross-module resolution

Decomposition、prototype、または write-capable worker handoff の前に、対象が
二つ以上の involved Git roots / modules にまたがるか、単一 module でもその
変更契約を消費する dependency repository があるかを判定します。該当しない
単一 module の変更は既存の fast path とし、cross-module survey は要求しません。

該当する場合だけ、involved roots に限定して、各 root の `.gitmodules`、
dependency / package / build manifest、import / include / source / build edge、
public API / consumer edge、gitlink / pin edge を調査します。gitlink / pin edge
は code / build / API edge と区別し、どの repository と consumer を結ぶかを
Change Impact Packet の既存 `dependency_dag`、`dependency_scope`、
`repair_batches`、`reuse_survey`、`validation_route`、`allowed_paths` /
`subagent_handoff_context` に記録します。新しい packet schema、承認、検査 gate
は作りません。

未解決 edge または cycle は実装を進める理由ではなく、design / order issue として
残します。実行順は source repository change / publication、dependent repository
update / validation / publication、parent gitlink pin / projection / validation
の topological order とします。involved-root identities、edge kinds、topological
order、dependency scope / reuse facts、common validation obligations は全 child に
同一の shared context として渡します。各 child の role / module に固有の
`allowed_paths`、`do_not_read`、write scope、exact validation commands は、その
shared context と child owner から個別に導出します。child ごとの再調査や別の
依存解釈を作りません。

Packet には次を含めます。

- `requested_target`: `path:start-end:qualname`、file、または finding id
- `code_dependency_surface`: static に見える import / include / source edge、
  function / public entrypoint 単位の direct callees、direct callers、re-export / public import surface
- `header_dependency_surface`: dependency manifest の upstream / downstream
  design、implementation、environment、test、workflow edge
- `search_surface`: responsibility-based context、text search が seed の場合の
  bounded `git grep -l` hit、`dependency_edit_scope.txt`
- `structural_surface`: `tool-finding-report` や structural checker が seed の
  場合の full finding packet、priority order、repair slice
- `tests_docs_config_log_info_edges`: test、doc、config、log、Info など code 以外の
  同時編集または review surface
- `unknown_dynamic_edges`: JAX / equinox / runtime dispatch / reflection など、
  static evidence だけでは未確定の edge
- `impact_blocks`: tool が連結した依存 component、dependency depth、責務 group、
  validation surface で機械生成する block。各 block には `block_id`、root
  targets、downstream targets、evidence artifact path、`blocked_by`、
  `parallel_safe`、allowed files、validation、non-goals を付けます。
- `scope_candidates`: 同じ影響範囲に対する候補粒度。object 単位、module 単位、
  responsibility group 単位、root contract + representative consumer 単位などを
  tool が列挙します。
- `selected_scope`: 選んだ粒度と、その評価値。wave 数、想定 tool rerun 数、
  write conflict risk、token budget、validation cost、semantic risk を記録します。
- `repair_batches`: `impact_blocks` から導く、依存の根本側から順に直す
  sequential root batch と、root 修正後に並列化できる downstream batch。
- `subagent_handoff_context`: 各 target object の current problem、intended
  structural change、forbidden semantic delta、validation signal、期待する
  final response format

code dependency と header dependency は packet 内でも section を分けます。
一本化するのは「実装者へ渡す計画 artifact」であり、edge の意味を混同しません。
影響範囲の block 化は tool の責務です。LLM は tool-generated block を受け取り、
必要に応じて accept、split、merge、`review_required` を判断します。その場合も
元の `block_id`、分割/統合理由、追加確認した artifact path を残します。
node の粒度も固定値ではなく最適化対象です。最もよい scope は「大きいほどよい」
でも「縮めるほど安全」でもなく、behavior contract が明確で、write conflict がなく、
token 予算に収まり、1 つの coherent な validation surface で確認できる最大の block
です。semantic risk、ownership、validation isolation が崩れる場合だけ block を縮めます。
LLM が full artifact を読むのは、現在の repair batch、争点になった edge、review
で根拠確認が必要な箇所に限定します。

Python structural finding を seed にする場合は、`tool-finding-report` が作った
full `python-structure-hash-report` JSON と `run_repo_dependency_review.sh` の
report directory を次の tool に渡します。

```bash
agent-canon python-structure-hash-scope-plan \
  --input <python-structure-hash-report.json> \
  --dependency-report-dir <dependency-review-dir> \
  --output <change-impact-packet.json>
```

この JSON は `Change Impact Packet` の機械生成正本です。親 agent はその中の
`impact_blocks`、`scope_candidates`、`selected_scope`、`repair_batches`、
`subagent_handoff_context` を使って orchestration plan を作ります。

## Core References

- [documents/design/dependency-manifest-design.md](../../documents/design/dependency-manifest-design.md)
- [agents/skills/change-review.md](change-review.md)
- [agents/canonical/CODEX_WORKFLOW.md](../canonical/CODEX_WORKFLOW.md)
- [templates/agents/closeout_gate.md](../../templates/agents/closeout_gate.md)

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Before any code edit, activate [LSP-First Recursive Context](#lsp-first-recursive-context), including for a direct cause fix. Reuse its inspected source context through planning, implementation, handoff, and review.
1. Read [documents/design/dependency-manifest-design.md](../../documents/design/dependency-manifest-design.md).
1. If the task selects or justifies a fix surface, read this skill's `Cause Investigation Surface` and `Root-Cause Repair Scope`; use `change-review` for the findings-first review after the owner is selected.
1. For code-improvement work, do not implement until the artifact records `Observation`, `Hypothesis`, `Expected Mechanism`, `Candidate Comparison`, `Disconfirming Evidence`, `Support Evidence`, and `fix_surface_validated=yes`.
1. Apply [Cause Investigation Surface](#cause-investigation-surface) before deriving
   an action: use its conditional cause-evidence note or direct cause proof,
   preserving the reason/evidence-only dispositions. Identify the concrete causal
   location and supported mechanism using the pre-edit LSP context, then follow
   [Root-Cause Repair Scope](#root-cause-repair-scope-after-cause-selection) to correct
   the owner and affected uses. Refresh relevant LSP context after the changes.
1. After the cause fix, refreshed LSP context, related repairs, and targeted validation, record `Post-Change Evidence` and `Hypothesis Decision: supported|rejected|inconclusive`. If the decision is `rejected` or `inconclusive`, return to hypothesis selection instead of expanding the implementation pass.
1. Choose the mode that answers the task without hiding dependency evidence:
   - code dependency surface: run `scan_code_dependencies.sh`
   - changed-file closeout gate: use `--changed`
   - explicit file review: pass file paths explicitly
   - repo migration inventory: run full scan without `--changed`
   - dependency edge change: include graph validation
   - repo-wide search triage: run responsibility-based search first, then use bounded `git grep -l` only as comparison evidence or within selected source surfaces before search-to-edit-scope expansion
   - design-document evidence: run `check_design_doc_claims.py` on changed or newly authored design docs
   - repair planning or subagent handoff: build a structured `Change Impact
     Packet` manifest before selecting implementation targets
1. Use the `Required Commands` and `Change Impact Packet` sections above for
   code and header evidence; preserve those surfaces separately when building
   the packet.
