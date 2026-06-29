# Dependency Manifest Design

<!--
@dependency-start
contract design
responsibility Defines the repository-wide dependency manifest DSL and validation model.
downstream design dependency-contract-kinds.toml registered dependency header contract kinds
downstream implementation ../tools/agent_tools/check_dependency_headers.py validates changed-file manifests
downstream implementation ../tools/agent_tools/scan_dependency_headers.sh scans manifest marker coverage
downstream implementation ../tools/agent_tools/check_dependency_header_format.sh validates manifest syntax and contract kinds
downstream implementation ../tools/agent_tools/check_dependency_graph.sh validates manifest graph semantics
downstream implementation ../tools/agent_tools/run_repo_dependency_review.sh wraps repo-wide dependency review
downstream implementation ../tools/agent_tools/scan_code_dependencies.sh extracts code dependency evidence separately
downstream implementation ../tools/agent_tools/check_design_doc_claims.py validates design claims against manifest evidence
downstream implementation ../tests/agent_tools/test_check_dependency_headers.py verifies manifest checker
downstream implementation ../tests/agent_tools/test_dependency_manifest_tools.py verifies manifest shell tools
downstream design ./structured-analysis/graph-dsl.md maps dependency manifest evidence into Graph DSL Core
downstream design ./structured-analysis/dependency-header-analysis.md maps manifest graph evidence into structured analysis
@dependency-end
-->

このメモは、file 先頭に置く依存 manifest block の次期設計を固定します。
目的は、agent と tool の両方が、ある file を編集する前後に読むべき関係 file を機械的に取得できるようにすることです。
旧 `Dependency Files:` block は廃止方向です。
この設計では `@dependency-start` / `@dependency-end` marker による line-oriented DSL を正とします。

## Reader Map

Use this design to answer what dependency headers must express, how manifest
blocks are parsed, and how dependency graphs drive edit-scope and validation
tools. Read Goals, Non-Goals, and the evidence contract first; then use Manifest
Block, Dependency Kinds, Contract Kinds, and Comment Wrapping for authoring.
The later sections cover graph artifacts, responsibility-first expansion,
consistency checks, isolated manifests, tool split, migration, and open design
questions.

## Goals

- 変更前に読むべき upstream context を、file から相対 path で取得できる
- 変更後に確認すべき downstream context を、file から相対 path で取得できる
- human reviewer、agent、CI tool が同じ manifest を読む
- Bash / awk で高速に scan と format check ができる
- graph-level の双方向整合、自己参照、循環、closure を tool で検証できる
- graph-level の孤立 manifest を tool で検証できる
- dependency header check から repo-wide の machine-readable graph artifact を自動生成できる
- responsibility-based search と bounded text search の hit file から、依存 graph を辿った edit-scope candidate を自動生成できる
- design document の implementation-backed claim、implicit DSL / standard-form assumption、parent-doc alignment を dependency graph から検証できる
- code、docs、workflow、test、environment file を同じ内部 DSL で扱う

## Non-Goals

- YAML / JSON の完全 parser を作らない
- 推移依存を各 file に手書きしない
- すべての generated / binary artifact を同じ manifest で管理しない
- write-capable subagent の並列数を増やすための設計ではない

## Design Claim Evidence Contract

Design documents state implementation-facing claims within the evidence exposed
by current code, dependency headers, existing docs, and parent design
documents. The design artifact records that evidence in an `Evidence And
Assumption Ledger` before file-by-file implementation planning.

The ledger carries four fields:

- `Evidence sources`: code paths, tool paths, dependency-header graph artifacts,
  or existing documents that support the claim.
- `Assumptions`: first-use DSL terms, problem standard forms, normalization
  rules, and governing definitions.
- `Parent-doc alignment`: parent documents that agree with the claim, plus the
  governing source when a child design chooses a more constrained interpretation.
- `Refactor handoff`: structure, ownership, or route changes passed to
  `dependency-analysis` and `structure-refactor`.

