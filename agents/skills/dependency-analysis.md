# dependency-analysis

<!--
@dependency-start
contract skill
responsibility Documents dependency-analysis for this repository.
upstream design ../../documents/design/dependency-manifest-design.md defines dependency manifest format and tools
upstream design ../canonical/CODEX_WORKFLOW.md defines workflow gate usage
upstream design ./catalog.yaml registers this public skill
upstream design ../../documents/tools/lsp_code_analysis.md owns LSP relation evidence and capability limits
upstream implementation ../../tools/analysis/dependencies/scip_index.py owns native SCIP index and bounded query operations
upstream implementation ../../tools/analysis/code/helper_function_inventory.py provides Python helper-role and naming evidence
@dependency-end
-->

## Reader Map

- Purpose: collect dependency-header, graph, code-dependency, and
  change-impact evidence before choosing or validating edit scope.
- Section path: Purpose and Use When explain the trigger; Required Commands
  lists the operational tool surface; Interpretation, Change Impact Packet, and
  Core References define how selected outputs feed planning and handoff.
- Use when: dependency manifests, changed-file gates, graph edges, reverse
  edges, source references, or repair-planning packets are needed.
- Boundary: code dependency evidence and dependency-header evidence remain
  separate until summarized in a structured Change Impact Packet.
  Repository-wide dependency graph projection and rendering is owned by
  `$code-visualization`, which receives the canonical `tool_call` envelope and
  `render_dependency_manifest_graph` coverage checks.

## Purpose

依存 manifest の header / scan / format / graph tool と、必要時の SCIP index/query を、依存関係が判断に影響するときだけ目的別に起動します。
code dependency と header dependency は別 evidence として扱います。Change Impact Packet を使う cross-surface 修正計画や handoff では両者を別 section に記録し、選択範囲に必要な excerpt と summary だけを載せます。局所修正の対象選定に packet は要求しません。

## Use When

- 依存 header / manifest / graph を確認したい
- `@dependency-start` / `@dependency-end` block を追加・修正した
- dependency edge、reverse edge、kind、cycle の問題を診断したい
- closeout 前に dependency manifest evidence を揃えたい
- repository-wide symbol/reference evidence が修正範囲を変え得るため、native SCIP indexを明示的に使いたい
- Python helperのrole/name evidenceが設計判断に必要で、helper inventoryのproperty-specific結果を確認したい
- repo-wide search の responsibility-based candidate と bounded `git grep` hit から、どの file を編集・確認すべきか dependency graph で展開したい
- design document の implementation-backed claim、DSL / standard-form assumption、parent-doc alignment を dependency header evidence と比較したい
- 明示された cross-module/API migration の影響 evidence を整理したい
- refactor-loop や implementation subagent に渡す repair batch / handoff context を機械的に作りたい

## Required Commands

Choose commands from the question and affected surfaces below; these are
conditional routes, not one command sequence. A changed-file gate applies when
changed headers or their gate are in scope, graph checks when edges change, and
a full migration inventory only for a repository-wide migration question.

SCIP index/query surface. Use only when repository-wide symbol/reference evidence can change scope:

```bash
python3 tools/analysis/dependencies/scip_index.py query \
  --root . \
  --runtime-root <external-runtime-root> \
  --index <runtime-relative-path>/index.scip \
  --path <source-path>
```

Build an index only when the project owner supplies the required language input.
See [SCIP index and query](../../documents/tools/scip_index.md) for the selected
Python environment, C/C++ compile-database, and output arguments; languages
without a qualified native producer remain unsupported.

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

Design documents use ordinary prose and Markdown links to identify source and
governing references. Read those sources directly at the selected revision;
`agent-canon docs check` owns local-link and Markdown validation. No separate
claim-token or evidence-ledger parser is part of this dependency route.

## Cause Investigation Surface

Dependency evidence is used to investigate the cause before it is used to
propose a fix when causal ambiguity remains unresolved, or when an
evidence-linked alternative could change the owner, fix surface, or validation
route. A straightforward finding with a type, schema, parser, compiler, state
invariant, or targeted reproduction proving one cause may use a compact direct
cause proof instead; no additional cause-evidence note is required. Rejected,
duplicate, already-covered, and unreachable findings retain their
reason/evidence without activating cause investigation.

For cause investigation, start with the target code, current diff, and governing
contract. Pinpoint the expression, branch, call, state update, or smallest
relevant block that fails its obligation, and explain how the observed input/state
produces the failure. A module name, candidate list, stack frame, or error/log
emission site alone is not cause identification.

Support the cause with source/specification evidence, mathematical or engineering
reasoning, or targeted observations; sufficient static proof does not require an
extra run. Distinguish the cause from where its effects become visible. Keep
independent failures separate. An unresolved cause remains `cause_unproven`;
preserve its uncertainty in the existing record.

