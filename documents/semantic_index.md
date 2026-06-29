<!--
@dependency-start
contract reference
responsibility Documents the semantic-index candidate-generation tool and Eval harness.
upstream design search-coordination.md coordinated search provider boundary
upstream design local-llm-responsibility-analysis.md local model advisory boundary
upstream design rust-agent-tool-migration.md Rust CLI migration policy
downstream implementation ../rust/agent-canon/src/semantic_index.rs implements the Rust semantic-index CLI
downstream implementation ../rust/agent-canon/src/main.rs routes the semantic-index command
downstream design ../tools/README.md documents operator-facing tool entrypoints
downstream design tools/README.md documents reader-facing tool entrypoints
downstream design ../tools/catalog.yaml catalogs the semantic-index tool
@dependency-end
-->

# Semantic Index

`agent-canon semantic-index` builds a repo-local semantic-vector cache for
text-like files and uses that cache for advisory search, similar-item, merge
candidate, natural-language relation, discourse-connective relation,
thin-document, provider-comparison, and fixture Eval reports.

The tool is candidate generation, not deletion authority. Strict structure
hashes, dependency graph analysis, AST equality, and safe removal decisions stay
in the existing strict analysis tools.

## Reader Map

Use this document to answer how semantic-index cache state is generated, which
commands expose search or discourse evidence, and where Local LLM, provider,
eval, and candidate-generation boundaries sit. Start with the evidence ledger,
generated cache, and Local LLM boundary; then use Commands for operational
entrypoints. The final sections explain providers, eval scope, and candidate
generation boundaries so search output is not mistaken for edit authority.

## Evidence And Assumption Ledger

- Evidence sources:
  `search-coordination.md`, `local-llm-responsibility-analysis.md`,
  `../rust/agent-canon/src/semantic_index.rs`, and
  `../tools/catalog.yaml`.
- Assumption:
  implementation surface routing uses semantic-index output as bounded
  candidate evidence. It does not replace source ownership, dependency-header
  closure, exact symbol search, static analysis, tests, or review judgement.
- Parent-doc alignment:
  The coordinated-search document owns provider order. This document owns the
  semantic-index cache and context-pack evidence contract.

## Generated Cache

The default database is:

```text
~/.cache/agent-canon/semantic-index/<repo-key>/index.sqlite
```

The default generated cache lives under the operator home directory, not in the
repository tree. Set `AGENT_CANON_SEMANTIC_INDEX_HOME` to move all semantic
index artifacts to another home-managed directory. Rebuild it after relevant
source, tool, workflow, or document changes. Do not commit SQLite files, vector
blobs, or local model output. The legacy repo-local `.agent-canon/semantic-index/`
path remains ignored for explicit `--db` runs and older worktrees.

The MVP stores file/node metadata, hashes, and provider-scoped dense vectors.
The same SQLite database can hold both deterministic baseline vectors and
LLM-backed embedding vectors for the same nodes. It does not store the full
original text as a durable truth surface.

Writes use a local temporary SQLite database, copy the completed cache to a
target-directory publish file, then atomically rename it over the requested
path. This keeps normal SQLite locking and journaling behavior during mutation
while still supporting generated cache paths on network-backed worktrees.

## Local LLM And Prose IR Boundary

The `semantic-index` command surface owns vector-cache commands: `build`,
`search`, `context-pack`, `thin-docs`, `merge-candidates`,
`natural-relations`, provider comparison, and Eval reports. Its result surface
is generated SQLite state plus bounded text, JSONL, context-pack, or report
artifacts. Those outputs are advisory evidence; they are not deletion
authority, rewrite approval, source truth, or dependency graph closure.

LLM-backed embeddings may call an OpenAI-compatible provider, but the prompt contract is
still a bounded query with source line ranges, provider metadata, and output
caps. Do not ask the embedding provider to produce raw word lists or settled
document structure in chat.

Prose IR and intermediate representation extraction are not stored in the
semantic-index database. When existing prose must become graph seed data, route
the document through `agent-canon local-llm extract-prose-ir` and
`$prose-reasoning-graph`; semantic-index can then supply search context,
candidate neighbors, or responsibility-bucket evidence. Skill integration
should pass `context-pack` cells to the receiving skill and keep final
acceptance with dependency review, structured analysis, tests, and human review
gates.

## Commands

Build an index:

```bash
agent-canon semantic-index build \
  --root . \
  --include documents \
  --include agents
```

When `search`, `context-pack`, `thin-docs`, or related commands fail because the
SQLite database is missing, build the index in the current worktree and retry
the bounded command. Do not treat a missing generated cache as permission to
skip semantic-index and immediately read broad raw text-search output.

Add an LLM-backed embedding provider to an existing index:

```bash
agent-canon semantic-index embed-provider \
  --root . \
  --db reports/semantic-index.sqlite \
  --provider llama-server-embedding \
  --model ggml-org/embeddinggemma-300M-GGUF:Q8_0 \
  --embedding-url http://127.0.0.1:8080/v1/embeddings
```