`check_design_doc_claims.py` implements the deterministic gate. It expands
`design` and `implementation` dependency edges recursively, checks backticked
code/path/command tokens against repo paths or evidence text, tracks implicit
DSL / standard-form terms through the ledger, and reports modal contradictions
between a design document and its upstream parent documents.

## Manifest Block

各 file の先頭付近に、共通 marker を含む dependency manifest block を置きます。
外側は file type ごとの comment syntax を使います。
内部 DSL はすべての file type で同じです。

```text
@dependency-start
contract design
responsibility Documents this file's role so agents can identify why it exists.
upstream design ../agents/canonical/CODEX_WORKFLOW.md workflow contract
upstream implementation ../tools/agent_tools/bootstrap_agent_run.py consumes workflow metadata
downstream implementation ../tests/agent_tools/test_task_start_and_close.py verifies emitted output
@dependency-end
```

manifest block には file の契約種別を 1 line で書きます。
文法は次です。

```text
contract <registered-kind>
```

- `contract` は file が持つ契約面の分類を表します
- dependency edge ではないため graph edge にはなりません
- すべての manifest block にちょうど 1 行だけ置きます
- `<registered-kind>` は `documents/dependency-contract-kinds.toml` の `allowed_kinds` から選びます
- 新しい contract kind は registry、checker、review route を同じ変更で更新します

manifest block には file の責務を 1 line で書きます。
文法は次です。

```text
responsibility <role statement...>
```

- `responsibility` は file が repo 内で担う役割を 1 文で表します
- dependency edge ではないため graph edge にはなりません
- すべての manifest block にちょうど 1 行だけ置きます
- agent は file を読む前に、この行で「なぜこの file が存在するか」を把握します

1 dependency は 1 line で表します。
文法は次です。

```text
<direction> <kind> <relative-path> <reason...>
```

- `direction` は `upstream` または `downstream`
- `kind` は `design`、`implementation`、`environment`
- `relative-path` は manifest を持つ file から見た相対 path
- `reason` は 4 field 目以降の短い説明

複数 file に依存する場合は、依存ごとに行を増やします。
依存がない direction は行を置きません。
空の placeholder 行や `none` 行は不要です。

ただし、manifest block 全体が空の file は graph 上の孤立 node になりやすいため、default graph gate では fail とします。
少なくとも、編集前に読むべき nearest canonical context を `upstream` に置くか、変更後に確認すべき consumer / index / generated mirror を `downstream` に置きます。
shared canon の file は、実依存がない場合でも `AGENTS.md`、`README.md`、directory-level README、canonical workflow doc、tool index、skill implementation guide のような canon 内 anchor に接続します。
Dockerfile や repo-local environment file は universal anchor にしません。
shared canon は派生 repo に配布されるため、environment edge はその file が本当に Docker / CI / requirements / runtime assumption に依存する場合だけ使います。

## Dependency Kinds

`design` は仕様、設計、workflow、規約、schema、ADR 的な上位判断を表します。

`implementation` は code、script、test、runtime consumer、生成元、生成先を表します。

`environment` は Docker、CI、requirements、lock、tool config、runtime assumption を表します。

最初はこの 3 種に限定します。
新しい kind を増やす場合は、tool、docs、review gate、migration plan を同じ変更で更新します。

## Contract Kinds

contract kind は file 全体の契約面を表します。
dependency kind は edge の意味を表すため、同じ manifest 内に複数現れます。
この 2 つは別の enum です。

登録済み contract kind の正本は `documents/dependency-contract-kinds.toml` です。
checker は registry にない contract kind を reject します。
agent は file を読む前に `contract` と `responsibility` を読み、設計、実装、tool、skill、workflow、test、environment などのどの契約面を扱うかを固定します。

## Comment Wrapping

