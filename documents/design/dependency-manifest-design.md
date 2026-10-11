# Dependency Manifest Design

<!--
@dependency-start
contract design
responsibility Defines the optional dependency manifest DSL and validation model for explicitly selected analysis.
downstream design source-owned-dependency-validation.md applies the DSL to source-owned validation
downstream design dependency-contract-kinds.toml registered dependency header contract kinds
downstream implementation ../../tools/validation/semantic/dependencies/check_dependency_headers.py validates changed-file manifests
downstream implementation ../../tools/analysis/dependencies/scan_dependency_headers.sh scans manifest marker coverage
downstream implementation ../../tools/validation/semantic/dependencies/check_dependency_header_format.sh validates manifest syntax and contract kinds
downstream implementation ../../tools/analysis/dependencies/check_dependency_graph.sh validates manifest graph semantics
downstream implementation ../../tools/analysis/dependencies/run_repo_dependency_review.sh wraps repo-wide dependency review
downstream implementation ../../tools/analysis/dependencies/scan_code_dependencies.sh launches bounded queries against a selected standard SCIP index
downstream implementation ../../tools/analysis/dependencies/render_dependency_manifest_graph.py renders dependency graph review artifacts
downstream implementation ../../tests/agent_tools/test_check_dependency_headers.py verifies manifest checker
downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py verifies manifest shell tools
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/dependency_manifest.rs owns the sole complete-file manifest parser and source snapshot
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/graph.rs owns canonical graph materialization and queries
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/structured_analysis.rs owns the shared graph storage schema
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/main.rs dispatches public graph commands
downstream implementation ../../tools/bin/agent-canon provides the stable bootstrap CLI for public graph commands
downstream implementation ../../tools/analysis/dependencies/graph_client.py provides the sole Python graph adapter
downstream design ../structured-analysis/graph-dsl.md maps dependency manifest evidence into Graph DSL Core
downstream design ../structured-analysis/dependency-header-analysis.md maps manifest graph evidence into structured analysis
@dependency-end
-->

このメモは、明示的な dependency analysis で使う任意の manifest block の文法を定義します。
通常の file 編集・追加・PR では manifest block を要求しません。選択された analysis では、既存注釈から agent と tool が関係 file を機械的に取得できます。
旧 `Dependency Files:` block は廃止方向です。
analysis 対象が注釈を持つ場合は `@dependency-start` / `@dependency-end` marker による line-oriented DSL を使います。

## Reader Map

Use this design when explicitly analyzing existing dependency annotations: it
defines their syntax, graph projections, and validation behavior. It does not
make annotations a prerequisite for ordinary edits, additions, or PRs. Read
Goals, Non-Goals, and the evidence contract first; then use Manifest Block,
Dependency Kinds, Contract Kinds, and Comment Wrapping when an analysis
annotation is deliberately authored.

## Goals

- 変更前に読むべき upstream context を、file から相対 path で取得できる
- 変更後に確認すべき downstream context を、file から相対 path で取得できる
- human reviewer、agent、selected analysis tool が既存 annotation を読む
- Bash / awk で高速に scan と format check ができる
- graph-level の双方向整合、自己参照、循環、closure を tool で検証できる
- graph-level の孤立 manifest を tool で検証できる
- dependency header check から repo-wide の machine-readable graph artifact を自動生成できる
- responsibility-based search と bounded text search の hit file から、依存 graph を辿った edit-scope candidate を自動生成できる
- design document の implementation-backed claim、implicit DSL / standard-form assumption、parent-doc alignment を dependency graph から検証できる
- code、docs、workflow、test、environment file に任意 annotation を付けて分析できる

## Non-Goals

- YAML / JSON の完全 parser を作らない
- 推移依存を各 file に手書きしない
- すべての generated / binary artifact を同じ manifest で管理しない
- write-capable subagent の並列数を増やすための設計ではない

## APT Package Version Selection

`apt-package` record は `version` を省略すると、declared Ubuntu
distribution の repository candidate を installer に選択させます。
Installer は version constraint なしで package を install し、`dpkg-query`
で観測した version を receipt の `resolved_package_version` に記録します。
image verification は manifest の未指定値ではなく、この receipt version と
live dpkg state を照合します。これは build ごとの実際の package 解決を記録する
契約であり、将来の repository index が同じ version を返す保証ではありません。