`embed-provider` does not rebuild files or nodes. It reads the existing node
line ranges, skips nodes that already have the requested `(provider, model)`
embedding, asks an OpenAI-compatible embedding endpoint for missing vectors,
and adds another `(provider, model, dim)` vector set to the same SQLite table.
Interrupted local-LLM embedding runs can be resumed by rerunning the same
command against the same database.

Search by meaning-like vector similarity:

```bash
agent-canon semantic-index search \
  --query "AgentCanon latest submodule pin workflow" \
  --format json
```

For long natural-language task descriptions, avoid shell-quoting the whole
paragraph. Put the text in a file or pipe it on stdin:

```bash
agent-canon semantic-index search \
  --query-file reports/search_query.txt \
  --top-k 20 \
  --format text

cat reports/search_query.txt \
  | agent-canon semantic-index search --query-stdin --top-k 20 --format jsonl
```

`jsonl` emits a bounded summary line followed by one JSON object per result and
does not echo long query text, so agents can stream or filter it without reading
one full JSON array.

For agent handoff, prefer a context pack instead of raw search JSONL or full
files:

```bash
agent-canon semantic-index context-pack \
  --query-file reports/search_query.txt \
  --max-cells 12 \
  --max-cell-chars 900 \
  --max-total-chars 6000 \
  --format text
```

`context-pack` reuses the same provider-scoped vector search but returns only
bounded evidence cells: path, line range, score, responsibility bucket, node
kind, and a capped excerpt. It is the default bridge from semantic search into
subagent prompts when raw JSONL or full documents would be too large.

For prompt context selection, put the current user request, reviewer question,
or handoff purpose in `reports/.../query.txt`, run `context-pack`, and pass only
the cells plus the exact follow-up task to the subagent. Do not paste full
AGENTS/read-packet files when the bounded cells identify the relevant path and
line ranges; use the source files only for follow-up reads.

Build a directory responsibility tree and verify DB coverage:

```bash
agent-canon semantic-index responsibility-tree \
  --root . \
  --include documents \
  --include agents \
  --db reports/semantic-index.sqlite \
  --check-directory-coverage \
  --report reports/semantic_index_responsibility_tree.json
```

`responsibility-tree` reads the current SQLite `files`, `nodes`, and
`embeddings` tables. It aggregates node vectors into every parent directory,
stores a vector hash for each directory, and can include full directory vectors
with `--include-vector`. The JSON report also contains two mechanically
comparable directory inventories: `repo_tree_directories` from the current
indexable filesystem tree and `db_tree_directories` from DB file paths.
`--check-directory-coverage` exits nonzero when either missing or stale
directories exist. This check uses the same include, exclude, and
`--max-file-bytes` rules as `build`, so non-indexable binary/cache directories
are not expected to appear in the DB.

List semantic similarity candidates:

```bash
agent-canon semantic-index similar --min-score 0.82
```

`similar` is allowed to cross repository surfaces. A code block and a document
block can be surfaced together when the result is useful as alignment evidence.

List cross-file merge candidates:

```bash
agent-canon semantic-index merge-candidates --min-score 0.82
```

`merge-candidates` still reads the full indexed repository, but it only scores
pairs inside the same responsibility scope, surface kind, document topic, and
node kind. The responsibility scope follows the top-level ownership buckets in
`responsibility-scope.toml`, so review output can distinguish
`runtime-entrypoints`, `shared-tooling`, `shared-policy-documents`,
`eval-and-hook-evidence`, and related surfaces. Documentation, code, and config
are separated first; document buckets are further split by surface such as
skill, workflow, tool docs, issue, memory, note, and general documents. A
code/document match is alignment evidence, never merge evidence, even when the
vectors are nearly identical. Runtime discovery surfaces such as
`.agents/skills/`, and accumulated eval/report logs, are
also alignment or evidence surfaces rather than merge surfaces. Preserved
source/split guide pairs are excluded for the same reason. Very small
heading-only sections are below the merge-candidate floor because they do not
carry enough local content to justify a consolidation recommendation.

For review, use the same command with JSONL output so each candidate carries its
responsibility metadata:

```bash
agent-canon semantic-index merge-candidates --min-score 0.90 --top-k 20 --format jsonl
```

Each result includes `same_responsibility`, `candidate_bucket`, and per-side
`responsibility_bucket` fields. These fields are review routing evidence only:
they make duplicate-responsibility and consolidation candidates visible, but
they do not authorize deletion or merge without dependency, structure, and
human review evidence.

List thin documentation wrappers:

```bash
agent-canon semantic-index thin-docs --top-k 20 --format text
```

`thin-docs` scores document nodes from the SQLite vector DB and nearby source
files. It combines low meaningful content, high single-target similarity,
reference density, and wrapper/entrypoint language. Protected runtime
entrypoints such as root README / AGENTS surfaces are reported as
`keep_entrypoint` rather than deletion candidates. Other actions are advisory:
`inline_into_target`, `replace_with_catalog_row`, `merge_with_peer`, and
`manual_review`.

List natural-language responsibility relations:

```bash
agent-canon semantic-index natural-relations --top-k 50 --format jsonl
```

