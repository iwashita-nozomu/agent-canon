# Dependency Manifest Design

<!--
@dependency-start
contract design
responsibility Defines the repository-wide dependency manifest DSL and validation model.
downstream design dependency-contract-kinds.toml registered dependency header contract kinds
downstream implementation ../../tools/agent_tools/check_dependency_headers.py validates changed-file manifests
downstream implementation ../../tools/agent_tools/scan_dependency_headers.sh scans manifest marker coverage
downstream implementation ../../tools/agent_tools/check_dependency_header_format.sh validates manifest syntax and contract kinds
downstream implementation ../../tools/agent_tools/check_dependency_graph.sh validates manifest graph semantics
downstream implementation ../../tools/agent_tools/run_repo_dependency_review.sh wraps repo-wide dependency review
downstream implementation ../../tools/agent_tools/scan_code_dependencies.sh extracts code dependency evidence separately
downstream implementation ../../tools/agent_tools/check_design_doc_claims.py validates design claims against manifest evidence
downstream implementation ../../tools/agent_tools/render_dependency_manifest_graph.py renders dependency graph review artifacts
downstream implementation ../../tools/ci/agent_canon_pr_graph_selector.py selects parent strict graph gating from this canonical dependency surface manifest
downstream implementation ../../tools/ci/check_agent_canon_pr.sh executes selected full or changed-responsibility graph acceptance
downstream implementation ../../tools/ci/run_all_checks.sh consumes the owner/root/PID/status-bound graph receipt
downstream implementation ../../tests/agent_tools/test_check_dependency_headers.py verifies manifest checker
downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py verifies manifest shell tools
downstream implementation ../../tests/tools/test_agent_canon_pr_graph_selector.py verifies parent gate selection from canonical profiles, surfaces, and diff evidence
downstream implementation ../../tests/tools/test_agent_canon_pr_graph_gate_integration.py verifies real parent gate orchestration for incomplete graph acceptance
downstream implementation ../../rust/agent-canon/src/dependency_manifest.rs owns the sole complete-file manifest parser and source snapshot
downstream implementation ../../rust/agent-canon/src/graph.rs owns canonical graph materialization and queries
downstream implementation ../../rust/agent-canon/src/structured_analysis.rs owns the shared graph storage schema
downstream implementation ../../rust/agent-canon/src/main.rs dispatches public graph commands
downstream implementation ../../tools/bin/agent-canon provides the stable bootstrap CLI for public graph commands
downstream implementation ../../tools/agent_tools/graph_client.py provides the sole Python graph adapter
downstream design ../structured-analysis/graph-dsl.md maps dependency manifest evidence into Graph DSL Core
downstream design ../structured-analysis/dependency-header-analysis.md maps manifest graph evidence into structured analysis
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

`check_design_doc_claims.py` implements the deterministic gate. It requests a
bounded dependency closure and token context from the canonical graph, checks
the returned typed evidence, and reports unsupported tokens or parent
contradictions. It does not parse dependency headers or open evidence files as
a second fact authority.

## Parent PR Gate Selection Contract

Dependency-manifest completeness is a conditional parent-repository PR gate,
not an unconditional prerequisite for publishing an AgentCanon gitlink. Every
parent pin publication still requires the gitlink to resolve to a reachable
commit, the staged gitlink to equal the checked-out `vendor/agent-canon` HEAD,
and the changed shared/root projection to pass its existing materialization
check. An actual materialization collision remains a blocker. A local parent
branch being ahead, behind, diverged, or dirty is preserved as repository state
and is not a failure predicate on its own.

The parent strict graph-completeness gate is selected only when at least one of
these conditions is true:

- the caller declares a parent graph migration;
- the change touches a dependency manifest/header or a downstream surface
  declared by this design document's canonical dependency manifest;
- the selected runtime validation profile explicitly requires dependency graph
  completeness through its
  `strict_dependency_graph_required` field in
  `documents/runtime/runtime-profiles-and-check-matrix.json`.