`apt-package` に `version` が明示される場合は引き続き exact version constraint
として install/verify します。`apt-repository`、NPM、PIPX、release asset、Rust
toolchain など、owner が version pin を要求する method では version は必須です。
第三者 artifact や compatibility が pin を必要とする dependency は明示 pin を
保持し、distribution-managed mode を代用しません。

## Mounted Language-Server Dependency Contract

共有 code analysis の LSP サーバーは product image の依存ではなく、
`.devcontainer/dependencies.toml` の mounted developer/agent tool record
として管理します。各 record は registry/repository の exact version、
source、provider、typed executable verification、`failure_policy = "fail"`
を持ち、検証済みの executable 以外を PATH から選択しません。Canonical
mapping は `python → pyright-langserver --stdio`、`c`/`cpp → clangd-18`、
`shellscript → bash-language-server start`、`rust → rust-analyzer` です。

`apt-repository` には `repository_suite` と
`repository_components` を明示します。`repository_packages_sha256` がある
record は source、suite、単一 component、`platform` から uncompressed
Packages index URL を決定し、取得 bytes の SHA-256 を source-line/apt
package の受入れ前に照合します。URL の欠落、取得失敗、digest 不一致、
署名付き source line の drift、または executable/version の drift は
warning に降格せず typed failure とします。Rust の `rust-src` は component
verification の対象ですが、独立 executable probe は持ちません。

`platforms` は shared manifest 内の record ごとの対応 OCI target を表し、
plan は現在の target に対応する record のみを選択します。別 target の
record を除いた結果、残る record がその provider に依存していれば provider
解決を失敗させます。単一の exact `platform` は選択条件ではなく strict pin の
ままです。
Immutable な apt artifact を固定する record は
`repository_package_url` と `repository_package_sha256` を必ず対で持ちます。
URL は HTTPS の `.deb`、SHA-256 は 64 桁 hex とし、installer は signed
source/key の update 後に exact URL を safe temporary path へ取得し、artifact
SHA を照合してから local-file `apt-get install` を実行します。receipt は
rolling Packages index identity と immutable artifact identity を別フィールド
として保存し、両者を混同した変更を stale receipt として拒否します。

依存 receipt の executable identity は manifest の install method が所有します。
`VerifiedExecutable(record_id, manifest_version, executable, absolute_path,
record_fingerprint, plan_fingerprint, verification_output)` と
`resolve_verified_executable(workspace, vendor_root, receipts, record_id,
executable)` が公開境界です。解決は exact record、receipt schema/fingerprint/
requested-provided binding、Installer の live verify、method-specific absolute
path、receipt の absolute path/output readback の順で行い、どれか一つでも
不一致なら fail closed とします。npm は `pyright` と
`pyright-langserver` を同一 package の bindings として保存し、apt は
`executable_owner_packages` で宣言された所有者群の lexical path と
resolved path を `/usr/bin/dpkg-query --listfiles` ownership で照合します。いずれかの
所有者が所有境界に失敗した場合は fail-closed です。Rust は pinned
toolchain の `rust-analyzer` path を保存します。ambient `PATH` や `shutil.which`
はこの境界に入りません。

## Explicit Dependency Analysis Route

Dependency-manifest analysis is source-owned and does not require a persisted
graph runtime. This document owns the manifest DSL, relation semantics,
contract kinds, changed-scope selection, and source-derived projections.

When explicitly selected, `run_repo_dependency_review.sh` runs source scan,
format, relation/cycle, and TSV/DOT projection checks for dependency analysis.
The normal PR and CI routes do not invoke a dependency-header gate or require a
dependency receipt. Persisted graph commands remain explicit analysis
capabilities rather than ordinary edit or PR prerequisites.

The normal repository review route remains independent of graph executables and
databases. `--ensure-graph` and `tools/bin/agent-canon graph
build|status|query|context` are explicit analysis capabilities with their own
runtime contract. They are mutually exclusive with source review where the
wrapper promises an ensure-only route. Ordinary PR validation does not select
or consume dependency-header graph evidence.

## Manifest Block

