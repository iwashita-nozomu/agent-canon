# dependency-analysis

<!--
@dependency-start
contract skill
responsibility Documents dependency-analysis for this repository.
upstream design ../../documents/dependency-manifest-design.md defines dependency manifest format and tools
upstream design ../canonical/CODEX_WORKFLOW.md defines workflow gate usage
upstream design ./catalog.yaml registers this public skill
upstream implementation ../../tools/agent_tools/scan_code_dependencies.sh extracts file-level code dependency evidence
upstream implementation ../../tools/agent_tools/helper_function_inventory.py extracts Python function-level call graph context
upstream implementation ../../tools/agent_tools/check_design_doc_claims.py validates design-document evidence claims
@dependency-end
-->

## Reader Map

- Purpose: collect dependency-header, graph, code-dependency, and
  change-impact evidence before choosing or validating edit scope.
- Section path: Purpose and Use When explain the trigger; Required Commands
  lists the operational tool surface; Interpretation, Change Impact Packet, and
  Core References define how outputs feed planning and handoff.
- Use when: dependency manifests, changed-file gates, graph edges, reverse
  edges, design-claim evidence, or repair-planning packets are needed.
- Boundary: code dependency evidence and dependency-header evidence remain
  separate until summarized in a structured Change Impact Packet.

## Purpose

依存 manifest の header / scan / format / graph tool と、実コード依存 scanner を目的別に起動します。
code dependency と header dependency は別 evidence として扱い、修正箇所選定や subagent handoff では両方を structured `Change Impact Packet` manifest に統合します。大量の依存情報そのものは artifact path に置き、LLM-visible context には planning に必要な selected excerpt、summary、artifact path を載せます。

## Use When

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
bash tools/agent_tools/scan_code_dependencies.sh --changed
```

Function-level Python dependency surface:

```bash
python3 tools/agent_tools/helper_function_inventory.py --changed --all-functions --format json
```

Changed-file gate:

```bash
python3 tools/agent_tools/check_dependency_headers.py --changed
bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing
bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header
```

Graph check when edges changed:

```bash
bash tools/agent_tools/check_dependency_graph.sh --changed --print-edges
```

Strict reverse-edge check when that is the migration target:

```bash
bash tools/agent_tools/check_dependency_graph.sh --changed --print-edges --check-bidirectional
```

Full migration inventory:

```bash
bash tools/agent_tools/scan_dependency_headers.sh
bash tools/agent_tools/check_dependency_graph.sh --print-edges
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
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --search-hits-file reports/search_hits.txt
```

Design-document claim evidence gate:

```bash
python3 tools/agent_tools/check_design_doc_claims.py \
  --root . \
  --recursive-depth 3 \
  documents/design/<topic>.md
```

or through the dependency review wrapper:

```bash
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --check-design-doc-claims
```

For an explicit design document:

```bash
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --check-design-doc-claims \
  --design-doc-claim-path documents/design/<topic>.md
```

## Interpretation

- code dependency は実 import / include / source 関係、header dependency は design / implementation / environment / test の明示文脈です。混ぜずに別々の evidence として記録します。
- Python code 変更では、`helper_function_inventory.py --changed --all-functions` を関数 / class / method 単位の evidence として使います。この tool は変更 Python file を報告対象にしつつ、whole-repo call graph context から direct callers / callees を保持します。変更 Python file count が 0 件の場合は `HELPER_INVENTORY_FILES=0` を scope evidence にします。
- 修正箇所を選ぶ task では、先に `scan_code_dependencies.sh` で実コード依存を抜き、次に header dependency graph で読むべき design / docs / tests を確認します。
- コード改善の修正箇所を選ぶ task では、`agents/workflows/hypothesis-validation-workflow.md` に従って `Observation`、`Hypothesis`、`Expected Mechanism`、`Candidate Comparison`、`Disconfirming Evidence`、`Support Evidence`、`fix_surface_validated=yes` を実装前に固定します。
- 実装後は `Post-Change Evidence` と `Hypothesis Decision: supported|rejected|inconclusive` を残します。`rejected` または `inconclusive` の場合は、同じ実装 pass を広げず次仮説へ戻します。
- changed-file header / scan / format failure は fix-now blocker です。
- default graph failure は孤立 manifest、自己参照、または cycle を示すため fix-now blocker です。
- `run_repo_dependency_review.sh --report-dir` は dependency header 由来の `dependency_graph.tsv` を生成します。
- search result を編集対象に変換するときは、responsibility-based context、bounded `git grep` hit、`dependency_edit_scope.txt` の `DEPENDENCY_EDIT_SCOPE_PATH` を issue / PR evidence に残します。raw text-search hit だけで編集対象を決めません。
- design document を修正または作成するときは、major claim の code / path token、初出 DSL / standard-form terms、parent-doc alignment を `Evidence And Assumption Ledger` に接続し、`check_design_doc_claims.py` の finding を design evidence gap として扱います。
- Dockerfile や environment file を universal anchor にしません。実際に Docker、CI、requirements、runtime configuration に依存する file だけ `environment` edge を使い、それ以外は `AGENTS.md`、`README.md`、directory README、workflow/design doc、tool index、skill guide などの nearest true canon anchor に接続します。
- `--check-bidirectional` の full-repo failure は、reverse-edge 移行期間中は baseline として扱えます。ただし pass とは呼びません。
- baseline 扱いにする場合も、今回差分で old-format header、自己参照、reverse edge 欠落、kind mismatch、cycle を増やしていないことを review artifact に残します。

## Change Impact Packet

`dependency-analysis` は、依存 evidence を集めるだけでなく、修正計画の入力になる
structured `Change Impact Packet` manifest の正本です。これは LLM が依存
graph 全体を prose 化する場所ではありません。tool output は JSON / TSV /
Markdown artifact として保存し、packet には path、count、object id、現在の
repair batch に必要な selected excerpt と structured summary を載せます。`refactor-loop`、
implementation handoff、原因仮説の fix-surface 選定では、raw text-search hit、raw
finding、単一 file 名だけを subagent に渡しません。

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

- `documents/dependency-manifest-design.md`
- `agents/workflows/hypothesis-validation-workflow.md`
- `agents/canonical/CODEX_WORKFLOW.md`
- `agents/templates/closeout_gate.md`