`natural-relations` reuses the same repo-wide SQLite nodes and provider-scoped
vectors, then scores each candidate pair in both directions:

- `left_is_kind_of_right_score` estimates whether "left is a kind of right" is
  natural.
- `right_is_kind_of_left_score` estimates the reverse direction.
- high / high is reported as `equivalent`.
- low / low is reported as `unrelated`.
- one high direction is reported as `left_is_kind_of_right` or
  `right_is_kind_of_left`.

The command persists results to the `natural_language_relations` table through
the shared `analysis_runs` table. It uses the file-type-aware node units that
`build` already creates: documents, Markdown sections, and text/code/config
blocks. This is dependency and responsibility evidence, not authority to merge
or delete files. Code/document relations are useful as alignment evidence, but
strict dependency headers, structure hashes, and human review remain the
authority for refactor decisions.

List discourse relation edges for paragraph/block ordering:

```bash
agent-canon semantic-index discourse-relations \
  --profile experiment-report \
  --top-k 50 \
  --format jsonl
```

`discourse-relations` reuses the same SQLite nodes and provider-scoped vectors
as `search`, `context-pack`, and `natural-relations`. It scans nearby document
blocks inside each file, checks discourse-connective profiles, and persists
candidate paragraph edges to the `discourse_relations` table through
`analysis_runs`. Profiles are:

- `general`
- `experiment-report`
- `methods-protocol`
- `academic-argument`
- `refactor-design`

The output separates the relation primitive from the surface connective:
`relation_family`, `relation_schema`, `surface_phrase`, `surface_order`, and
`logical_direction` are distinct fields. This keeps paired variants such as
`A therefore B` and `B because A` as the same `reason_to_result` schema while
recording different surface order and logical direction. Results also include
`naturalness_score`, `inverse_naturalness_score`, `direction_confidence`,
`ambiguity`, and `gap_flags`.

Use this command before writing or rendering nontrivial reports, experiment
plans, papers, long documents, and refactor structure contracts when paragraph
order or logic gaps matter. It is structure evidence only: it does not replace
the structure contract, citation/evidence review, report review, dependency
checks, or human judgment. If an LLM-backed embedding provider has been added
with `embed-provider`, the same command can run against those latent vectors by
selecting that provider and model.

Run a fixture Eval:

```bash
agent-canon semantic-index eval \
  --fixture tests/fixtures/semantic-index/basic \
  --report reports/agents/<run-id>/semantic_index_eval.json
```

Evaluate generated review artifacts:

```bash
agent-canon semantic-index eval-output \
  --merge-candidates reports/agents/<run-id>/semantic_index_merge_candidates_agentcanon.jsonl \
  --thin-docs reports/agents/<run-id>/semantic_index_thin_docs_agentcanon.jsonl \
  --search reports/agents/<run-id>/semantic_index_search_agentcanon.jsonl \
  --report reports/agents/<run-id>/semantic_index_output_eval_agentcanon.json
```

Compare provider outputs without changing the downstream candidate logic:

```bash
agent-canon semantic-index compare-providers \
  --db reports/semantic-index.sqlite \
  --query-file reports/search_query.txt \
  --right-provider llama-server-embedding \
  --right-model ggml-org/embeddinggemma-300M-GGUF:Q8_0 \
  --report reports/semantic_index_provider_compare.json
```

The comparison reports search and merge-candidate overlap, left/right-only
candidate keys, provider/model/dim provenance, and query length. It does not
echo the full query text.

## Providers

The deterministic baseline provider is `deterministic-dense-v1`, model
`hash-token-char-v1`. It is deterministic and offline so tests and CI can
measure the tool without a local model.

The LLM-backed provider path is `llama-server-embedding`, also accepted as
`openai-compatible-embedding` for non-llama.cpp endpoints. It uses
`llama-server` or another OpenAI-compatible `/v1/embeddings` endpoint. The
provider writes only vector blobs and provenance keys. It does not write model
labels, summaries, or repository-wide ownership decisions.

The existing search, merge-candidate, thin-doc, and responsibility-bucket logic
is shared across providers. Provider changes affect candidate rankings and
scores, not the authority boundary.

## Eval Boundary

`semantic-index eval` measures candidate quality. It checks:

- indexed files and nodes
- missing embeddings
- query Recall@5 and MRR
- known similar pair scores
- must-not pair violations
- build runtime

`semantic-index eval-output` measures output artifact contract quality. It
checks that review JSONL has bounded summaries, matching result counts,
responsibility-scoped merge candidates, legal thin-doc actions, and search
summaries that do not echo long query text.

`semantic-index compare-providers` measures provider delta. It is diagnostic
evidence for tuning thresholds and deciding whether an LLM embedding provider
improves candidate ranking. It is not classification authority.

Eval failure means the candidate generator needs tuning. It does not prove that
a document should be merged or deleted.

## Candidate Generation Boundary

Full-repo input is the normal path. The tool avoids full pairwise comparison by
using vector prefix features to propose exact-rescored candidates. Operators
should not constrain `--include` just to make `merge-candidates` finish; if full
input is too slow, fix candidate generation or responsibility bucketing instead.