dependency manifest を明示的な analysis 注釈として使う場合、file の先頭付近に共通 marker を含む block を置きます。
外側は file type ごとの comment syntax を使います。
内部 DSL はすべての file type で同じです。

```text
@dependency-start
contract design
responsibility Documents this file's role so agents can identify why it exists.
upstream design ../../agents/canonical/CODEX_WORKFLOW.md workflow contract
upstream implementation ../../tools/runtime/lifecycle/bootstrap_agent_run.py consumes workflow metadata
downstream implementation ../tests/agent_tools/test_bootstrap_and_close.py verifies emitted output
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
- `<registered-kind>` は `documents/design/dependency-contract-kinds.toml` の `allowed_kinds` から選びます
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
- `kind` は `design`、`implementation`、`environment`、`reference`
- `relative-path` は manifest を持つ file から見た相対 path
- `relative-path` は `./` の有無や bare sibling を問わず、宣言元 file の
  repo-relative parent から正規化します。absolute path は受理せず、root の
  外へ出る `..` も `target-absolute` / `target-escapes-root` の typed
  diagnostic として保持します
- `reason` は 4 field 目以降の短い説明

複数 file に依存する場合は、依存ごとに行を増やします。
依存がない direction は行を置きません。
空の placeholder 行や `none` 行は不要です。

孤立判定は全 source topology の outgoing / incoming edge を使います。
自分から宣言がない manifest も、他の file から実依存が宣言されていれば孤立ではありません。
`reference` の `upstream` / `downstream` は参照方向だけを記録し、実際の前提を意味しません。
それ以外の kind では `upstream` は実際の前提、`downstream` はその前提を使う consumer に限ります。
単なる索引、相互参照、生成 mirror という理由で前提へ昇格させず、孤立診断を消すための架空の anchor は追加しません。
Dockerfile や repo-local environment file は universal anchor にしません。
shared canon は派生 repo に配布されるため、environment edge はその file が本当に Docker / CI / requirements / runtime assumption に依存する場合だけ使います。

## Dependency Kinds

`design` は仕様、設計、workflow、規約、schema、ADR 的な上位判断を表します。

`implementation` は code、script、test、runtime consumer、生成元、生成先を表します。

`test` は contract kind registry の file-level contract 分類であり、
dependency relation kind ではありません。テストへの依存も
`downstream implementation` として宣言します。

`environment` は Docker、CI、requirements、lock、tool config、runtime assumption を表します。

`reference` は、memo、source record、調査ノートなどの非権威資料を参照する
evidence relation です。対象は通常の dependency target と同様に repository 内で
解決可能でなければなりません。明示的な context projection では対象を
`evidence_paths` に含めますが、`parent_paths` や prerequisite ordering には
含めず、design/contract owner として扱いません。仕様や設計判断の正本には
引き続き `design` を使います。

`reference` を含む dependency relation は、この明示的な source review / graph
analysis の入力です。通常の edit や PR の必須 header gate にはなりません。
`test`、`review`、`report` などの file-level contract 分類は、
`dependency-contract-kinds.toml` の contract kind として別に管理します。
`contract reference` も file-level 分類であり、`upstream reference` / `downstream reference`
relation の意味とは独立です。
新しい relation kind を増やす場合は、optional parser、tool、docs、および
明示的な graph-analysis instructions を同じ変更で更新します。

## Contract Kinds

contract kind は file 全体の契約面を表します。
dependency kind は edge の意味を表すため、同じ manifest 内に複数現れます。
この 2 つは別の enum です。

登録済み contract kind の正本は `documents/design/dependency-contract-kinds.toml` です。
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
upstream design ../../agents/canonical/CODEX_WORKFLOW.md workflow contract
responsibility Provides a Python helper entrypoint for agent run bootstrap.
downstream implementation ../../tools/runtime/lifecycle/bootstrap_agent_run.py consumes workflow contract
@dependency-end
-->
```

Python / shell / TOML:

```python
# @dependency-start
# contract tool
# responsibility Implements one repository tool or runtime helper.
# upstream implementation ../../tools/agent/orchestration/agent_team.py imports helper contract
# downstream implementation ../tests/agent_tools/test_bootstrap_and_close.py verifies CLI behavior
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

The declaration views serve different context queries: upstream identifies a
file's prerequisites; downstream identifies its consumers. Read-time closure may
keep those views separate, but cycle validation uses one prerequisite ordering:

```text
A downstream B  =>  A -> B
B upstream A    =>  A -> B
```

The two declarations coalesce to one edge, not a two-node cycle. Kind and source
provenance remain in the existing declaration/TSV output. `reference` relations
remain visible there but do not assert prerequisite ordering and are excluded
from cycle detection. A prerequisite cycle may cross direction spellings and
the `design`, `implementation`, and `environment` kinds.

## Explicit Graph Analysis Artifact

`tools/runtime/dispatch/agent-canon/src/dependency_manifest.rs::ManifestParser` is the sole
complete-file parser. `agent-canon graph build` captures its parent-profile
source snapshot and atomically publishes the parent-owned SQLite database at
`.agent-canon/knowledge-graph/graph.sqlite`. Source facts and their typed
completeness diagnostics are required for this explicit graph artifact. A
captured runtime event plus latest committed receipt is an optional producer
snapshot: when
`reports/agents/.active_run` is absent, or the pointed active run has no
captured runtime-event certificate, the same Rust builder publishes a
source-only graph with explicit `runtime_evidence=null`. The empty-run case is
an observability closeout condition, not a semantic graph prerequisite. Once a
captured certificate is present, duplicate, malformed, missing, uncertain, or
source-mismatched runtime evidence remains a fail-closed runtime boundary.
`status`, `query`, and `context` are read-only; they never rebuild or fall back
to a header scan.
Canonical current-tree consumers let `status` derive the current producer and
manifest identity. The PR selector's trusted-base readback instead repeats the
exact current producer identity and exact base-tree manifest used by its
preceding build. `status` validates those explicit typed inputs, re-probes the
base snapshot, and compares the resulting HEAD/source/input fingerprints with
the persisted integration record; a missing, changed, or substituted input
fails before diagnostic classification.

Explicit graph freshness recovery belongs only to the `--ensure-graph` route.
That route may admit one canonical build followed by status read-back under its
own typed status contract; every other stale reason, typed-unavailable status,
persisted read-back corruption, producer mismatch, incomplete or invalid
status, build failure, and non-fresh read-back fails closed. The normal source
review wrapper does not perform this recovery or treat its result as a receipt
prerequisite. The graph producer continues to own its existing lock, staging,
atomic rename, and durability read-back.

The standalone runtime dashboard workflow is the periodic producer authority,
not an ordinary graph consumer. Only its scheduled event invokes the
source-root-resolved canonical Graph CLI to run one direct `graph build`; pull
request, push, and manual-dispatch events skip that step. A fresh checkout with
no ignored graph database therefore starts from the producer rather than from
consumer status. The Graph CLI emits build exit `0` only with `status=fresh`;
that result is required before the workflow runs `graph status` readback.
Build failure and published incomplete status fail before readback. The
read-only status command must then return exit `0` and fresh while revalidating
the persisted publication, snapshot HEAD,
source/content/input fingerprints, and producer identity. The scheduled build
uses the producer's existing lock, staging, atomic rename, and durability
contract. Its cron value remains owned only by that workflow.

source snapshot の候補 path は、解決先の内容ではなく候補 path 自体の
filesystem object を読む。`dependency_manifest.rs` の単一 source-path
byte/mode reader は対象を `symlink_metadata` で判定し、regular file では
`fs::read` の bytes と mode `100644` を返す。symlink では `read_link` が
返すリンク先表現の raw bytes（対応する Unix の `OsStrExt::as_bytes`）と
mode `120000` を返し、target が directory であってもその内容へ展開しない。
`to_string_lossy` や推測による非 Unix fallback は使わない。missing path は
従来契約どおり空 bytes と `exists=false` で扱う。broken symlink は
`symlink_metadata` が取得できる限り path 自体が存在するため `exists=true` とし、
symlink の target 表現を identity/hash の入力にする。

source fingerprint の各 identity 行は path、exists、file mode、source bytes の
hash を結合する。したがって、同じ bytes `foo` を持つ regular file (`100644`) と
target が `foo` の symlink (`120000`) は異なる fingerprint になる。

この reader は source fingerprint と snapshot capture の双方から共有し、
各経路が symlink / regular file / missing の読み方を二重実装しない。

The canonical machine interface is the four JSON graph operations documented
in [agents/canonical/CLI_ENTRYPOINTS.md](../../agents/canonical/CLI_ENTRYPOINTS.md). A dependency query uses
`--all --relation dependency --direction both --depth 0` and preserves stable
fact IDs, source spans, producer, evidence reference, authority, and the
dependency detail. Python consumers use `GraphClient` and
`GraphResponse.dependency_facts`; shell consumers invoke the same executable
with fixed arguments.

dependency fact の `from` / `to` は stable node ID です。現行の source node ID は
`node:source:<path>` ですが、consumer は文字列 prefix を除去して path を作ってはいけません。
`nodes[]` の `id` と `path` の対応を正本とし、`nodes[].id -> nodes[].path` の map を一度作って
endpoint ID を repo-relative path へ解決します。optional な `payload.from_selector` /
`payload.to_selector`、文字列加工、header の再 parse などの fallback には依存しません。
`nodes[]` で endpoint を解決できない場合は、空の endpoint を含む projection を黙認せず、
consumer が checker failure として明示診断します。

`dependency_graph.tsv` is the deterministic review projection generated by
`check_dependency_graph.sh`. The renderer also accepts an existing TSV through
`--graph-tsv` as rendering input; a supplied TSV does not establish that source
dependency manifests pass validation.

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

This dependency graph contains declared header facts only. SCIP code
definitions/references remain a separate evidence source: the optional
`scip_index.py` API reads/writes standard `index.scip` artifacts and returns a
bounded query projection, but does not write a Graph DSL relation or persistent
code-graph mirror. The dependency graph build does not invoke a code indexer.

Completeness is explicit. Unresolved targets, ambiguous bindings, uncovered
eligible sources, and excluded sources are persisted as typed sets. A published
incomplete graph is inspectable through status but cannot authorize query or
context evidence. Freshness binds parent HEAD, dirty fingerprint, source
snapshot, producer hashes, profile pair `default`/`parent`, schema, and tool
versions; stale state is reported and never silently rebuilt.

GitHub Issue records are external authority and are not traversed as source
documents or dependency-header owners. Repository-qualified URLs/numbers may
be cited by active canon, while private offline packets contain only locator
and digest metadata under `agent-canon-log`.

### Executable finite-set contract

For one captured source/producer state `S` and public profile `p=default`, graph
build constructs named finite sets rather than inferring completeness from row
counts:

- `P(S)` is the snapshot candidate-source set, `X(S)` is the set of explicit
  source exclusions, and `U(S)=P(S)\X(S)` is the eligible source set.
- `D` is the canonical `ManifestParser` declaration-ID set. `R` is the set of
  accepted explicit producer relation IDs. Inferred relations are not members
  of `R`.
- `G` is the set of semantic node, declaration, explicit/projection relation,
  and diagnostic members represented by the Graph DSL store. `Vp` is the
  default profile projection of `G`.
- `X_R(S,p)`, `Unresolved(S,p)`, `Ambiguous(S,p)`, and `Uncovered(S,p)` are
  explicit diagnostic-ID sets. A fresh profile requires all three latter sets
  to be empty; a structurally valid nonempty result is `incomplete`.

The candidate stores these exact sorted sets in
`metadata.mathematical_contract`, together with typed functions
`source_identity:U(S)->V(G)`, `relation_endpoints:(R union reverse(R))->V(G)^2`,
and `reverse_projection:R->reverse(R)`. Candidate validation directly decides
the following equalities and totality conditions:

$$
P(S) = U(S) union X(S)
U(S) intersect X(S) = empty
domain(source_identity) = U(S)
domain(reverse_projection) = R
Vp subset G and, for default, Vp = G
Unresolved(S,p) = Ambiguous(S,p) = Uncovered(S,p) = empty  iff  status=fresh
$$

Every relation kind is parsed through the closed `RelationKind` registry. Each
accepted relation has two existing endpoint IDs, one authoritative producer
artifact, and a nonempty evidence reference. Exclusion dominance forbids a
member of `X(S)` from becoming a source identity or relation endpoint. Every
`r in R` has exactly one `reverse:r`, with swapped endpoints, the same typed
kind and evidence reference, and `inferred=true`; no other inferred relation is
accepted.

For a seed `s`, relation selector `k`, direction `a`, and requested depth `d`,
query uses the monotone operator on the finite lattice
`powerset(V(G) x {0..d})`:

$$
F(C) = {(s,0)} union C union
       {(v,n+1) | (u,n) in C, n < d, and a k-typed edge permits u -> v}
$$

It iterates from the empty set until equality and returns the minimum depth for
each member of `mu F`. Validation applies `F` once more to decide fixed-point
equality and requires a typed predecessor at depth `n-1` for every non-seed
member; closure and generatedness together decide leastness. Direction, depth,
or result-size thresholds are not completeness substitutes.

`input_fingerprint` binds the source snapshot, schema/profile pair, and
authoritative producer identities/content. Runtime-dashboard rows are a
non-authorizing observation projection: when present, its immutable producer
ID/version is an input-freshness term, while its exact captured payload hash
remains in the producer artifact and `graph_fingerprint`. Runtime absence is
an explicit source-only fingerprint term rather than an incomplete graph.
New hook activity therefore does not make graph observation self-invalidating,
and context still returns the exact runtime snapshot bound to that graph
fingerprint when one exists. Persisted logical records are rehashed on status;
modifying a node, relation, diagnostic, producer record, or mathematical
witness yields `invalid`.

Publication is the state transition `T(old,candidate)`. The transition reaches
`new` only after candidate schema, finite-set, relation, fingerprint, and
integration validation and an atomic rename plus directory sync. Producer,
write, validation, rename, or sync failure returns an error and requires the
durable target's existence/content hash to equal `old`; sync failure rolls the
renamed candidate back before returning. The executable failure-seam tests
compare bytes/hashes, not retry counts or timing heuristics.

When a repo has known graph-cycle debt, PR gates may run
`run_repo_dependency_review.sh --cycle-report-only --report-dir <dir>` and
publish `render_dependency_manifest_graph.py` output from the same canonical
graph query.
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
bash tools/analysis/dependencies/run_repo_dependency_review.sh \
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
If it appears in neither position in the full source topology, the explicit
graph review reports an isolated manifest. Selected review must not discard
incoming edges declared by unselected files before this check. Repair an actual
missing prerequisite or consumer declaration when supported by source evidence;
do not invent a canon, index, or environment dependency just to silence a finding.

## Self Reference And Cycles

Self reference remains a graph-level error, including in `--cycle-report-only`.
Canonicalizing a generated view can expose a self edge; investigation must
separate that declaration from a genuine source self-dependency rather than
silently dropping either one.

`check_dependency_graph.sh` computes all strongly connected components (SCCs)
over the full, normalized source topology. A component is cyclic if it contains
more than one node or a self edge. Full review reports every cyclic component
once, in deterministic order. Explicit selected paths or `--changed` restrict
only the reported components to those containing a selected node, not the edges
used to compute SCCs. An empty changed set reports no cycles; a reachable but
unselected component is not a selected finding. Explicit paths take precedence
over changed scope. Declaration output remains scoped to its declaring files.

Cycles fail by default. `--cycle-report-only` emits
`DEPENDENCY_GRAPH_CYCLES=report_only` without making cycle findings blocking;
parse, projection, isolation, and self-reference failures retain their existing
failure semantics. No additional always-on gate is introduced, and retiring
mandatory headers/gates under Issue #1228 remains independent of this correction.

Example: A `downstream` B plus B `upstream` A is one valid ordering edge.
Example: A `downstream` B, C `upstream` B, and C `downstream` A form one cycle,
even when only A is selected and B/C are unchanged.

## Tool Split

Code dependency evidence remains separate from dependency-manifest validation.
`scip_index.py` writes the standard SCIP artifact using a selected native
producer and projects bounded definitions, references, and explicitly declared
implementation relationships through the official SCIP reader. The
`scan_code_dependencies.sh` path is only a compatibility launcher for that
query; it no longer scans text, emits dependency TSV, or supplies a lexical
fallback. Point LSP analysis and diagnostics remain owned by
`lsp_code_analysis.py analyze` and are not repository-wide SCIP indexing.
The manifest tools read only `@dependency-start` / `@dependency-end` blocks.
Keep the evidence meanings separate: SCIP records indexed symbol occurrences,
while header dependency evidence answers which design, implementation,
environment, and test context must be read. References are not call edges, and
an unsupported or unindexed target is not evidence of no references.

### `scan_code_dependencies.sh`

Responsibilities:

- pass an explicitly selected external `index.scip` and bounded target paths to `scip_index.py query`
- keep output independent from manifest upstream/downstream edges
- provide optional pre-edit evidence for [agents/skills/dependency-analysis.md](../../agents/skills/dependency-analysis.md)
- never scan source text or fabricate unsupported-language coverage

### `scan_dependency_headers.sh`

Responsibilities:

- parse tracked `@dependency-start` / `@dependency-end` source blocks
- select caller-requested, changed, or tracked paths without deriving facts
- report existing annotations and missing annotations within an explicitly
  selected analysis scope
- keep missing annotations report-only by default; ordinary edits and PRs do
  not activate this scanner

### `check_dependency_header_format.sh`

Responsibilities:

- parse each selected source block and validate one registered contract and one
  responsibility line
- map missing or malformed source evidence to the existing pass/fail output
- accept `--allow-frontmatter` as a compatibility flag without interpreting text

The source parser and contract registry own syntax, target, and completeness
validation. This shell owns no persisted graph state or runtime status.

### `check_dependency_graph.sh`

Responsibilities:

- consume source-derived dependency projections from `source_dependency_graph.py`
- filter explicit dependency facts and project their typed detail
- fail manifest files that are isolated from the edge graph
- validate self reference
- detect all cyclic SCCs in the normalized full source topology, then apply review scope
- list every manifest edge declared by, or pointing at, focused changed files
- print upstream and downstream related surfaces for changed files
- emit a deterministic review-only TSV projection with `--graph-tsv`
- expand text-search hits into edit-scope candidates with `--edit-scope`, `--edit-scope-changed`, or `--search-hits-file`
- with `--check-bidirectional`, validate bidirectional consistency and kind match on reverse edges

When explicitly invoked, default graph validation rejects isolated manifests,
self reference, and cycles. Bidirectional consistency is an optional stricter
check over declared reverse edges; it does not impose repository-wide annotation
coverage.

The shell may use `jq`, `awk`, and `sort` to project canonical query rows. It
cannot read source headers, rebuild graph facts, or open SQLite.

### `run_repo_dependency_review.sh`

Responsibilities:

- run source scan, format, relation/cycle, TSV/DOT, and edit-scope projections
- keep the normal route independent of graph executable and persisted database
- keep missing manifests report-only by default; ordinary edits and PRs do not
  require repository-wide manifest coverage
- offer `--fail-missing` for a user-selected strict coverage audit; ordinary
  edits and PRs do not use it
- offer `--explain-missing` for owner-classified missing-header repair output
- accept `--allow-frontmatter` and pass it to the manifest tools for
  policy-explicit analysis callers
- pass `--check-bidirectional` through to graph validation when strict reverse-edge review is requested
- offer `--list-changed-dependencies` so checkpoint review can hand reviewers every surface that changed files declare or are referenced by
- automatically write `dependency_graph.tsv` when `--report-dir` is set
- accept `--search-hits-file` and write `dependency_edit_scope.txt` when `--report-dir` is set

Template repos expose `make dependency-review-surfaces` to run an explicit
strict review against both the parent root view and `vendor/agent-canon` source
tree. Persisted graph preparation is available only through the explicit
`--ensure-graph` route; it exits before source review and is never a normal
receipt prerequisite.

## Usage Boundary

Dependency annotations remain available for explicitly selected analysis.
Their absence is not a blocker for ordinary file edits, additions, or PRs, and
the standard validation route does not ask writers to add them. The optional
scanner and graph reviewer may report annotation gaps when a user selects that
analysis contract; that does not create a repository-wide migration or PR gate.

## Open Design Questions

- Whether explicitly reviewed cycle debt needs any policy beyond report-only review
- Whether closure output should be ordered by graph distance, kind, or stable path sort