内部 marker と DSL は全 file type 共通です。
外側 comment syntax だけを file type に合わせます。
manifest は「file 先頭付近」に置き、`check_dependency_headers.py` は先頭 40 行、shell tool 群は既定で先頭 80 行を走査します。
この範囲内であれば、`SKILL.md` の YAML frontmatter、Markdown の H1 title、shebang、encoding comment の後に manifest block を置いてよいです。
ただし、長い前置き prose や generated banner を manifest より前に置いて、agent が責務と依存を読むまでの距離を伸ばしてはいけません。

Markdown:

```markdown
<!--
@dependency-start
contract design
upstream design ../agents/canonical/CODEX_WORKFLOW.md workflow contract
responsibility Provides a Python helper entrypoint for agent run bootstrap.
downstream implementation ../tools/agent_tools/bootstrap_agent_run.py consumes workflow contract
@dependency-end
-->
```

Python / shell / TOML:

```python
# @dependency-start
# contract tool
# responsibility Implements one repository tool or runtime helper.
# upstream implementation ../tools/agent_tools/agent_team.py imports helper contract
# downstream implementation ../tests/agent_tools/test_task_start_and_close.py verifies CLI behavior
# @dependency-end
```

C-like languages:

```c
/*
@dependency-start
contract implementation
responsibility Defines a C or C++ source/header surface and its edit context.
upstream design ../include/public_api.h public API contract
downstream implementation ../tests/test_public_api.cpp validates API behavior
@dependency-end
*/
```

Line comments are allowed because TOML, shell, Python, and many config formats do not have a native multiline comment.
The canonical parser must ignore common comment prefixes before reading each manifest line.
Commentless formats such as strict JSON are classified separately by the scan tool; they do not define the common path.

## Upstream And Downstream Graphs

`upstream` and `downstream` are separate graphs.
They are not mixed into one dependency graph.

The upstream graph answers: before editing this file, what context must be read?

The downstream graph answers: after editing this file, what affected files must be checked?

This separation exists for human and agent context management.
An agent can load upstream closure before editing, then load downstream closure after the diff exists.

## Machine-Readable Graph Artifact

Dependency header tools must be able to emit a stable TSV graph artifact from the same parser used for validation.
This artifact is the interchange format for issue triage, search-to-edit-scope expansion, dependency visualization, and PR evidence.
It is generated by `check_dependency_graph.sh --graph-tsv <path>` and automatically by `run_repo_dependency_review.sh --report-dir <dir>`.

The first row is a header and every following row has exactly four tab-separated fields:

```text
direction<TAB>kind<TAB>source<TAB>target
upstream<TAB>design<TAB>documents/example.md<TAB>README.md
downstream<TAB>implementation<TAB>tools/example.py<TAB>tests/tools/test_example.py
```

- `direction` is `upstream` or `downstream`
- `kind` is one of the manifest dependency kinds
- `source` and `target` are repo-relative normalized paths
- rows are sorted and de-duplicated before writing

This graph is header-manifest evidence only.
It must not be merged with language import/include/source edges from `scan_code_dependencies.sh`.

When a repo has known graph-cycle debt, PR gates may run
`run_repo_dependency_review.sh --cycle-report-only --report-dir <dir>` and
publish `render_dependency_manifest_graph.py` output from the generated TSV.
This keeps missing/invalid/self-reference findings blocking while making cycles
visible as review debt instead of silently blocking unrelated PR work.

## Responsibility-First Search-To-Edit-Scope Expansion

Repo-wide search must run responsibility-based context first and must feed
dependency triage instead of stopping at raw text-search hits. When the responsibility
pass and bounded text search find relevant files or folders, pass those hit
paths to the graph checker:

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

The generated `dependency_edit_scope.txt` contains stable `DEPENDENCY_EDIT_SCOPE_PATH` lines.
The roles have the following meaning:

- `search_hit`: the file or folder that matched text search
- `declared_upstream` / `declared_downstream`: a dependency declared by the hit file
- `incoming_upstream` / `incoming_downstream`: another file that points at the hit file
- `directory_related_upstream` / `directory_related_downstream`: an edge whose source or target lives under the hit directory

Issue files should cite this output when deciding which files need edits.
A finding is too coarse if it only says "update docs" without listing hit files, dependency candidates, and intentionally excluded candidates.