Fix the identified causal location next; identification is not a separate
stopping point. Then compare the target diff with the required behavior, run the
selected validation, and report the result. Use the existing note and handoff;
do not add a schema, checker, or report.

When causal alternatives could change the owner, mechanism, or validation, record
the observed input/state, source location, relevant supporting or refuting
evidence, and resulting action in the existing note. Keep the record limited to
what establishes that decision; do not create fields or a packet for a direct
cause proof.

Do not impose a full-repository scan or fixed candidate count. Stop when the
cause and its relevant input/state are established and decision-changing
alternatives are resolved or recorded as uncertain.
A static type/schema/parser/compiler/state invariant may establish a single
cause; record its concrete location and evidence.
Do not turn a symptom into a fix merely because its file appears in the search
result. Derive the immediate owning edit and its targeted validation from the
supported cause.

The cause-to-action sequence is ordered, not a list of independent checks:

1. Record the observed failure or request and the source snapshot.
2. Classify the finding. A direct type/schema/parser/compiler/state-invariant
   proof may go straight to `direct_cause_proof`; a duplicate,
   already-covered, or unreachable finding may close with its reason and
   evidence. Those dispositions do not require a new cause search.
3. Compare only alternatives that could change the owner, fix, or validation,
   and record their evidence in the existing note when needed.
4. Fix the concrete causal location using the supported mechanism. An unresolved
   cause stays analysis work; it does not become a symptom-level action or a
   completed cause search.

## Root-Cause Repair Scope After Cause Selection

For a local cause repair, fix the identified cause, compare the target diff with
the required behavior, run the selected validation, and report the result.

1. Correct the identified expression, branch, call, state update, or missing
   operation at its owner. Preserve the governing contract with the simplest
   sufficient change. Do not suppress the symptom with a wrapper, compatibility
   shim, weakened oracle, or caller workaround that leaves the root cause intact.
2. Inspect the final target diff against the required behavior and contract.
3. Run the selected validation and report the observed result, changes, and
   remaining uncertainty in the existing Issue/PR. Preserve explicit read-only
   and write-authority boundaries.

LSP establishes symbol relations, not program correctness. Check the actual
contracts and behavior at those locations. Preserve unsupported/failed/partial
results as verification gaps, not proof of no references or no problems; use
other available source/test evidence without claiming it was LSP verification.
Do not roll back or defer a justified cause fix merely because an optional
relation capability is unavailable. Broader checks are not a prerequisite to
that fix; unresolved required verification still prevents a verified closeout.

## Interpretation