Profile selection uses one canonical ID in
`AGENT_CANON_PR_VALIDATION_PROFILE` or comma-separated canonical IDs in
`AGENT_CANON_PR_VALIDATION_PROFILES`. Supplying both inputs, an empty list
element, a duplicate, or an unknown ID is a typed selector failure.

When none of these conditions holds, the PR gate emits a typed skipped receipt
with non-empty selector reason/evidence, and its quick-CI consumer does not
rebuild the parent graph or promote repository-wide missing-header diagnostics
into a blocker. Standalone AgentCanon source PRs retain the strict source graph
gate. This separation keeps manifest migration debt visible without making
unrelated parent pin-only changes satisfy a repository-wide completeness
baseline.

When the gate is selected, graph construction still covers the complete parent
repository. A complete graph produces the existing `prepared` receipt and
retains the full strict review. If construction publishes an incomplete graph,
the gate first builds an equivalent graph from the exact trusted base SHA in an
isolated checkout. The base build must publish a valid graph result and bound
SQLite database; missing, stale, malformed, unavailable, or concurrently
replaced base evidence fails closed. For a derived parent, every `160000`
submodule gitlink recorded by the exact base tree is recursively materialized
and verified at that commit before the builder runs. The builder process exit
code must exactly equal the JSON result `exit_code`; only matching `0` or `1`
results are admissible. The graph builder receives the current AgentCanon
source's surface-manifest producer and the unique surface-manifest path found
inside that exact base gitlink. The producer runs with the isolated base root,
so dependency target existence is evaluated against base content while parser
semantics remain those of the current producer; no base-pinned helper is used
as a compatibility fallback. The head gate then classifies every unique
persisted diagnostic identity against the exact validated PR diff, the head
graph's dependency/surface edges, and the trusted base diagnostics.

The canonical diagnostic identity is the normalized tuple
`(code, source, target, declaration)`. Line numbers, diagnostic counts, and
message formatting that does not change the declaration are not identity. Changed
paths are responsibility seeds, reachability is traversed in both directions,
and a diagnostic is related when its source, target, or required closure is
changed. A related diagnostic blocks when its identity is absent from the
trusted base or its severity is worse than the trusted-base instance. A related
diagnostic with the same non-worsened identity is retained as baseline evidence.
A changed target that makes an unchanged declaration unresolved is therefore a
new related blocker even when the source file is unchanged. Invalid
`manifest-grammar` in a changed declaration cannot be hidden by baseline state.

The `ManifestParser` owns the normalized declaration components: direction,
kind, canonical repository-relative target, and reason. Every source diagnostic
persists those components, the canonical declaration, and its source span in
the strict `agent-canon.source-diagnostic.v1` `payload_json` object, together
with the producer-resolved source and target. Non-source layers retain the
shared diagnostics table through a valid generic/default payload object; they do
not require the source identity schema. The graph fingerprint binds each
typed diagnostic payload and severity, so a semantic identity change cannot
reuse result or database identity.

Before evaluating the changed-responsibility predicate $S(d)$ or the base
identity/severity predicates $N(d)$ or $W(d)$, the selector validates the
current diagnostics columns and typed payload field-for-field. Missing,
malformed, empty, wrongly typed, span-inconsistent, target-node-inconsistent,
or declaration-component-inconsistent identity data fails closed. This
consumer validation does not replace the #513 current-producer and exact
trusted-base authority: the current producer remains authoritative for head
semantics, the exact base snapshot remains authoritative for comparison, and
no base-pinned, message-derived, legacy-schema, or parser fallback is allowed.

The report contains a duplicate-free, lossless partition of all head diagnostic
identities into `blocking_diagnostics` and `baseline_diagnostics`, together with
the base graph identity and diagnostic-set fingerprint. If a source identity
outside the changed responsibility cannot be confirmed, the gate fails closed.
This accepted incomplete state produces a `scoped` receipt; `scoped` is not a
complete graph and its quick-CI consumer does not run graph-query consumers. An
explicit parent graph migration owns the full graph, so every diagnostic remains
in scope. Standalone AgentCanon source PRs also retain full completeness.