## Bidirectional Consistency

Bidirectional consistency is a graph-level validation, not a hand-maintained prose rule.

If file A declares:

```text
downstream implementation ../b.py B consumes A
```

then file B must declare the matching reverse edge:

```text
upstream implementation ../a.py A is consumed by B
```

The same rule applies in the other direction.
Kind must match unless a later design explicitly allows cross-kind reverse edges.

The graph checker compares the downstream edge set with the inverse upstream edge set.
It should report missing reverse edges and kind mismatches with file-relative diagnostics.

## Isolated Manifests

A file with a dependency manifest must appear in the graph as either a source or a target.
If it appears in neither position, the manifest does not help an agent choose context and should fail the default graph gate.

Valid ways to avoid isolation:

- add an `upstream design` edge to the nearest canonical contract
- add an `upstream implementation` edge to the helper, generator, or runtime it uses
- add a `downstream implementation` edge to tests, mirrors, generated views, or consumers that must be checked after edits
- add an `environment` edge only when the file truly depends on Docker, CI, requirements, or runtime configuration

Do not add synthetic Dockerfile dependencies just to make a node non-isolated.
For `agent-canon`, generic files should connect to canon-owned anchors such as `AGENTS.md`, `README.md`, `agents/canonical/*.md`, `documents/*.md`, or `tools/README.md`.

## Self Reference And Cycles

Self reference is a graph-level error.
It belongs in `check_dependency_graph.sh`, not in the format checker, because the graph checker resolves paths and normalizes edges across the repository.

Cycle detection is also graph-level.
The checker should analyze upstream and downstream separately.

- upstream cycles are fail by default because upstream represents prerequisite context
- downstream cycles are fail by default during initial rollout unless a documented allowlist is introduced
- bidirectional consistency itself is not treated as a cycle because upstream and downstream are separate graphs

Example: A `downstream` B plus B `upstream` A is expected and valid.
Example: A `upstream` B plus B `upstream` A is an upstream cycle and should fail.

## Tool Split

Tools are Bash-first.
Python is not required for the first implementation because the DSL is line-oriented.

Code dependency extraction is deliberately separate from dependency manifest validation.
`scan_code_dependencies.sh` reads language syntax such as Python imports, local C/C++ includes, and shell source statements.
The manifest tools read only `@dependency-start` / `@dependency-end` blocks.
Do not combine these outputs into one graph: code dependency evidence answers "what does this code reference", while header dependency evidence answers "which design, implementation, environment, and test context must be read".

### `scan_code_dependencies.sh`

Responsibilities:

- extract best-effort code edges from import / include / source statements
- keep output independent from manifest upstream/downstream edges
- support explicit path lists and `--changed`
- provide pre-edit evidence for `agents/workflows/hypothesis-validation-workflow.md`
- remain Bash-first and lightweight; deeper language-specific precision can be added later without changing the header manifest DSL

### `scan_dependency_headers.sh`

Responsibilities:

- enumerate tracked files with `git ls-files`
- classify binary, generated, vendored external, commentless, unsupported, and checkable files
- report files missing `@dependency-start` / `@dependency-end`
- group missing manifest output by owner class: `product_file`, `root_view`, `symlink`, `submodule_source`, or `other`
- with `--explain-missing`, print the detected missing-marker reason and the first 20 lines for fast repair
- run in report-only mode during migration
- later become a CI fail gate

### `check_dependency_header_format.sh`

Responsibilities:

- validate marker count and marker order
- validate placement near the top of the file
- strip common comment prefixes
- validate each manifest has exactly one registered `contract` line
- validate each manifest has exactly one non-empty `responsibility` line
- validate each dependency line has direction, kind, relative path, and reason
- validate direction and kind enum values
- validate path is relative
- validate target path exists
- accept `--allow-frontmatter` as an explicit policy flag; frontmatter is already allowed by default within the top-of-file scan window