- SCIP definitions/references と dependency-header evidence は別 evidence として記録します。SCIP references は caller/callee relation や build reachability を意味せず、header edge は source symbol resolution を意味しません。両者を結合するのは Change Impact Packet の影響範囲整理だけです。
- Python helperのrole、name alignment、redundancy evidenceには `helper_function_inventory.py --changed --all-functions` を使います。そのAST-derived local call hintsはSCIP symbol/reference evidenceではありません。`HELPER_INVENTORY_FILES=0` は対象 Python file がないことだけを示します。
- 原因箇所を特定したら修正し、対象差分と選択した validation を確認します。LSP / SCIP は依頼された依存分析に必要な場合だけ使い、未対応 index の結果を reference absence と扱いません。
- 複数の因果仮説が owner / fix / validation を変え得る場合は、観測、候補、比較根拠、選択した原因を既存記録に残します。straightforward finding は direct cause proof、rejected/duplicate/already-covered/unreachable finding は reason/evidence だけで閉じます。
- 原因探索の最終目標は、原因となるコードの具体的な一か所の特定です。[Cause Investigation Surface](#cause-investigation-surface) に従い、source snapshot、path、symbol、該当行/block と、入力/状態から現象に至る因果根拠を既存記録に残します。候補一覧・原因分類・症状の発生地点だけでは完了しません。一か所と因果関係を特定し、判断を変え得る代替を disconfirmed / bounded にしたら、その原因箇所の修正へ進みます。十分な静的根拠に追加実行を要求せず、未特定は `cause_unproven` とし、根拠なく一つに断定しません。
- activated packet の `required_action` は `Selected Cause` と `Expected Mechanism` から、straightforward packet の action は direct cause proof から導出します。症状だけの修正提案は `cause_unproven` として保留します。発生不能な分岐と過剰・重複ガードは、`reason_code=unreachable_branch|overcheck` と証拠を残して review 対象から除外します。
- 複数の因果仮説を比較して修正箇所を選ぶ task では、比較に必要な evidence を既存 packet に記録します。直接原因の証明や reason/evidence-only disposition には追加記録を要求しません。
- 既存 hypothesis packet を使った場合は、原因修正後の関連確認と対象検証のうち判断に必要な evidence を `Post-Change Evidence` と `Hypothesis Decision: supported|rejected|inconclusive` として残します。`rejected` または `inconclusive` の場合は、同じ実装 pass を広げず次仮説へ戻します。
- changed-file header / scan / format failure は fix-now blocker です。
- default graph failure は孤立 manifest、自己参照、または cycle を示すため fix-now blocker です。
- `run_repo_dependency_review.sh --report-dir` は dependency header 由来の `dependency_graph.tsv` を生成します。
- search result を編集対象に変換するときは、responsibility-based context、bounded `git grep` hit、`dependency_edit_scope.txt` の `DEPENDENCY_EDIT_SCOPE_PATH` を issue / PR evidence に残します。raw text-search hit だけで編集対象を決めません。
- design document を修正または作成するときは、重要な implementation-facing statement を通常の Markdown source link と説明文で根拠に結び付け、関連 source と governing parent document を直接確認します。初出の専門用語や前提は、判断に影響する範囲で本文中に定義します。
- Dockerfile や environment file を universal anchor にしません。実際に Docker、CI、requirements、runtime configuration に依存する file だけ `environment` edge を使い、それ以外は [AGENTS.md](../../AGENTS.md)、`README.md`、directory README、workflow/design doc、tool index、skill guide などの nearest true canon anchor に接続します。
- `--check-bidirectional` の full-repo failure は、reverse-edge 移行期間中は baseline として扱えます。ただし pass とは呼びません。
- baseline 扱いにする場合も、今回差分で old-format header、自己参照、reverse edge 欠落、kind mismatch、cycle を増やしていないことを review artifact に残します。

## Change Impact Packet

`dependency-analysis` は、選択された cross-surface 修正計画や handoff の入力になる
structured `Change Impact Packet` manifest の正本です。これは LLM が依存
graph 全体を prose 化する場所ではありません。tool output は JSON / TSV /
Markdown artifact として保存し、packet には path、count、object id、選択範囲に
必要な selected excerpt と structured summary を載せます。`refactor-loop` や dependency
evidence を要する handoff では、raw text-search hit、raw finding、単一 file 名だけを
subagent に渡しません。局所原因修正は特定した箇所と因果根拠から直接開始し、packet や
LSP 探索を前提にしません。

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

この節は、依頼が明示的に複数の Git roots / modules をまたぐ変更や API migration を
含む場合、または既知の dependency repository の移行が依頼範囲に含まれる場合に使います。

該当する範囲だけ、involved roots に限定して、各 root の `.gitmodules`、
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
- `code_dependency_surface`: selected SCIP definition/reference facts,
  explicit implementation relationships, and source index references. Keep helper-role
  evidence property-specific; do not convert references into a call graph.
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

1. Read [documents/design/dependency-manifest-design.md](../../documents/design/dependency-manifest-design.md)
   when dependency-header format, graph semantics, or tool ownership affects the decision.
1. For an unresolved cause, use this skill's `Cause Investigation Surface`; use `change-review` when a findings-first review is selected after the owner is known.
1. When competing causal hypotheses could change the fix surface, record the
   comparison in the existing packet before implementation; direct cause proofs
   and reason/evidence-only dispositions do not need that comparison.
1. Apply [Cause Investigation Surface](#cause-investigation-surface) to establish
   an unresolved cause. For code causes, identify the location and mechanism,
   fix the cause, inspect the target diff, and run selected validation. Do not
   treat unsupported LSP results as proof that no relation exists.
1. When an existing hypothesis packet is used, record its post-change evidence
   and decision there; return to hypothesis selection when evidence rejects or
   leaves that hypothesis inconclusive.
1. Choose the mode that answers the task without hiding dependency evidence:
   - code dependency surface: when repository-wide symbol/reference closure can change scope, query an explicitly selected external SCIP index with `scip_index.py`; do not make whole-repository indexing a default step
   - changed-file closeout gate: use `--changed`
   - explicit file review: pass file paths explicitly
   - repo migration inventory: run full scan without `--changed`
   - dependency edge change: include graph validation
   - repo-wide search triage: run responsibility-based search first, then use bounded `git grep -l` only as comparison evidence or within selected source surfaces before search-to-edit-scope expansion
   - design-source review: read linked implementation and governing documents directly; use the selected documentation owner's standard Markdown/link check for syntax and target validity
   - explicitly cross-module repair planning, or a selected subagent handoff
     that needs dependency evidence: build a structured `Change Impact Packet`
     manifest for the declared scope before dispatch
1. Use the `Required Commands` and `Change Impact Packet` sections above for
   code and header evidence; preserve those surfaces separately when building
   the packet.