The selector reads dependency surfaces from this document's downstream
manifest instead of maintaining a second path list. The manifest therefore
owns the complete bootstrap surface, including scanners, format and changed-file
checkers, graph parser/storage and client adapters, report rendering, and the
selector itself. Strict graph validation remains the semantic authority after
selection; the bootstrap read only decides whether that authority is required.

CI comparison uses the pull request base SHA from the trusted GitHub event.
The PR entrypoint first runs the selector's `--prepare-ci-base` mode. An existing
exact base object with usable merge-base history skips fetch without requiring a
credential. If the checkout is shallow or incomplete, only the static-gate step
receives `AGENT_CANON_PR_READ_TOKEN: ${{ github.token }}`; the selector uses it as
process-local Git configuration while fetching the exact event SHA and connected
history. It does not persist the credential in checkout or repository Git config,
and `actions/checkout` keeps `persist-credentials: false`. Public, private, and
fork PRs all use that same trusted event-SHA route. The emitted SHA is passed back
through `--trusted-base-sha`, and normal selection accepts the argument only when
it exactly matches the event SHA. CI `AGENT_CANON_PR_BASE_REF` overrides and local
trusted-base arguments are typed failures. Local and fixture selection supplies
an explicit, credential-free `AGENT_CANON_PR_BASE_REF`. Equal-to-HEAD, unresolved,
history-unreachable, missing-fetch-credential, fetch, or diff failures do not
become an empty change set. Unknown profile IDs and malformed canonical
profile/surface owners fail by the same rule.

The receipt's owner/root/PID/status binding and required skipped
reason/evidence are sufficient for the checker-to-quick-CI handoff. A
cryptographic nonce against a hostile local caller is outside this trust
boundary: such a caller can omit the checker entirely, so cryptography would
not add evidence that the required gate ran.

## Manifest Block

各 file の先頭付近に、共通 marker を含む dependency manifest block を置きます。
外側は file type ごとの comment syntax を使います。
内部 DSL はすべての file type で同じです。

```text
@dependency-start
contract design
responsibility Documents this file's role so agents can identify why it exists.
upstream design ../../agents/canonical/CODEX_WORKFLOW.md workflow contract
upstream implementation ../../tools/agent_tools/bootstrap_agent_run.py consumes workflow metadata
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
- `kind` は `design`、`implementation`、`environment`、`requirements`、
  `review`、`evidence`
- `relative-path` は manifest を持つ file から見た相対 path
- `relative-path` は `./` の有無や bare sibling を問わず、宣言元 file の
  repo-relative parent から正規化します。absolute path は受理せず、root の
  外へ出る `..` も `target-absolute` / `target-escapes-root` の typed
  diagnostic として保持します
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

`requirements` は同じ責任単位を拘束する要求成果物、`review` は承認・
差し戻し判断、`evidence` は再利用される観測証拠を表します。これらは
run bundle の会話や schedule を authority に昇格させず、明示された immutable
artifact 間の edge にだけ使用します。

登録済みの 6 種に限定します。
新しい kind を増やす場合は、tool、docs、review gate、migration plan を同じ変更で更新します。

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
downstream implementation ../../tools/agent_tools/bootstrap_agent_run.py consumes workflow contract
@dependency-end
-->
```

Python / shell / TOML:

```python
# @dependency-start
# contract tool
# responsibility Implements one repository tool or runtime helper.
# upstream implementation ../../tools/agent_tools/agent_team.py imports helper contract
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

`rust/agent-canon/src/dependency_manifest.rs::ManifestParser` is the sole
complete-file parser. `agent-canon graph build` captures its parent-profile
source snapshot and atomically publishes the parent-owned SQLite database at
`.agent-canon/knowledge-graph/graph.sqlite`. Source facts and their typed
completeness diagnostics are always required. A prepared runtime-event plus
latest committed receipt is an optional producer snapshot: when
`reports/agents/.active_run` is absent, or the pointed active run has no
prepared runtime-event certificate, the same Rust builder publishes a
source-only graph with explicit `runtime_evidence=null`. The empty-run case is
an observability closeout condition, not a semantic graph prerequisite. Once a
prepared certificate is present, duplicate, malformed, missing, uncertain, or
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

Freshness recovery remains outside the read-only Graph operations.
`run_repo_dependency_review.sh` owns the consumer transition: fresh status
skips production. Exactly the typed canonical status tuple `status=stale`,
`reason=source_changed`, and `probe_reason=source_changed`, with matching process
and record exit code `2`, permits one canonical build followed by status
readback. Every other stale reason, typed-unavailable status, persisted readback
corruption, runtime receipt or evidence failure, producer mismatch, incomplete
or invalid status, build failure, and non-fresh readback fails closed without
admitting a build. The producer continues to own its existing lock, staging,
atomic rename, and durability readback.

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
in `agents/canonical/CLI_ENTRYPOINTS.md`. A dependency query uses
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

`dependency_graph.tsv` remains a deterministic review projection only. It is
generated from canonical query rows by `check_dependency_graph.sh` or
`render_dependency_manifest_graph.py`; it is never accepted as an alternate
input or fact authority.

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

Dependency facts remain distinct from code `import`, `include`, and `symbol`
facts, although all relation families share the same validated Graph DSL
storage. `scan_code_dependencies.sh` is the sole code-relation producer and is
invoked once by graph build with an authoritative paths file. Consumers never
invoke it or reconstruct its rows.

Completeness is explicit. Unresolved targets, ambiguous bindings, uncovered
eligible sources, and excluded sources are persisted as typed sets. A published
incomplete graph is inspectable through status but cannot authorize query or
context evidence. Freshness binds parent HEAD, dirty fingerprint, source
snapshot, producer hashes, profile pair `default`/`parent`, schema, and tool
versions; stale state is reported and never silently rebuilt.

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

- invoke graph status, then one all-dependency query
- select caller-requested, changed, or tracked paths without deriving facts
- report source nodes whose parser-owned `manifest_present` value is false
- with `--explain-missing`, print typed graph owner and producer evidence
- run in report-only mode during migration
- later become a CI fail gate
- accept a selector-owned `--changed-path-packet` containing the trusted PR
  base/head, tree, merge-base, exact changed-path set, and path-set digest
- fail closed when that packet is missing, malformed, stale, or differs from
  the repository's verified base/head diff; the PR gate passes its separately
  trusted base SHA and the scanner requires an exact packet binding to it
- under a trusted PR packet, report unchanged missing headers as baseline
  evidence and block only missing headers on changed or newly added paths;
  deleted paths and existing root-view, symlink, and submodule skip rules stay
  owned by this scanner
- remain independent of graph-selection activation: a valid trusted PR packet
  is sufficient to run this header gate even when a derived-parent graph is
  not required; standalone AgentCanon still owns unconditional full graph
  completeness separately

### `check_dependency_header_format.sh`

Responsibilities:

- invoke graph status once and graph context once per sorted selected path
- require one parser-owned `manifest.present` item
- when present, require exactly one `manifest.contract` and one
  `manifest.responsibility` item from `source-snapshot`/`ManifestParser`
- map missing or malformed graph evidence to the existing pass/fail output
- accept `--allow-frontmatter` as a compatibility flag without interpreting text

The Rust parser and graph build own syntax, registry, target, and completeness
validation. This shell owns no tokenizer or target normalizer.

### `check_dependency_graph.sh`

Responsibilities:

- invoke graph status and one all-relation query with direction `both`
- filter explicit dependency facts and project their typed detail
- fail manifest files that are isolated from the edge graph
- validate self reference
- detect cycles separately in upstream and downstream graphs
- list every manifest edge declared by, or pointing at, focused changed files
- print upstream and downstream related surfaces for changed files
- emit a deterministic review-only TSV projection with `--graph-tsv`
- expand text-search hits into edit-scope candidates with `--edit-scope`, `--edit-scope-changed`, or `--search-hits-file`
- with `--check-bidirectional`, validate bidirectional consistency and kind match on reverse edges

Default graph validation is the fail gate for isolated manifests, self reference, and cycles.
Bidirectional consistency is a stricter migration gate because a partially migrated repository can have useful upstream/downstream context before every reverse edge is written.

The shell may use `jq`, `awk`, and `sort` to project canonical query rows. It
cannot read source headers, rebuild graph facts, or open SQLite.

### `run_repo_dependency_review.sh`

Responsibilities:

- invoke graph status followed by all-dependency and all-owner queries
- run the graph-backed scan, format, and graph projections over selected files
- keep missing manifests report-only by default while repository-wide migration is incomplete
- offer `--fail-missing` for strict checkpoint runs after a subtree or repo has been migrated
- offer `--explain-missing` for owner-classified missing-header repair output
- accept `--allow-frontmatter` and pass it to the manifest tools for policy-explicit CI callers
- pass `--check-bidirectional` through to graph validation when strict reverse-edge review is requested
- offer `--list-changed-dependencies` so checkpoint review can hand reviewers every surface that changed files declare or are referenced by
- automatically write `dependency_graph.tsv` when `--report-dir` is set
- accept `--search-hits-file` and write `dependency_edit_scope.txt` when `--report-dir` is set
- accept `--changed-path-packet` from the trusted PR graph selector and pass it
  to the canonical header scan; the wrapper does not derive a second local
  branch diff or duplicate changed-path authority
- support a header-scan-only route that does not require a fresh graph status;
  the PR gate uses it when derived-parent graph selection is skipped while
  still requiring the trusted changed-path packet and strict missing-header
  gate

Template repos expose `make dependency-review-surfaces` to run an explicit
strict review against both the parent root view and `vendor/agent-canon` source
tree. The AgentCanon parent PR gate invokes this wrapper only when its
migration, touched-manifest, or selected-profile condition is active.

## Migration Plan

Phase 1: add this design and make changed-file validation require `@dependency-start` / `@dependency-end`.

Phase 2: provide the shell entrypoints as graph consumers:

- `scan_dependency_headers.sh`
- `check_dependency_header_format.sh`
- `check_dependency_graph.sh`

`scan_dependency_headers.sh` starts as full-repo report-only so it can list
missing manifests without blocking unrelated work. Both changed-file checkers
consume parser-owned graph context; neither parses source text or the registry.
The parent PR gate supplies a selector-owned changed-path packet rather than a
local branch diff. The scanner verifies the packet against the trusted
base/head snapshot, blocks missing manifests only for changed/new paths, and
reports unchanged missing paths with stable count/path baseline evidence.
`check_dependency_graph.sh` default mode rejects self references and cycles.
`check_dependency_graph.sh --cycle-report-only` reports cycles without failing
and is valid only when paired with a durable graph report artifact.
`check_dependency_graph.sh --check-bidirectional` is used as a stricter migration report until reverse edges are complete.

Phase 3: migrate files one by one from checker findings.
Each touched file must be converted from `Dependency Files:` to `@dependency-start` in the same change that touches it.

Phase 4: enable CI fail gate for changed files.
Full-repo missing-header scan remains report-only until the repository is migrated.
この repository では full-repo migration、touched dependency-manifest change、または
canonical profile owner が graph-required と宣言する validation profile のときだけ
graph gate を起動します。full-repo migration と standalone source は
`bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` の strict
baseline を維持します。parent PR の incomplete graph は changed responsibility
closure を gate し、base と同一で非到達な `target-unresolved` や
`manifest-grammar` は個別 evidence として残します。pin-only parent changes は
skipped receipt で表現します。Goal-driven cleanup or shared-surface migration
closeout repeats the strict baseline and records stable
`DEPENDENCY_HEADER_SCAN_MISSING=0` and `REPO_DEPENDENCY_REVIEW=pass` evidence.

Phase 5: remove legacy `Dependency Files:` wording from remaining docs after all checkable files use dependency manifest blocks.

## Open Design Questions

- Whether strict JSON files should require a sidecar manifest or remain classified as commentless unsupported files
- Whether downstream cycles should eventually support an explicit allowlist
- Whether generated files should point to generators via sidecar metadata or stay outside the checkable set
- Whether closure output should be ordered by graph distance, kind, or stable path sort