This tool does not check bidirectional consistency, self reference, closure, or cycles.

### `check_dependency_graph.sh`

Responsibilities:

- extract normalized edges from all manifest blocks
- build separate upstream and downstream edge sets
- fail manifest files that are isolated from the edge graph
- validate self reference
- detect cycles separately in upstream and downstream graphs
- list every manifest edge declared by, or pointing at, focused changed files
- print upstream and downstream related surfaces for changed files
- emit machine-readable TSV for graph artifacts with `--graph-tsv`
- expand text-search hits into edit-scope candidates with `--edit-scope`, `--edit-scope-changed`, or `--search-hits-file`
- with `--check-bidirectional`, validate bidirectional consistency and kind match on reverse edges

Default graph validation is the fail gate for isolated manifests, self reference, and cycles.
Bidirectional consistency is a stricter migration gate because a partially migrated repository can have useful upstream/downstream context before every reverse edge is written.

The graph checker can be implemented with Bash, `awk`, `sort`, `comm`, and a small DFS in `awk`.
If later graph requirements outgrow shell tooling, a Python implementation can replace only this layer while preserving the DSL and CLI contract.

### `run_repo_dependency_review.sh`

Responsibilities:

- run the scan, format, and graph tools over all tracked checkable files
- keep missing manifests report-only by default while repository-wide migration is incomplete
- offer `--fail-missing` for strict checkpoint runs after a subtree or repo has been migrated
- offer `--explain-missing` for owner-classified missing-header repair output
- accept `--allow-frontmatter` and pass it to the manifest tools for policy-explicit CI callers
- pass `--check-bidirectional` through to graph validation when strict reverse-edge review is requested
- offer `--list-changed-dependencies` so checkpoint review can hand reviewers every surface that changed files declare or are referenced by
- automatically write `dependency_graph.tsv` when `--report-dir` is set
- accept `--search-hits-file` and write `dependency_edit_scope.txt` when `--report-dir` is set

Template repos expose `make dependency-review-surfaces` to run strict review against both the parent root view and `vendor/agent-canon` source tree.

## Migration Plan

Phase 1: add this design and make changed-file validation require `@dependency-start` / `@dependency-end`.

Phase 2: implement Bash tools first:

- `scan_dependency_headers.sh`
- `check_dependency_header_format.sh`
- `check_dependency_graph.sh`

`scan_dependency_headers.sh` starts as full-repo report-only so it can list missing manifests without blocking unrelated work.
`check_dependency_headers.py --changed` rejects changed files that do not have valid `@dependency-start` blocks or registered contract kinds.
`check_dependency_header_format.sh --changed` rejects changed files that do not have valid `@dependency-start` blocks or registered contract kinds.
`check_dependency_graph.sh` default mode rejects self references and cycles.
`check_dependency_graph.sh --cycle-report-only` reports cycles without failing
and is valid only when paired with a durable graph report artifact.
`check_dependency_graph.sh --check-bidirectional` is used as a stricter migration report until reverse edges are complete.

Phase 3: migrate files one by one from checker findings.
Each touched file must be converted from `Dependency Files:` to `@dependency-start` in the same change that touches it.

Phase 4: enable CI fail gate for changed files.
Full-repo missing-header scan remains report-only until the repository is migrated.
この repository では full-repo migration 後の strict baseline を `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` で固定します。
goal-driven cleanup や shared surface migration の closeout では、この strict baseline を繰り返し実行して `DEPENDENCY_HEADER_SCAN_MISSING=0` と `REPO_DEPENDENCY_REVIEW=pass` が安定することを evidence にします。

Phase 5: remove legacy `Dependency Files:` wording from remaining docs after all checkable files use dependency manifest blocks.

## Open Design Questions

- Whether strict JSON files should require a sidecar manifest or remain classified as commentless unsupported files
- Whether downstream cycles should eventually support an explicit allowlist
- Whether generated files should point to generators via sidecar metadata or stay outside the checkable set
- Whether closure output should be ordered by graph distance, kind, or stable path sort
